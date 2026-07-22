"""Agent capability tokens (ATXN ``allowed_actions``) — fail-closed, HMAC-signed.

A capability token scopes which actions an agent may submit to ``POST /intents``.
Tokens are HMAC-SHA256 signed with ``AGENT_CAPABILITY_SIGNING_SECRET`` (read from
the environment, never hard-coded). If the secret is unset the verifier DENIES by
default. An action outside the token's ``allowed_actions`` raises
``CapabilityError`` — the router maps that to ``403`` and NO workflow is started.

Wire format (compact, dependency-free):  ``<b64url(payload_json)>.<hmac_hex>``
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from collections.abc import Iterable
from typing import Any

CAPABILITY_SECRET_ENV = "AGENT_CAPABILITY_SIGNING_SECRET"


class CapabilityError(Exception):
    """Capability check failed (missing/invalid token, or action out of scope)."""

    code = "FORBIDDEN"


def _secret(override: str | None = None) -> str | None:
    if override:
        return override
    value = os.environ.get(CAPABILITY_SECRET_ENV, "").strip()
    return value or None


def _sign(b64_payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()


def mint_capability(
    *,
    agent_id: str,
    allowed_actions: Iterable[str],
    company_id: str | None = None,
    secret: str | None = None,
) -> str:
    """Issue a signed capability token. Used by agents/tests; default-deny if unset."""
    sec = _secret(secret)
    if sec is None:
        raise CapabilityError("capability signing secret is not configured")
    payload = {
        "agent_id": agent_id,
        "allowed_actions": sorted(set(allowed_actions)),
        "company_id": company_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    return f"{b64}.{_sign(b64, sec)}"


def verify_capability(token: str, action: str, *, secret: str | None = None) -> dict[str, Any]:
    """Verify signature + scope. Raises ``CapabilityError`` on any failure (fail-closed)."""
    sec = _secret(secret)
    if sec is None:
        raise CapabilityError("capability signing secret is not configured (default deny)")
    if not token:
        raise CapabilityError("missing capability token")
    try:
        b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise CapabilityError("malformed capability token") from exc
    if not hmac.compare_digest(_sign(b64, sec), signature):
        raise CapabilityError("invalid capability token signature")
    try:
        claims = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")))
    except (ValueError, json.JSONDecodeError) as exc:
        raise CapabilityError("unreadable capability payload") from exc
    if action not in claims.get("allowed_actions", []):
        raise CapabilityError(f"action '{action}' is not within the capability scope")
    return claims
