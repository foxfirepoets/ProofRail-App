"""Bank-detail fingerprinting (BEC / Gate 4 support).

We NEVER store or log raw bank fields. A vendor's banking identity is reduced to a
SHA-256 ``bank_fingerprint`` over *normalised* details. Two payees with the same
account/routing/IBAN produce the same fingerprint; any change flips it, which is the
only signal the bank-change gate ever sees. The raw dict is consumed here and never
returned, persisted, or echoed.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

# Fields that identify a bank account. Order is irrelevant — we sort canonically.
_BANK_FIELDS: tuple[str, ...] = (
    "account_number",
    "routing_number",
    "iban",
    "swift",
    "sort_code",
    "bank_name",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalise_value(value: Any) -> str:
    """Lower-case and strip every non-alphanumeric char so formatting can't fork a fingerprint."""
    return _NON_ALNUM.sub("", str(value).lower())


def normalise_bank_details(details: Mapping[str, Any]) -> str:
    """Build the canonical, raw-free string the fingerprint hashes.

    Only known bank fields are considered; unknown keys are ignored so stray PII
    (e.g. a memo line) can't leak into the commitment.
    """
    parts = []
    for field in _BANK_FIELDS:
        if field in details and details[field] not in (None, ""):
            parts.append(f"{field}={_normalise_value(details[field])}")
    return "|".join(sorted(parts))


def compute_bank_fingerprint(details: Mapping[str, Any]) -> str | None:
    """Return the SHA-256 hex fingerprint of bank details, or ``None`` if none supplied.

    The input dict is read once and discarded; nothing raw escapes this function.
    """
    canonical = normalise_bank_details(details)
    if not canonical:
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_changed(stored: str | None, fresh: str | None) -> bool:
    """A bank-change is a non-null fresh fingerprint that differs from the stored one.

    A first-seen vendor (no stored fingerprint) is NOT a change. Missing fresh
    details (nothing to compare) is NOT a change.
    """
    if fresh is None or stored is None:
        return False
    return stored != fresh
