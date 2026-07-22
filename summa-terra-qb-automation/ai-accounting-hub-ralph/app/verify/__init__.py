"""VerifyAPI gate (Gate 3) + gated qbXML write-back (CHUNK_6_VERIFY).

Public surface for the workflow's autonomous-execution step:
    from app.verify import execute_approved_write, run_verifyapi
"""
from __future__ import annotations

from app.verify.errors import CoADrift, QBEditConflict, VerifyError, VerifyNotReady
from app.verify.execution import execute_approved_write
from app.verify.verifyapi import (
    VerifyVerdict,
    run_verifyapi,
    verdict_to_bundle,
)

__all__ = [
    "CoADrift",
    "QBEditConflict",
    "VerifyError",
    "VerifyNotReady",
    "VerifyVerdict",
    "execute_approved_write",
    "run_verifyapi",
    "verdict_to_bundle",
]
