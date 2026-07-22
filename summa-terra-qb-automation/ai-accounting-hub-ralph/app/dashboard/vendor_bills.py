"""Vendor Bills / Non-GC Invoices module (shadow mode).

Day-to-day AP vendor invoices that are NOT GC draw packages. Reuses the canonical ``Bill``
model — the non-GC vendor-bill fields ride in ``Bill.raw_extensions`` (no schema change to the
frozen models). Every intake and every status change writes an AIVS audit row (the same
hash-chained AuditProof spine the draw engine uses).

Shadow mode is absolute: there is NO import of, or call into, QuickBooks / QBWC / BillAdd /
payment execution anywhere in this module. Intake and status transitions touch the canonical
store only.

Bank details are never stored or logged raw — only a SHA-256 *fingerprint* is kept, and it is
compared against the vendor's stored ``bank_fingerprint`` to raise a bank-change warning.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import append_audit_row
from app.ingestion.normalize import normalize_name
from app.models import AuditRow, Bill, Vendor, VendorCandidate

BILL_TYPE = "vendor_bill"
ACTOR_DEFAULT = "operator"

# Exception (hard) + warning codes surfaced in the work queue.
EXC_DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
EXC_MISSING_CODING = "MISSING_CODING"
EXC_VENDOR_NOT_SET_UP = "VENDOR_NOT_SET_UP"
WARN_VENDOR_BANK_CHANGE = "VENDOR_BANK_CHANGE"

# Canonical-only statuses (never a QuickBooks status).
ST_PENDING = "pending_review"
ST_NEEDS_INFO = "needs_info"
ST_APPROVED = "approved_for_accounting"
ST_REJECTED = "rejected"
OPEN_STATUSES = frozenset({ST_PENDING, ST_NEEDS_INFO})
_ACTION_STATUS = {"approve": ST_APPROVED, "reject": ST_REJECTED, "needs-info": ST_NEEDS_INFO}


class VendorBillError(Exception):
    """Raised on an unknown vendor bill or an illegal action."""


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------
def bank_fingerprint(raw_bank_detail: str | None) -> str | None:
    """SHA-256 fingerprint of bank details. The raw value is NEVER stored, logged, or returned."""
    if not raw_bank_detail:
        return None
    norm = "".join(ch for ch in raw_bank_detail if ch.isalnum()).upper()
    if not norm:
        return None
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _to_cents(amount: str | float | Decimal | None) -> Decimal:
    try:
        return Decimal(str(amount if amount is not None else "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _coding_missing(
    customer_job: str | None, class_ref: str | None, item_cost_code: str | None
) -> list[str]:
    missing: list[str] = []
    if not customer_job:
        missing.append("Customer:Job")
    if not class_ref:
        missing.append("Class")
    if not item_cost_code:
        missing.append("Item")
    return missing


# ---------------------------------------------------------------------------
# Audit trail (canonical AIVS hash chain — not a QuickBooks write)
# ---------------------------------------------------------------------------
def _audit(
    session: Session,
    *,
    action_type: str,
    actor: str,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> Any:
    # Fresh session_id per action: each is its own one-row chain (matches the draw-engine
    # attestation pattern) so we never re-validate an unrelated prior chain.
    return append_audit_row(
        session,
        session_id=str(uuid.uuid4()),
        action_type=action_type,
        actor=actor,
        tool_name="vendor_bills",
        inputs=dict(inputs),
        outputs=dict(outputs),
    )


# ---------------------------------------------------------------------------
# Intake + extraction (VB-1/VB-2)
# ---------------------------------------------------------------------------
def _match_vendor(session: Session, company_id: str, vendor_name: str) -> Vendor | None:
    norm = normalize_name(vendor_name or "")
    if not norm:
        return None
    for v in session.scalars(select(Vendor).where(Vendor.company_id == company_id)).all():
        if normalize_name(v.name) == norm:
            return v
    return None


def _queue_candidate(
    session: Session, company_id: str, name: str, source_ref: str | None
) -> VendorCandidate:
    norm = normalize_name(name or "")
    existing = session.scalars(
        select(VendorCandidate).where(
            VendorCandidate.company_id == company_id,
            VendorCandidate.normalized_name == norm,
        )
    ).first()
    if existing is not None:
        return existing
    vc = VendorCandidate(
        company_id=company_id,
        name=name,
        normalized_name=norm,
        source_ref=source_ref or "vendor_bill_intake",
    )
    session.add(vc)
    session.flush()
    return vc


def _is_duplicate(
    session: Session, company_id: str, vendor_id: str, invoice_no: str | None
) -> bool:
    """A duplicate is the SAME vendor + SAME invoice number within the company (an existing
    vendor bill). A shared invoice string across different vendors is not a duplicate."""
    if not invoice_no:
        return False
    rows = session.scalars(
        select(Bill).where(Bill.company_id == company_id, Bill.vendor_id == vendor_id)
    ).all()
    for b in rows:
        rx = b.raw_extensions or {}
        if rx.get("bill_type") == BILL_TYPE and rx.get("invoice_no") == invoice_no:
            return True
    return False


def intake_vendor_bill(
    session: Session,
    *,
    company_id: str,
    vendor_name: str,
    invoice_no: str | None,
    amount: str | float | Decimal | None,
    due_date: str | None = None,
    customer_job: str | None = None,
    class_ref: str | None = None,
    item_cost_code: str | None = None,
    bank_detail: str | None = None,
    source_ref: str | None = None,
    actor: str = ACTOR_DEFAULT,
) -> dict[str, Any]:
    """Intake one vendor invoice. Matches the vendor (or queues a candidate), runs the
    duplicate / bank-change / missing-coding checks, persists a canonical vendor bill, and
    writes an audit row. No QuickBooks side effects."""
    fp = bank_fingerprint(bank_detail)
    vendor = _match_vendor(session, company_id, vendor_name)

    if vendor is None:
        cand = _queue_candidate(session, company_id, vendor_name, source_ref)
        _audit(
            session,
            action_type="vendor_bill.intake_unmatched",
            actor=actor,
            inputs={"vendor_name": vendor_name, "invoice_no": invoice_no},
            outputs={"candidate_id": cand.id, "exceptions": [EXC_VENDOR_NOT_SET_UP]},
        )
        return {
            "status": "vendor_unmatched",
            "bill_id": None,
            "candidate_id": cand.id,
            "exceptions": [EXC_VENDOR_NOT_SET_UP],
            "warnings": [],
            "missing_coding": [],
        }

    exceptions: list[str] = []
    warnings: list[str] = []
    if _is_duplicate(session, company_id, vendor.id, invoice_no):
        exceptions.append(EXC_DUPLICATE_INVOICE)
    bank_changed = bool(fp and vendor.bank_fingerprint and fp != vendor.bank_fingerprint)
    if bank_changed:
        warnings.append(WARN_VENDOR_BANK_CHANGE)
    missing = _coding_missing(customer_job, class_ref, item_cost_code)
    if missing:
        exceptions.append(EXC_MISSING_CODING)

    status = ST_NEEDS_INFO if exceptions else ST_PENDING
    amt = _to_cents(amount)
    bill = Bill(
        company_id=company_id,
        vendor_id=vendor.id,
        status=status,
        raw_extensions={
            "bill_type": BILL_TYPE,
            "invoice_no": invoice_no,
            "due_date": due_date,
            "customer_job": customer_job,
            "class_ref": class_ref,
            "item_cost_code": item_cost_code,
            "vendor_name_raw": vendor_name,
            "bank_fingerprint_seen": fp,
            "bank_change": bank_changed,
            "missing_coding": missing,
            "exceptions": exceptions,
            "warnings": warnings,
            "source_ref": source_ref,
        },
    )
    bill.amount = amt  # type: ignore[assignment]  # Numeric round-trips Decimal at runtime
    session.add(bill)
    session.flush()
    _audit(
        session,
        action_type="vendor_bill.intake",
        actor=actor,
        inputs={"vendor_id": vendor.id, "invoice_no": invoice_no, "amount": str(amt)},
        outputs={
            "bill_id": bill.id,
            "status": status,
            "exceptions": exceptions,
            "warnings": warnings,
            "bank_fingerprint_seen": fp,
        },
    )
    return {
        "status": "intaken",
        "bill_id": bill.id,
        "vendor_id": vendor.id,
        "bill_status": status,
        "exceptions": exceptions,
        "warnings": warnings,
        "missing_coding": missing,
    }


# ---------------------------------------------------------------------------
# Reads (VB-3 work queue)
# ---------------------------------------------------------------------------
def _bill_view(b: Bill, vendor_name: str | None = None) -> dict[str, Any]:
    rx = b.raw_extensions or {}
    exceptions = list(rx.get("exceptions") or [])
    warnings = list(rx.get("warnings") or [])
    return {
        "id": b.id,
        "company_id": b.company_id,
        "vendor_id": b.vendor_id,
        "vendor_name": vendor_name or rx.get("vendor_name_raw"),
        "amount": str(b.amount),
        "status": b.status,
        "invoice_no": rx.get("invoice_no"),
        "due_date": rx.get("due_date"),
        "customer_job": rx.get("customer_job"),
        "class_ref": rx.get("class_ref"),
        "item_cost_code": rx.get("item_cost_code"),
        "exceptions": exceptions,
        "warnings": warnings,
        "missing_coding": list(rx.get("missing_coding") or []),
        "has_exceptions": bool(exceptions),
        "has_warnings": bool(warnings),
        "qb_txn_id": b.qb_txn_id,
        "posted_to_qb": b.qb_txn_id is not None,
    }


def list_vendor_bills(session: Session, company_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(Bill).order_by(Bill.created_at.desc())
    if company_id:
        stmt = stmt.where(Bill.company_id == company_id)
    out: list[dict[str, Any]] = []
    for b in session.scalars(stmt.limit(500)).all():
        if (b.raw_extensions or {}).get("bill_type") != BILL_TYPE:
            continue
        out.append(_bill_view(b))
    return out


def get_vendor_bill(session: Session, bill_id: str) -> dict[str, Any] | None:
    b = session.get(Bill, bill_id)
    if b is None or (b.raw_extensions or {}).get("bill_type") != BILL_TYPE:
        return None
    vendor = session.get(Vendor, b.vendor_id) if b.vendor_id else None
    view = _bill_view(b, vendor_name=vendor.name if vendor else None)
    view["audit_trail"] = vendor_bill_audit_trail(session, bill_id)
    return view


def vendor_bill_audit_trail(session: Session, bill_id: str) -> list[dict[str, Any]]:
    """Every audit row this module wrote that references the bill (intake + status changes)."""
    rows = session.scalars(
        select(AuditRow)
        .where(AuditRow.tool_name == "vendor_bills")
        .order_by(AuditRow.row_id.desc())
    ).all()
    trail: list[dict[str, Any]] = []
    for r in rows:
        inp = r.inputs_json or {}
        out = r.outputs_json or {}
        if inp.get("bill_id") == bill_id or out.get("bill_id") == bill_id:
            trail.append({
                "action_type": r.action_type,
                "actor": r.actor,
                "row_hash": r.row_hash[:12],
                "outputs": {k: v for k, v in out.items() if k != "_aivs"},
            })
    return trail


def vendor_bill_count(session: Session) -> int:
    """Open (to-review) vendor bills for the work-queue landing count."""
    return sum(1 for b in list_vendor_bills(session) if b["status"] in OPEN_STATUSES)


# ---------------------------------------------------------------------------
# Actions (VB-3 — canonical status ONLY, each writes an audit row)
# ---------------------------------------------------------------------------
def set_vendor_bill_status(
    session: Session, bill_id: str, action: str, actor: str = ACTOR_DEFAULT
) -> dict[str, Any]:
    if action not in _ACTION_STATUS:
        raise VendorBillError(f"unknown action {action!r}")
    b = session.get(Bill, bill_id)
    if b is None or (b.raw_extensions or {}).get("bill_type") != BILL_TYPE:
        raise VendorBillError(f"vendor bill {bill_id} not found")
    new_status = _ACTION_STATUS[action]
    b.status = new_status
    session.flush()
    _audit(
        session,
        action_type=f"vendor_bill.{action}",
        actor=actor,
        inputs={"bill_id": bill_id},
        outputs={"bill_id": bill_id, "status": new_status},
    )
    return {"bill_id": bill_id, "status": new_status}
