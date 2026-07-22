"""Request schemas for the gated intent pipeline.

Validation is performed explicitly inside the router (not via FastAPI's default
body coercion) so failures return the project ``{"data","error","meta"}`` envelope
with a ``400`` rather than FastAPI's default ``{"detail": ...}`` shape.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class IntentIn(BaseModel):
    """An AI accounting intent submitted to ``POST /intents``."""

    intent: str = Field(min_length=1, max_length=48)
    company_id: str = Field(min_length=1)
    vendor_id: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    idempotency_key: str | None = None
    raw_extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intent", "company_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class ApprovalIn(BaseModel):
    """A human approve/reject decision at the commit boundary."""

    decision: Literal["approve", "reject"]
    approver: str = Field(min_length=1)
