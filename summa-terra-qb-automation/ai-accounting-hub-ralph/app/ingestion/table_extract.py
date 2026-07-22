"""Table-aware extraction of the Builder's Draw Request Summary (CHUNK_7B).

CHUNK_7's line parser ran on ``pdftotext -layout`` text and only reconstructed ~71% of the
amount-due column. This module uses ``pdftotext -table`` (Xpdf 4.x), whose column alignment lets
us read the seven summary columns directly:

    ITEM #  |  INV #  |  PAYABLE TO  |  DESCRIPTION  |  INV AMOUNT  |  RETAINAGE (-)  |  AMOUNT DUE

Key invariants proven against Hunter's Landing Draw #29 (962,845.68):

* Every logical row is anchored by a physical line that begins with a 3-digit ITEM # *and*
  carries an AMOUNT DUE value. The amount-due column summed over the 57 anchors equals the
  document's authoritative Total This Draw exactly.
* ``ITEM #`` is read only from the leftmost column, so an invoice number that looks like a code
  (402/403/404) can never be mistaken for a cost code.
* Multi-line cells (wrapped invoice lists, wrapped vendor names) are bound to their anchor by an
  invoice comma-chain walk: a list fragment ending in ',' continues into the next physical line.
* Retainage is *derived* as ``inv_amount - amount_due`` (signed; negative = retention release),
  which both ties every row by construction and recovers the withheld/release sign that the raw
  glyphs ("($ 3,947.37)" vs "-$17,699.18") encode inconsistently.

Pure text in, structured rows out for the page parser; the PDF shell-out lives in one function so
the rest is unit-testable with hermetic ``-table`` snippets. No DB, no QuickBooks, no I/O besides
``pdftotext``.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

CENT = Decimal("0.01")
_ITEM = re.compile(r"^\s*(\d{3})(?:\s|$)")
# A money glyph: optional sign/paren/$, grouped digits, two decimals, optional close paren.
# Whitespace bounded to a single optional char to avoid catastrophic backtracking on layout runs.
_MONEY = re.compile(r"\(?\s?-?\$?\s?\(?\s?-?[\d,]+\.\d{2}\s?\)?")
_SKIP_MARKERS = ("Total This Draw", "CONTRACTOR", "SIGNATURE", "DRAW REQUEST SUMMARY")

# Confidence levels for a reconstructed row.
EXACT = "exact"
RECONSTRUCTED = "reconstructed"
NEEDS_REVIEW = "needs_review"
UNRECOVERABLE = "unrecoverable"

PdfExtractError = OSError


@dataclass
class SummaryRow:
    item_code: str | None
    invoice_no: str | None
    payable_to: str | None
    description: str | None
    inv_amount: Decimal | None
    retainage: Decimal | None
    amount_due: Decimal | None
    row_confidence: str
    raw_text: str


@dataclass
class SummaryTotals:
    inv_total: Decimal | None = None
    retainage_total: Decimal | None = None
    amount_due_total: Decimal | None = None


@dataclass
class TableExtract:
    rows: list[SummaryRow]
    totals: SummaryTotals
    pages: tuple[int, ...] = ()
    notes: list[str] = field(default_factory=list)


# ──────────────────────────── token helpers ────────────────────────────

def _magnitude(token: str) -> Decimal | None:
    digits = re.sub(r"[^\d.]", "", token)
    if not digits or digits == ".":
        return None
    return Decimal(digits)


def _money_spans(line: str) -> list[tuple[int, Decimal]]:
    """(start_index, positive magnitude) for each money glyph, left to right."""
    out: list[tuple[int, Decimal]] = []
    for m in _MONEY.finditer(line):
        v = _magnitude(m.group())
        if v is not None:
            out.append((m.start(), v))
    return out


def _is_skip(line: str) -> bool:
    return any(mark in line for mark in _SKIP_MARKERS)


def _invoice_cell(line: str, money_left: int | None = None) -> str:
    """Text in the INV # column: between the item code (if any) and the first money glyph."""
    m = _ITEM.match(line)
    start = m.end() if m else 0
    if money_left is None:
        spans = _money_spans(line)
        money_left = spans[0][0] if spans else len(line)
    seg = line[start:money_left]
    cells = [c.strip() for c in re.split(r"\s{2,}", seg.strip()) if c.strip()]
    # The invoice column is the leftmost cell that carries a digit/“Retention”/date but is not a
    # vendor-style all-caps name; fall back to the first cell.
    for c in cells:
        if not _is_vendor(c):
            return c
    return cells[0] if cells else ""


def _is_vendor(cell: str) -> bool:
    # A vendor name is pure letters/punctuation; an invoice token carrying digits (HL 2508,
    # AC25024, 697265) is never a vendor even when its letters are upper-case.
    if any(ch.isdigit() for ch in cell):
        return False
    alpha = [c for c in cell if c.isalpha()]
    if len(alpha) < 4:
        return False
    caps = sum(c.isupper() for c in alpha) / len(alpha)
    return caps >= 0.8


def _cluster_money_bands(starts: list[int], k: int = 3) -> list[tuple[int, int]]:
    """Split money start positions into <=k left-to-right bands by the largest gaps."""
    s = sorted(set(starts))
    if len(s) <= 1:
        return [(s[0] if s else 0, s[0] if s else 10**9)]
    gaps = sorted(range(1, len(s)), key=lambda i: s[i] - s[i - 1], reverse=True)
    cuts = sorted(gaps[: k - 1])
    idxs = [0, *cuts, len(s)]
    return [(s[a], s[b - 1]) for a, b in zip(idxs, idxs[1:], strict=False)]


# ──────────────────────────── page parser ────────────────────────────

def parse_table_page(page_text: str) -> tuple[list[SummaryRow], SummaryTotals]:
    """Parse one ``pdftotext -table`` page of the summary into rows + (optional) totals.

    Blank lines are dropped first: ``-table`` interleaves empty lines between rows, which would
    otherwise break the physical-line adjacency the multi-line cell chains rely on. Column
    assignment is by character position, so removing blank lines is information-preserving.
    """
    lines = [ln for ln in page_text.splitlines() if ln.strip()]
    hidx = -1
    for i, ln in enumerate(lines):
        if "ITEM" in ln and "PAYABLE" in ln and "AMOUNT DUE" in ln:
            hidx = i
            break

    # money bands for this page (from data lines, excluding header/totals)
    starts: list[int] = []
    totals = SummaryTotals()
    totals_line_idx: set[int] = set()
    for i, ln in enumerate(lines):
        if i <= hidx or "INV AMOUNT" in ln:
            continue
        spans = _money_spans(ln)
        # totals row: 3 money glyphs, no leading item code, not a per-row anchor
        if len(spans) == 3 and not _ITEM.match(ln):
            totals.inv_total, totals.retainage_total, totals.amount_due_total = (
                spans[0][1], -spans[1][1] if _retainage_is_release(ln, spans[1][0]) else spans[1][1],
                spans[2][1],
            )
            totals_line_idx.add(i)
            continue
        if _is_skip(ln) and not _ITEM.match(ln):
            continue
        starts.extend(st for st, _ in spans)
    bands = _cluster_money_bands(starts, 3)

    def band_of(st: int) -> int:
        return min(range(len(bands)), key=lambda i: abs(st - sum(bands[i]) / 2))

    def is_anchor(i: int, ln: str) -> bool:
        return i > hidx and i not in totals_line_idx and bool(_ITEM.match(ln)) and bool(_money_spans(ln))

    anchors = [i for i, ln in enumerate(lines) if is_anchor(i, ln)]
    anchor_set = set(anchors)
    claimed: dict[int, int] = {}

    def skippable(i: int, ln: str) -> bool:
        return (
            i <= hidx or i in anchor_set or i in totals_line_idx
            or not ln.strip() or _is_skip(ln) or ln.strip() == "DATE"
        )

    # 1. upward head-chain: above-wrap invoice fragments ending in ',' begin this anchor's list.
    for a in anchors:
        i = a - 1
        while i > hidx and i not in anchor_set and i not in claimed and not skippable(i, lines[i]):
            if _invoice_cell(lines[i]).rstrip().endswith(","):
                claimed[i] = a
                i -= 1
            else:
                break
    # 2. downward tail-chain: while the running invoice cell ends in ',', the next line continues it.
    for a in anchors:
        prev_inv = _invoice_cell(lines[a])
        i = a + 1
        while i < len(lines) and i not in anchor_set and i not in claimed and not skippable(i, lines[i]):
            if not prev_inv.rstrip().endswith(","):
                break
            claimed[i] = a
            prev_inv = _invoice_cell(lines[i])
            i += 1
    # 3. remaining wrap lines (vendor-name continuations) → nearest anchor, ties upward.
    for i, ln in enumerate(lines):
        if i in claimed or skippable(i, ln):
            continue
        above = [a for a in anchors if a < i]
        below = [a for a in anchors if a > i]
        da = i - above[-1] if above else 10**9
        db = below[0] - i if below else 10**9
        if above or below:
            claimed[i] = above[-1] if da <= db else below[0]

    rows: list[SummaryRow] = []
    for a in anchors:
        member_idxs = sorted([a, *[i for i, tgt in claimed.items() if tgt == a]])
        rows.append(_build_row(lines, a, member_idxs, band_of, len(bands)))
    return rows, totals


def _retainage_is_release(line: str, start: int) -> bool:
    """A retainage glyph denotes a release (negative) when it carries a leading '-' or a nested
    paren ``($ (…)``; a single-paren ``($ …)`` is a positive withholding."""
    glyph = line[start:start + 20]
    return "-" in glyph or glyph.count("(") >= 2


def _build_row(lines, anchor, member_idxs, band_of, nbands) -> SummaryRow:
    aline = lines[anchor]
    item = _ITEM.match(aline).group(1)  # type: ignore[union-attr]

    inv_parts: list[str] = []
    pay_parts: list[str] = []
    desc_parts: list[str] = []
    for li in member_idxs:
        ln = lines[li]
        spans = _money_spans(ln)
        money_left = min((st for st, _ in spans), default=len(ln))
        am = _ITEM.match(ln)
        start = am.end() if (li == anchor and am) else 0
        seg = ln[start:money_left]
        for cell in (c.strip() for c in re.split(r"\s{2,}", seg.strip()) if c.strip()):
            if _is_vendor(cell):
                pay_parts.append(cell)
            elif any(ch.isdigit() for ch in cell) or cell.lower() in ("retention",):
                inv_parts.append(cell)
            elif any(ch.isalpha() for ch in cell):
                desc_parts.append(cell)

    # money values on the anchor line, assigned to columns by band
    by_band: dict[int, Decimal] = {}
    for st, v in _money_spans(aline):
        by_band[band_of(st)] = v
    due = by_band.get(nbands - 1)
    if due is None and _money_spans(aline):
        due = _money_spans(aline)[-1][1]
    inv_amt = by_band.get(0) if nbands >= 3 else None
    # a 2-token row with a value only in the retainage band is a retention-only row (inv blank)
    if nbands >= 3 and inv_amt is None and 1 in by_band:
        inv_amt = None

    retainage = None
    if due is not None:
        base = inv_amt if inv_amt is not None else Decimal("0")
        retainage = base - due  # signed: negative ⇒ release

    confidence = _confidence(member_idxs, inv_amt, retainage, due, aline, band_of)
    invoice = " ".join(inv_parts) or None
    payable = " ".join(pay_parts) or None
    desc = " ".join(desc_parts) or None
    raw = " ⏎ ".join(lines[li].strip() for li in member_idxs)[:500]
    return SummaryRow(
        item_code=item,
        invoice_no=(invoice[:64] if invoice else None),
        payable_to=(payable[:255] if payable else None),
        description=(desc[:255] if desc else None),
        inv_amount=inv_amt,
        retainage=retainage,
        amount_due=due,
        row_confidence=confidence,
        raw_text=raw,
    )


def _confidence(member_idxs, inv_amt, retainage, due, aline, band_of) -> str:
    if due is None:
        return UNRECOVERABLE
    # cross-check the printed retainage glyph (band 1) against the derived value
    spans = _money_spans(aline)
    printed_ret = None
    for st, v in spans:
        if band_of(st) == 1:
            printed_ret = v
    tie_ok = retainage is None or printed_ret is None or abs(abs(retainage) - printed_ret) <= CENT
    if not tie_ok:
        return NEEDS_REVIEW
    return EXACT if len(member_idxs) == 1 else RECONSTRUCTED


# ──────────────────────────── PDF orchestration ────────────────────────────

_PDFTOTEXT = "pdftotext"


def _table_text(pdf_path: Path, page: int) -> str:
    try:
        proc = subprocess.run(
            [_PDFTOTEXT, "-table", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
            capture_output=True, check=True,
        )
    except FileNotFoundError as e:  # pragma: no cover - environment guard
        raise PdfExtractError(f"{_PDFTOTEXT} not found on PATH") from e
    except subprocess.CalledProcessError as e:  # pragma: no cover
        raise PdfExtractError(f"pdftotext failed on page {page}: {e.stderr!r}") from e
    return proc.stdout.decode("utf-8", errors="replace")


def _page_count(pdf_path: Path) -> int:
    try:
        proc = subprocess.run(
            ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return 0
    for line in proc.stdout.splitlines():
        if line.lower().startswith("pages:"):
            return int(line.split()[-1])
    return 0


def _is_summary_page(text: str) -> bool:
    return "PAYABLE TO" in text and "AMOUNT DUE" in text and "RETAINAGE" in text


def _continues_summary(text: str) -> bool:
    """A summary continuation page: item-coded money rows, no foreign section header."""
    if any(h in text for h in ("Budget Reallocation", "CONTINUATION SHEET",
                               "APPLICATION AND CERTIFICATION", "DRAW REQUEST FORM")):
        return False
    return any(_ITEM.match(ln) and _money_spans(ln) for ln in text.splitlines())


def find_summary_pages(pdf_path: Path, scan_limit: int = 30) -> tuple[int, ...]:
    """Locate the summary table dynamically: the header page plus any item-row continuation pages
    (no hard-coded page numbers; CHUNK_7 hard-coded (9,10) and truncated longer summaries)."""
    n = _page_count(pdf_path) or scan_limit
    start = None
    for p in range(1, min(n, scan_limit) + 1):
        if _is_summary_page(_table_text(pdf_path, p)):
            start = p
            break
    if start is None:
        return ()
    pages = [start]
    p = start + 1
    while p <= n:
        text = _table_text(pdf_path, p)
        if _is_summary_page(text) or _continues_summary(text):
            pages.append(p)
            if "Total This Draw" in text:  # totals row ends the summary
                break
            p += 1
        else:
            break
    return tuple(pages)


def extract_summary_table(pdf_path: Path, pages: tuple[int, ...] | None = None) -> TableExtract:
    """Extract the full summary table from the PDF (dynamic page detection by default)."""
    pages = pages or find_summary_pages(pdf_path)
    rows: list[SummaryRow] = []
    totals = SummaryTotals()
    notes: list[str] = []
    for p in pages:
        page_rows, page_totals = parse_table_page(_table_text(pdf_path, p))
        rows.extend(page_rows)
        if page_totals.amount_due_total is not None:
            totals = page_totals
    if not pages:
        notes.append("no summary page found")
    return TableExtract(rows=rows, totals=totals, pages=pages, notes=notes)
