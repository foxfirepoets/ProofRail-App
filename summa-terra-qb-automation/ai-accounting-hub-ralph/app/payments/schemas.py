"""Request models for the AP intake endpoint.

Bank details, when present, are accepted only to compute a fingerprint; they are never
persisted or echoed. The JSON path mirrors the canonical bill-draft fields.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineItemIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    amount: float = 0.0


class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company_id: str = Field(min_length=1)
    vendor_id: str = Field(min_length=1)
    invoice_number: str | None = None
    po_ref: str | None = None
    amount: float = Field(ge=0)
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    # Transient: used only for the bank fingerprint, never stored/logged raw.
    bank_details: dict[str, Any] | None = None


class IntakeJsonIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    invoice: InvoiceIn
