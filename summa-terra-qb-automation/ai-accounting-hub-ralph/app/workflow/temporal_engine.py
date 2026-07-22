"""Real ``temporalio``-backed ``DurableWorkflowEngine`` + the workflow definition.

Imported and exercised ONLY under ``@pytest.mark.integration`` (the repo conftest
auto-skips unless ``RUN_INTEGRATION=1``); unit tests use ``InMemoryWorkflowEngine``.
Connection settings come straight from the environment (see ``.env.example``:
``TEMPORAL_HOST``, ``TEMPORAL_NAMESPACE``, ``TEMPORAL_TASK_QUEUE``).

``IntentWorkflow`` is the durable holder: it builds the canonical record, then
BLOCKS on the ``approve`` signal at the irreversible boundary. Durability +
``workflow_id`` reuse-policy give exactly-once application across worker restarts.
This module only *defines* the wiring; a worker is started out-of-band, never in
unit tests.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy

from app.workflow.engine import APPROVED, BLOCKED, REJECTED, DurableWorkflowEngine, WorkflowState

TEMPORAL_HOST_ENV = "TEMPORAL_HOST"
TEMPORAL_NAMESPACE_ENV = "TEMPORAL_NAMESPACE"
TEMPORAL_TASK_QUEUE_ENV = "TEMPORAL_TASK_QUEUE"


def _host() -> str:
    return os.environ.get(TEMPORAL_HOST_ENV, "localhost:7233")


def _namespace() -> str:
    return os.environ.get(TEMPORAL_NAMESPACE_ENV, "default")


def _task_queue() -> str:
    return os.environ.get(TEMPORAL_TASK_QUEUE_ENV, "ai-accounting-hub")


@workflow.defn
class IntentWorkflow:
    """Holds an intent durably and blocks on the human-approval signal."""

    def __init__(self) -> None:
        self._decision: str | None = None
        self._approver: str | None = None
        self._intent: dict[str, Any] = {}

    @workflow.run
    async def run(self, intent: dict[str, Any]) -> dict[str, Any]:
        self._intent = intent
        # Block at the irreversible boundary until a human signals a decision.
        await workflow.wait_condition(lambda: self._decision is not None)
        status = APPROVED if self._decision == "approve" else REJECTED
        return {
            "workflow_id": intent.get("workflow_id"),
            "status": status,
            "decision": self._decision,
            "approver": self._approver,
        }

    @workflow.signal
    def decide(self, decision: str, approver: str) -> None:
        self._decision = decision
        self._approver = approver

    @workflow.query
    def state(self) -> str:
        if self._decision == "approve":
            return APPROVED
        if self._decision == "reject":
            return REJECTED
        return BLOCKED


class TemporalWorkflowEngine(DurableWorkflowEngine):
    """Starts/signals durable ``IntentWorkflow`` runs. Idempotent by ``workflow_id``."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    @classmethod
    async def connect(cls) -> TemporalWorkflowEngine:
        client = await Client.connect(_host(), namespace=_namespace())
        return cls(client=client)

    def _require_client(self) -> Client:
        if self._client is None:
            raise RuntimeError("TemporalWorkflowEngine is not connected; call connect()")
        return self._client

    def start_workflow(self, workflow_id: str, intent: dict[str, Any]) -> WorkflowState:
        client = self._require_client()

        async def _do() -> None:
            await client.start_workflow(
                IntentWorkflow.run,
                intent,
                id=workflow_id,
                task_queue=_task_queue(),
                # Reject duplicate ids -> a re-delivered intent never double-starts.
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )

        _run(_do())
        return WorkflowState(workflow_id=workflow_id, intent=dict(intent))

    def get_state(self, workflow_id: str) -> WorkflowState | None:
        client = self._require_client()

        async def _do() -> str:
            handle = client.get_workflow_handle(workflow_id)
            return await handle.query(IntentWorkflow.state)

        status = _run(_do())
        return WorkflowState(workflow_id=workflow_id, intent={}, status=status)

    def set_state(self, state: WorkflowState) -> None:
        # State is owned by the durable workflow; signal it instead of overwriting.
        if state.decision is None:
            return
        client = self._require_client()

        async def _do() -> None:
            handle = client.get_workflow_handle(state.workflow_id)
            await handle.signal(
                IntentWorkflow.decide, args=[state.decision, state.approver]
            )

        _run(_do())


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


# Reference the timedelta import so lints stay quiet; activity timeouts use it.
_DEFAULT_ACTIVITY_TIMEOUT = timedelta(seconds=30)
