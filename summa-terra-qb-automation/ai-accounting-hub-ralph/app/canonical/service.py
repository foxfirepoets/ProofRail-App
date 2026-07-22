"""Canonical read service: unified search, record reads, and dashboard aggregation.

Pure-ish query logic kept separate from the FastAPI transport (router.py) so it can be
unit-tested against a fake/mocked Session without a live database. Unified search uses
the ``pg_trgm`` GIN index on ``vendors.name`` (``idx_vendors_name_trgm``); on a real
Postgres connection ``similarity()``/``ILIKE`` ride that index for the p95 < 2s target.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models import Bill, Company, Vendor

# Validation guardrails for the unified search query.
MAX_Q_LEN = 200
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class SearchValidationError(ValueError):
    """Raised when the ``q`` parameter is empty or exceeds the sane length cap.

    The router maps this to an enveloped HTTP 400 (never a 500).
    """


def validate_query(q: str | None) -> str:
    """Return a trimmed query, or raise SearchValidationError for empty/oversized input."""
    if q is None:
        raise SearchValidationError("query parameter 'q' is required")
    cleaned = q.strip()
    if not cleaned:
        raise SearchValidationError("query parameter 'q' must not be empty")
    if len(cleaned) > MAX_Q_LEN:
        raise SearchValidationError(
            f"query parameter 'q' must be at most {MAX_Q_LEN} characters"
        )
    return cleaned


def _namespaced_id(company_id: str, entity_id: str) -> str:
    """Disambiguate identical names across companies: ``<company_id>:<entity_id>``."""
    return f"{company_id}:{entity_id}"


def _vendor_hit(row: Any) -> dict[str, Any]:
    return {
        "kind": "vendor",
        "company_id": row["company_id"],
        "id": row["id"],
        "namespaced_id": _namespaced_id(row["company_id"], row["id"]),
        "name": row["name"],
        "score": float(row["score"]) if row["score"] is not None else 0.0,
    }


def _bill_hit(row: Any) -> dict[str, Any]:
    return {
        "kind": "bill",
        "company_id": row["company_id"],
        "id": row["id"],
        "namespaced_id": _namespaced_id(row["company_id"], row["id"]),
        "vendor_name": row["vendor_name"],
        "po_ref": row["po_ref"],
        "amount": float(row["amount"]) if row["amount"] is not None else 0.0,
        "status": row["status"],
        "score": float(row["score"]) if row["score"] is not None else 0.0,
    }


def _vendor_search_stmt(cleaned: str, pattern: str, limit: int) -> Any:
    return (
        select(
            Vendor.company_id.label("company_id"),
            Vendor.id.label("id"),
            Vendor.name.label("name"),
            func.similarity(Vendor.name, cleaned).label("score"),
        )
        .where(Vendor.name.ilike(pattern))
        .order_by(text("score DESC"))
        .limit(limit)
    )


def _bill_search_stmt(cleaned: str, pattern: str, limit: int) -> Any:
    # Bills ARE the transactions; match on the joined vendor name or the PO reference.
    return (
        select(
            Bill.company_id.label("company_id"),
            Bill.id.label("id"),
            Bill.po_ref.label("po_ref"),
            Bill.amount.label("amount"),
            Bill.status.label("status"),
            Vendor.name.label("vendor_name"),
            func.greatest(
                func.similarity(Vendor.name, cleaned),
                func.similarity(func.coalesce(Bill.po_ref, ""), cleaned),
            ).label("score"),
        )
        .join(Vendor, Bill.vendor_id == Vendor.id)
        .where(or_(Vendor.name.ilike(pattern), Bill.po_ref.ilike(pattern)))
        .order_by(text("score DESC"))
        .limit(limit)
    )


def search(session: Session, q: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Unified search over vendors AND bills across ALL companies.

    ``q`` must already be validated (see ``validate_query``). Results are namespaced by
    ``company_id`` so identical vendor names in different companies are disambiguated.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    pattern = f"%{q}%"

    vendor_rows = session.execute(_vendor_search_stmt(q, pattern, limit)).mappings().all()
    bill_rows = session.execute(_bill_search_stmt(q, pattern, limit)).mappings().all()

    hits = [_vendor_hit(r) for r in vendor_rows] + [_bill_hit(r) for r in bill_rows]
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:limit]


def get_vendor(session: Session, vendor_id: str) -> dict[str, Any] | None:
    """Canonical vendor record including ``raw_extensions``; None if unknown."""
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        return None
    return {
        "id": vendor.id,
        "company_id": vendor.company_id,
        "qb_list_id": vendor.qb_list_id,
        "qb_edit_sequence": vendor.qb_edit_sequence,
        "name": vendor.name,
        "bank_fingerprint": vendor.bank_fingerprint,
        "swarmscore": vendor.swarmscore,
        "raw_extensions": vendor.raw_extensions,
    }


def get_bill(session: Session, bill_id: str) -> dict[str, Any] | None:
    """Canonical bill record including ``raw_extensions``; None if unknown."""
    bill = session.get(Bill, bill_id)
    if bill is None:
        return None
    return {
        "id": bill.id,
        "company_id": bill.company_id,
        "vendor_id": bill.vendor_id,
        "qb_txn_id": bill.qb_txn_id,
        "qb_edit_sequence": bill.qb_edit_sequence,
        "po_ref": bill.po_ref,
        "amount": float(bill.amount) if bill.amount is not None else 0.0,
        "status": bill.status,
        "invoiceproof_bundle_id": bill.invoiceproof_bundle_id,
        "raw_extensions": bill.raw_extensions,
    }


def dashboard(session: Session) -> list[dict[str, Any]]:
    """Per-company aggregation of synced vendor/bill counts and bill totals for display."""
    companies = session.execute(
        select(Company.id.label("id"), Company.legal_name.label("legal_name"))
    ).mappings().all()

    vendor_counts = session.execute(
        select(Vendor.company_id.label("company_id"), func.count().label("n")).group_by(
            Vendor.company_id
        )
    ).mappings().all()

    bill_aggs = session.execute(
        select(
            Bill.company_id.label("company_id"),
            func.count().label("n"),
            func.coalesce(func.sum(Bill.amount), 0).label("total"),
        ).group_by(Bill.company_id)
    ).mappings().all()

    vmap = {r["company_id"]: r["n"] for r in vendor_counts}
    bmap = {r["company_id"]: r for r in bill_aggs}

    out: list[dict[str, Any]] = []
    for c in companies:
        agg = bmap.get(c["id"])
        out.append(
            {
                "company_id": c["id"],
                "legal_name": c["legal_name"],
                "vendor_count": int(vmap.get(c["id"], 0)),
                "bill_count": int(agg["n"]) if agg else 0,
                "bill_total": float(agg["total"]) if agg and agg["total"] is not None else 0.0,
            }
        )
    return out
