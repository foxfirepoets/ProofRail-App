"""VCAP Full Bundle proof for payment decisions (NOT AIVS-Micro).

Every payment decision is sealed with a VCAP proof:

    proof_signature = HMAC-SHA256(canonical_json(proof_body), VCAP_SHARED_SECRET)

``proof_hash`` is a plain SHA-256 commitment over the same canonical body, so the
bundle is tamper-evident even without the shared secret. The secret is read from the
environment (never hard-coded); if it is unset, signing is refused — fail-closed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

VCAP_SHARED_SECRET_ENV = "VCAP_SHARED_SECRET"
VCAP_STATE_PENDING = "PENDING"
VCAP_STATE_RELEASED = "RELEASED"


class VcapSecretMissing(Exception):
    """VCAP_SHARED_SECRET is not configured — cannot sign a Full Bundle (default deny)."""

    code = "VCAP_SECRET_MISSING"


def canonical_json(body: Any) -> str:
    """Deterministic JSON (sorted keys, no whitespace) — the exact bytes we sign/hash."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _secret(override: str | None = None) -> str:
    value = (override or os.environ.get(VCAP_SHARED_SECRET_ENV) or "").strip()
    if not value:
        raise VcapSecretMissing("VCAP_SHARED_SECRET is not set")
    return value


def proof_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def sign_proof(body: dict[str, Any], *, secret: str | None = None) -> str:
    """HMAC-SHA256 the canonical proof body with the VCAP shared secret."""
    key = _secret(secret)
    return hmac.new(key.encode("utf-8"), canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(body: dict[str, Any], signature: str, *, secret: str | None = None) -> bool:
    """Constant-time check that ``signature`` matches the body under the shared secret."""
    try:
        expected = sign_proof(body, secret=secret)
    except VcapSecretMissing:
        return False
    return hmac.compare_digest(expected, signature)


def build_vcap_bundle(
    proof_body: dict[str, Any],
    *,
    passed: bool,
    secret: str | None = None,
    vcap_state: str = VCAP_STATE_PENDING,
) -> dict[str, Any]:
    """Assemble a ``ProofBundle``-shaped dict (kind='invoiceproof') with a Full Bundle signature.

    Signing always runs — including on a BLOCK decision — so every decision carries a
    verifiable proof. Raises ``VcapSecretMissing`` if the secret is absent (fail-closed).
    """
    body_hash = proof_hash(proof_body)
    signature = sign_proof(proof_body, secret=secret)
    return {
        "kind": "invoiceproof",
        "vcap_state": vcap_state,
        "proof_hash": body_hash,
        "proof_signature": signature,
        "passed": passed,
        "payload": {"bundle_type": "VCAP_FULL", "proof_body": proof_body},
    }
