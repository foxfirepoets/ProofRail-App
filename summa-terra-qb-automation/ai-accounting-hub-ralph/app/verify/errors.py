"""Typed, fail-closed errors for the VerifyAPI gate and gated qbXML write-back.

Each carries a stable ``code`` and the ``http_status`` the workflow surfaces, so a
gate failure is never a silent log line — it routes to the human queue and blocks
the write (SwarmSync proof-spine invariant: all gates fail closed).
"""
from __future__ import annotations


class VerifyError(Exception):
    """Base for write-gate failures. Subclasses pin a code + HTTP status."""

    code = "VERIFY_ERROR"
    http_status = 500

    def __init__(self, message: str, *, detail: dict[str, object] | None = None) -> None:
        self.message = message
        self.detail = detail or {}
        super().__init__(f"{self.code}: {message}")


class VerifyNotReady(VerifyError):
    """VerifyAPI did not reach VERIFIED/COMPLETE + low risk — no autonomous exec."""

    code = "VERIFY_NOT_READY"
    http_status = 409


class QBEditConflict(VerifyError):
    """QB ``EditSequence`` optimistic-lock conflict survived the single retry."""

    code = "QB_EDIT_CONFLICT"
    http_status = 409


class CoADrift(VerifyError):
    """Referenced account is missing from the company file (chart-of-accounts drift)."""

    code = "COA_DRIFT"
    http_status = 422
