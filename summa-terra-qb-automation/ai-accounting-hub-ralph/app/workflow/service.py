"""Core gated-intent orchestration (CHUNK_5_WORKFLOW).

``WorkflowService`` ties the seams together:

1. ``submit_intent`` — verify the agent's capability scope (fail-closed; an
   out-of-scope action raises ``CapabilityError`` and NO workflow is started),
   then publish to the ``EventBus`` and start the durable workflow. Idempotent by
   ``workflow_id``: a re-delivered intent neither double-publishes nor double-starts.
2. ``resolve`` — apply a human approve/reject signal at the irreversible boundary.
   EVERY decision appends an AuditProof row (``app.audit.append_audit_row``). On
   *approve*, the canonical write commits ONLY after the AIVS chain validates
   (``app.audit.validate_chain``); a raised ``AuditChainBroken`` blocks the commit
   (fail-closed). Re-signalling a resolved workflow is a no-op (no double-apply).

Every collaborator (audit append, chain validate, chain load, canonical commit) is
injectable so the whole flow is unit-testable against in-memory fakes, exercising
the *real* ``validate_chain`` gate without a database.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from app.audit import AuditRecord, append_audit_row, validate_chain
from app.workflow.capability import verify_capability
from app.workflow.engine import (
    APPROVED,
    REJECTED,
    DurableWorkflowEngine,
    EventBus,
    WorkflowState,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# JetStream subject AI intents are published to.
INTENT_SUBJECT = "intents.submitted"

# Stable namespace so an idempotency key deterministically maps to one workflow_id.
_IDEMPOTENCY_NS = uuid.UUID("8f1d3c2a-0b6e-4d5f-9a7b-2c4e6f8a0b1d")

AppendAudit = Callable[..., Any]
ChainValidator = Callable[[Sequence[AuditRecord]], Any]
ChainLoader = Callable[["Session", str], Sequence[AuditRecord]]
CanonicalCommit = Callable[["Session", dict[str, Any]], Any]


class WorkflowNotFound(Exception):
    """No durable workflow exists for the given ``workflow_id``."""

    code = "WORKFLOW_NOT_FOUND"


def _default_load_chain(session: Session, session_id: str) -> list[AuditRecord]:
    """Load the persisted AIVS chain for a session (integration/real-DB path only)."""
    from app.audit.service import _record_from_orm
    from app.models import AuditRow

    rows = (
        session.query(AuditRow)
        .filter(AuditRow.session_id == session_id)
        .order_by(AuditRow.row_id.asc())
        .all()
    )
    return [_record_from_orm(r) for r in rows]


def _default_commit_canonical(session: Session, intent: dict[str, Any]) -> Any:
    """Commit the canonical record (a Bill) — the irreversible write (real-DB path)."""
    from app.models import Bill

    bill = Bill(
        company_id=intent["company_id"],
        vendor_id=intent["vendor_id"],
        amount=intent["amount"],
        status="approved",
        raw_extensions=intent.get("raw_extensions") or {},
    )
    session.add(bill)
    session.flush()
    return bill


class WorkflowService:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        engine: DurableWorkflowEngine,
        append_audit: AppendAudit = append_audit_row,
        chain_validator: ChainValidator = validate_chain,
        load_chain: ChainLoader = _default_load_chain,
        commit_canonical: CanonicalCommit = _default_commit_canonical,
        capability_secret: str | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.engine = engine
        self._append_audit = append_audit
        self._validate_chain = chain_validator
        self._load_chain = load_chain
        self._commit_canonical = commit_canonical
        self._capability_secret = capability_secret

    # -- intake ---------------------------------------------------------------

    @staticmethod
    def _workflow_id(payload: dict[str, Any]) -> str:
        key = payload.get("idempotency_key")
        if key:
            return str(uuid.uuid5(_IDEMPOTENCY_NS, str(key)))
        return str(uuid.uuid4())

    def submit_intent(self, session: Session, payload: dict[str, Any], *, token: str) -> str:
        """Capability-gate, publish, and start the durable workflow. Returns workflow_id.

        Raises ``CapabilityError`` (fail-closed) for an out-of-scope action BEFORE
        any publish or workflow start.
        """
        action = payload["intent"]
        claims = verify_capability(token, action, secret=self._capability_secret)

        workflow_id = self._workflow_id(payload)
        if self.engine.get_state(workflow_id) is not None:
            # Idempotent re-submission: already in flight; do not double-publish.
            return workflow_id

        envelope = {"workflow_id": workflow_id, "agent_id": claims.get("agent_id"), **payload}
        self.event_bus.publish(INTENT_SUBJECT, envelope)
        self.engine.start_workflow(workflow_id, envelope)
        return workflow_id

    # -- commit boundary ------------------------------------------------------

    def resolve(
        self, session: Session, workflow_id: str, decision: str, approver: str
    ) -> dict[str, Any]:
        """Apply a human approve/reject signal at the irreversible commit boundary."""
        state = self.engine.get_state(workflow_id)
        if state is None:
            raise WorkflowNotFound(workflow_id)

        if state.is_resolved:
            # Re-delivered signal: never double-apply.
            return self._result(state)

        session_id = workflow_id  # workflow_id is a UUID -> valid audit_rows.session_id

        # AuditProof row on EVERY decision (approve or reject).
        self._append_audit(
            session,
            session_id=session_id,
            action_type=f"approval.{decision}",
            actor=approver,
            inputs={"workflow_id": workflow_id, "intent": state.intent.get("intent")},
            outputs={"decision": decision},
        )

        if decision == "reject":
            state.status = REJECTED
            state.decision = decision
            state.approver = approver
            state.result = {"workflow_id": workflow_id, "status": REJECTED, "committed": False}
            self.engine.set_state(state)
            return state.result

        # approve: fail-closed AIVS gate BEFORE the irreversible canonical write.
        records = self._load_chain(session, session_id)
        self._validate_chain(records)  # raises AuditChainBroken -> commit blocked

        bill = self._commit_canonical(session, state.intent)
        state.status = APPROVED
        state.decision = decision
        state.approver = approver
        state.result = {
            "workflow_id": workflow_id,
            "status": APPROVED,
            "committed": True,
            "bill_id": getattr(bill, "id", None),
        }
        self.engine.set_state(state)
        return state.result

    @staticmethod
    def _result(state: WorkflowState) -> dict[str, Any]:
        if state.result is not None:
            return state.result
        return {
            "workflow_id": state.workflow_id,
            "status": state.status,
            "committed": state.status == APPROVED,
        }
