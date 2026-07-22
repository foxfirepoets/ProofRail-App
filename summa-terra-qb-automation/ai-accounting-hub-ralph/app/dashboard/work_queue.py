"""Generic accounting work-queue engine (FIN-1, shadow mode).

One shared framework behind every non-draw, non-GC-bill module. Each module is just a
``module_key`` filter over the canonical ``work_items`` table — intake, exception computation
(MISSING_CODING / DUPLICATE / BANK_CHANGE), a work queue, a detail view, and approve / reject /
needs-info actions that change canonical status ONLY. Every intake and every action writes an
AIVS audit row (the same hash-chained AuditProof spine the draw engine and vendor-bills module
use), with ``tool_name = "work_queue:{module_key}"``.

Shadow mode is absolute: there is NO import of, or call into, QuickBooks / QBWC / BillAdd /
payment / draw-engine anywhere in this module. Intake and status transitions touch the canonical
store only.

Bank details are NEVER stored or logged raw — only a SHA-256 *fingerprint* is kept (reusing the
``vendor_bills.bank_fingerprint`` helper). A new fingerprint that differs from a prior one for the
same counterparty raises a BANK_CHANGE warning; the raw value never reaches the database.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import append_audit_row
from app.dashboard.vendor_bills import bank_fingerprint
from app.models import AuditRow, WorkItem

ACTOR_DEFAULT = "operator"

# Exception (hard) + warning codes surfaced in every work queue.
EXC_DUPLICATE = "DUPLICATE"
EXC_MISSING_CODING = "MISSING_CODING"
WARN_BANK_CHANGE = "BANK_CHANGE"

# Canonical-only statuses (never a QuickBooks status).
ST_NEEDS_REVIEW = "needs_review"
ST_NEEDS_INFO = "needs_info"
ST_APPROVED = "approved_for_accounting"
ST_REJECTED = "rejected"
OPEN_STATUSES = frozenset({ST_NEEDS_REVIEW, ST_NEEDS_INFO})
_ACTION_STATUS = {"approve": ST_APPROVED, "reject": ST_REJECTED, "needs-info": ST_NEEDS_INFO}


class WorkItemError(Exception):
    """Raised on an unknown work item or an illegal action."""


# The WorkItem-backed modules (module_key -> bank-sensitive?). bank=True modules accept a
# fingerprintable bank detail and raise the BANK_CHANGE warning. The two aggregation views
# (month_end, missing_dimensions) are NOT in here — they are read-only cross-module rollups.
WORKITEM_MODULES: dict[str, bool] = {
    "non_gc_invoices": False,
    "bank_feed": True,
    "credit_card": True,
    "loan_draws": False,
    "interest_reserve": False,
    "owner_contributions": False,
    "distributions": False,
    "intercompany": False,
    "developer_fees": False,
    "management_fees": False,
    "vendor_setup": True,
}


def is_workitem_module(module_key: str) -> bool:
    return module_key in WORKITEM_MODULES


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------
def _to_cents(amount: str | float | Decimal | None) -> Decimal | None:
    if amount is None or amount == "":
        return None
    try:
        return Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


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
    module_key: str,
    action_type: str,
    actor: str,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> Any:
    # Fresh session_id per action: each is its own one-row chain (matches the draw-engine /
    # vendor-bills attestation pattern) so we never re-validate an unrelated prior chain.
    return append_audit_row(
        session,
        session_id=str(uuid.uuid4()),
        action_type=action_type,
        actor=actor,
        tool_name=f"work_queue:{module_key}",
        inputs=dict(inputs),
        outputs=dict(outputs),
    )


# ---------------------------------------------------------------------------
# Exception predicates (DB)
# ---------------------------------------------------------------------------
def _is_duplicate(
    session: Session, company_id: str, module_key: str, reference: str | None
) -> bool:
    """A duplicate is the SAME company + module + reference as an existing work item."""
    if not reference:
        return False
    existing = session.scalars(
        select(WorkItem).where(
            WorkItem.company_id == company_id,
            WorkItem.module_key == module_key,
            WorkItem.reference == reference,
        )
    ).first()
    return existing is not None


def _prior_fingerprint(
    session: Session, company_id: str, module_key: str, counterparty: str | None
) -> str | None:
    """Most recent stored fingerprint for the same counterparty in this company+module."""
    stmt = (
        select(WorkItem)
        .where(
            WorkItem.company_id == company_id,
            WorkItem.module_key == module_key,
            WorkItem.bank_fingerprint.isnot(None),
        )
        .order_by(WorkItem.created_at.desc())
    )
    if counterparty:
        stmt = stmt.where(WorkItem.counterparty == counterparty)
    row = session.scalars(stmt).first()
    return row.bank_fingerprint if row is not None else None


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------
def intake_work_item(
    session: Session,
    module_key: str,
    *,
    company_id: str,
    title: str,
    reference: str | None = None,
    counterparty: str | None = None,
    amount: str | float | Decimal | None = None,
    txn_date: str | None = None,
    project_ref: str | None = None,
    customer_job: str | None = None,
    class_ref: str | None = None,
    item_cost_code: str | None = None,
    bank_detail: str | None = None,
    source_ref: str | None = None,
    actor: str = ACTOR_DEFAULT,
) -> dict[str, Any]:
    """Intake one work item for a module. Runs duplicate / bank-change / missing-coding checks,
    persists a canonical ``work_items`` row, and writes an audit row. No QuickBooks side effects.
    The raw bank detail is fingerprinted (SHA-256) and discarded — only the fingerprint persists.
    """
    fp = bank_fingerprint(bank_detail)
    exceptions: list[str] = []
    warnings: list[str] = []

    if _is_duplicate(session, company_id, module_key, reference):
        exceptions.append(EXC_DUPLICATE)

    bank_changed = False
    if fp:
        prior = _prior_fingerprint(session, company_id, module_key, counterparty)
        if prior and prior != fp:
            bank_changed = True
            warnings.append(WARN_BANK_CHANGE)

    missing = _coding_missing(customer_job, class_ref, item_cost_code)
    if missing:
        exceptions.append(EXC_MISSING_CODING)

    item = WorkItem(
        company_id=company_id,
        module_key=module_key,
        title=title,
        reference=reference,
        counterparty=counterparty,
        txn_date=txn_date,
        status=ST_NEEDS_REVIEW,
        project_ref=project_ref,
        customer_job=customer_job,
        class_ref=class_ref,
        item_cost_code=item_cost_code,
        bank_fingerprint=fp,
        raw_extensions={
            "exceptions": exceptions,
            "warnings": warnings,
            "missing_coding": missing,
            "bank_change": bank_changed,
            "bank_fingerprint_seen": fp,
            "source_ref": source_ref,
        },
    )
    item.amount = _to_cents(amount)  # type: ignore[assignment]  # Numeric round-trips Decimal
    session.add(item)
    session.flush()
    _audit(
        session,
        module_key=module_key,
        action_type=f"work_item.intake:{module_key}",
        actor=actor,
        inputs={"module_key": module_key, "reference": reference, "title": title},
        outputs={
            "item_id": item.id,
            "status": item.status,
            "exceptions": exceptions,
            "warnings": warnings,
            "bank_fingerprint_seen": fp,
        },
    )
    return {
        "status": "intaken",
        "item_id": item.id,
        "module_key": module_key,
        "item_status": item.status,
        "exceptions": exceptions,
        "warnings": warnings,
        "missing_coding": missing,
    }


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def _item_view(it: WorkItem) -> dict[str, Any]:
    rx = it.raw_extensions or {}
    exceptions = list(rx.get("exceptions") or [])
    warnings = list(rx.get("warnings") or [])
    return {
        "id": it.id,
        "company_id": it.company_id,
        "module_key": it.module_key,
        "title": it.title,
        "reference": it.reference,
        "counterparty": it.counterparty,
        "amount": str(it.amount) if it.amount is not None else None,
        "txn_date": it.txn_date,
        "status": it.status,
        "project_ref": it.project_ref,
        "customer_job": it.customer_job,
        "class_ref": it.class_ref,
        "item_cost_code": it.item_cost_code,
        "has_bank_fingerprint": it.bank_fingerprint is not None,
        "exceptions": exceptions,
        "warnings": warnings,
        "missing_coding": list(rx.get("missing_coding") or []),
        "has_exceptions": bool(exceptions),
        "has_warnings": bool(warnings),
    }


def list_work_items(
    session: Session, module_key: str, company_id: str | None = None
) -> list[dict[str, Any]]:
    stmt = (
        select(WorkItem)
        .where(WorkItem.module_key == module_key)
        .order_by(WorkItem.created_at.desc())
    )
    if company_id:
        stmt = stmt.where(WorkItem.company_id == company_id)
    return [_item_view(it) for it in session.scalars(stmt.limit(500)).all()]


def get_work_item(session: Session, item_id: str) -> dict[str, Any] | None:
    it = session.get(WorkItem, item_id)
    if it is None:
        return None
    view = _item_view(it)
    view["audit_trail"] = work_item_audit_trail(session, it.module_key, item_id)
    return view


def work_item_audit_trail(
    session: Session, module_key: str, item_id: str
) -> list[dict[str, Any]]:
    """Every audit row this module wrote that references the item (intake + status changes)."""
    rows = session.scalars(
        select(AuditRow)
        .where(AuditRow.tool_name == f"work_queue:{module_key}")
        .order_by(AuditRow.row_id.desc())
    ).all()
    trail: list[dict[str, Any]] = []
    for r in rows:
        inp = r.inputs_json or {}
        out = r.outputs_json or {}
        if inp.get("item_id") == item_id or out.get("item_id") == item_id:
            trail.append({
                "action_type": r.action_type,
                "actor": r.actor,
                "row_hash": r.row_hash[:12],
                "outputs": {k: v for k, v in out.items() if k != "_aivs"},
            })
    return trail


def work_item_count(session: Session, module_key: str) -> int:
    """Open (to-review) items for the work-queue landing count."""
    return sum(
        1 for it in list_work_items(session, module_key) if it["status"] in OPEN_STATUSES
    )


# ---------------------------------------------------------------------------
# Actions (canonical status ONLY, each writes an audit row)
# ---------------------------------------------------------------------------
def set_work_item_status(
    session: Session, item_id: str, action: str, actor: str = ACTOR_DEFAULT
) -> dict[str, Any]:
    if action not in _ACTION_STATUS:
        raise WorkItemError(f"unknown action {action!r}")
    it = session.get(WorkItem, item_id)
    if it is None:
        raise WorkItemError(f"work item {item_id} not found")
    new_status = _ACTION_STATUS[action]
    it.status = new_status
    session.flush()
    _audit(
        session,
        module_key=it.module_key,
        action_type=f"work_item.{action}:{it.module_key}",
        actor=actor,
        inputs={"item_id": item_id, "module_key": it.module_key},
        outputs={"item_id": item_id, "status": new_status},
    )
    return {"item_id": item_id, "status": new_status}


# ---------------------------------------------------------------------------
# Aggregation views (read-only cross-module rollups — no writes, no QB)
# ---------------------------------------------------------------------------
def _module_title(module_key: str) -> str:
    # Local import avoids a circular import at module load (modules imports nothing here).
    from app.dashboard import modules

    m = modules.get_module(module_key)
    return m.title if m is not None else module_key


def month_end_exceptions(session: Session) -> list[dict[str, Any]]:
    """Every open exception across every source (draw packages, vendor bills, work items),
    flattened into one close-exceptions list with a link to each source item. Read-only."""
    from app.dashboard import vendor_bills as vb
    from app.models import DrawPackage

    out: list[dict[str, Any]] = []

    # Draw packages still in review are close-blocking exceptions.
    draws = session.scalars(
        select(DrawPackage).where(DrawPackage.status == "needs_review")
    ).all()
    for d in draws:
        out.append({
            "source": "Draw Review",
            "module_key": "draw_review",
            "reference": f"Draw #{d.draw_number}",
            "entity": d.customer_job,
            "exception": "DRAW_NEEDS_REVIEW",
            "amount": str(d.package_total),
            "link": f"/ui/draws/{d.id}",
        })

    # Vendor bills carrying exceptions.
    for b in vb.list_vendor_bills(session):
        for exc in b["exceptions"]:
            out.append({
                "source": "Vendor Bills",
                "module_key": "vendor_bills",
                "reference": b.get("invoice_no") or "—",
                "entity": b.get("vendor_name") or "—",
                "exception": exc,
                "amount": b.get("amount"),
                "link": f"/ui/vendor-bills/{b['id']}",
            })

    # Work items carrying exceptions, across every WorkItem-backed module.
    items = session.scalars(select(WorkItem)).all()
    for it in items:
        for exc in list((it.raw_extensions or {}).get("exceptions") or []):
            out.append({
                "source": _module_title(it.module_key),
                "module_key": it.module_key,
                "reference": it.reference or "—",
                "entity": it.counterparty or it.title,
                "exception": exc,
                "amount": str(it.amount) if it.amount is not None else None,
                "link": f"/ui/m/{it.module_key}/{it.id}",
            })
    return out


def missing_dimensions_items(session: Session) -> list[dict[str, Any]]:
    """Every item across modules missing Customer:Job / Class / Item, linking to fix coding on
    the source. Read-only cross-module rollup."""
    from app.dashboard import vendor_bills as vb

    out: list[dict[str, Any]] = []

    for b in vb.list_vendor_bills(session):
        if b["missing_coding"]:
            out.append({
                "source": "Vendor Bills",
                "module_key": "vendor_bills",
                "reference": b.get("invoice_no") or "—",
                "entity": b.get("vendor_name") or "—",
                "missing": b["missing_coding"],
                "amount": b.get("amount"),
                "link": f"/ui/vendor-bills/{b['id']}",
            })

    items = session.scalars(select(WorkItem)).all()
    for it in items:
        missing = list((it.raw_extensions or {}).get("missing_coding") or [])
        if missing:
            out.append({
                "source": _module_title(it.module_key),
                "module_key": it.module_key,
                "reference": it.reference or "—",
                "entity": it.counterparty or it.title,
                "missing": missing,
                "amount": str(it.amount) if it.amount is not None else None,
                "link": f"/ui/m/{it.module_key}/{it.id}",
            })
    return out
