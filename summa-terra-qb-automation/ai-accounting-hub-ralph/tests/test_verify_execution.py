"""Gated write-back orchestration tests (CHUNK_6_VERIFY) — DB-free, fakes only.

Covers: happy path (approved → VerifyAPI VERIFIED → BillAdd → qb_txn_id reconciled),
edge case (stale EditSequence → re-read + re-base + single retry succeeds), failure
case (VerifyAPI non-VERIFIED → write blocked + routed to human; CoA drift caught
pre-write → 422), and fail-closed when the AIVS chain is broken.
"""
from __future__ import annotations

from decimal import Decimal

from app.audit import AuditChainBroken
from app.models import Bill, ProofBundle
from app.verify.execution import execute_approved_write

COMPANY = "11111111-1111-1111-1111-111111111111"
GOOD_HEAD = "a" * 64


class _FakeSession:
    """Records ProofBundle adds; satisfies write_proof_bundle's add/flush."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = f"pb-{len(self.added)}"

    @property
    def proof_bundles(self) -> list:
        return [o for o in self.added if isinstance(o, ProofBundle)]


def _bill(status: str = "approved") -> Bill:
    b = Bill(
        company_id=COMPANY,
        vendor_id="v1",
        amount=Decimal("12500.00"),
        po_ref="PO-2291",
        status=status,
        raw_extensions={},
    )
    b.id = "b1"
    return b


def _add_response(status_code: str = "0", *, txn_id: str = "NEW-TXN-1", edit_seq: str = "5") -> str:
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


def _empty_chain(_session, _sid):
    return []


def test_happy_path_writes_and_reconciles():
    session = _FakeSession()
    sent: list[str] = []

    def writer(req: str) -> str:
        sent.append(req)
        return _add_response()

    bill = _bill()
    out = execute_approved_write(
        session,
        bill,
        vendor_list_id="80000001-1",
        account_name="6100",
        writer=writer,
        aivs_head=GOOD_HEAD,
        known_accounts=["6100", "6200"],
        load_chain=_empty_chain,
    )

    assert out["error"] is None
    assert out["data"]["qb_txn_id"] == "NEW-TXN-1"
    assert out["data"]["qb_edit_sequence"] == "5"
    # Reconciled into the canonical bill.
    assert bill.qb_txn_id == "NEW-TXN-1"
    assert bill.qb_edit_sequence == "5"
    assert bill.status == "synced"
    # Exactly one BillAdd emitted, and it is an Add (write) request.
    assert len(sent) == 1 and "BillAddRq" in sent[0]
    # A verifyapi proof bundle was written and passed.
    [pb] = session.proof_bundles
    assert pb.kind == "verifyapi" and pb.passed is True
    assert out["meta"]["independent_attestor_signature"]


def test_stale_edit_sequence_rereads_rebases_and_retries_once():
    session = _FakeSession()
    calls = {"n": 0}

    def writer(req: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return _add_response("3200")  # EditSequence conflict on first try
        return _add_response(txn_id="TXN-AFTER-RETRY", edit_seq="7")

    reread = {"n": 0}

    def re_read_bill() -> dict:
        reread["n"] += 1
        return {"qb_txn_id": "TXN-AFTER-RETRY", "qb_edit_sequence": "6"}

    bill = _bill()
    out = execute_approved_write(
        session,
        bill,
        vendor_list_id="80000001-1",
        account_name="6100",
        writer=writer,
        aivs_head=GOOD_HEAD,
        load_chain=_empty_chain,
        re_read_bill=re_read_bill,
    )

    assert out["error"] is None
    assert calls["n"] == 2  # exactly one retry
    assert reread["n"] == 1  # re-read happened once
    assert out["meta"]["rebased"] is True
    assert bill.qb_txn_id == "TXN-AFTER-RETRY"
    assert bill.status == "synced"


def test_persistent_edit_conflict_routes_to_human():
    session = _FakeSession()

    def writer(_req: str) -> str:
        return _add_response("3200")  # conflict on every attempt

    routed: list = []
    bill = _bill()
    out = execute_approved_write(
        session,
        bill,
        vendor_list_id="80000001-1",
        account_name="6100",
        writer=writer,
        aivs_head=GOOD_HEAD,
        load_chain=_empty_chain,
        re_read_bill=lambda: {"qb_txn_id": None, "qb_edit_sequence": "9"},
        route_to_human=routed.append,
    )

    assert out["error"]["code"] == "QB_EDIT_CONFLICT"
    assert out["error"]["http_status"] == 409
    assert routed and routed[0]["code"] == "QB_EDIT_CONFLICT"
    assert bill.status == "approved"  # never reconciled


def test_verifyapi_not_ready_blocks_write_and_routes_to_human():
    session = _FakeSession()
    sent: list = []
    routed: list = []

    def writer(req: str) -> str:  # pragma: no cover - must never be called
        sent.append(req)
        return _add_response()

    bill = _bill(status="drafted")  # not approved → VerifyAPI NOT_READY
    out = execute_approved_write(
        session,
        bill,
        vendor_list_id="80000001-1",
        account_name="6100",
        writer=writer,
        aivs_head=GOOD_HEAD,
        load_chain=_empty_chain,
        route_to_human=routed.append,
    )

    assert out["error"]["code"] == "VERIFY_NOT_READY"
    assert out["error"]["http_status"] == 409
    assert sent == []  # write never attempted
    assert routed and routed[0]["code"] == "VERIFY_NOT_READY"
    # Fail-closed still records the (non-passing) verifyapi proof bundle.
    [pb] = session.proof_bundles
    assert pb.kind == "verifyapi" and pb.passed is False


def test_coa_drift_caught_pre_write_returns_422():
    session = _FakeSession()
    sent: list = []
    routed: list = []

    def writer(req: str) -> str:  # pragma: no cover - must never be called
        sent.append(req)
        return _add_response()

    bill = _bill()
    out = execute_approved_write(
        session,
        bill,
        vendor_list_id="80000001-1",
        account_name="9999-missing",
        writer=writer,
        aivs_head=GOOD_HEAD,
        known_accounts=["6100", "6200"],  # 9999-missing absent → drift
        load_chain=_empty_chain,
        route_to_human=routed.append,
    )

    assert out["error"]["code"] == "COA_DRIFT"
    assert out["error"]["http_status"] == 422
    assert sent == []  # caught BEFORE any qbXML is emitted
    assert routed and routed[0]["code"] == "COA_DRIFT"


def test_broken_aivs_chain_fails_closed():
    session = _FakeSession()
    sent: list = []
    routed: list = []

    def writer(req: str) -> str:  # pragma: no cover - must never be called
        sent.append(req)
        return _add_response()

    def broken_validator(_records):
        raise AuditChainBroken("prev_hash mismatch", index=1, row_id=2)

    bill = _bill()
    out = execute_approved_write(
        session,
        bill,
        vendor_list_id="80000001-1",
        account_name="6100",
        writer=writer,
        aivs_head=GOOD_HEAD,
        load_chain=_empty_chain,
        chain_validator=broken_validator,
        route_to_human=routed.append,
    )

    assert out["error"]["code"] == "AUDIT_CHAIN_BROKEN"
    assert sent == []  # write blocked
    assert routed and routed[0]["code"] == "AUDIT_CHAIN_BROKEN"
    assert bill.status == "approved"
