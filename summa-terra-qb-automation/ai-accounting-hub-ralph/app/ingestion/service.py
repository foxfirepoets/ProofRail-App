"""Ingest a real draw-package PDF into the canonical store (CHUNK_7, SHADOW MODE).

Pipeline: extract text → parse header+lines → persist DrawPackage + draw_lines (idempotent) →
map cost codes/vendors + queue candidates → validate → set import status → return result.
NO QuickBooks writes, no BillAdd, no payments. A clean+approved draw can then be handed to the
existing shadow fee engine (app.draw_engine).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.mapping import MappingResult, map_draw_lines
from app.ingestion.parser import ParsedDraw, parse_header, summary_rows_to_lines
from app.ingestion.pdf_text import extract_text
from app.ingestion.table_extract import extract_summary_table
from app.ingestion.validate import DrawException, has_hard_exceptions, validate_draw
from app.models import Company, DrawLine, DrawPackage

STATUS_PARSED = "parsed"
STATUS_NEEDS_REVIEW = "needs_review"
CENT = Decimal("0.01")


@dataclass
class IngestResult:
    draw_id: str
    draw_number: str
    status: str
    line_count: int
    review_line_count: int
    parsed_amount_due: Decimal
    reconstructed_amount_due: Decimal
    authoritative_total: Decimal | None
    unresolved_delta: Decimal | None
    pct_coverage: Decimal | None
    confidence_breakdown: dict[str, int]
    summary_pages: tuple[int, ...]
    mapping: MappingResult
    exceptions: list[DrawException] = field(default_factory=list)


def _get_or_create_package(
    session: Session,
    company_id: str,
    draw: ParsedDraw,
    source_doc_ref: str,
    fixture_meta: dict[str, Any] | None = None,
) -> DrawPackage:
    h = draw.header
    draw_number = h.draw_number or "UNKNOWN"
    pkg = session.scalars(
        select(DrawPackage).where(
            DrawPackage.company_id == company_id, DrawPackage.draw_number == draw_number
        )
    ).one_or_none()
    header_raw: dict[str, Any] = {
        "project": h.project, "lender": h.lender, "draw_date": h.draw_date,
        "borrower": h.borrower, "collateral_address": h.collateral_address,
        "summary_inv_total": str(h.summary_inv_total) if h.summary_inv_total is not None else None,
        "summary_retainage_total": str(h.summary_retainage_total) if h.summary_retainage_total is not None else None,
        "summary_amount_due_total": str(h.summary_amount_due_total) if h.summary_amount_due_total is not None else None,
    }
    if fixture_meta:
        # Historical fixture flags (CHUNK_7B): a format reference only — never posts/pays.
        header_raw.update(fixture_meta)
    values: dict[str, Any] = {
        "customer_job": h.project or "UNKNOWN",
        "package_total": h.total_this_draw or Decimal("0"),
        "lender_ref": h.lender,
        "borrower": h.borrower,
        "collateral_address": h.collateral_address,
        "draw_date": h.draw_date,
        "source_doc_ref": source_doc_ref,
        "raw_extensions": header_raw,
    }
    if pkg is None:
        pkg = DrawPackage(company_id=company_id, draw_number=draw_number, status=STATUS_PARSED, **values)
        session.add(pkg)
    else:
        for k, v in values.items():
            setattr(pkg, k, v)
    session.flush()
    return pkg


def _upsert_lines(session: Session, draw_id: str, parsed_lines: list) -> None:
    """Idempotent batch upsert keyed on (draw_package_id, line_no). One SELECT, not one-per-line."""
    existing = {
        row.line_no: row
        for row in session.scalars(
            select(DrawLine).where(DrawLine.draw_package_id == draw_id)
        ).all()
    }
    for ln in parsed_lines:
        values: dict[str, Any] = {
            "item_code": ln.item_code, "invoice_no": ln.invoice_no, "payable_to": ln.payable_to,
            "description": ln.description, "inv_amount": ln.inv_amount, "retainage": ln.retainage,
            "amount_due": ln.amount_due, "vendor_id": ln.vendor_id, "cost_code_id": ln.cost_code_id,
            "needs_review": ln.needs_review, "row_confidence": ln.row_confidence,
            "raw_text": ln.raw_text,
            "raw_extensions": {"review_reasons": ln.review_reasons},
        }
        row = existing.get(ln.line_no)
        if row is None:
            session.add(DrawLine(draw_package_id=draw_id, line_no=ln.line_no, **values))
        else:
            for k, v in values.items():
                setattr(row, k, v)
    session.flush()


def ingest_draw(
    session: Session,
    pdf_path: Path,
    company_id: str,
    *,
    header_pages: tuple[int, int] = (1, 7),
    fixture_meta: dict[str, Any] | None = None,
) -> IngestResult:
    """Ingest a draw-package PDF (table-aware, CHUNK_7B).

    Summary pages are detected dynamically and the lines are reconstructed column-by-column.
    ``fixture_meta`` stamps historical-fixture flags (e.g. not_for_posting) into the package's
    raw_extensions so the shadow fee engine refuses to auto-fire on a reference document.
    """
    company = session.get(Company, company_id)
    if company is None:
        raise ValueError(f"company {company_id} not found")

    header_text = extract_text(pdf_path, first=header_pages[0], last=header_pages[1])
    table = extract_summary_table(pdf_path)
    header = parse_header(header_text)
    # The summary's totals row is authoritative for the money figures.
    if table.totals.amount_due_total is not None:
        header.total_this_draw = table.totals.amount_due_total
        header.summary_inv_total = table.totals.inv_total
        header.summary_retainage_total = table.totals.retainage_total
        header.summary_amount_due_total = table.totals.amount_due_total
    lines = summary_rows_to_lines(table.rows)
    draw = ParsedDraw(header=header, lines=lines)

    pkg_meta: dict[str, Any] = {"summary_pages": list(table.pages)}
    if fixture_meta:
        pkg_meta.update(fixture_meta)
    pkg = _get_or_create_package(session, company_id, draw, pdf_path.name, pkg_meta)
    mapping = map_draw_lines(session, company_id, draw.lines)
    _upsert_lines(session, pkg.id, draw.lines)

    exceptions = validate_draw(draw)
    reconstructed = sum((ln.amount_due for ln in draw.lines if ln.amount_due is not None), Decimal("0"))
    authoritative = header.total_this_draw
    delta = (authoritative - reconstructed) if authoritative is not None else None
    ties = delta is not None and abs(delta) <= CENT
    unrecoverable = any(ln.row_confidence == "unrecoverable" for ln in draw.lines)
    status = (
        STATUS_PARSED
        if ties and not unrecoverable and not has_hard_exceptions(exceptions)
        else STATUS_NEEDS_REVIEW
    )
    pkg.status = status
    session.flush()

    breakdown: dict[str, int] = {}
    for ln in draw.lines:
        breakdown[ln.row_confidence] = breakdown.get(ln.row_confidence, 0) + 1
    pct = (
        (reconstructed / authoritative * 100).quantize(Decimal("0.01"))
        if authoritative else None
    )
    return IngestResult(
        draw_id=pkg.id,
        draw_number=draw.header.draw_number or "UNKNOWN",
        status=status,
        line_count=len(draw.lines),
        review_line_count=sum(1 for ln in draw.lines if ln.needs_review),
        parsed_amount_due=reconstructed,
        reconstructed_amount_due=reconstructed,
        authoritative_total=authoritative,
        unresolved_delta=delta,
        pct_coverage=pct,
        confidence_breakdown=breakdown,
        summary_pages=table.pages,
        mapping=mapping,
        exceptions=exceptions,
    )
