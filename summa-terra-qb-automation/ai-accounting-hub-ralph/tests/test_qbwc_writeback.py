"""QBWC write-back adapter tests (Phase 6 — spec-qbwc-writeback-adapter-2026-07-01.md).

DB-free — all SQLAlchemy I/O is mocked (mirrors tests/test_daily_digest.py's and
tests/test_verify_execution.py's patterns: MagicMock session with
``execute(...).mappings().first()/.all()`` configured per query, real qbXML
request/response XML strings so the codec itself is exercised end-to-end).

No real QuickBooks/Web Connector session exists in this environment — every
qbXML "response" here is a hand-built string simulating what QuickBooks would
return. These tests prove the adapter's request-building, idempotency,
proof-boundary, session-gap, and EditSequence-retry LOGIC is correct against
those simulated responses. They do NOT and cannot prove real QuickBooks
connectivity — that is Section 10's 9-step sandbox E2E plan, blocked on a
human operator building the sandbox .QBW file (see IMPLEMENTATION_PLAN.md).
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.transport import qbwc_writeback as wb
from app.transport import qbxml
from app.transport.qbwc_writeback import (
    BillAddFields,
    ProofBoundaryRefused,
    select_pending_bills,
    sync_bill_to_qb,
    verify_proof_boundary,
)

FIELDS = BillAddFields(
    vendor_list_id="80000001-1",
    account_name="6100 Cost Code",
    class_name="Project A:Phase 1",
    customer_job="Project A LLC:Job 1",
    draw_number=3,
)


# --------------------------------------------------------------------------- #
# Fake DB session helpers
# --------------------------------------------------------------------------- #
def _proof_session(
    *,
    bill_found: bool = True,
    status: str = "approved",
    bundle_id: str | None = "pb-1",
    proof_row_found: bool = True,
    passed: bool = True,
) -> MagicMock:
    """A MagicMock session whose execute() branches on the query text, mirroring
    the raw-SQL/text() pattern already used in intents_router.py."""
    session = MagicMock()

    def _execute(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM bills" in sql and "WHERE id" in sql:
            row = (
                {"id": params["bid"], "status": status, "invoiceproof_bundle_id": bundle_id}
                if bill_found
                else None
            )
            result.mappings.return_value.first.return_value = row
        elif "FROM proof_bundles" in sql:
            row = {"passed": passed} if proof_row_found else None
            result.mappings.return_value.first.return_value = row
        else:
            raise AssertionError(f"unexpected query in proof-boundary check: {sql}")
        return result

    session.execute.side_effect = _execute
    return session


def _bill(**overrides) -> dict:
    base = {
        "id": "b1",
        "amount": Decimal("12500.00"),
        "po_ref": "PO-2291",
        "status": "approved",
        "qb_sync_attempts": 0,
        "invoiceproof_bundle_id": "pb-1",
        "qb_txn_id": None,
        "qb_edit_sequence": None,
        "qb_synced_at": None,
    }
    base.update(overrides)
    return base


def _add_response(status_code: str = "0", *, txn_id: str = "80000002-1", edit_seq: str = "3") -> str:
    if status_code != "0":
        return (
            '<?xml version="1.0"?><QBXML><QBXMLMsgsRs>'
            f'<BillAddRs statusCode="{status_code}" statusSeverity="Error" '
            'statusMessage="qb error" /></QBXMLMsgsRs></QBXML>'
        )
    return (
        '<?xml version="1.0"?><QBXML><QBXMLMsgsRs>'
        '<BillAddRs statusCode="0" statusSeverity="Info" statusMessage="Status OK">'
        f"<BillRet><TxnID>{txn_id}</TxnID><EditSequence>{edit_seq}</EditSequence>"
        "<RefNumber>PO-2291</RefNumber><AmountDue>12500.00</AmountDue></BillRet>"
        "</BillAddRs></QBXMLMsgsRs></QBXML>"
    )


# --------------------------------------------------------------------------- #
# BillAdd qbXML request-building (spec §6)
# --------------------------------------------------------------------------- #
def test_build_bill_add_writeback_includes_all_dimensions():
    req = qbxml.build_bill_add_writeback(
        {"amount": Decimal("12500.00"), "po_ref": "PO-2291"},
        vendor_list_id="80000001-1",
        account_name="6100 Cost Code",
        class_name="Project A:Phase 1",
        customer_job="Project A LLC:Job 1",
        draw_number=3,
        request_id="b1",
    )
    assert '<BillAddRq requestID="b1">' in req
    assert "<VendorRef><ListID>80000001-1</ListID></VendorRef>" in req
    assert "<RefNumber>PO-2291</RefNumber>" in req
    assert "<AccountRef><FullName>6100 Cost Code</FullName></AccountRef>" in req
    assert "<Amount>12500.00</Amount>" in req
    assert "<ClassRef><FullName>Project A:Phase 1</FullName></ClassRef>" in req
    assert "<CustomerRef><FullName>Project A LLC:Job 1</FullName></CustomerRef>" in req
    assert "<DataExtName>Draw #</DataExtName>" in req
    assert "<DataExtValue>3</DataExtValue>" in req


def test_build_bill_add_writeback_omits_optional_dimensions_when_absent():
    req = qbxml.build_bill_add_writeback(
        {"amount": Decimal("100.00")},
        vendor_list_id="80000001-1",
        account_name="6100",
        request_id="b2",
    )
    assert "ClassRef" not in req
    assert "CustomerRef" not in req
    assert "DataExtName" not in req
    assert "RefNumber" not in req  # no po_ref supplied


# --------------------------------------------------------------------------- #
# Idempotency filter (spec §7 table): never selects a bill with qb_txn_id set
# --------------------------------------------------------------------------- #
def test_select_pending_bills_query_filters_on_status_and_null_txn_id():
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {"id": "b1", "qb_txn_id": None, "status": "approved"},
    ]
    rows = select_pending_bills(session)

    assert rows == [{"id": "b1", "qb_txn_id": None, "status": "approved"}]
    sql = str(session.execute.call_args[0][0])
    assert "status = 'approved'" in sql
    assert "qb_txn_id IS NULL" in sql


def test_select_pending_bills_respects_limit():
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    select_pending_bills(session, limit=5)
    sql = str(session.execute.call_args[0][0])
    params = session.execute.call_args[0][1]
    assert "LIMIT :limit" in sql
    assert params == {"limit": 5}


# --------------------------------------------------------------------------- #
# Proof boundary — MUST-NOT-BREAK: refuses a write missing a passed proof
# bundle or status != 'approved', even when called directly (spec §9).
# --------------------------------------------------------------------------- #
def test_proof_boundary_refuses_missing_invoiceproof_bundle_id():
    session = _proof_session(bundle_id=None)
    with pytest.raises(ProofBoundaryRefused, match="no invoiceproof_bundle_id"):
        verify_proof_boundary(session, "b1")


def test_proof_boundary_refuses_when_proof_bundle_not_passed():
    session = _proof_session(passed=False)
    with pytest.raises(ProofBoundaryRefused, match="passed is not True"):
        verify_proof_boundary(session, "b1")


def test_proof_boundary_refuses_when_status_not_approved():
    session = _proof_session(status="drafted")
    with pytest.raises(ProofBoundaryRefused, match="not 'approved'"):
        verify_proof_boundary(session, "b1")


def test_proof_boundary_refuses_when_bill_not_found():
    session = _proof_session(bill_found=False)
    with pytest.raises(ProofBoundaryRefused, match="not found"):
        verify_proof_boundary(session, "ghost")


def test_proof_boundary_passes_when_all_three_conditions_hold():
    session = _proof_session()
    verify_proof_boundary(session, "b1")  # must not raise


def test_sync_bill_to_qb_refuses_write_when_proof_boundary_fails_even_if_directly_invoked():
    """The MUST-NOT-BREAK guarantee: even calling sync_bill_to_qb directly on a
    bill lacking a passed proof bundle refuses to write — the writer callable
    must NEVER be invoked."""
    session = _proof_session(passed=False)
    bill = _bill()

    def writer(_req: str) -> str:  # pragma: no cover - must never be called
        raise AssertionError("writer must never be called when the proof boundary fails")

    with pytest.raises(ProofBoundaryRefused):
        sync_bill_to_qb(session, bill, writer=writer, fields=FIELDS)


def test_sync_bill_to_qb_refuses_write_when_status_is_not_approved_even_if_directly_invoked():
    session = _proof_session(status="verified")
    bill = _bill(status="verified")

    def writer(_req: str) -> str:  # pragma: no cover - must never be called
        raise AssertionError("writer must never be called when status != approved")

    with pytest.raises(ProofBoundaryRefused):
        sync_bill_to_qb(session, bill, writer=writer, fields=FIELDS)


# --------------------------------------------------------------------------- #
# Happy path: proof boundary passes -> BillAdd written -> response reconciled
# --------------------------------------------------------------------------- #
def test_sync_bill_to_qb_happy_path_reconciles_and_audits():
    session = _proof_session()
    bill = _bill()
    sent: list[str] = []

    def writer(req: str) -> str:
        sent.append(req)
        return _add_response()

    with patch.object(wb, "append_audit_row") as m_audit:
        out = sync_bill_to_qb(session, bill, writer=writer, fields=FIELDS)

    assert out["error"] is None
    assert out["data"]["qb_txn_id"] == "80000002-1"
    assert bill["qb_txn_id"] == "80000002-1"
    assert bill["qb_edit_sequence"] == "3"
    assert bill["status"] == "qb_synced"
    assert bill["qb_synced_at"] is not None
    assert bill["qb_sync_attempts"] == 1
    assert len(sent) == 1 and "BillAddRq" in sent[0]
    m_audit.assert_called_once()
    assert m_audit.call_args.kwargs["action_type"] == "qb_write_confirmed"
    assert m_audit.call_args.kwargs["session_id"] == "b1"


# --------------------------------------------------------------------------- #
# Session-gap re-check (spec §7): never blindly resubmit
# --------------------------------------------------------------------------- #
def test_sync_bill_to_qb_session_gap_recheck_finds_existing_and_does_not_resubmit():
    session = _proof_session()
    bill = _bill()

    def writer(_req: str) -> str:  # pragma: no cover - must never be called
        raise AssertionError("must never resubmit once an existing QB record is found")

    def check_existing(_bill) -> dict:
        return {"qb_txn_id": "PRIOR-SESSION-TXN", "qb_edit_sequence": "1"}

    with patch.object(wb, "append_audit_row") as m_audit:
        out = sync_bill_to_qb(
            session, bill, writer=writer, fields=FIELDS, check_existing=check_existing
        )

    assert out["error"] is None
    assert out["meta"]["session_gap_recovered"] is True
    assert bill["qb_txn_id"] == "PRIOR-SESSION-TXN"
    assert bill["status"] == "qb_synced"
    m_audit.assert_called_once()
    assert m_audit.call_args.kwargs["action_type"] == "qb_write_confirmed"


def test_sync_bill_to_qb_session_gap_recheck_finds_nothing_proceeds_to_write():
    session = _proof_session()
    bill = _bill()
    sent: list[str] = []

    def writer(req: str) -> str:
        sent.append(req)
        return _add_response()

    with patch.object(wb, "append_audit_row"):
        out = sync_bill_to_qb(
            session, bill, writer=writer, fields=FIELDS, check_existing=lambda _b: None
        )

    assert out["error"] is None
    assert len(sent) == 1  # fell through to a real BillAdd write


# --------------------------------------------------------------------------- #
# EditSequence conflict handling (spec §7): re-read -> retry once -> exception
# --------------------------------------------------------------------------- #
def test_sync_bill_to_qb_edit_sequence_conflict_retries_once_and_succeeds():
    session = _proof_session()
    bill = _bill()
    calls = {"n": 0}

    def writer(_req: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return _add_response("3200")
        return _add_response(txn_id="TXN-AFTER-RETRY", edit_seq="9")

    reread = {"n": 0}

    def re_read_bill() -> dict:
        reread["n"] += 1
        return {"qb_edit_sequence": "8"}

    with patch.object(wb, "append_audit_row") as m_audit:
        out = sync_bill_to_qb(
            session, bill, writer=writer, fields=FIELDS, re_read_bill=re_read_bill
        )

    assert out["error"] is None
    assert calls["n"] == 2  # exactly one retry
    assert reread["n"] == 1
    assert out["meta"]["rebased"] is True
    assert bill["qb_txn_id"] == "TXN-AFTER-RETRY"
    assert bill["status"] == "qb_synced"
    assert bill["qb_sync_attempts"] == 1  # one poll-cycle attempt, not one per qbXML call
    assert m_audit.call_args.kwargs["action_type"] == "qb_write_confirmed"


def test_sync_bill_to_qb_edit_sequence_conflict_persists_marks_exception_no_infinite_loop():
    session = _proof_session()
    bill = _bill()
    calls = {"n": 0}

    def writer(_req: str) -> str:
        calls["n"] += 1
        return _add_response("3200")  # conflict on every attempt

    with patch.object(wb, "append_audit_row") as m_audit:
        out = sync_bill_to_qb(
            session,
            bill,
            writer=writer,
            fields=FIELDS,
            re_read_bill=lambda: {"qb_edit_sequence": "8"},
        )

    assert calls["n"] == 2  # initial attempt + exactly one retry, then stop
    assert out["error"]["code"] == "QB_EDIT_CONFLICT"
    assert out["meta"]["after_retry"] is True
    assert bill["status"] == "exception"
    assert bill["qb_txn_id"] is None  # never reconciled
    assert m_audit.call_args.kwargs["action_type"] == "qb_write_exception"


def test_sync_bill_to_qb_edit_sequence_conflict_without_re_read_bill_fails_closed_no_retry():
    """If the caller supplied no re_read_bill, a conflict must fail closed
    immediately rather than silently retrying with stale data."""
    session = _proof_session()
    bill = _bill()
    calls = {"n": 0}

    def writer(_req: str) -> str:
        calls["n"] += 1
        return _add_response("3200")

    with patch.object(wb, "append_audit_row"):
        out = sync_bill_to_qb(session, bill, writer=writer, fields=FIELDS)

    assert calls["n"] == 1
    assert out["error"]["code"] == "QB_EDIT_CONFLICT"
    assert bill["status"] == "exception"


def test_sync_bill_to_qb_missing_list_reference_fails_closed_never_auto_creates():
    """List drift (spec §7): fail closed, do NOT auto-create the missing entry."""
    session = _proof_session()
    bill = _bill()

    def writer(_req: str) -> str:
        return _add_response(qbxml.ACCOUNT_NOT_FOUND)

    with patch.object(wb, "append_audit_row") as m_audit:
        out = sync_bill_to_qb(session, bill, writer=writer, fields=FIELDS)

    assert out["error"]["code"] == "QB_LIST_REFERENCE_MISSING"
    assert bill["status"] == "exception"
    assert m_audit.call_args.kwargs["action_type"] == "qb_write_exception"
