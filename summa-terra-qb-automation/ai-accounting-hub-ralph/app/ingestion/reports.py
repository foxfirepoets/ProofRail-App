"""The seven CHUNK_7 ingestion reports — queries over the persisted draw (shadow mode).

Parse Report, Line Validation, Vendor Match, Retainage Exception, Cost Code Mapping Exception,
Draw Total Tie-Out, Ready-for-Approval Queue. All read-only; no QuickBooks writes.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DrawLine, DrawPackage, VendorCandidate

CENT = Decimal("0.01")


def _pkg(session: Session, draw_id: str) -> DrawPackage:
    pkg = session.get(DrawPackage, draw_id)
    if pkg is None:
        raise ValueError(f"draw_package {draw_id} not found")
    return pkg


def _lines(session: Session, draw_id: str) -> list[DrawLine]:
    return list(
        session.scalars(
            select(DrawLine).where(DrawLine.draw_package_id == draw_id).order_by(DrawLine.line_no)
        ).all()
    )


def draw_package_parse_report(session: Session, draw_id: str) -> dict[str, Any]:
    pkg = _pkg(session, draw_id)
    lines = _lines(session, draw_id)
    return {
        "draw_number": pkg.draw_number,
        "project": pkg.customer_job,
        "lender": pkg.lender_ref,
        "borrower": pkg.borrower,
        "collateral_address": pkg.collateral_address,
        "draw_date": pkg.draw_date,
        "total_this_draw": str(pkg.package_total),
        "source_doc_ref": pkg.source_doc_ref,
        "status": pkg.status,
        "line_count": len(lines),
        "review_line_count": sum(1 for ln in lines if ln.needs_review),
    }


def draw_line_validation_report(session: Session, draw_id: str) -> list[dict[str, Any]]:
    rows = []
    for ln in _lines(session, draw_id):
        ok = None
        if None not in (ln.inv_amount, ln.retainage, ln.amount_due):
            ok = abs((Decimal(str(ln.inv_amount)) - Decimal(str(ln.retainage))) - Decimal(str(ln.amount_due))) <= CENT
        rows.append({
            "line_no": ln.line_no, "item_code": ln.item_code, "invoice_no": ln.invoice_no,
            "payable_to": ln.payable_to, "amount_due": str(ln.amount_due) if ln.amount_due is not None else None,
            "needs_review": ln.needs_review, "retainage_math_ok": ok,
        })
    return rows


def vendor_match_report(session: Session, draw_id: str) -> dict[str, Any]:
    lines = _lines(session, draw_id)
    matched = [ln for ln in lines if ln.vendor_id]
    unmatched = sorted({ln.payable_to for ln in lines if ln.payable_to and not ln.vendor_id})
    pkg = _pkg(session, draw_id)
    candidates = list(
        session.scalars(
            select(VendorCandidate.name).where(VendorCandidate.company_id == pkg.company_id)
        ).all()
    )
    return {
        "matched_lines": len(matched),
        "unmatched_payees": unmatched,
        "queued_candidates": sorted(candidates),
    }


def retainage_exception_report(session: Session, draw_id: str) -> list[dict[str, Any]]:
    out = []
    for ln in _lines(session, draw_id):
        if None not in (ln.inv_amount, ln.retainage, ln.amount_due):
            inv, ret, due = Decimal(str(ln.inv_amount)), Decimal(str(ln.retainage)), Decimal(str(ln.amount_due))
            if abs((inv - ret) - due) > CENT:
                out.append({
                    "line_no": ln.line_no, "item_code": ln.item_code,
                    "inv_amount": str(inv), "retainage": str(ret), "amount_due": str(due),
                    "expected_due": str(inv - ret),
                })
    return out


def cost_code_mapping_exception_report(session: Session, draw_id: str) -> list[dict[str, Any]]:
    return [
        {"line_no": ln.line_no, "item_code": ln.item_code, "raw_text": ln.raw_text}
        for ln in _lines(session, draw_id)
        if ln.item_code and ln.cost_code_id is None
    ]


def draw_total_tie_out_report(session: Session, draw_id: str) -> dict[str, Any]:
    pkg = _pkg(session, draw_id)
    lines = _lines(session, draw_id)
    parsed_due = sum((Decimal(str(ln.amount_due)) for ln in lines if ln.amount_due is not None), Decimal("0"))
    total = Decimal(str(pkg.package_total))
    raw = pkg.raw_extensions or {}
    summary_total = raw.get("summary_amount_due_total")
    return {
        "total_this_draw": str(total),
        "summary_amount_due_total": summary_total,
        "header_ties_to_summary": summary_total is not None and Decimal(summary_total) == total,
        "parsed_line_amount_due_sum": str(parsed_due),
        "parsed_lines_fully_reconcile": abs(parsed_due - total) <= CENT,
        "unreconciled_delta": str(total - parsed_due),
    }


def amount_coverage_report(session: Session, draw_id: str) -> dict[str, Any]:
    """CHUNK_7B: how completely the line reconstruction covers the authoritative total.

    ``reconstructed`` sums ``exact`` + ``reconstructed`` rows; ``parsed`` sums every row carrying
    an amount-due. Both are reported so any shortfall is explicit, never hidden.
    """
    pkg = _pkg(session, draw_id)
    lines = _lines(session, draw_id)
    authoritative = Decimal(str(pkg.package_total))

    def _sum(rows: list[DrawLine]) -> Decimal:
        return sum((Decimal(str(ln.amount_due)) for ln in rows if ln.amount_due is not None), Decimal("0"))

    parsed = _sum(lines)
    reconstructed = _sum([ln for ln in lines if ln.row_confidence in ("exact", "reconstructed")])
    breakdown: dict[str, int] = {}
    for ln in lines:
        breakdown[ln.row_confidence] = breakdown.get(ln.row_confidence, 0) + 1
    delta = authoritative - reconstructed
    pct = (reconstructed / authoritative * 100).quantize(CENT) if authoritative else Decimal("0")
    return {
        "authoritative_total": str(authoritative),
        "parsed_amount_due_total": str(parsed),
        "reconstructed_amount_due_total": str(reconstructed),
        "unresolved_delta": str(delta),
        "pct_coverage": str(pct),
        "fully_reconciled": abs(delta) <= CENT,
        "confidence_breakdown": breakdown,
        "summary_pages": list(pkg.raw_extensions.get("summary_pages", [])) if pkg.raw_extensions else [],
    }


def ready_for_approval_queue(session: Session, company_id: str) -> list[dict[str, Any]]:
    """Draws that parsed clean (status='parsed', zero review lines) — eligible for approval."""
    pkgs = session.scalars(
        select(DrawPackage).where(
            DrawPackage.company_id == company_id, DrawPackage.status == "parsed"
        )
    ).all()
    out = []
    for p in pkgs:
        review = session.scalar(
            select(func.count()).select_from(DrawLine).where(
                DrawLine.draw_package_id == p.id, DrawLine.needs_review.is_(True)
            )
        )
        if review == 0:
            out.append({"draw_number": p.draw_number, "total_this_draw": str(p.package_total)})
    return out
