"""Transport abstractions + in-memory fakes for the gated intent pipeline.

Two seams keep the workflow logic free of external services:

* ``EventBus`` — publish/subscribe (NATS/JetStream in production).
* ``DurableWorkflowEngine`` — start / get-state / set-state for a durable,
  signal-blocked workflow (Temporal in production).

``InMemoryEventBus`` and ``InMemoryWorkflowEngine`` provide deterministic fakes
used by every unit test, so the full intent -> block -> approve -> commit flow
runs with zero infrastructure. The engine is idempotent by ``workflow_id`` so a
re-delivered intent (e.g. after a worker restart) never starts a second
workflow or double-applies.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Workflow lifecycle states. ``blocked`` == holding at the human-approval gate.
BLOCKED = "blocked"
APPROVED = "approved"
REJECTED = "rejected"


@dataclass
class WorkflowState:
    """Durable, replayable state for one intent workflow."""

    workflow_id: str
    intent: dict[str, Any]
    status: str = BLOCKED
    decision: str | None = None
    approver: str | None = None
    result: dict[str, Any] | None = None

    @property
    def is_resolved(self) -> bool:
        return self.status in (APPROVED, REJECTED)


class EventBus(ABC):
    """Publish/subscribe transport (NATS/JetStream)."""

    @abstractmethod
    def publish(self, subject: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    def subscribe(self, subject: str, handler: Callable[[dict[str, Any]], None]) -> None: ...


class DurableWorkflowEngine(ABC):
    """Durable workflow engine (Temporal): start, read, and persist state."""

    @abstractmethod
    def start_workflow(self, workflow_id: str, intent: dict[str, Any]) -> WorkflowState:
        """Start (or return the existing) workflow. Idempotent by ``workflow_id``."""

    @abstractmethod
    def get_state(self, workflow_id: str) -> WorkflowState | None: ...

    @abstractmethod
    def set_state(self, state: WorkflowState) -> None: ...


class InMemoryEventBus(EventBus):
    """Synchronous in-memory bus. Records every publish for assertions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    def publish(self, subject: str, payload: dict[str, Any]) -> None:
        self.published.append((subject, dict(payload)))
        for handler in self._subscribers.get(subject, []):
            handler(payload)

    def subscribe(self, subject: str, handler: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.setdefault(subject, []).append(handler)


class InMemoryWorkflowEngine(DurableWorkflowEngine):
    """In-memory durable engine. ``start_workflow`` is idempotent by id."""

    def __init__(self) -> None:
        self._states: dict[str, WorkflowState] = {}

    def start_workflow(self, workflow_id: str, intent: dict[str, Any]) -> WorkflowState:
        existing = self._states.get(workflow_id)
        if existing is not None:
            # Re-delivery (e.g. worker restart): do not start a second workflow.
            return existing
        state = WorkflowState(workflow_id=workflow_id, intent=dict(intent))
        self._states[workflow_id] = state
        return state

    def get_state(self, workflow_id: str) -> WorkflowState | None:
        return self._states.get(workflow_id)

    def set_state(self, state: WorkflowState) -> None:
        self._states[state.workflow_id] = state


# ---------------------------------------------------------------------------
# Engine factory (Fix 2 — spec-compliance-audit-stv-integration-layer).
# ---------------------------------------------------------------------------


def get_workflow_engine() -> DurableWorkflowEngine:
    """Env-driven engine selection: ``TEMPORAL_HOST`` set -> real durable Temporal
    engine; unset -> ``InMemoryWorkflowEngine`` (dev/test default, zero infra).

    ``app.workflow.temporal_engine`` is imported lazily (only when TEMPORAL_HOST
    is set) so importing this module — and every module that imports it — never
    requires a reachable Temporal server, and unit tests / import-safety checks
    are unaffected.

    Connecting is async (``TemporalWorkflowEngine.connect``); this bridges it
    synchronously with the same ``run_until_complete`` pattern already used by
    ``TemporalWorkflowEngine`` itself (see ``temporal_engine._run``), since the
    call sites here are plain module-level singletons, not coroutines.

    NOTE: this function only *selects* the engine. No Temporal worker is started
    here or anywhere in this codebase yet — a worker process must be deployed
    out-of-band before TEMPORAL_HOST is set in any environment (see CLAUDE.md
    "Open spikes" — Rightworks poller approval — and the module docstring of
    ``temporal_engine.py``).
    """
    import os

    if not os.environ.get("TEMPORAL_HOST"):
        return InMemoryWorkflowEngine()

    import asyncio

    from app.workflow.temporal_engine import TemporalWorkflowEngine

    return asyncio.get_event_loop().run_until_complete(TemporalWorkflowEngine.connect())
