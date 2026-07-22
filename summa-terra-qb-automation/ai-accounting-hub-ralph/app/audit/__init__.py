"""AuditProof / AIVS hash-chain audit layer (SwarmSync proof spine, Gate 2).

Public service surface for later chunks:
    from app.audit import append_audit_row, validate_chain, build_aivs_bundle
"""
from __future__ import annotations

from app.audit.chain import (
    AuditRecord,
    append_to_chain,
    chain_head,
    make_record,
    validate_chain,
)
from app.audit.errors import AuditChainBroken
from app.audit.hashing import GENESIS_HASH, compute_row_hash, redact
from app.audit.service import (
    append_audit_row,
    build_aivs_bundle,
    load_session_records,
    write_proof_bundle,
)

__all__ = [
    "AuditChainBroken",
    "AuditRecord",
    "GENESIS_HASH",
    "append_audit_row",
    "append_to_chain",
    "build_aivs_bundle",
    "chain_head",
    "compute_row_hash",
    "load_session_records",
    "make_record",
    "redact",
    "validate_chain",
    "write_proof_bundle",
]
