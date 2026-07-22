"""End-to-end payable pipeline orchestrator (CHUNK_8_SCALE).

Composes the existing public services into ONE gated pipeline — the workflow→verify→
payments wiring deferred from earlier chunks is wired HERE, by composition only (this
module imports and calls those services; it never edits them):

    OCR (app.payments.ocr)
      → InvoiceProof / Gate 1 (app.payments.PaymentsService)
        → human approval (app.workflow.WorkflowService)  ── appends AuditProof / Gate 2
          → VerifyAPI / Gate 3 + qbXML write-back (app.verify.execution.execute_approved_write)

FAIL-CLOSED is the invariant: the qbXML write (``writer``) is the LAST step and is
reached only after every prior gate passes. Any gate that blocks OR a proof callable
that raises (a simulated proof-service outage) short-circuits to a blocked result and
the writer is never invoked.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, validate_chain
from app.models import Bill
from app.payments.ocr import bill_draft_from_json
from app.payments.service import PaymentsService, VendorContext
from app.transport.adapter import QBXMLWriter, WriteableAccountingAdapter
from app.verify.execution import execute_approved_write
from app.workflow.service import WorkflowService

ChainLoader = Callable[[Any, str], Sequence[AuditRecord]]
ChainValidator = Callable[[Sequence[AuditRecord]], Any]

# Pipeline stages, in order. ``complete`` == the write-back reconciled green.
OCR = "ocr"
INVOICEPROOF = "invoiceproof"
APPROVAL = "approval"
VERIFY = "verify"
COMPLETE = "complete"


@dataclass
class PipelineResult:
    """Outcome of one end-to-end payable run, stage by stage."""

    stage: str
    blocked: bool
    wrote: bool
    draft: dict[str, Any]
    invoiceproof: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    writeback: dict[str, Any] | None = None
    error: str | None = None

    @property
    def green(self) -> bool:
        """A fully green run: every gate passed and the write reconciled."""
        return self.wrote and not self.blocked and self.stage == COMPLETE


def _blocked(
    stage: str,
    draft: dict[str, Any],
    *,
    error: str | None = None,
    invoiceproof: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    writeback: dict[str, Any] | None = None,
) -> PipelineResult:
    return PipelineResult(
        stage=stage,
        blocked=True,
        wrote=False,
        draft=draft,
        invoiceproof=invoiceproof,
        approval=approval,
        writeback=writeback,
        error=error,
    )


def run_payable_pipeline(
    session: Any,
    invoice_body: dict[str, Any],
    *,
    payments: PaymentsService,
    workflow: WorkflowService,
    capability_token: str,
    writer: QBXMLWriter,
    vendor_list_id: str,
    account_name: str,
    aivs_head: str,
    approver: str = "cfo@firm",
    intent_action: str = "create_bill",
    adapter: WriteableAccountingAdapter | None = None,
    known_accounts: Sequence[str] | None = None,
    load_chain: ChainLoader = lambda _s, _sid: [],
    chain_validator: ChainValidator = validate_chain,
    payments_context: VendorContext | None = None,
) -> PipelineResult:
    """Run ONE payable end to end through every gate. Returns a stage-by-stage result.

    Fail-closed: a blocking verdict or a raised proof callable at any gate returns a
    blocked result WITHOUT emitting the qbXML write.
    """
    # 1. OCR → canonical draft.
    draft = bill_draft_from_json(invoice_body)

    # 2. Gate 1 — InvoiceProof. A raise here is a proof-service outage → fail closed.
    try:
        decision = payments.process_intake(session, draft, context=payments_context)
    except Exception as exc:  # noqa: BLE001 - fail-closed: any proof error blocks the write
        return _blocked(INVOICEPROOF, draft, error=f"{type(exc).__name__}: {exc}")
    if not decision["passed"]:
        return _blocked(INVOICEPROOF, draft, invoiceproof=decision, error=decision.get("reason"))

    # 3. Human approval — appends AuditProof (Gate 2) and commits the canonical bill.
    intent = {
        "intent": intent_action,
        "company_id": draft["company_id"],
        "vendor_id": draft["vendor_id"],
        "amount": draft["amount"],
        "po_ref": draft.get("po_ref"),
        "idempotency_key": draft.get("invoice_number"),
        "raw_extensions": {},
    }
    try:
        workflow_id = workflow.submit_intent(session, intent, token=capability_token)
        approval = workflow.resolve(session, workflow_id, "approve", approver=approver)
    except Exception as exc:  # noqa: BLE001 - capability/AIVS failure blocks the write
        return _blocked(APPROVAL, draft, invoiceproof=decision, error=f"{type(exc).__name__}: {exc}")
    if not approval.get("committed"):
        return _blocked(APPROVAL, draft, invoiceproof=decision, approval=approval)

    # 4. Gate 3 — VerifyAPI + qbXML write-back. The write is the LAST step.
    bill = Bill(
        company_id=draft["company_id"],
        vendor_id=draft["vendor_id"],
        amount=draft["amount"],
        po_ref=draft.get("po_ref"),
        status="approved",
        raw_extensions={},
    )
    bill.id = approval.get("bill_id") or str(draft.get("invoice_number"))
    try:
        writeback = execute_approved_write(
            session,
            bill,
            vendor_list_id=vendor_list_id,
            account_name=account_name,
            writer=writer,
            aivs_head=aivs_head,
            session_id=workflow_id,
            adapter=adapter,
            known_accounts=known_accounts,
            load_chain=load_chain,
            chain_validator=chain_validator,
        )
    except Exception as exc:  # noqa: BLE001 - VerifyAPI/proof outage → fail closed, no write
        return _blocked(
            VERIFY, draft, invoiceproof=decision, approval=approval,
            error=f"{type(exc).__name__}: {exc}",
        )

    if writeback["error"] is not None:
        return _blocked(VERIFY, draft, invoiceproof=decision, approval=approval, writeback=writeback)

    return PipelineResult(
        stage=COMPLETE,
        blocked=False,
        wrote=True,
        draft=draft,
        invoiceproof=decision,
        approval=approval,
        writeback=writeback,
    )
