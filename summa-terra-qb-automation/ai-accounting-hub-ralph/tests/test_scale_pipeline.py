"""End-to-end payable pipeline test (CHUNK_8_SCALE) — the HEADLINE test.

Proves the full firm pipeline runs GREEN end to end with in-memory fakes for the DB
only, exercising the REAL proof logic at every gate:

    OCR → InvoiceProof (Gate 1) → human approval → AuditProof (Gate 2)
        → VerifyAPI (Gate 3) → qbXML write-back

Shared builders here are reused by ``test_scale_failclosed.py``.
"""
from __future__ import annotations

from typing import Any

from app.audit import chain_head
from app.audit.chain import make_record
from app.payments.service import PaymentsService, VendorContext
from app.scale.pipeline import COMPLETE, run_payable_pipeline
from app.workflow.capability import mint_capability
from app.workflow.engine import InMemoryEventBus, InMemoryWorkflowEngine
from app.workflow.service import WorkflowService

SECRET = "unit-test-secret"
VCAP_SECRET = "unit-test-vcap-secret-which-is-long-enough"
SESSION_ID = "11111111-1111-1111-1111-111111111111"


class FakeSession:
    """Satisfies execute_approved_write's write_proof_bundle (add/flush only)."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = f"pb-{len(self.added)}"


class FakeBill:
    def __init__(self, bill_id: str = "bill-1") -> None:
        self.id = bill_id


def intact_chain() -> list:
    """A real, intact 2-row AIVS chain so the REAL validate_chain gate passes."""
    r1 = make_record(row_id=1, session_id=SESSION_ID, action_type="a", actor="x", prev_hash="0" * 64)
    r2 = make_record(row_id=2, session_id=SESSION_ID, action_type="b", actor="x", prev_hash=r1.row_hash)
    return [r1, r2]


def add_response(txn_id: str = "NEW-TXN-1", edit_seq: str = "5") -> str:
    return (
        '<?xml version="1.0"?><QBXML><QBXMLMsgsRs>'
        '<BillAddRs statusCode="0" statusSeverity="Info" statusMessage="Status OK">'
        f"<BillRet><TxnID>{txn_id}</TxnID><EditSequence>{edit_seq}</EditSequence>"
        "<RefNumber>PO-2291</RefNumber><AmountDue>4321.99</AmountDue></BillRet>"
        "</BillAddRs></QBXMLMsgsRs></QBXML>"
    )


def build_payments() -> PaymentsService:
    """Real InvoiceProof + VCAP; DB collaborators are fakes."""
    return PaymentsService(
        load_context=lambda s, c, v: VendorContext(swarmscore=900),
        write_bundle=lambda s, b: "bundle-1",
        commit_bill=lambda s, d, bid: FakeBill("bill-paid"),
        append_audit=lambda s, **kw: object(),
        release_fn=lambda s, bid: True,
        vcap_secret=VCAP_SECRET,
    )


def build_workflow(chain: list) -> WorkflowService:
    """Real capability gate + REAL validate_chain; audit/commit are fakes."""
    return WorkflowService(
        event_bus=InMemoryEventBus(),
        engine=InMemoryWorkflowEngine(),
        append_audit=lambda s, **kw: object(),
        load_chain=lambda s, sid: chain,
        commit_canonical=lambda s, intent: FakeBill("bill-approved"),
        capability_secret=SECRET,
    )


def good_invoice() -> dict[str, Any]:
    """A clean invoice that fires NO critical InvoiceProof rule."""
    return {
        "invoice": {
            "company_id": SESSION_ID,
            "vendor_id": "vendor-1",
            "invoice_number": "INV-2291",
            "po_ref": "PO-2291",
            "amount": 4321.99,
            "line_items": [{"amount": 4321.99}],
        }
    }


def run_green_pipeline(writer, **overrides):
    """Drive the full pipeline with all gates passing (caller can override knobs)."""
    chain = overrides.pop("chain", None) or intact_chain()
    kwargs: dict[str, Any] = dict(
        payments=build_payments(),
        workflow=build_workflow(chain),
        capability_token=mint_capability(
            agent_id="agent-1", allowed_actions=("create_bill",), secret=SECRET
        ),
        writer=writer,
        vendor_list_id="80000001-1",
        account_name="6100",
        aivs_head=chain_head(chain),
        known_accounts=["6100", "6200"],
        load_chain=lambda s, sid: chain,
    )
    kwargs.update(overrides)
    return run_payable_pipeline(FakeSession(), good_invoice(), **kwargs)


def test_full_pipeline_runs_green_end_to_end():
    sent: list[str] = []

    def writer(req: str) -> str:
        sent.append(req)
        return add_response()

    result = run_green_pipeline(writer)

    # Headline assertion: the whole firm pipeline is GREEN.
    assert result.green is True
    assert result.stage == COMPLETE

    # Gate 1 — InvoiceProof passed (no critical findings).
    assert result.invoiceproof["passed"] is True
    assert result.invoiceproof["invoiceproof"]["riskLevel"] != "CRITICAL"

    # Human approval committed the canonical bill (AuditProof / Gate 2 ran inside).
    assert result.approval["committed"] is True

    # Gate 3 — VerifyAPI advanced and sealed an independent attestor signature.
    assert result.writeback["error"] is None
    assert result.writeback["meta"]["independent_attestor_signature"]

    # qbXML write-back actually emitted exactly one BillAdd and reconciled the txn id.
    assert len(sent) == 1 and "BillAddRq" in sent[0]
    assert result.writeback["data"]["qb_txn_id"] == "NEW-TXN-1"
