"""Integration smoke tests for the real NATS/Temporal transports.

Auto-skipped unless ``RUN_INTEGRATION=1`` (repo conftest). These only assert the
real implementations are importable and constructible against env config; they do
NOT start a worker or test server in the default unit run.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_nats_bus_importable_and_constructible():
    from app.workflow.nats_bus import NatsEventBus

    bus = NatsEventBus(url="nats://localhost:4222", stream="accounting-intents")
    assert bus._url == "nats://localhost:4222"


@pytest.mark.integration
def test_temporal_engine_importable():
    from app.workflow.temporal_engine import IntentWorkflow, TemporalWorkflowEngine

    engine = TemporalWorkflowEngine(client=None)
    assert engine is not None
    assert IntentWorkflow is not None
