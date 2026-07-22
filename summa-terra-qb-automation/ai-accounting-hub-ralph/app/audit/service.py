"""AuditProof service layer (Gate 2).

Public entrypoints consumed by later chunks:
    - append_audit_row(...)  : fail-closed write of one AIVS row
    - validate_chain(...)    : re-export of the pure validator
    - build_aivs_bundle(...) : assemble a ProofBundle payload for AuditProof

The hash-chain core is DB-free (see ``app.audit.chain``); this module adds the
SQLAlchemy persistence and the per-session "load existing chain -> validate ->
link -> insert" gate. The DB path is exercised only under @pytest.mark.integration.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.audit.chain import (
    AuditRecord,
    append_to_chain,
    chain_head,
    make_record,
    validate_chain,
)
from app.audit.hashing import GENESIS_HASH
from app.audit.signing import maybe_sign_head

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Reserved key under outputs_json that carries the scalar fields the hash needs
# but which have no dedicated column on ``audit_rows``.
AIVS_META_KEY = "_aivs"

__all__ = [
    "append_audit_row",
    "load_session_records",
    "validate_chain",
    "build_aivs_bundle",
    "AuditRecord",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _record_from_orm(row: Any) -> AuditRecord:
    """Map an ``AuditRow`` ORM instance back to a DB-free record for validation."""
    outputs = dict(row.outputs_json or {})
    meta = outputs.pop(AIVS_META_KEY, {}) if isinstance(outputs, dict) else {}
    return AuditRecord(
        row_id=row.row_id,
        session_id=str(row.session_id),
        action_type=row.action_type,
        actor=row.actor,
        prev_hash=row.prev_hash,
        row_hash=row.row_hash,
        tool_name=row.tool_name,
        cost_cents=int(meta.get("cost_cents", 0)),
        timestamp=str(meta.get("timestamp", "")),
        inputs=dict(row.inputs_json or {}),
        outputs=outputs,
    )


def _load_session_records(session: Session, session_id: str) -> list[AuditRecord]:
    from app.models import AuditRow

    rows = (
        session.query(AuditRow)
        .filter(AuditRow.session_id == session_id)
        .order_by(AuditRow.row_id.asc())
        .all()
    )
    return [_record_from_orm(r) for r in rows]


# Public wrapper — exported from app.audit.__init__.__all__ so callers can use
# a stable, type-checked import rather than the private ``_load_session_records``.
def load_session_records(session: Session, session_id: str) -> list[AuditRecord]:
    """Load all AIVS audit rows for *session_id*, ordered by row_id ascending.

    Public stable API for modules that need to reconstruct the audit chain (e.g.
    the approve_bill_intent handler). Import via ``from app.audit import
    load_session_records`` — never import the private ``_load_session_records``
    directly.
    """
    return _load_session_records(session, session_id)


def append_audit_row(
    session: Session,
    *,
    session_id: str,
    action_type: str,
    actor: str,
    tool_name: str | None = None,
    cost_cents: int = 0,
    inputs: Mapping[str, Any] | None = None,
    outputs: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> Any:
    """Append one AIVS row, fail-closed.

    Loads the session's existing chain, validates it (raising ``AuditChainBroken``
    and BLOCKING the write if it is broken/out-of-order), links a new redacted
    row, and inserts it. Returns the persisted ``AuditRow``.

    IMPORTANT (bug fix — discovered while writing a live-DB Gate 1 wiring test,
    spec-compliance-audit-stv-integration-layer-2026-06-30.md follow-up):
    ``audit_rows.row_id`` is a table-wide ``BigInteger`` autoincrement primary
    key (one Postgres sequence shared across every session), NOT a per-session
    counter. The AIVS ``row_hash`` commits to ``row_id`` (spec header), so the
    row_id baked into the hash MUST equal the value Postgres actually assigns to
    the primary key column — otherwise ``validate_chain`` recomputes a different
    hash than the one stored and raises ``AuditChainBroken`` the next time this
    session's chain is reloaded (i.e. on the very next ``append_audit_row`` /
    ``load_session_records`` call for the same ``session_id``), even though
    nothing was tampered with. The previous implementation computed a *locally
    counted* row_id (``existing[-1].row_id + 1`` or ``1``), which only ever
    coincidentally matched the real primary key on a completely empty table —
    i.e. it was broken for every real multi-row / multi-session deployment and
    was never exercised against a live DB by the existing test suite (all
    prior audit-chain tests are either pure in-memory or use a mocked session).
    Fixed by reserving the next value from the backing sequence up front and
    using it for both the hash computation and the explicit primary key on
    insert, so hash and stored row_id always agree.
    """
    from app.models import AuditRow

    ts = timestamp or _now_iso()
    existing = _load_session_records(session, session_id)

    # Reserve the REAL primary-key value from the shared sequence before hashing,
    # so the row_id committed into row_hash matches the row_id actually persisted.
    next_row_id = session.execute(
        text("SELECT nextval(pg_get_serial_sequence('audit_rows', 'row_id'))")
    ).scalar_one()

    # Gate: refuse to extend a broken chain.
    record = append_to_chain(
        existing,
        row_id=next_row_id,
        session_id=session_id,
        action_type=action_type,
        actor=actor,
        tool_name=tool_name,
        cost_cents=cost_cents,
        timestamp=ts,
        inputs=inputs,
        outputs=outputs,
    )

    stored_outputs = dict(record.outputs)
    stored_outputs[AIVS_META_KEY] = {"cost_cents": cost_cents, "timestamp": ts}

    row = AuditRow(
        row_id=next_row_id,
        session_id=session_id,
        action_type=action_type,
        tool_name=tool_name,
        inputs_json=record.inputs,
        outputs_json=stored_outputs,
        actor=actor,
        prev_hash=record.prev_hash,
        row_hash=record.row_hash,
    )
    session.add(row)
    session.flush()
    return row


def build_aivs_bundle(
    records: list[AuditRecord],
    *,
    kind: str = "auditproof",
    vcap_state: str | None = "verified",
) -> dict[str, Any]:
    """Validate a chain and assemble a ``ProofBundle``-shaped dict.

    Raises ``AuditChainBroken`` (fail-closed) if the chain is invalid, so a
    bundle is only ever produced for an intact chain. ``proof_signature`` is set
    only when Ed25519 signing is enabled.
    """
    validate_chain(records)
    head = chain_head(records)
    signature = maybe_sign_head(head) if head != GENESIS_HASH else None
    payload = {
        "head": head,
        "row_count": len(records),
        "session_ids": sorted({r.session_id for r in records}),
        "signed": signature is not None,
    }
    return {
        "kind": kind,
        "vcap_state": vcap_state,
        "proof_hash": head,
        "proof_signature": signature,
        "passed": True,
        "payload": payload,
    }


def write_proof_bundle(session: Session, bundle: dict[str, Any]) -> Any:
    """Persist a ``ProofBundle`` row for an AuditProof result."""
    from app.models import ProofBundle

    row = ProofBundle(
        kind=bundle["kind"],
        vcap_state=bundle.get("vcap_state"),
        proof_hash=bundle.get("proof_hash"),
        proof_signature=bundle.get("proof_signature"),
        passed=bundle.get("passed", False),
        payload=bundle.get("payload"),
    )
    session.add(row)
    session.flush()
    return row


# Re-exported so callers can build records without importing chain internals.
make_audit_record = make_record
