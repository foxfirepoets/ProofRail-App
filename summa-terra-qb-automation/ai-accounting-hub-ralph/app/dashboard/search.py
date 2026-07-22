"""Cross-entity search for the operator dashboard (read-only, shadow mode).

Searches the canonical store across draws, GC bills, vendor bills, vendors, work items,
projects, and open exceptions using parameterized SQLAlchemy ILIKE queries — the ``pg_trgm``
GIN index on ``vendors.name`` backs the vendor-name match, and every wildcard pattern is a
bound parameter (never raw string SQL). Each hit links to the entity's existing detail page.

Shadow mode is absolute: there is NO import of, or call into, QuickBooks / QBWC / BillAdd /
payment / draw-engine here. This module only reads the canonical store.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.dashboard import modules, work_queue
from app.dashboard.vendor_bills import BILL_TYPE
from app.models import Bill, DrawPackage, Vendor, WorkItem

# A query shorter than this is treated as "too short" — a friendly prompt, never an error.
MIN_Q_LEN = 2
MAX_Q_LEN = 200
# Per-entity-group result cap (keeps the page bounded; ILIKE rides the trigram index).
GROUP_LIMIT = 25


def normalize_query(q: str | None) -> str | None:
    """Return a trimmed, length-capped query, or None for empty/too-short input.

    None signals the router to render a friendly prompt instead of running a search — an
    empty or one-character ``q`` is never an error.
    """
    if q is None:
        return None
    cleaned = q.strip()
    if len(cleaned) < MIN_Q_LEN:
        return None
    return cleaned[:MAX_Q_LEN]


def _hit(label: str, sublabel: str | None, link: str, status: str | None = None) -> dict[str, Any]:
    return {"label": label, "sublabel": sublabel or "", "status": status, "link": link}


def _draw_hits(session: Session, pattern: str, limit: int) -> list[dict[str, Any]]:
    stmt = (
        select(DrawPackage)
        .where(
            or_(
                DrawPackage.draw_number.ilike(pattern),
                DrawPackage.customer_job.ilike(pattern),
                DrawPackage.borrower.ilike(pattern),
                DrawPackage.lender_ref.ilike(pattern),
                DrawPackage.collateral_address.ilike(pattern),
            )
        )
        .order_by(DrawPackage.created_at.desc())
        .limit(limit)
    )
    return [
        _hit(f"Draw #{d.draw_number}", d.customer_job or d.borrower, f"/ui/draws/{d.id}", d.status)
        for d in session.scalars(stmt).all()
    ]


def _bill_hits(
    session: Session, pattern: str, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """GC bills (/ui/bills) and vendor bills (/ui/vendor-bills) share the ``bills`` table; split
    them by ``raw_extensions.bill_type`` so each hit links to its correct detail page."""
    stmt = (
        select(Bill, Vendor.name.label("vendor_name"))
        .outerjoin(Vendor, Bill.vendor_id == Vendor.id)
        .where(
            or_(
                Bill.po_ref.ilike(pattern),
                Vendor.name.ilike(pattern),
                Bill.raw_extensions["invoice_no"].astext.ilike(pattern),
            )
        )
        .order_by(Bill.created_at.desc())
        .limit(limit * 2)
    )
    gc: list[dict[str, Any]] = []
    vbills: list[dict[str, Any]] = []
    for b, vendor_name in session.execute(stmt).all():
        rx = b.raw_extensions or {}
        if rx.get("bill_type") == BILL_TYPE:
            vbills.append(
                _hit(rx.get("invoice_no") or "(no invoice #)", vendor_name,
                     f"/ui/vendor-bills/{b.id}", b.status)
            )
        else:
            gc.append(
                _hit(b.po_ref or f"Bill {b.id[:8]}", vendor_name, f"/ui/bills/{b.id}", b.status)
            )
    return gc[:limit], vbills[:limit]


def _vendor_hits(session: Session, pattern: str, limit: int) -> list[dict[str, Any]]:
    stmt = select(Vendor).where(Vendor.name.ilike(pattern)).order_by(Vendor.name).limit(limit)
    return [_hit(v.name, None, f"/ui/vendors/{v.id}") for v in session.scalars(stmt).all()]


def _work_item_hits(session: Session, pattern: str, limit: int) -> list[dict[str, Any]]:
    stmt = (
        select(WorkItem)
        .where(
            or_(
                WorkItem.title.ilike(pattern),
                WorkItem.reference.ilike(pattern),
                WorkItem.counterparty.ilike(pattern),
                WorkItem.project_ref.ilike(pattern),
                WorkItem.customer_job.ilike(pattern),
            )
        )
        .order_by(WorkItem.created_at.desc())
        .limit(limit)
    )
    return [
        _hit(it.title, it.reference or it.counterparty, f"/ui/m/{it.module_key}/{it.id}", it.status)
        for it in session.scalars(stmt).all()
    ]


def _project_hits(session: Session, pattern: str, limit: int) -> list[dict[str, Any]]:
    """Distinct projects (draw ``customer_job`` + work-item ``project_ref``/``customer_job``)
    matching the query, each linking to a representative source detail page."""
    seen: dict[str, dict[str, Any]] = {}
    for d in session.scalars(
        select(DrawPackage).where(DrawPackage.customer_job.ilike(pattern)).limit(limit)
    ).all():
        seen.setdefault(d.customer_job, _hit(d.customer_job, "Draw project", f"/ui/draws/{d.id}"))
    for it in session.scalars(
        select(WorkItem)
        .where(or_(WorkItem.project_ref.ilike(pattern), WorkItem.customer_job.ilike(pattern)))
        .limit(limit)
    ).all():
        name = it.project_ref or it.customer_job
        if name and name not in seen:
            seen[name] = _hit(name, "Work-item project", f"/ui/m/{it.module_key}/{it.id}")
    return list(seen.values())[:limit]


def _exception_hits(session: Session, q: str, limit: int) -> list[dict[str, Any]]:
    """Open exceptions (reusing the month-end cross-module rollup) whose text matches the query."""
    needle = q.lower()
    out: list[dict[str, Any]] = []
    for e in work_queue.month_end_exceptions(session):
        haystack = " ".join(
            str(e.get(k) or "") for k in ("reference", "entity", "exception", "source")
        ).lower()
        if needle in haystack:
            out.append(
                _hit(f"{e['exception']} — {e['reference']}", f"{e['source']}: {e['entity']}",
                     e["link"])
            )
        if len(out) >= limit:
            break
    return out


def search(session: Session, q: str, limit: int = GROUP_LIMIT) -> dict[str, Any]:
    """Grouped read-only search across every dashboard entity. ``q`` must already be normalized
    (see :func:`normalize_query`). Returns groups (by entity type) each linking to a detail page."""
    pattern = f"%{q}%"
    gc_bills, vendor_bills_hits = _bill_hits(session, pattern, limit)
    raw_groups: list[tuple[str, list[dict[str, Any]]]] = [
        ("Draws", _draw_hits(session, pattern, limit)),
        ("Bills", gc_bills),
        ("Vendor Bills", vendor_bills_hits),
        ("Vendors", _vendor_hits(session, pattern, limit)),
        ("Invoices / Work Items", _work_item_hits(session, pattern, limit)),
        ("Projects", _project_hits(session, pattern, limit)),
        ("Exceptions", _exception_hits(session, q, limit)),
    ]
    groups = [
        {"kind": kind, "count": len(hits), "hits": hits} for kind, hits in raw_groups if hits
    ]
    return {"q": q, "groups": groups, "total": sum(g["count"] for g in groups)}


def module_title(module_key: str) -> str:
    m = modules.get_module(module_key)
    return m.title if m is not None else module_key
