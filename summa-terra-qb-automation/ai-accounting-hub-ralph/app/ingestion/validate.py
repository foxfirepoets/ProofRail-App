"""Validate a parsed draw: totals tie-out, retainage math, duplicate invoices (CHUNK_7).

Pure over ParsedDraw. The document's summary *totals row* is the authoritative figure; per-line
parse completeness is reconciled against it and any shortfall is reported (never hidden). Money
rule (confirmed from Draw #29): amount_due = inv_amount − retainage, retainage signed
(negative = retention release).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.ingestion.normalize import normalize_name
from app.ingestion.parser import ParsedDraw

CENT = Decimal("0.01")


@dataclass(frozen=True)
class DrawException:
    code: str
    detail: str
    severity: str = "exception"  # "exception" (hard) | "warning" (review)


def validate_draw(draw: ParsedDraw) -> list[DrawException]:
    out: list[DrawException] = []
    h = draw.header

    # 1. Totals tie-out: summary amount-due column total == Total This Draw.
    if h.total_this_draw is None:
        out.append(DrawException("MISSING_TOTAL", "Total This Draw not found in header"))
    elif h.summary_amount_due_total is not None and h.summary_amount_due_total != h.total_this_draw:
        out.append(DrawException(
            "TOTAL_TIE_OUT_MISMATCH",
            f"summary amount-due total {h.summary_amount_due_total} != Total This Draw {h.total_this_draw}",
        ))

    # 2. Totals-row retainage math: amount_due = inv_amount - retainage.
    inv_t, ret_t, due_t = h.summary_inv_total, h.summary_retainage_total, h.summary_amount_due_total
    if inv_t is not None and ret_t is not None and due_t is not None:
        expected = inv_t - ret_t
        if abs(expected - due_t) > CENT:
            out.append(DrawException(
                "RETAINAGE_MATH_MISMATCH",
                f"inv {inv_t} - retainage {ret_t} = {expected} != amount_due {due_t}",
            ))

    # 3. Per-line retainage math (only where all three are present).
    for ln in draw.lines:
        inv, ret, due = ln.inv_amount, ln.retainage, ln.amount_due
        if inv is not None and ret is not None and due is not None:
            if abs((inv - ret) - due) > CENT:
                out.append(DrawException(
                    "LINE_RETAINAGE_MISMATCH",
                    f"line {ln.line_no} ({ln.item_code}): {inv} - {ret} != {due}",
                ))

    # 4. Duplicate invoice — only a *true* duplicate (same vendor + invoice + amount) is an
    # exception. One vendor invoice allocated across several cost codes (different amounts) is a
    # normal draw split, not a double-charge, so the amount is part of the key.
    seen: dict[tuple[str, str, str], int] = {}
    for ln in draw.lines:
        if ln.invoice_no and ln.payable_to and ln.amount_due is not None:
            key = (normalize_name(ln.payable_to), ln.invoice_no.strip().upper(), str(ln.amount_due))
            if key in seen:
                out.append(DrawException(
                    "DUPLICATE_INVOICE",
                    f"invoice {ln.invoice_no!r} for {ln.payable_to} repeats at the same "
                    f"amount {ln.amount_due} (lines {seen[key]} and {ln.line_no})",
                ))
            else:
                seen[key] = ln.line_no

    # 5. Missing invoice numbers → review warnings, not hard failures.
    for ln in draw.lines:
        if ln.amount_due is not None and not ln.invoice_no:
            out.append(DrawException(
                "MISSING_INVOICE", f"line {ln.line_no} ({ln.item_code}) has no invoice number",
                severity="warning",
            ))

    # 6. Parse-completeness reconciliation (honest: report any shortfall vs authoritative total).
    parsed_due = sum((ln.amount_due for ln in draw.lines if ln.amount_due is not None), Decimal("0"))
    if h.summary_amount_due_total is not None and abs(parsed_due - h.summary_amount_due_total) > CENT:
        out.append(DrawException(
            "PARSE_INCOMPLETE",
            f"sum of parsed line amount_due {parsed_due} != authoritative summary total "
            f"{h.summary_amount_due_total} (delta {h.summary_amount_due_total - parsed_due}); "
            f"unparsed/partial lines need review",
            severity="warning",
        ))

    return out


def has_hard_exceptions(exceptions: list[DrawException]) -> bool:
    return any(e.severity == "exception" for e in exceptions)
