"""Read + canonical-status-only write services for the operator dashboard.

Read functions aggregate the canonical store. Write functions transition canonical status or
canonical mappings ONLY — none of them call QuickBooks, QBWC, BillAdd, or any payment path.
The fee panel reuses the pure ``app.catalog.fee_math`` arithmetic (no DB, no write-back).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import fee_math
from app.dashboard import modules, vendor_bills, work_queue
from app.ingestion.reports import (
    amount_coverage_report,
    cost_code_mapping_exception_report,
    draw_line_validation_report,
    retainage_exception_report,
)
from app.models import (
    Bill,
    Company,
    CostCode,
    DrawLine,
    DrawPackage,
    FeeEntry,
    ProofBundle,
    Vendor,
    VendorCandidate,
    WorkItem,
)

# Statuses that mean "this draw is heading into the books". Approving into any of these is
# the gated transition the not_for_posting guard protects.
POSTING_STATUSES = frozenset({"approved_for_accounting"})


class ShadowGuardError(Exception):
    """Raised when an action would violate shadow-mode / not-for-posting invariants."""


# ---------------------------------------------------------------------------
# Guards (pure — unit-testable without a DB)
# ---------------------------------------------------------------------------
def is_historical(flags: dict[str, Any] | None) -> bool:
    f = flags or {}
    return bool(f.get("not_for_posting") or f.get("historical_example") or f.get("already_paid"))


def assert_postable(detail: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason). A historical / not_for_posting draw can never be approved-to-post."""
    if is_historical(detail.get("flags")):
        return False, (
            "Draw is flagged historical / not_for_posting — it can never be approved for "
            "posting. (Draw #29 is a paid historical fixture.)"
        )
    return True, "postable"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def list_companies(session: Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in session.scalars(select(Company).order_by(Company.legal_name)).all():
        vendors = session.scalar(
            select(func.count()).select_from(Vendor).where(Vendor.company_id == c.id)
        )
        bills = session.scalar(
            select(func.count()).select_from(Bill).where(Bill.company_id == c.id)
        )
        draws = session.scalar(
            select(func.count()).select_from(DrawPackage).where(DrawPackage.company_id == c.id)
        )
        out.append({
            "id": c.id, "legal_name": c.legal_name, "entity_type": c.entity_type,
            "role": c.role, "qb_entity_code": c.qb_entity_code,
            "vendor_count": vendors or 0, "bill_count": bills or 0, "draw_count": draws or 0,
        })
    return out


def get_company(session: Session, company_id: str) -> dict[str, Any] | None:
    c = session.get(Company, company_id)
    if c is None:
        return None
    return {
        "id": c.id, "legal_name": c.legal_name, "entity_type": c.entity_type,
        "role": c.role, "qb_entity_code": c.qb_entity_code, "qb_file_id": c.qb_file_id,
        "expense_dev_fee": c.expense_dev_fee,
    }


def list_vendors(session: Session, company_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(Vendor).order_by(Vendor.name)
    if company_id:
        stmt = stmt.where(Vendor.company_id == company_id)
    return [
        {"id": v.id, "name": v.name, "company_id": v.company_id,
         "qb_list_id": v.qb_list_id, "swarmscore": v.swarmscore}
        for v in session.scalars(stmt.limit(500)).all()
    ]


def get_vendor(session: Session, vendor_id: str) -> dict[str, Any] | None:
    v = session.get(Vendor, vendor_id)
    if v is None:
        return None
    return {
        "id": v.id, "name": v.name, "company_id": v.company_id, "qb_list_id": v.qb_list_id,
        "qb_edit_sequence": v.qb_edit_sequence, "swarmscore": v.swarmscore,
        "has_bank_fingerprint": v.bank_fingerprint is not None,
    }


def list_bills(session: Session, company_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(Bill).order_by(Bill.created_at.desc())
    if company_id:
        stmt = stmt.where(Bill.company_id == company_id)
    return [
        {"id": b.id, "company_id": b.company_id, "vendor_id": b.vendor_id,
         "amount": str(b.amount), "status": b.status, "po_ref": b.po_ref,
         "qb_txn_id": b.qb_txn_id, "draw_package_id": b.draw_package_id}
        for b in session.scalars(stmt.limit(500)).all()
    ]


def get_bill(session: Session, bill_id: str) -> dict[str, Any] | None:
    b = session.get(Bill, bill_id)
    if b is None:
        return None
    return {
        "id": b.id, "company_id": b.company_id, "vendor_id": b.vendor_id,
        "amount": str(b.amount), "status": b.status, "po_ref": b.po_ref,
        "qb_txn_id": b.qb_txn_id, "draw_package_id": b.draw_package_id,
        "net_amount_due": str(b.net_amount_due) if b.net_amount_due is not None else None,
    }


def list_draws(session: Session, company_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(DrawPackage).order_by(DrawPackage.created_at.desc())
    if company_id:
        stmt = stmt.where(DrawPackage.company_id == company_id)
    out: list[dict[str, Any]] = []
    for d in session.scalars(stmt.limit(500)).all():
        out.append({
            "id": d.id, "draw_number": d.draw_number, "project": d.customer_job,
            "company_id": d.company_id, "package_total": str(d.package_total),
            "status": d.status, "historical": is_historical(d.raw_extensions),
        })
    return out


def get_draw_detail(session: Session, draw_id: str) -> dict[str, Any] | None:
    d = session.get(DrawPackage, draw_id)
    if d is None:
        return None
    lines = session.scalars(
        select(DrawLine).where(DrawLine.draw_package_id == draw_id).order_by(DrawLine.line_no)
    ).all()
    line_rows = [
        {"line_no": ln.line_no, "item_code": ln.item_code, "invoice_no": ln.invoice_no,
         "payable_to": ln.payable_to, "description": ln.description,
         "inv_amount": str(ln.inv_amount) if ln.inv_amount is not None else None,
         "retainage": str(ln.retainage) if ln.retainage is not None else None,
         "amount_due": str(ln.amount_due) if ln.amount_due is not None else None,
         "row_confidence": ln.row_confidence, "needs_review": ln.needs_review,
         "mapped_cost_code": ln.cost_code_id is not None, "id": ln.id}
        for ln in lines
    ]
    coverage = amount_coverage_report(session, draw_id)
    exceptions = retainage_exception_report(session, draw_id)
    cost_code_gaps = cost_code_mapping_exception_report(session, draw_id)
    warnings = [r for r in draw_line_validation_report(session, draw_id) if r["needs_review"]]
    return {
        "id": d.id, "draw_number": d.draw_number, "project": d.customer_job,
        "company_id": d.company_id, "package_total": str(d.package_total),
        "status": d.status, "borrower": d.borrower, "lender": d.lender_ref,
        "collateral_address": d.collateral_address, "draw_date": d.draw_date,
        "source_doc_ref": d.source_doc_ref, "cm_approved": d.cm_approved,
        "watson_approved": d.watson_approved, "flags": dict(d.raw_extensions or {}),
        "historical": is_historical(d.raw_extensions),
        "lines": line_rows, "coverage": coverage,
        "retainage_exceptions": exceptions, "cost_code_gaps": cost_code_gaps,
        "warnings": warnings,
        "fee_panel": fee_panel(Decimal(str(d.package_total))),
        "fee_entries": fee_entries(session, draw_id),
        "proof": proof_status(session, draw_id),
    }


def fee_panel(package_total: Decimal) -> dict[str, Any]:
    """Pure 5/2/1 split for display. Shadow draft only — never posted to QuickBooks."""
    lines = fee_math.split_developer_fee(package_total)
    return {
        "package_total": str(package_total),
        "lines": [
            {"book": ln.book, "fee_role": ln.fee_role,
             "rate": str(ln.rate), "amount": str(ln.amount)}
            for ln in lines
        ],
        "partnership_total": str(fee_math.partnership_total(lines)),
        "parent_debit_total": str(fee_math.parent_debit_total(lines)),
        "distinct_economic_total_8pct": str(fee_math.distinct_economic_total(lines)),
        "naive_double_counted_13pct": str(fee_math.naive_double_counted_sum(lines)),
        "posted": False,
    }


def fee_entries(session: Session, draw_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(FeeEntry).where(FeeEntry.draw_package_id == draw_id)
    ).all()
    return [
        {"fee_role": r.fee_role, "amount": str(r.amount), "percent": str(r.percent),
         "dr_account": r.dr_account, "cr_account": r.cr_account, "status": r.status,
         "qb_txn_id": r.qb_txn_id, "posted_to_qb": r.qb_txn_id is not None}
        for r in rows
    ]


def proof_status(session: Session, draw_id: str) -> dict[str, Any]:
    bundle_ids = session.scalars(
        select(FeeEntry.proof_bundle_id).where(
            FeeEntry.draw_package_id == draw_id, FeeEntry.proof_bundle_id.isnot(None)
        )
    ).all()
    bundles = []
    for bid in {b for b in bundle_ids if b}:
        pb = session.get(ProofBundle, bid)
        if pb is not None:
            bundles.append({"id": pb.id, "kind": pb.kind, "passed": pb.passed,
                            "vcap_state": pb.vcap_state, "proof_hash": pb.proof_hash})
    return {"bundles": bundles, "count": len(bundles)}


def list_vendor_candidates(session: Session, company_id: str | None = None) -> list[dict[str, Any]]:
    stmt = select(VendorCandidate).where(VendorCandidate.status == "candidate")
    if company_id:
        stmt = stmt.where(VendorCandidate.company_id == company_id)
    return [
        {"id": vc.id, "name": vc.name, "normalized_name": vc.normalized_name,
         "company_id": vc.company_id, "source_ref": vc.source_ref}
        for vc in session.scalars(stmt.order_by(VendorCandidate.name)).all()
    ]


def work_queue_overview(session: Session) -> dict[str, Any]:
    """Module registry + live pending counts for the work-queue landing page.

    Draw Review (the one functional module) gets a real "to review" count; every other module
    is a placeholder with no count yet. Pure read — no QuickBooks, no write-back.
    """
    review_count = session.scalar(
        select(func.count()).select_from(DrawPackage).where(
            DrawPackage.status == "needs_review"
        )
    ) or 0
    draw_total = session.scalar(select(func.count()).select_from(DrawPackage)) or 0
    vb_count = vendor_bills.vendor_bill_count(session)
    groups: list[dict[str, Any]] = []
    for group, mods in modules.grouped_modules():
        cards: list[dict[str, Any]] = []
        for m in mods:
            if m.key == "draw_review":
                count: int | None = review_count
                count_label = f"{review_count} to review"
            elif m.key == "vendor_bills":
                count = vb_count
                count_label = f"{vb_count} to review"
            elif work_queue.is_workitem_module(m.key):
                count = work_queue.work_item_count(session, m.key)
                count_label = f"{count} to review"
            elif m.key == "month_end":
                count = len(work_queue.month_end_exceptions(session))
                count_label = f"{count} open"
            elif m.key == "missing_dimensions":
                count = len(work_queue.missing_dimensions_items(session))
                count_label = f"{count} to fix"
            else:
                count = None
                count_label = "—"
            cards.append({
                "key": m.key, "title": m.title, "status": m.status, "route": m.route,
                "description": m.description, "pending_count": count, "count_label": count_label,
            })
        groups.append({"group": group, "modules": cards})
    return {
        "groups": groups,
        "module_count": len(modules.MODULES),
        "draw_count": draw_total,
        "shadow_mode": True,
        "qb_write_back": "DISABLED",
        "attention": attention_overview(session),
    }


# ---------------------------------------------------------------------------
# "What needs my attention today" — read-only cross-module action rollup.
# Reuses the existing month_end / missing_dimensions aggregation helpers rather than
# re-deriving exception/missing-coding logic. No writes, no QuickBooks path.
# ---------------------------------------------------------------------------
def _att_item(label: str, sublabel: str, link: str) -> dict[str, Any]:
    return {"label": label, "sublabel": sublabel, "link": link}


def _open_work_items(session: Session) -> list[dict[str, Any]]:
    """Every open (action-needed) item across vendor bills, work items, and draws, carrying its
    exceptions/warnings so the attention panel can bucket it without re-querying."""
    rows: list[dict[str, Any]] = []
    for b in vendor_bills.list_vendor_bills(session):
        if b["status"] in vendor_bills.OPEN_STATUSES:
            rows.append({
                "source": "Vendor Bills",
                "label": b.get("invoice_no") or "(no invoice #)",
                "sublabel": f"Vendor Bills: {b.get('vendor_name') or '—'}",
                "exceptions": list(b["exceptions"]),
                "warnings": list(b["warnings"]),
                "link": f"/ui/vendor-bills/{b['id']}",
            })
    for it in session.scalars(select(WorkItem)).all():
        if it.status in work_queue.OPEN_STATUSES:
            rx = it.raw_extensions or {}
            title = work_queue._module_title(it.module_key)
            rows.append({
                "source": title,
                "label": it.reference or it.title,
                "sublabel": f"{title}: {it.counterparty or it.title}",
                "exceptions": list(rx.get("exceptions") or []),
                "warnings": list(rx.get("warnings") or []),
                "link": f"/ui/m/{it.module_key}/{it.id}",
            })
    for d in session.scalars(
        select(DrawPackage).where(DrawPackage.status == "needs_review")
    ).all():
        rows.append({
            "source": "Draw Review",
            "label": f"Draw #{d.draw_number}",
            "sublabel": f"Draw Review: {d.customer_job or d.borrower or '—'}",
            "exceptions": ["DRAW_NEEDS_REVIEW"],
            "warnings": [],
            "link": f"/ui/draws/{d.id}",
        })
    return rows


def _bank_change_items(session: Session) -> list[dict[str, Any]]:
    """Vendor + work-item bank-change warnings (fingerprint-derived; raw bank fields never read)."""
    out: list[dict[str, Any]] = []
    for b in vendor_bills.list_vendor_bills(session):
        if vendor_bills.WARN_VENDOR_BANK_CHANGE in b["warnings"]:
            out.append(_att_item(
                b.get("invoice_no") or "(no invoice #)",
                f"Vendor Bills: {b.get('vendor_name') or '—'}",
                f"/ui/vendor-bills/{b['id']}",
            ))
    for it in session.scalars(select(WorkItem)).all():
        if work_queue.WARN_BANK_CHANGE in list((it.raw_extensions or {}).get("warnings") or []):
            title = work_queue._module_title(it.module_key)
            out.append(_att_item(
                it.reference or it.title, f"{title}: {it.counterparty or it.title}",
                f"/ui/m/{it.module_key}/{it.id}",
            ))
    return out


def attention_overview(session: Session) -> dict[str, Any]:
    """Everything needing action across all modules, grouped by urgency/type with counts and
    links. Read-only: reuses month_end / missing_dimensions rollups + open-status scans."""
    exceptions = [
        _att_item(f"{e['exception']} — {e['reference']}", f"{e['source']}: {e['entity']}", e["link"])
        for e in work_queue.month_end_exceptions(session)
    ]
    missing = [
        _att_item(
            f"Missing {', '.join(m['missing'])} — {m['reference']}",
            f"{m['source']}: {m['entity']}", m["link"],
        )
        for m in work_queue.missing_dimensions_items(session)
    ]
    bank = _bank_change_items(session)
    opens = _open_work_items(session)
    needs = [_att_item(r["label"], r["sublabel"], r["link"]) for r in opens]
    pending = [
        _att_item(r["label"], r["sublabel"], r["link"])
        for r in opens
        if not r["exceptions"] and not r["warnings"]
    ]
    groups = [
        {"kind": "Open exceptions (close-blocking)", "urgency": "high",
         "count": len(exceptions), "rows": exceptions},
        {"kind": "Vendor bank-change warnings", "urgency": "high",
         "count": len(bank), "rows": bank},
        {"kind": "Missing coding (Customer:Job / Class / Item)", "urgency": "medium",
         "count": len(missing), "rows": missing},
        {"kind": "Needs info / needs review", "urgency": "medium",
         "count": len(needs), "rows": needs},
        {"kind": "Pending approvals", "urgency": "low",
         "count": len(pending), "rows": pending},
    ]
    return {
        "groups": groups,
        "total": sum(g["count"] for g in groups),
        "shadow_mode": True,
        "qb_write_back": "DISABLED",
    }


def sync_overview(session: Session) -> dict[str, Any]:
    """Counts + the FinalSpec Phase 1 sync-tracking placeholders (poller spikes still open)."""
    companies = session.scalar(select(func.count()).select_from(Company)) or 0
    vendors = session.scalar(select(func.count()).select_from(Vendor)) or 0
    bills = session.scalar(select(func.count()).select_from(Bill)) or 0
    draws = session.scalar(select(func.count()).select_from(DrawPackage)) or 0
    proofs = session.scalar(
        select(func.count()).select_from(ProofBundle).where(ProofBundle.passed.is_(True))
    ) or 0
    return {
        "counts": {"companies": companies, "vendors": vendors, "bills": bills, "draws": draws},
        "qbwc_poll_cadence": {
            "status": "pending spike #1",
            "detail": "Real QBWC poll cadence not yet measured on a Rightworks file.",
            "value_seconds": None,
        },
        "rightworks_persistent_poller": {
            "status": "pending written approval — spike #2",
            "detail": "Persistent poller awaiting written Rightworks approval; no inbound fallback.",
            "ticket": None,
        },
        "auditproof_runs": {"passed_bundles": proofs},
        "shadow_mode": True,
        "qb_write_back": "DISABLED",
    }


# ---------------------------------------------------------------------------
# Writes (canonical status / mapping ONLY — no QuickBooks side effects)
# ---------------------------------------------------------------------------
def transition_draw_status(session: Session, draw_id: str, new_status: str) -> dict[str, Any]:
    d = session.get(DrawPackage, draw_id)
    if d is None:
        raise ShadowGuardError(f"draw {draw_id} not found")
    if new_status in POSTING_STATUSES and is_historical(d.raw_extensions):
        raise ShadowGuardError(
            "historical / not_for_posting draw can never be approved for posting"
        )
    d.status = new_status
    session.flush()
    return {"id": d.id, "status": d.status}


def mark_draw_historical(session: Session, draw_id: str) -> dict[str, Any]:
    d = session.get(DrawPackage, draw_id)
    if d is None:
        raise ShadowGuardError(f"draw {draw_id} not found")
    # Reassign the dict so SQLAlchemy flags the JSONB column dirty.
    d.raw_extensions = {
        **(dict(d.raw_extensions) if d.raw_extensions else {}),
        "not_for_posting": True, "historical_example": True,
    }
    session.flush()
    return {"id": d.id, "historical": True, "flags": dict(d.raw_extensions)}


def resolve_vendor_candidate(session: Session, candidate_id: str, vendor_id: str) -> dict[str, Any]:
    vc = session.get(VendorCandidate, candidate_id)
    if vc is None:
        raise ShadowGuardError(f"vendor candidate {candidate_id} not found")
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise ShadowGuardError(f"vendor {vendor_id} not found")
    # Backfill any draw lines for this company whose payee matches the candidate.
    updated = 0
    lines = session.scalars(
        select(DrawLine)
        .join(DrawPackage, DrawLine.draw_package_id == DrawPackage.id)
        .where(DrawPackage.company_id == vc.company_id, DrawLine.payable_to == vc.name,
               DrawLine.vendor_id.is_(None))
    ).all()
    for ln in lines:
        ln.vendor_id = vendor_id
        updated += 1
    vc.status = "resolved"
    session.flush()
    return {"candidate_id": vc.id, "vendor_id": vendor_id, "lines_linked": updated}


def remap_draw_line_cost_code(session: Session, line_id: str, cost_code_id: str) -> dict[str, Any]:
    ln = session.get(DrawLine, line_id)
    if ln is None:
        raise ShadowGuardError(f"draw line {line_id} not found")
    cc = session.get(CostCode, cost_code_id)
    if cc is None:
        raise ShadowGuardError(f"cost code {cost_code_id} not found")
    ln.cost_code_id = cost_code_id
    ln.item_code = cc.code
    session.flush()
    return {"line_id": ln.id, "cost_code_id": cost_code_id, "item_code": cc.code}
