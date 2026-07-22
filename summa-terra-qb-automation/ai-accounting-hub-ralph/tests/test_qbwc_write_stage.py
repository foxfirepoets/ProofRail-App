"""Live-session WRITE-STAGE tests (Phase 6, task 9): the QBWC session manager,
constructed with a WritebackConfig, drains approved+proof-passed bills and emits
BillAdd across the split sendRequestXML/receiveResponseXML poll cycle.

DB-free: the DB session is a MagicMock branching on query text (proof-boundary +
select-pending), and QuickBooks' qbXML replies are hand-built strings so the real
qbxml codec runs end-to-end. No real QuickBooks/Web Connector session exists here
(that is Section 10's sandbox E2E plan); these prove the wiring LOGIC:
  * the write stage runs ONLY after the two read stages,
  * the proof boundary is re-checked before any write (fail closed -> no write),
  * an unresolved entity marks the bill exception and skips the write,
  * a 3200 EditSequence conflict re-bases and retries once across poll cycles,
  * a 3140 account-not-found marks the bill exception without crashing the session,
  * a draw/fee bill routes through the same BillAdd path.
The read-only handshake path is asserted to still work untouched (no writeback).
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.transport import qbwc_writeback as wb
from app.transport.metrics import PollMetrics
from app.transport.qbwc import QBWCSessionManager, WritebackConfig
from app.transport.qbwc_writeback import BillAddFields
from tests.test_transport_qbxml import BILL_RESPONSE, VENDOR_RESPONSE

USER, PWD = "qbwc", "s3cret"

FIELDS = BillAddFields(
    vendor_list_id="80000001-1",
    account_name="15200 CIP Hard Costs",
    class_name="Phase 1",
    customer_job="Proj A:Job 1",
    draw_number=3,
)


def _add_response(status_code="0", *, txn_id="80000002-1", edit_seq="3") -> str:
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
        "<RefNumber>PO-1</RefNumber><AmountDue>100.00</AmountDue></BillRet>"
        "</BillAddRs></QBXMLMsgsRs></QBXML>"
    )


def _pending_bill(**overrides) -> dict:
    base = {
        "id": "b1",
        "company_id": "c1",
        "vendor_id": "v1",
        "amount": Decimal("100.00"),
        "po_ref": "PO-1",
        "status": "approved",
        "qb_sync_attempts": 0,
        "invoiceproof_bundle_id": "pb-1",
        "qb_txn_id": None,
        "qb_edit_sequence": None,
        "qb_synced_at": None,
        "draw_package_id": None,
        "raw_extensions": {},
    }
    base.update(overrides)
    return base


def _db_session(
    pending_bills, *, proof_status="approved", proof_bundle_id="pb-1", passed=True
) -> MagicMock:
    """MagicMock DB session: select_pending_bills + proof-boundary re-check."""
    session = MagicMock()

    def _execute(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM bills" in sql and "WHERE status = 'approved'" in sql:
            result.mappings.return_value.all.return_value = pending_bills
        elif "FROM bills" in sql and "WHERE id" in sql:
            result.mappings.return_value.first.return_value = {
                "id": params["bid"],
                "status": proof_status,
                "invoiceproof_bundle_id": proof_bundle_id,
            }
        elif "FROM proof_bundles" in sql:
            result.mappings.return_value.first.return_value = {"passed": passed}
        elif "UPDATE bills" in sql:
            result.rowcount = 1
        else:
            raise AssertionError(f"unexpected query: {sql}")
        return result

    session.execute.side_effect = _execute
    return session


def _manager(db_session, resolver=None, on_unresolved=None) -> QBWCSessionManager:
    cfg = WritebackConfig(
        db_factory=lambda: db_session,
        resolver=resolver or (lambda _bill: FIELDS),
        on_unresolved=on_unresolved,
    )
    return QBWCSessionManager(
        metrics=PollMetrics(), username=USER, password=PWD, writeback=cfg
    )


def _run_read_phase(mgr, ticket):
    """Drive the two read stages so the session reaches the write phase."""
    assert "VendorQueryRq" in mgr.send_request_xml(ticket)
    mgr.receive_response_xml(ticket, VENDOR_RESPONSE)
    assert "BillQueryRq" in mgr.send_request_xml(ticket)
    mgr.receive_response_xml(ticket, BILL_RESPONSE)


# --------------------------------------------------------------------------- #
# Read-only path untouched when no writeback config is present.
# --------------------------------------------------------------------------- #
def test_no_writeback_config_is_pure_read_only_session():
    mgr = QBWCSessionManager(metrics=PollMetrics(), username=USER, password=PWD)
    ticket, _ = mgr.authenticate(USER, PWD)
    assert "VendorQueryRq" in mgr.send_request_xml(ticket)
    mgr.receive_response_xml(ticket, VENDOR_RESPONSE)
    assert "BillQueryRq" in mgr.send_request_xml(ticket)
    assert mgr.receive_response_xml(ticket, BILL_RESPONSE) == 100
    # No write stage: next send is empty (session done).
    assert mgr.send_request_xml(ticket) == ""
    assert mgr.sessions[ticket].is_complete


# --------------------------------------------------------------------------- #
# Happy path: write stage runs after reads, emits BillAdd, reconciles.
# --------------------------------------------------------------------------- #
def test_write_stage_happy_path_emits_billadd_and_reconciles():
    bill = _pending_bill()
    db = _db_session([bill])
    mgr = _manager(db)
    ticket, _ = mgr.authenticate(USER, PWD)
    _run_read_phase(mgr, ticket)

    with patch.object(wb, "append_audit_row"):
        req = mgr.send_request_xml(ticket)  # enters write phase
        assert "BillAddRq" in req
        pct = mgr.receive_response_xml(ticket, _add_response())
        assert 0 <= pct < 100
        # Next send: driver finished this bill, no more bills -> "" (done).
        assert mgr.send_request_xml(ticket) == ""

    # select_pending_bills copies rows (dict(row)); the worker mutates + flushes
    # the copy to the DB, so assert on the authoritative write_results, not the
    # original test dict.
    results = mgr.sessions[ticket].write_results
    assert len(results) == 1 and results[0]["error"] is None
    assert results[0]["data"]["status"] == "qb_synced"
    assert results[0]["data"]["qb_txn_id"] == "80000002-1"


# --------------------------------------------------------------------------- #
# Proof-boundary failure -> NO write (writer never emits a BillAdd).
# --------------------------------------------------------------------------- #
def test_write_stage_proof_boundary_fail_produces_no_billadd():
    bill = _pending_bill()
    db = _db_session([bill], passed=False)  # proof bundle not passed
    mgr = _manager(db)
    ticket, _ = mgr.authenticate(USER, PWD)
    _run_read_phase(mgr, ticket)

    with patch.object(wb, "append_audit_row"):
        req = mgr.send_request_xml(ticket)
        # The driver's worker raised ProofBoundaryRefused BEFORE any writer call,
        # so no BillAdd is emitted; the session moves on without a write.
        assert req == "" or "BillAddRq" not in req

    results = mgr.sessions[ticket].write_results
    assert len(results) == 1
    assert results[0]["error"]["code"] == "PROOF_BOUNDARY_REFUSED"


# --------------------------------------------------------------------------- #
# Unresolved entity -> exception, no write.
# --------------------------------------------------------------------------- #
def test_write_stage_unresolved_entity_marks_exception_no_write():
    bill = _pending_bill()
    db = _db_session([bill])

    def bad_resolver(_bill):
        raise wb_resolution_error()

    marked = {}

    def on_unresolved(b, exc):
        b["status"] = "exception"
        marked["reason"] = str(exc)
        marked["bill_id"] = b["id"]

    mgr = _manager(db, resolver=bad_resolver, on_unresolved=on_unresolved)
    ticket, _ = mgr.authenticate(USER, PWD)
    _run_read_phase(mgr, ticket)

    with patch.object(wb, "append_audit_row"):
        req = mgr.send_request_xml(ticket)
        assert req == ""  # unresolved -> no BillAdd emitted at all

    assert marked["reason"]  # on_unresolved fired
    assert marked["bill_id"] == "b1"
    results = mgr.sessions[ticket].write_results
    assert results and results[0]["meta"].get("unresolved") is True


def wb_resolution_error():
    from app.transport.qbwc_resolution import EntityResolutionError

    return EntityResolutionError("vendor has no qb_list_id", code="VENDOR_NOT_IN_QB")


# --------------------------------------------------------------------------- #
# 3200 EditSequence conflict -> re-base + retry once across poll cycles.
# --------------------------------------------------------------------------- #
def test_write_stage_edit_sequence_conflict_retries_then_succeeds():
    bill = _pending_bill()
    db = _db_session([bill])

    def resolver(_bill):
        return FIELDS

    mgr = _manager(db, resolver=resolver)
    # Inject a re_read_bill so the retry can re-base (mirrors the qbwc_writeback
    # test): patch BillWriteDriver to pass re_read_bill through.
    orig_driver = wb.BillWriteDriver

    def driver_factory(session, b, **kw):
        kw["re_read_bill"] = lambda: {"qb_edit_sequence": "9"}
        return orig_driver(session, b, **kw)

    ticket, _ = mgr.authenticate(USER, PWD)
    _run_read_phase(mgr, ticket)

    with patch.object(wb, "append_audit_row"), patch.object(
        wb, "BillWriteDriver", side_effect=driver_factory
    ):
        req1 = mgr.send_request_xml(ticket)  # first BillAdd
        assert "BillAddRq" in req1
        mgr.receive_response_xml(ticket, _add_response("3200"))  # conflict
        req2 = mgr.send_request_xml(ticket)  # retry BillAdd (re-based)
        assert "BillAddRq" in req2
        mgr.receive_response_xml(ticket, _add_response(txn_id="TXN-RETRY", edit_seq="9"))
        assert mgr.send_request_xml(ticket) == ""  # drain done

    results = mgr.sessions[ticket].write_results
    assert results[0]["error"] is None
    assert results[0]["data"]["status"] == "qb_synced"
    assert results[0]["data"]["qb_txn_id"] == "TXN-RETRY"
    assert results[0]["meta"].get("rebased") is True


# --------------------------------------------------------------------------- #
# 3140 account-not-found -> exception, session does NOT crash.
# --------------------------------------------------------------------------- #
def test_write_stage_account_not_found_marks_exception_session_survives():
    bill = _pending_bill()
    db = _db_session([bill])
    mgr = _manager(db)
    ticket, _ = mgr.authenticate(USER, PWD)
    _run_read_phase(mgr, ticket)

    with patch.object(wb, "append_audit_row"):
        req = mgr.send_request_xml(ticket)
        assert "BillAddRq" in req
        pct = mgr.receive_response_xml(ticket, _add_response("3140"))
        assert pct >= 0  # not a session-fatal negative
        assert mgr.send_request_xml(ticket) == ""  # session drains cleanly

    results = mgr.sessions[ticket].write_results
    assert results[0]["error"]["code"] == "QB_LIST_REFERENCE_MISSING"
    # Session did not error out (3140 is a per-bill exception, not session-fatal).
    assert not mgr.sessions[ticket].has_error


# --------------------------------------------------------------------------- #
# Draw/fee bill routes through the SAME BillAdd write path (task 11).
# --------------------------------------------------------------------------- #
def test_write_stage_draw_fee_bill_writes_via_same_path():
    fee_bill = _pending_bill(
        id="fee1",
        draw_package_id="d1",
        raw_extensions={"fee_role": "ceo_2_parent", "draw_package_id": "d1"},
    )
    db = _db_session([fee_bill])

    fee_fields = BillAddFields(
        vendor_list_id="80000009-1",
        account_name="60200 CEO Commission Expense",
        class_name=None,
        customer_job="Proj A:Job 1",
        draw_number="7",
    )
    mgr = _manager(db, resolver=lambda _b: fee_fields)
    ticket, _ = mgr.authenticate(USER, PWD)
    _run_read_phase(mgr, ticket)

    with patch.object(wb, "append_audit_row"):
        req = mgr.send_request_xml(ticket)
        assert "BillAddRq" in req
        assert "<AccountRef><FullName>60200 CEO Commission Expense</FullName></AccountRef>" in req
        assert "<DataExtName>Draw #</DataExtName>" in req
        mgr.receive_response_xml(ticket, _add_response(txn_id="FEE-TXN"))
        assert mgr.send_request_xml(ticket) == ""

    results = mgr.sessions[ticket].write_results
    assert results[0]["error"] is None
    assert results[0]["data"]["status"] == "qb_synced"
    assert results[0]["data"]["qb_txn_id"] == "FEE-TXN"
