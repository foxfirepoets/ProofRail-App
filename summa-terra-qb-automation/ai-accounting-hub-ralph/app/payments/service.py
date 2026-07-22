"""Payments orchestration (CHUNK_7) — the atomic money-movement path.

``PaymentsService`` runs one AP decision end to end:

1. Load prior vendor banking + payment context from the canonical store so BEC
   detection has history (``load_context``; injectable for DB-free tests).
2. Run InvoiceProof (Gate 1) over the assembled evidence.
3. Bank-change gate (Gate 4): compute a fresh bank FINGERPRINT, compare to the
   vendor's stored fingerprint, and on change run an ATEP tier check. Below the
   required tier ⇒ auto-block + escalate (``BANK_CHANGE_BLOCKED``). Raw bank fields
   are consumed for the fingerprint only — never stored, logged, or put in the proof.
4. Seal a VCAP Full Bundle proof + an AuditProof row for EVERY decision.
5. FAIL CLOSED: a Bill is written and the bundle released (atomic CAS) ONLY when the
   decision passed with a valid proof. A block writes the proof/audit but no Bill.

Every collaborator is injectable so the whole flow is unit-testable with fakes.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.payments.atep import evaluate_atep
from app.payments.fingerprint import compute_bank_fingerprint, fingerprint_changed
from app.payments.invoiceproof import run_invoiceproof
from app.payments.release import ReleaseGuard, sql_cas_release
from app.payments.vcap import VCAP_STATE_PENDING, build_vcap_bundle

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class VendorContext:
    """Prior canonical context for a vendor (raw bank details NEVER appear here)."""

    bank_fingerprint: str | None = None
    swarmscore: int | None = None
    existing_bills: list[dict[str, Any]] = field(default_factory=list)
    payment_history: list[dict[str, Any]] = field(default_factory=list)


# Session-typed params use ``Any`` so the same callables work for the DB path
# (real ``Session``) and DB-free tests (``None``/fakes) without variance errors.
LoadContext = Callable[[Any, str, str], VendorContext]
WriteBundle = Callable[[Any, dict[str, Any]], str]
CommitBill = Callable[[Any, dict[str, Any], str], Any]
AppendAudit = Callable[..., Any]
ReleaseFn = Callable[[Any, str], bool]


def _strip_bank_details(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Return the draft with the transient raw ``bank_details`` removed (never persisted)."""
    return {k: v for k, v in draft.items() if k != "bank_details"}


def _default_load_context(session: Session, company_id: str, vendor_id: str) -> VendorContext:
    """Load vendor master + payment history from the canonical store (real-DB path)."""
    from app.models import Bill, Vendor

    vendor = session.get(Vendor, vendor_id)
    bills = (
        session.query(Bill)
        .filter(Bill.company_id == company_id, Bill.vendor_id == vendor_id)
        .all()
    )
    existing = [
        {
            "company_id": b.company_id,
            "vendor_id": b.vendor_id,
            "invoice_number": (b.raw_extensions or {}).get("invoice_number"),
            "po_ref": b.po_ref,
            "amount": float(b.amount) if b.amount is not None else 0.0,
        }
        for b in bills
    ]
    history = [
        {"vendor_id": b.vendor_id, "amount": float(b.amount) if b.amount is not None else 0.0,
         "paid_at": str(b.created_at)}
        for b in bills
        if b.status in ("paid", "approved")
    ]
    return VendorContext(
        bank_fingerprint=vendor.bank_fingerprint if vendor else None,
        swarmscore=vendor.swarmscore if vendor else None,
        existing_bills=existing,
        payment_history=history,
    )


def _default_write_bundle(session: Session, bundle: dict[str, Any]) -> str:
    from app.models import ProofBundle

    row = ProofBundle(
        kind=bundle["kind"],
        vcap_state=bundle.get("vcap_state"),
        proof_hash=bundle.get("proof_hash"),
        proof_signature=bundle.get("proof_signature"),
        passed=bundle.get("passed", False),
        payload=bundle.get("payload"),
    )
    session.add(row)
    session.flush()
    return str(row.id)


def _default_commit_bill(session: Session, draft: dict[str, Any], bundle_id: str) -> Any:
    """Persist the Bill and link its InvoiceProof bundle (the gated payment write)."""
    from app.models import Bill

    raw = dict(draft.get("raw_extensions") or {})
    if draft.get("invoice_number"):
        raw["invoice_number"] = draft["invoice_number"]
    bill = Bill(
        company_id=draft["company_id"],
        vendor_id=draft["vendor_id"],
        po_ref=draft.get("po_ref"),
        amount=draft.get("amount") or 0,
        status="approved",
        invoiceproof_bundle_id=bundle_id,
        raw_extensions=raw,
    )
    session.add(bill)
    session.flush()
    return bill


def _default_release(session: Session | None, bundle_id: str) -> bool:
    if session is None:
        return True
    return sql_cas_release(session, bundle_id)


class PaymentsService:
    def __init__(
        self,
        *,
        load_context: LoadContext = _default_load_context,
        write_bundle: WriteBundle = _default_write_bundle,
        commit_bill: CommitBill = _default_commit_bill,
        append_audit: AppendAudit | None = None,
        release_fn: ReleaseFn = _default_release,
        vcap_secret: str | None = None,
        required_tier: str | None = None,
        release_guard: ReleaseGuard | None = None,
    ) -> None:
        self._load_context = load_context
        self._write_bundle = write_bundle
        self._commit_bill = commit_bill
        self._append_audit = append_audit
        self._release_fn = release_fn
        self._vcap_secret = vcap_secret
        self._required_tier = required_tier
        self._guard = release_guard or ReleaseGuard()

    # -- bank-change / Gate 4 -------------------------------------------------

    def _bank_change(self, draft: Mapping[str, Any], ctx: VendorContext) -> dict[str, Any]:
        """Compute the fresh fingerprint and, on change, run the ATEP tier gate.

        Returns a raw-free summary. ``blocked`` is True when a change is detected and
        the vendor is below the required trust tier.
        """
        fresh = compute_bank_fingerprint(draft.get("bank_details") or {})
        changed = fingerprint_changed(ctx.bank_fingerprint, fresh)
        result: dict[str, Any] = {
            "detected": changed,
            "fresh_fingerprint": fresh,
            "stored_fingerprint": ctx.bank_fingerprint,
            "blocked": False,
            "atep": None,
        }
        if changed:
            atep = evaluate_atep(ctx.swarmscore, required=self._required_tier)
            result["atep"] = atep
            result["blocked"] = not atep["allowed"]
        return result

    # -- main flow ------------------------------------------------------------

    def process_intake(
        self,
        session: Session | None,
        draft: Mapping[str, Any],
        *,
        actor: str = "ap-intake",
        context: VendorContext | None = None,
    ) -> dict[str, Any]:
        """Run the full gated decision for one invoice draft. Returns a raw-free decision."""
        company_id = str(draft["company_id"])
        vendor_id = str(draft["vendor_id"])
        ctx = context if context is not None else self._load_context(session, company_id, vendor_id)

        clean_draft = _strip_bank_details(draft)

        evidence = {
            "invoice": {
                "company_id": company_id,
                "vendor_id": vendor_id,
                "invoice_number": draft.get("invoice_number"),
                "po_ref": draft.get("po_ref"),
                "amount": draft.get("amount", 0),
                "line_items": list(draft.get("line_items") or []),
            },
            "po": draft.get("po"),
            "existing_bills": ctx.existing_bills,
            "payment_history": ctx.payment_history,
        }

        verdict = run_invoiceproof(evidence)
        bank = self._bank_change(draft, ctx)

        passed = bool(verdict["passed"]) and not bank["blocked"]
        if bank["blocked"]:
            reason = "BANK_CHANGE_BLOCKED"
        elif not verdict["passed"]:
            reason = "INVOICEPROOF_FAILED"
        else:
            reason = None

        # VCAP Full Bundle proof body — fingerprints only, never raw bank fields.
        proof_body = {
            "company_id": company_id,
            "vendor_id": vendor_id,
            "invoice_number": draft.get("invoice_number"),
            "amount": str(draft.get("amount", 0)),
            "passed": passed,
            "reason": reason,
            "invoiceproof": {
                "riskLevel": verdict["riskLevel"],
                "criticalRules": verdict["criticalRules"],
                "findings": verdict["findings"],
            },
            "bankChange": {
                "detected": bank["detected"],
                "blocked": bank["blocked"],
                "fresh_fingerprint": bank["fresh_fingerprint"],
                "stored_fingerprint": bank["stored_fingerprint"],
                "atep": bank["atep"],
            },
        }
        bundle = build_vcap_bundle(
            proof_body, passed=passed, secret=self._vcap_secret, vcap_state=VCAP_STATE_PENDING
        )

        bundle_id = self._write_bundle(session, bundle)

        # AuditProof row for EVERY decision (raw-free inputs/outputs).
        if self._append_audit is not None:
            self._append_audit(
                session,
                session_id=company_id,
                action_type="payment.decision",
                actor=actor,
                tool_name="invoiceproof",
                inputs={"vendor_id": vendor_id, "invoice_number": draft.get("invoice_number")},
                outputs={
                    "passed": passed,
                    "reason": reason,
                    "riskLevel": verdict["riskLevel"],
                    "bundle_id": bundle_id,
                    "bank_change_detected": bank["detected"],
                },
            )

        # FAIL CLOSED: write the Bill + release ONLY on a passing decision with a proof.
        bill_id: str | None = None
        released = False
        if passed and bundle.get("proof_signature"):
            if self._guard.release(bundle_id) and self._release_fn(session, bundle_id):
                released = True
                bill = self._commit_bill(session, clean_draft, bundle_id)
                bill_id = str(getattr(bill, "id", None)) if bill is not None else None

        return {
            "decision": "APPROVED" if passed else "BLOCKED",
            "passed": passed,
            "reason": reason,
            "bundle_id": bundle_id,
            "bill_id": bill_id,
            "released": released,
            "proof_signature": bundle.get("proof_signature"),
            "invoiceproof": verdict,
            "bankChange": {k: bank[k] for k in ("detected", "blocked", "atep")},
        }

    def release_bundle(self, session: Session | None, bundle_id: str) -> bool:
        """Idempotent atomic release: True only for the first successful claim."""
        if not self._guard.release(bundle_id):
            return False
        return self._release_fn(session, bundle_id)
