"""Invoice intake → canonical bill DRAFT.

Two paths feed the same canonical draft shape consumed by InvoiceProof:

* ``bill_draft_from_pdf`` — invoice2data OCR/extraction over a PDF (vendor, amount,
  line-items, PO). Real PDFs run only on the integration path (needs OCR backends).
* ``bill_draft_from_json`` — a pre-parsed JSON body (already-structured invoice).

A draft NEVER carries raw bank details into persistence; ``bank_details`` (if present)
is kept only transiently for fingerprinting and is not part of the canonical bill.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

INVOICE2DATA_TEMPLATES_DIR_ENV = "INVOICE2DATA_TEMPLATES_DIR"


class OcrError(ValueError):
    """OCR/extraction failed to produce a usable invoice draft (fail-closed)."""

    code = "OCR_FAILED"


def _coerce_amount(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _canonical_draft(
    *,
    company_id: str | None,
    vendor_id: str | None,
    vendor_name: str | None,
    invoice_number: str | None,
    po_ref: str | None,
    amount: float | None,
    line_items: list[dict[str, Any]],
    bank_details: Mapping[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    """The single canonical bill-draft shape. ``bank_details`` stays out of persisted fields."""
    return {
        "company_id": company_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "po_ref": po_ref,
        "amount": amount,
        "line_items": line_items,
        # Transient: consumed by the fingerprinter, never written to the bill record.
        "bank_details": dict(bank_details) if bank_details else None,
        "source": source,
    }


def bill_draft_from_json(body: Mapping[str, Any]) -> dict[str, Any]:
    """Build a canonical draft from a pre-parsed invoice JSON body."""
    if "invoice" in body:
        invoice = body["invoice"]
        if not isinstance(invoice, Mapping):
            raise OcrError("JSON intake requires an 'invoice' object")
    else:
        invoice = body
    line_items = list(invoice.get("line_items") or [])
    return _canonical_draft(
        company_id=invoice.get("company_id"),
        vendor_id=invoice.get("vendor_id"),
        vendor_name=invoice.get("vendor_name"),
        invoice_number=invoice.get("invoice_number"),
        po_ref=invoice.get("po_ref"),
        amount=_coerce_amount(invoice.get("amount")),
        line_items=[dict(li) for li in line_items],
        bank_details=invoice.get("bank_details") if isinstance(invoice.get("bank_details"), Mapping) else None,
        source="json",
    )


def bill_draft_from_pdf(
    pdf_path: str,
    *,
    company_id: str | None = None,
    vendor_id: str | None = None,
    templates_dir: str | None = None,
) -> dict[str, Any]:
    """Extract an invoice draft from a PDF via invoice2data (integration path).

    ``company_id``/``vendor_id`` are supplied by the caller (resolved from the
    authenticated org / vendor master), since OCR yields a vendor *name*, not an id.
    """
    try:
        from invoice2data import extract_data  # type: ignore[import-untyped]
        from invoice2data.extract.loader import read_templates  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - import guarded for integration only
        raise OcrError(f"invoice2data is unavailable: {exc}") from exc

    tdir = templates_dir or os.environ.get(INVOICE2DATA_TEMPLATES_DIR_ENV)
    templates = read_templates(tdir) if tdir and os.path.isdir(tdir) else None

    result = extract_data(pdf_path, templates=templates) if templates else extract_data(pdf_path)
    if not result:
        raise OcrError(f"no invoice fields extracted from {pdf_path!r}")

    line_items = list(result.get("lines") or [])
    return _canonical_draft(
        company_id=company_id,
        vendor_id=vendor_id,
        vendor_name=result.get("issuer"),
        invoice_number=result.get("invoice_number"),
        po_ref=result.get("po_number") or result.get("po_ref"),
        amount=_coerce_amount(result.get("amount")),
        line_items=[dict(li) for li in line_items],
        bank_details=None,
        source="invoice2data",
    )
