"""ATEP trust-tier gate (Gate 4 — bank-change / BEC).

Releasing a PAYMENT_FORM after a detected bank-account change requires the vendor to
be at or above the configured trust tier (default ``TRUSTED``). Below tier ⇒ the
payment is auto-blocked and escalated (``BANK_CHANGE_BLOCKED``); fail-closed.

Tier is derived from the vendor's SwarmScore (0–1000). An unknown/None score maps to
the lowest tier so missing reputation never clears the gate.
"""
from __future__ import annotations

import os

# Lowest → highest. Index position is the comparable rank.
TIER_ORDER: tuple[str, ...] = ("UNTRUSTED", "BASIC", "VERIFIED", "TRUSTED")

# SwarmScore lower-bounds (inclusive) for each tier.
_TIER_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (750, "TRUSTED"),
    (500, "VERIFIED"),
    (250, "BASIC"),
    (0, "UNTRUSTED"),
)

DEFAULT_REQUIRED_TIER = "TRUSTED"
ATEP_REQUIRED_TIER_ENV = "ATEP_REQUIRED_TIER"


def required_tier(override: str | None = None) -> str:
    """Required release tier from arg → env → default. Unknown values fall back to TRUSTED."""
    value = (override or os.environ.get(ATEP_REQUIRED_TIER_ENV) or DEFAULT_REQUIRED_TIER).strip().upper()
    return value if value in TIER_ORDER else DEFAULT_REQUIRED_TIER


def tier_for_score(swarmscore: int | None) -> str:
    """Map a SwarmScore to a trust tier. None / negative ⇒ UNTRUSTED (fail-closed)."""
    if swarmscore is None or swarmscore < 0:
        return "UNTRUSTED"
    for threshold, tier in _TIER_THRESHOLDS:
        if swarmscore >= threshold:
            return tier
    return "UNTRUSTED"


def _rank(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier.upper())
    except ValueError:
        return 0


def tier_meets(tier: str, needed: str) -> bool:
    """True iff ``tier`` is at least as trusted as ``needed``."""
    return _rank(tier) >= _rank(needed)


def evaluate_atep(swarmscore: int | None, *, required: str | None = None) -> dict[str, object]:
    """Decide whether a PAYMENT_FORM may release given the vendor's reputation.

    Returns the tier, the requirement, and an ``allowed`` flag. Callers block +
    escalate when ``allowed`` is False.
    """
    need = required_tier(required)
    tier = tier_for_score(swarmscore)
    return {
        "capability": "PAYMENT_FORM",
        "tier": tier,
        "required_tier": need,
        "swarmscore": swarmscore,
        "allowed": tier_meets(tier, need),
    }
