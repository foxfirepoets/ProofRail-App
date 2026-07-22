"""Parse a draw-package PDF into a structured header + summary lines (CHUNK_7).

Header fields and the summary *totals row* extract reliably and are the authoritative figures.
Per-line extraction is best-effort over imperfect column text: every candidate row is kept with
its raw text; rows whose cells can't be resolved are flagged ``needs_review`` rather than
dropped (spec req #9/#10). Pure functions over text — no DB, no PDF I/O here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.ingestion.normalize import money_tokens

_ITEM_RE = re.compile(r"^\s*(\d{3})\b")


def _caps_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def _is_vendor(col: str) -> bool:
    """A vendor column is mostly uppercase letters, >=4 alpha chars, not a money token."""
    alpha = sum(c.isalpha() for c in col)
    return alpha >= 4 and _caps_ratio(col) >= 0.8 and not money_tokens(col)


@dataclass
class DrawHeader:
    project: str | None = None
    draw_number: str | None = None
    lender: str | None = None
    draw_date: str | None = None
    borrower: str | None = None
    collateral_address: str | None = None
    total_this_draw: Decimal | None = None
    summary_inv_total: Decimal | None = None
    summary_retainage_total: Decimal | None = None
    summary_amount_due_total: Decimal | None = None


@dataclass
class ParsedLine:
    line_no: int
    item_code: str | None
    invoice_no: str | None
    payable_to: str | None
    description: str | None
    inv_amount: Decimal | None
    retainage: Decimal | None
    amount_due: Decimal | None
    raw_text: str
    needs_review: bool
    review_reasons: list[str] = field(default_factory=list)
    # Row-confidence from table-aware extraction (CHUNK_7B): exact | reconstructed |
    # needs_review | unrecoverable. Defaults to needs_review for the legacy line parser.
    row_confidence: str = "needs_review"
    # Filled by app.ingestion.mapping (None until matched).
    vendor_id: str | None = None
    cost_code_id: str | None = None


@dataclass
class ParsedDraw:
    header: DrawHeader
    lines: list[ParsedLine]


def _search(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def parse_header(text: str) -> DrawHeader:
    h = DrawHeader()
    h.draw_number = _search(r"Draw\s*#\s*(\d+)", text)
    h.draw_date = _search(r"(\d{2}\.\d{2}\.\d{4})", text)
    # Loan/project name (form line is authoritative; fall back to the title block).
    h.project = _search(r"LOAN\s*#:\s*(.+)", text) or _search(r"\n\s*(HUNTER[''']S LANDING)", text)
    h.borrower = _search(r"BORROWER:\s*(.+?)(?:\s{2,}|LOAN|$)", text)
    h.collateral_address = _search(r"COLLATERAL ADDRESS:\s*(.+?)(?:\s{2,}|UNIT|$)", text)
    h.lender = _search(r"([A-Za-z][A-Za-z ]+?(?:Credit Union|Bank|\bCU\b))", text)
    h.total_this_draw = (
        m := re.search(r"Total This Draw\s*\$?\s*([\d,]+\.\d{2})", text)
    ) and Decimal(m.group(1).replace(",", "")) or None
    # Summary totals row: a line with >=3 money tokens whose last equals Total This Draw.
    for line in text.splitlines():
        toks = money_tokens(line)
        if len(toks) >= 3 and h.total_this_draw is not None and abs(toks[-1]) == h.total_this_draw:
            h.summary_inv_total = toks[-3]
            h.summary_retainage_total = toks[-2]
            h.summary_amount_due_total = toks[-1]
            break
    return h


def parse_summary_lines(text: str) -> list[ParsedLine]:
    out: list[ParsedLine] = []
    line_no = 0
    for raw in text.splitlines():
        m = _ITEM_RE.match(raw)
        if not m:
            continue
        # Skip the grand-total row (handled in the header).
        if "Total This Draw" in raw:
            continue
        line_no += 1
        item_code = m.group(1)
        rest = raw[m.end():]
        toks = money_tokens(raw)
        # Column-split the row remainder; classify each column.
        cols = [c.strip() for c in re.split(r"\s{2,}", rest.strip()) if c.strip()]
        nonmoney = [c for c in cols if not money_tokens(c)]
        vendor_cols = [c for c in nonmoney if _is_vendor(c)]
        payable = max(vendor_cols, key=len)[:255] if vendor_cols else None
        # Invoice = first non-money, non-vendor column that contains a digit.
        invoice = next(
            (c[:64] for c in nonmoney if c not in vendor_cols and any(ch.isdigit() for ch in c)),
            None,
        )
        # Description = a non-money, non-vendor, non-invoice column (title-case text).
        desc = next(
            (c[:255] for c in nonmoney if c not in vendor_cols and c != invoice
             and any(ch.isalpha() for ch in c)),
            None,
        )
        reasons: list[str] = []
        inv_amount = retainage = amount_due = None
        if len(toks) >= 3:
            inv_amount, retainage, amount_due = toks[-3], toks[-2], toks[-1]
        elif len(toks) == 2:
            inv_amount, amount_due = toks[0], toks[1]
        elif len(toks) == 1:
            amount_due = toks[0]
        else:
            reasons.append("no amount parsed")
        if invoice is None:
            reasons.append("missing invoice number")  # review warning, not hard failure
        if payable is None:
            reasons.append("payee not resolved")
        out.append(ParsedLine(
            line_no=line_no, item_code=item_code, invoice_no=invoice, payable_to=payable,
            description=desc, inv_amount=inv_amount, retainage=retainage, amount_due=amount_due,
            raw_text=raw.strip()[:500], needs_review=bool(reasons), review_reasons=reasons,
        ))
    return out


def parse_draw(header_text: str, summary_text: str) -> ParsedDraw:
    return ParsedDraw(header=parse_header(header_text), lines=parse_summary_lines(summary_text))


def summary_rows_to_lines(rows: list) -> list[ParsedLine]:
    """Convert table-aware ``SummaryRow``s (CHUNK_7B) into ``ParsedLine``s for the pipeline.

    ``UNRECOVERABLE`` / ``NEEDS_REVIEW`` rows are flagged needs_review; a missing invoice is a
    review reason (warning), never a drop. ``item_code`` comes only from the leftmost column, so
    invoice numbers can never enter cost-code mapping.
    """
    out: list[ParsedLine] = []
    for i, r in enumerate(rows, start=1):
        reasons: list[str] = []
        if r.row_confidence in ("needs_review", "unrecoverable"):
            reasons.append(f"row confidence {r.row_confidence}")
        if r.amount_due is None:
            reasons.append("amount due not parsed")
        if not r.invoice_no:
            reasons.append("missing invoice number")  # review warning, not a hard failure
        out.append(ParsedLine(
            line_no=i, item_code=r.item_code, invoice_no=r.invoice_no, payable_to=r.payable_to,
            description=r.description, inv_amount=r.inv_amount, retainage=r.retainage,
            amount_due=r.amount_due, raw_text=r.raw_text,
            needs_review=r.row_confidence in ("needs_review", "unrecoverable"),
            review_reasons=reasons, row_confidence=r.row_confidence,
        ))
    return out
