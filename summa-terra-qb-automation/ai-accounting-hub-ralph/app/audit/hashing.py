"""Pure-stdlib AIVS hashing + redaction primitives (no DB, no third-party deps).

``row_hash`` follows the AIVS spec header:

    SHA-256("{row_id}:{session_id}:{action_type}:{tool_name}:{cost_cents}:"
            "{timestamp}:{prev_hash}:{inputs_digest}:{outputs_digest}")

The seven-field prefix is verbatim from the spec; ``inputs_digest`` and
``outputs_digest`` are SHA-256 commitments over the *redacted* request/response
bodies so that tampering with ``inputs_json`` (or ``outputs_json``) also breaks
the chain, while raw bank fields / secrets never enter the hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# The first row in a session links to 64 zeros.
GENESIS_HASH = "0" * 64

# A key is redacted if its name (case-insensitive) contains any of these.
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "bank",
    "account",
    "routing",
    "secret",
    "password",
    "token",
    "ssn",
    "key",
)

REDACTED = "[REDACTED]"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(sub in lowered for sub in SENSITIVE_KEY_SUBSTRINGS)


def redact(value: Any) -> Any:
    """Recursively replace values of sensitive keys with ``[REDACTED]``.

    Operates on plain JSON-compatible structures (dict / list / scalar) and
    never mutates the input.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _is_sensitive(str(k)):
                out[str(k)] = REDACTED
            else:
                out[str(k)] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def _canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no insignificant whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    """SHA-256 over the redacted, canonicalised body (hex)."""
    canonical = _canonical_json(redact(value if value is not None else {}))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_row_hash(
    *,
    row_id: int,
    session_id: str,
    action_type: str,
    tool_name: str | None,
    cost_cents: int,
    timestamp: str,
    prev_hash: str,
    inputs: Any = None,
    outputs: Any = None,
) -> str:
    """Compute the canonical ``row_hash`` for one audit row."""
    canonical = (
        f"{row_id}:{session_id}:{action_type}:{tool_name or ''}:{cost_cents}:"
        f"{timestamp}:{prev_hash}:{digest(inputs)}:{digest(outputs)}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
