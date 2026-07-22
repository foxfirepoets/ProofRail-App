"""Gated intent pipeline (CHUNK_5_WORKFLOW).

The async-by-design execution core: AI agents submit intents (capability-scoped)
onto an ``EventBus`` (NATS/JetStream), a ``DurableWorkflowEngine`` (Temporal) holds
them durably and BLOCKS on a human-approval signal at the irreversible commit
boundary, and the canonical write commits ONLY after the AIVS hash chain validates
(fail-closed, via ``app.audit.validate_chain``).

Both transports are abstracted so the full intent -> block -> approve -> commit
flow is unit-testable with in-memory fakes and zero external services. The real
``temporalio`` / ``nats`` backed implementations live in ``temporal_engine`` and
``nats_bus`` and are exercised only under ``@pytest.mark.integration``.
"""
from __future__ import annotations

from app.workflow.capability import CapabilityError, mint_capability, verify_capability
from app.workflow.engine import (
    DurableWorkflowEngine,
    EventBus,
    InMemoryEventBus,
    InMemoryWorkflowEngine,
    WorkflowState,
)
from app.workflow.service import (
    INTENT_SUBJECT,
    WorkflowNotFound,
    WorkflowService,
)

__all__ = [
    "INTENT_SUBJECT",
    "CapabilityError",
    "DurableWorkflowEngine",
    "EventBus",
    "InMemoryEventBus",
    "InMemoryWorkflowEngine",
    "WorkflowNotFound",
    "WorkflowService",
    "WorkflowState",
    "mint_capability",
    "verify_capability",
]
