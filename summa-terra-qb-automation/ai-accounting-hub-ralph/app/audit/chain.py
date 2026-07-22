"""AIVS chain model + validator. Pure Python over in-memory records (no DB).

Detects tampering (recomputed hash mismatch), insert/delete (prev_hash
discontinuity), and reorder (non-monotonic row_id ordering). Any defect is a
hard, fail-closed ``AuditChainBroken``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.audit.errors import AuditChainBroken
from app.audit.hashing import GENESIS_HASH, compute_row_hash, redact


@dataclass
class AuditRecord:
    """A DB-free view of one ``audit_rows`` row used by the core logic."""

    row_id: int
    session_id: str
    action_type: str
    actor: str
    prev_hash: str
    row_hash: str
    tool_name: str | None = None
    cost_cents: int = 0
    timestamp: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def recompute_hash(self) -> str:
        return compute_row_hash(
            row_id=self.row_id,
            session_id=self.session_id,
            action_type=self.action_type,
            tool_name=self.tool_name,
            cost_cents=self.cost_cents,
            timestamp=self.timestamp,
            prev_hash=self.prev_hash,
            inputs=self.inputs,
            outputs=self.outputs,
        )


def make_record(
    *,
    row_id: int,
    session_id: str,
    action_type: str,
    actor: str,
    prev_hash: str,
    tool_name: str | None = None,
    cost_cents: int = 0,
    timestamp: str = "",
    inputs: Mapping[str, Any] | None = None,
    outputs: Mapping[str, Any] | None = None,
) -> AuditRecord:
    """Build a fully-linked record: redacts bodies, then seals the row_hash."""
    red_in = redact(dict(inputs or {}))
    red_out = redact(dict(outputs or {}))
    row_hash = compute_row_hash(
        row_id=row_id,
        session_id=session_id,
        action_type=action_type,
        tool_name=tool_name,
        cost_cents=cost_cents,
        timestamp=timestamp,
        prev_hash=prev_hash,
        inputs=red_in,
        outputs=red_out,
    )
    return AuditRecord(
        row_id=row_id,
        session_id=session_id,
        action_type=action_type,
        actor=actor,
        prev_hash=prev_hash,
        row_hash=row_hash,
        tool_name=tool_name,
        cost_cents=cost_cents,
        timestamp=timestamp,
        inputs=red_in,
        outputs=red_out,
    )


def validate_chain(records: Iterable[AuditRecord]) -> bool:
    """Validate an ordered, single-session chain. Raises ``AuditChainBroken``.

    Returns ``True`` when the chain is intact. The caller treats the exception
    as a hard gate failure (block the write / roll back).
    """
    prev_hash = GENESIS_HASH
    prev_row_id: int | None = None
    seen = False

    for index, rec in enumerate(records):
        seen = True
        # Reorder / insert: row_id must strictly increase in chain order.
        if prev_row_id is not None and rec.row_id <= prev_row_id:
            raise AuditChainBroken(
                "row_id is not strictly increasing (reorder/duplicate)",
                index=index,
                row_id=rec.row_id,
            )
        # Insert / delete / reorder: each row must link to the running head.
        if rec.prev_hash != prev_hash:
            raise AuditChainBroken(
                "prev_hash does not match the running chain head",
                index=index,
                row_id=rec.row_id,
            )
        # Tamper: stored row_hash must equal a fresh recompute of the fields.
        if rec.recompute_hash() != rec.row_hash:
            raise AuditChainBroken(
                "row_hash does not match recomputed contents (tampered row)",
                index=index,
                row_id=rec.row_id,
            )
        prev_hash = rec.row_hash
        prev_row_id = rec.row_id

    if not seen:
        # An empty chain is vacuously valid (nothing to gate yet).
        return True
    return True


def chain_head(records: list[AuditRecord]) -> str:
    """Return the head hash (last row_hash, or genesis for an empty chain)."""
    return records[-1].row_hash if records else GENESIS_HASH


def append_to_chain(
    records: list[AuditRecord],
    *,
    row_id: int,
    session_id: str,
    action_type: str,
    actor: str,
    tool_name: str | None = None,
    cost_cents: int = 0,
    timestamp: str = "",
    inputs: Mapping[str, Any] | None = None,
    outputs: Mapping[str, Any] | None = None,
) -> AuditRecord:
    """Fail-closed append: validate the existing chain, then link a new record.

    The list is mutated in place (the new record is appended) and also returned.
    If the existing chain is broken this raises before any append happens.
    """
    validate_chain(records)  # gate: never extend a broken chain
    record = make_record(
        row_id=row_id,
        session_id=session_id,
        action_type=action_type,
        actor=actor,
        prev_hash=chain_head(records),
        tool_name=tool_name,
        cost_cents=cost_cents,
        timestamp=timestamp,
        inputs=inputs,
        outputs=outputs,
    )
    records.append(record)
    return record
