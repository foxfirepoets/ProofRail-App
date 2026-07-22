"""OCR / intake draft tests. JSON path is DB-free; the real-PDF path is integration."""
from __future__ import annotations

import os

import pytest

from app.payments.ocr import OcrError, bill_draft_from_json


def test_json_draft_maps_canonical_fields():
    draft = bill_draft_from_json(
        {
            "invoice": {
                "company_id": "co-1",
                "vendor_id": "v-1",
                "invoice_number": "INV-9",
                "po_ref": "PO-2",
                "amount": "1500.25",
                "line_items": [{"amount": 1500.25}],
            }
        }
    )
    assert draft["company_id"] == "co-1"
    assert draft["amount"] == 1500.25
    assert draft["line_items"] == [{"amount": 1500.25}]
    assert draft["source"] == "json"


def test_json_draft_accepts_bare_invoice():
    draft = bill_draft_from_json({"company_id": "co-1", "vendor_id": "v-1", "amount": 10})
    assert draft["company_id"] == "co-1"
    assert draft["amount"] == 10.0


def test_json_draft_requires_invoice_object():
    with pytest.raises(OcrError):
        bill_draft_from_json({"invoice": "not-an-object"})


@pytest.mark.integration
def test_pdf_extraction_with_invoice2data(tmp_path):
    """Real invoice2data extraction over a synthetic PDF (needs OCR backends installed)."""
    from app.payments.ocr import bill_draft_from_pdf

    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "sample_invoice.pdf")
    if not os.path.exists(fixture):
        pytest.skip("sample_invoice.pdf fixture not present")
    draft = bill_draft_from_pdf(fixture, company_id="co-1", vendor_id="v-1")
    assert draft["source"] == "invoice2data"
    assert draft["amount"] is not None
