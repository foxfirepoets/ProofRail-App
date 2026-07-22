"""FastAPI router for the gated intent pipeline (CHUNK_5_WORKFLOW).

Defines a module-level ``router``; per the isolation contract it must be registered
in app/main.py by the orchestrator (do not wire it here).

* ``POST /intents``                      -> 202 ``{"data": {"workflow_id": ...}}``
  (async submit)
* ``POST /workflow/approvals/{id}``      -> approve/reject the commit-boundary
  signal for the *generic* capability-token intent pipeline (CHUNK_5_WORKFLOW).

NOTE (Fix 3, spec-compliance-audit-stv-integration-layer-2026-06-30): the literal
spec path ``POST /approvals/{workflow_id}`` is owned by the STV integration
layer's dual-auth handler at ``app.integration.intents_router.approve_bill_intent``
— that is what System A's ``approval_signal.py`` POSTs to. This router's own
approval endpoint was moved to ``/workflow/approvals/{workflow_id}`` to remove
the path collision; it remains fully functional for the generic ``WorkflowService``
pipeline (e.g. ``app.scale.pipeline``), which is unrelated to the STV bill-intent
flow and is unaffected by the path rename (it calls ``WorkflowService`` directly,
never over HTTP).

Bodies are validated explicitly so validation/authorization failures return the
project ``{"data","error","meta"}`` envelope with the right status code (NOT
FastAPI's default ``{"detail": ...}``). The default service uses the in-memory
EventBus/engine so the API is import-safe with no NATS/Temporal running.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit import AuditChainBroken
from app.db import get_session
from app.workflow.capability import CapabilityError
from app.workflow.engine import InMemoryEventBus, get_workflow_engine
from app.workflow.schemas import ApprovalIn, IntentIn
from app.workflow.service import WorkflowNotFound, WorkflowService

router = APIRouter()

# Module-level singletons so function-call defaults aren't evaluated inline (ruff B008).
SessionDep = Depends(get_session)
BodyDefault = Body(default=None)

# Process-wide default wiring: get_workflow_engine() is env-driven (TEMPORAL_HOST
# set -> real Temporal engine; unset -> in-memory dev/test fake — Fix 2). Kept as
# a module singleton so state persists across requests.
_service = WorkflowService(
    event_bus=InMemoryEventBus(),
    engine=get_workflow_engine(),
)


def get_service() -> WorkflowService:
    return _service


def _ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta or {}}


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message}, "meta": {}},
    )


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid"))


@router.post("/intents", status_code=202)
def submit_intent_endpoint(
    payload: dict[str, Any] = BodyDefault,
    x_agent_capability: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """Submit an AI accounting intent (async). 202 + workflow_id, or 400/403 enveloped."""
    try:
        intent = IntentIn.model_validate(payload or {})
    except ValidationError as exc:
        return _error(400, "invalid_intent", _first_error(exc))

    try:
        workflow_id = get_service().submit_intent(
            session, intent.model_dump(), token=x_agent_capability
        )
    except CapabilityError as exc:
        return _error(403, "forbidden", str(exc))

    return _ok({"workflow_id": workflow_id})


@router.post("/workflow/approvals/{workflow_id}")
def resolve_endpoint(
    workflow_id: str,
    payload: dict[str, Any] = BodyDefault,
    session: Session = SessionDep,
) -> Any:
    """Human approve/reject the commit-boundary signal for ``workflow_id``.

    Generic ``WorkflowService`` pipeline only (CHUNK_5_WORKFLOW) — NOT the STV
    bill-intent approval path. See the module docstring (Fix 3) for why this is
    no longer at the literal ``/approvals/{workflow_id}`` spec path.
    """
    try:
        decision = ApprovalIn.model_validate(payload or {})
    except ValidationError as exc:
        return _error(400, "invalid_decision", _first_error(exc))

    try:
        result = get_service().resolve(
            session, workflow_id, decision.decision, decision.approver
        )
    except WorkflowNotFound:
        return _error(404, "not_found", f"workflow '{workflow_id}' not found")
    except AuditChainBroken as exc:
        # Fail-closed: AIVS chain invalid -> canonical commit blocked.
        return _error(409, "audit_chain_broken", str(exc))

    return _ok(result)
