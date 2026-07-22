"""VerifyAPI gate (Gate 3) — a SELF-CONTAINED, in-process verdict.

This is the in-process model of ``runProofProduct({product:'verifyapi'})``: it
NEVER calls a network service or a JS package. Given a write subject (the approved
bill plus the AIVS chain head), it computes a *deterministic* verdict and, on a
VERIFIED + low-risk result, seals an ``independent_attestor_signature`` so the
autonomous-execution step can prove the gate ran independently of the workflow.

``SWARMSYNC_PROOF_MODE`` selects the seam: ``in_process`` (default, implemented
here) or ``rest`` (would POST ``{API_BASE_URL}/api/verify`` with the self-issued
``sa_*`` key). Per the fail-closed invariant we ALWAYS evaluate in-process and
never block on the network; ``rest`` is a documented future seam only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# Verdict vocabulary mirrors the hosted VerifyAPI product.
VERIFIED = "VERIFIED"
COMPLETE = "COMPLETE"
NOT_READY = "NOT_READY"
RISK_LOW = "low"
RISK_HIGH = "high"

_ADVANCING_STATES = frozenset({VERIFIED, COMPLETE})
# An approved bill is the only status the gate will advance.
_REQUIRED_STATUS = "approved"


@dataclass
class VerifyVerdict:
    """Deterministic VerifyAPI result. ``advance`` is the single source of truth."""

    status: str
    risk: str
    reasons: list[str]
    proof_hash: str
    subject_id: str | None = None
    independent_attestor_signature: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def advance(self) -> bool:
        """True ONLY on VERIFIED/COMPLETE + low risk (fail-closed otherwise)."""
        return self.status in _ADVANCING_STATES and self.risk == RISK_LOW


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _attestor_key() -> bytes:
    """Self-issued service-account key acts as the independent attestor secret."""
    return os.environ.get("SWARMSYNC_SA_API_KEY", "sa_in_process").encode("utf-8")


def _proof_hash(subject: Mapping[str, Any]) -> str:
    canonical = json.dumps(subject, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _attest(proof_hash: str) -> str:
    """HMAC-SHA256 over the verdict's proof hash — the independent attestor sig."""
    return hmac.new(_attestor_key(), proof_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def run_verifyapi(subject: Mapping[str, Any]) -> VerifyVerdict:
    """Evaluate the write subject and return a deterministic VerifyAPI verdict.

    ``subject`` is expected to carry: ``bill_id``, ``status``, ``amount``,
    ``vendor_id``, and ``aivs_head`` (the validated AIVS chain head). Any missing
    precondition, a non-approved status, a non-positive amount, or a genesis/empty
    AIVS head yields a non-advancing verdict (``NOT_READY`` / high risk).
    """
    reasons: list[str] = []

    status = str(subject.get("status") or "")
    if status != _REQUIRED_STATUS:
        reasons.append(f"bill status is {status!r}, expected {_REQUIRED_STATUS!r}")

    if not subject.get("vendor_id"):
        reasons.append("missing vendor_id")

    amount = _to_decimal(subject.get("amount"))
    if amount is None:
        reasons.append("amount is not a number")
    elif amount <= 0:
        reasons.append("amount must be positive")

    aivs_head = str(subject.get("aivs_head") or "")
    if not aivs_head or set(aivs_head) == {"0"}:
        reasons.append("AIVS chain head is empty or genesis (chain not yet sealed)")

    proof_hash = _proof_hash(subject)
    advancing = not reasons
    verdict_status = VERIFIED if advancing else NOT_READY
    risk = RISK_LOW if advancing else RISK_HIGH
    signature = _attest(proof_hash) if advancing else None

    return VerifyVerdict(
        status=verdict_status,
        risk=risk,
        reasons=reasons,
        proof_hash=proof_hash,
        subject_id=subject.get("bill_id"),
        independent_attestor_signature=signature,
        payload={
            "mode": os.environ.get("SWARMSYNC_PROOF_MODE", "in_process"),
            "product": "verifyapi",
            "reasons": reasons,
            "risk": risk,
            "status": verdict_status,
        },
    )


def verdict_to_bundle(verdict: VerifyVerdict) -> dict[str, Any]:
    """Shape a VerifyAPI verdict into a ``proof_bundles`` row (kind='verifyapi')."""
    return {
        "kind": "verifyapi",
        "vcap_state": "verified" if verdict.advance else "not_ready",
        "proof_hash": verdict.proof_hash,
        "proof_signature": verdict.independent_attestor_signature,
        "passed": verdict.advance,
        "payload": {
            **verdict.payload,
            "subject_id": verdict.subject_id,
            "independent_attestor_signature": verdict.independent_attestor_signature,
        },
    }
