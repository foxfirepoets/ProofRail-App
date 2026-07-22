"""InvoiceProof — the AP money-movement gate (Gate 1), self-contained & in-process.

Models ``runProofProduct({product:'invoiceproof', evidenceInputs})`` with NO network
or JS call. Given an evidence bundle (the candidate invoice plus prior context loaded
from the canonical store), it runs every rule and returns a verdict.

``riskLevel`` is the highest finding severity. A CRITICAL risk level (i.e. any CRITICAL
finding) BLOCKS to the human queue (``INVOICEPROOF_FAILED``); ``passed`` is True only
when nothing critical fired. Fail-closed: malformed evidence raises before a verdict.

Evidence shape (all keys optional except ``invoice``)::

    {
      "invoice": {"company_id","vendor_id","invoice_number","po_ref","amount",
                  "line_items":[{"amount": ...}, ...]},
      "po": {"po_ref","authorized_amount"},
      "existing_bills": [{"company_id","invoice_number","po_ref","amount"}, ...],
      "payment_history": [{"vendor_id","amount","paid_at"}, ...],
    }

``existing_bills`` / ``payment_history`` are pre-scoped by ``company_id`` by the loader,
but every duplicate rule re-checks ``company_id`` so the same invoice sent to two
entities is still caught per-entity.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

# Severity ranks (low → high).
SEVERITY_ORDER: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# Cent tolerance for money equality (rounding noise, not real mismatch).
_CENT = Decimal("0.01")

# A "recent" duplicate payment looks back this many entries of supplied history.
RECENT_HISTORY_WINDOW = 50


class InvoiceProofError(ValueError):
    """Evidence could not be evaluated (malformed/uncoercible) — fail-closed."""

    code = "INVOICEPROOF_INVALID"


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_CENT)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvoiceProofError(f"un-coercible money value: {value!r}") from exc


def _finding(rule: str, severity: str, message: str, **evidence: Any) -> dict[str, Any]:
    return {"rule": rule, "severity": severity, "message": message, "evidence": evidence}


def _same_invoice_key(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Two records are the 'same invoice' when same company + same invoice_number (or PO)."""
    if str(a.get("company_id")) != str(b.get("company_id")):
        return False
    inv_a, inv_b = a.get("invoice_number"), b.get("invoice_number")
    if inv_a and inv_b:
        return str(inv_a) == str(inv_b)
    po_a, po_b = a.get("po_ref"), b.get("po_ref")
    return bool(po_a and po_b and str(po_a) == str(po_b))


# -- individual rules ---------------------------------------------------------


def _rule_duplicates(inv: Mapping[str, Any], existing: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """EXACT_DUPLICATE and MODIFIED_DUPLICATE against already-recorded bills (same company)."""
    out: list[dict[str, Any]] = []
    amount = _money(inv.get("amount", 0))
    for prior in existing:
        if not _same_invoice_key(inv, prior):
            continue
        prior_amount = _money(prior.get("amount", 0))
        if abs(prior_amount - amount) <= _CENT:
            out.append(
                _finding(
                    "EXACT_DUPLICATE",
                    "CRITICAL",
                    "Invoice already recorded with the same number and amount for this company.",
                    invoice_number=inv.get("invoice_number"),
                    amount=str(amount),
                )
            )
        else:
            out.append(
                _finding(
                    "MODIFIED_DUPLICATE",
                    "CRITICAL",
                    "Invoice number already recorded but the amount differs (possible tampering).",
                    invoice_number=inv.get("invoice_number"),
                    amount=str(amount),
                    prior_amount=str(prior_amount),
                )
            )
    return out


def _rule_recent_history(inv: Mapping[str, Any], history: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """RECENT_DUPLICATE_IN_PAYMENT_HISTORY — same vendor + amount already paid recently."""
    amount = _money(inv.get("amount", 0))
    vendor = str(inv.get("vendor_id"))
    for paid in history[:RECENT_HISTORY_WINDOW]:
        if str(paid.get("vendor_id")) != vendor:
            continue
        if abs(_money(paid.get("amount", 0)) - amount) <= _CENT:
            return [
                _finding(
                    "RECENT_DUPLICATE_IN_PAYMENT_HISTORY",
                    "CRITICAL",
                    "A payment of the same amount to this vendor exists in recent payment history.",
                    vendor_id=vendor,
                    amount=str(amount),
                    paid_at=paid.get("paid_at"),
                )
            ]
    return []


def _rule_missing_po(inv: Mapping[str, Any]) -> list[dict[str, Any]]:
    """MISSING_PO_REFERENCE — no PO reference on the invoice."""
    if not inv.get("po_ref"):
        return [
            _finding(
                "MISSING_PO_REFERENCE",
                "MEDIUM",
                "Invoice has no purchase-order reference.",
            )
        ]
    return []


def _rule_po_amount(inv: Mapping[str, Any], po: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """PO_AMOUNT_EXCEEDED — invoice amount exceeds the PO's authorized amount."""
    if not po or po.get("authorized_amount") is None:
        return []
    amount = _money(inv.get("amount", 0))
    authorized = _money(po.get("authorized_amount", 0))
    if amount > authorized + _CENT:
        return [
            _finding(
                "PO_AMOUNT_EXCEEDED",
                "CRITICAL",
                "Invoice amount exceeds the authorized purchase-order amount.",
                amount=str(amount),
                authorized_amount=str(authorized),
            )
        ]
    return []


def _rule_line_item_math(inv: Mapping[str, Any]) -> list[dict[str, Any]]:
    """LINE_ITEM_MATH_ERROR — line-item total does not reconcile to the invoice amount."""
    line_items = inv.get("line_items")
    if not line_items:
        return []
    total = sum((_money(li.get("amount", 0)) for li in line_items), Decimal("0.00"))
    amount = _money(inv.get("amount", 0))
    if abs(total - amount) > _CENT:
        return [
            _finding(
                "LINE_ITEM_MATH_ERROR",
                "CRITICAL",
                "Sum of line items does not equal the invoice amount.",
                line_item_total=str(total),
                amount=str(amount),
            )
        ]
    return []


def _rule_round_dollar(inv: Mapping[str, Any]) -> list[dict[str, Any]]:
    """ROUND_DOLLAR_AMOUNT — suspiciously round amount (whole hundreds), a fraud signal."""
    amount = _money(inv.get("amount", 0))
    if amount > 0 and amount % Decimal("100") == 0:
        return [
            _finding(
                "ROUND_DOLLAR_AMOUNT",
                "LOW",
                "Invoice amount is a round-dollar figure (common in fraudulent/test invoices).",
                amount=str(amount),
            )
        ]
    return []


# -- orchestration ------------------------------------------------------------


def _risk_level(findings: list[dict[str, Any]]) -> str:
    level = "LOW"
    for f in findings:
        if SEVERITY_ORDER.index(f["severity"]) > SEVERITY_ORDER.index(level):
            level = f["severity"]
    return level


def run_invoiceproof(evidence_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Run the full InvoiceProof ruleset. Returns the verdict; never raises on rule firing.

    ``passed`` is False (blocked, ``INVOICEPROOF_FAILED``) iff ``riskLevel == CRITICAL``.
    Raises ``InvoiceProofError`` only for structurally invalid evidence (fail-closed).
    """
    invoice = evidence_inputs.get("invoice")
    if not isinstance(invoice, Mapping):
        raise InvoiceProofError("evidence_inputs.invoice is required")

    existing = list(evidence_inputs.get("existing_bills") or [])
    history = list(evidence_inputs.get("payment_history") or [])
    po = evidence_inputs.get("po")

    findings: list[dict[str, Any]] = []
    findings += _rule_duplicates(invoice, existing)
    findings += _rule_recent_history(invoice, history)
    findings += _rule_missing_po(invoice)
    findings += _rule_po_amount(invoice, po if isinstance(po, Mapping) else None)
    findings += _rule_line_item_math(invoice)
    findings += _rule_round_dollar(invoice)

    risk_level = _risk_level(findings)
    blocked = risk_level == "CRITICAL"
    critical_rules = sorted({f["rule"] for f in findings if f["severity"] == "CRITICAL"})

    return {
        "product": "invoiceproof",
        "passed": not blocked,
        "riskLevel": risk_level,
        "blocked": blocked,
        "reason": "INVOICEPROOF_FAILED" if blocked else None,
        "criticalRules": critical_rules,
        "findings": findings,
    }
