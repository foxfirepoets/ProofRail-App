"""AuditProof error types. A broken chain is a HARD gate failure (fail-closed)."""
from __future__ import annotations


class AuditChainBroken(Exception):
    """Raised when the AIVS hash chain is tampered, reordered, or discontinuous.

    Carrying the stable code ``AUDIT_CHAIN_BROKEN`` lets callers map this to a
    hard rollback (never a warning) per the SwarmSync proof-spine invariant.
    """

    code = "AUDIT_CHAIN_BROKEN"

    def __init__(self, reason: str, *, index: int | None = None, row_id: int | None = None) -> None:
        self.reason = reason
        self.index = index
        self.row_id = row_id
        detail = reason
        if index is not None:
            detail += f" (index={index})"
        if row_id is not None:
            detail += f" (row_id={row_id})"
        super().__init__(f"{self.code}: {detail}")
