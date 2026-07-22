"""InvoiceProof Gate 1 rule coverage — DB-free. Each rule fires on a crafted input."""
from __future__ import annotations

import pytest

from app.payments.invoiceproof import InvoiceProofError, run_invoiceproof


def _clean_invoice(**over):
    inv = {
        "company_id": "co-1",
        "vendor_id": "v-1",
        "invoice_number": "INV-1001",
        "po_ref": "PO-555",
        "amount": 1234.56,
        "line_items": [{"amount": 1000.00}, {"amount": 234.56}],
    }
    inv.update(over)
    return inv


def test_happy_path_clean_invoice_low_and_passes():
    verdict = run_invoiceproof({"invoice": _clean_invoice()})
    assert verdict["passed"] is True
    assert verdict["riskLevel"] == "LOW"
    assert verdict["findings"] == []
    assert verdict["reason"] is None


def test_exact_duplicate_blocks():
    inv = _clean_invoice()
    existing = [{"company_id": "co-1", "invoice_number": "INV-1001", "amount": 1234.56}]
    verdict = run_invoiceproof({"invoice": inv, "existing_bills": existing})
    assert verdict["passed"] is False
    assert verdict["riskLevel"] == "CRITICAL"
    assert "EXACT_DUPLICATE" in verdict["criticalRules"]


def test_modified_duplicate_blocks():
    inv = _clean_invoice()
    existing = [{"company_id": "co-1", "invoice_number": "INV-1001", "amount": 9999.00}]
    verdict = run_invoiceproof({"invoice": inv, "existing_bills": existing})
    assert "MODIFIED_DUPLICATE" in verdict["criticalRules"]
    assert verdict["passed"] is False


def test_duplicate_scoped_by_company_id():
    # Same invoice, DIFFERENT company → not a duplicate for this entity.
    inv = _clean_invoice(company_id="co-1")
    existing = [{"company_id": "co-2", "invoice_number": "INV-1001", "amount": 1234.56}]
    verdict = run_invoiceproof({"invoice": inv, "existing_bills": existing})
    assert verdict["criticalRules"] == []
    assert verdict["passed"] is True


def test_recent_duplicate_in_payment_history_blocks():
    inv = _clean_invoice()
    history = [{"vendor_id": "v-1", "amount": 1234.56, "paid_at": "2026-06-01"}]
    verdict = run_invoiceproof({"invoice": inv, "payment_history": history})
    assert "RECENT_DUPLICATE_IN_PAYMENT_HISTORY" in verdict["criticalRules"]
    assert verdict["passed"] is False


def test_missing_po_reference_medium_does_not_block():
    inv = _clean_invoice(po_ref=None)
    verdict = run_invoiceproof({"invoice": inv})
    rules = {f["rule"] for f in verdict["findings"]}
    assert "MISSING_PO_REFERENCE" in rules
    assert verdict["riskLevel"] == "MEDIUM"
    assert verdict["passed"] is True


def test_po_amount_exceeded_blocks():
    inv = _clean_invoice(amount=5000.00, line_items=[{"amount": 5000.00}])
    po = {"po_ref": "PO-555", "authorized_amount": 1000.00}
    verdict = run_invoiceproof({"invoice": inv, "po": po})
    assert "PO_AMOUNT_EXCEEDED" in verdict["criticalRules"]
    assert verdict["passed"] is False


def test_line_item_math_error_blocks():
    inv = _clean_invoice(amount=1234.56, line_items=[{"amount": 100.00}, {"amount": 100.00}])
    verdict = run_invoiceproof({"invoice": inv})
    assert "LINE_ITEM_MATH_ERROR" in verdict["criticalRules"]
    assert verdict["passed"] is False


def test_round_dollar_amount_low_signal():
    inv = _clean_invoice(amount=2000.00, po_ref="PO-9", line_items=[{"amount": 2000.00}])
    verdict = run_invoiceproof({"invoice": inv})
    rules = {f["rule"] for f in verdict["findings"]}
    assert "ROUND_DOLLAR_AMOUNT" in rules
    assert verdict["passed"] is True  # LOW signal alone does not block


def test_malformed_evidence_fails_closed():
    with pytest.raises(InvoiceProofError):
        run_invoiceproof({})  # no invoice


def test_uncoercible_amount_fails_closed():
    with pytest.raises(InvoiceProofError):
        run_invoiceproof({"invoice": _clean_invoice(amount="not-a-number")})
