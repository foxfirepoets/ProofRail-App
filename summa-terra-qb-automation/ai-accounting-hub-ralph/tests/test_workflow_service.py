"""Unit tests for the gated intent pipeline — zero external services.

Every test drives the full intent -> block -> approve/reject -> commit flow through
``WorkflowService`` with the in-memory EventBus/engine. Audit append and canonical
commit are recorded by fakes, but the AIVS gate uses the REAL
``app.audit.validate_chain`` so the fail-closed behaviour is genuinely exercised.
"""
from __future__ import annotations

import uuid

import pytest

from app.audit import AuditChainBroken
from app.audit.chain import make_record
from app.workflow.capability import CapabilityError, mint_capability
from app.workflow.engine import (
    APPROVED,
    BLOCKED,
    REJECTED,
    InMemoryEventBus,
    InMemoryWorkflowEngine,
)
from app.workflow.service import INTENT_SUBJECT, WorkflowNotFound, WorkflowService

SECRET = "unit-test-secret"


class FakeBill:
    id = "bill-123"


class RecordingDeps:
    """Collects audit-append and canonical-commit calls; supplies a chain to validate."""

    def __init__(self, chain=None):
        self.audit_calls: list[dict] = []
        self.commit_calls: list[dict] = []
        self._chain = chain if chain is not None else []

    def append_audit(self, session, **kwargs):
        self.audit_calls.append(kwargs)
        return object()

    def load_chain(self, session, session_id):
        return self._chain

    def commit_canonical(self, session, intent):
        self.commit_calls.append(intent)
        return FakeBill()


def _service(deps: RecordingDeps) -> WorkflowService:
    return WorkflowService(
        event_bus=InMemoryEventBus(),
        engine=InMemoryWorkflowEngine(),
        append_audit=deps.append_audit,
        load_chain=deps.load_chain,
        commit_canonical=deps.commit_canonical,
        capability_secret=SECRET,
    )


def _intent(action="create_bill", **extra):
    base = {
        "intent": action,
        "company_id": "co-1",
        "vendor_id": "v-1",
        "amount": 100,
        "idempotency_key": None,
        "raw_extensions": {},
    }
    base.update(extra)
    return base


def _token(actions=("create_bill",)):
    return mint_capability(agent_id="agent-1", allowed_actions=actions, secret=SECRET)


# -- capability scope --------------------------------------------------------

def test_unauthorized_action_403_and_no_workflow_started():
    deps = RecordingDeps()
    svc = _service(deps)
    token = _token(actions=("read_only",))  # does NOT include create_bill

    with pytest.raises(CapabilityError):
        svc.submit_intent(None, _intent("create_bill"), token=token)

    # No workflow started, nothing published.
    assert svc.event_bus.published == []
    assert deps.audit_calls == []


def test_missing_token_denies():
    svc = _service(RecordingDeps())
    with pytest.raises(CapabilityError):
        svc.submit_intent(None, _intent(), token="")


# -- submit / durability -----------------------------------------------------

def test_submit_publishes_and_blocks():
    deps = RecordingDeps()
    svc = _service(deps)
    wid = svc.submit_intent(None, _intent(), token=_token())

    assert uuid.UUID(wid)  # valid uuid -> valid audit session_id
    assert svc.event_bus.published[0][0] == INTENT_SUBJECT
    state = svc.engine.get_state(wid)
    assert state is not None and state.status == BLOCKED


def test_resubmit_same_idempotency_key_does_not_double_start():
    deps = RecordingDeps()
    svc = _service(deps)
    payload = _intent(idempotency_key="abc-123")

    wid1 = svc.submit_intent(None, payload, token=_token())
    wid2 = svc.submit_intent(None, payload, token=_token())

    assert wid1 == wid2
    assert len(svc.event_bus.published) == 1  # no double publish


# -- approve path ------------------------------------------------------------

def test_approve_appends_audit_and_commits():
    deps = RecordingDeps(chain=[])  # empty chain validates cleanly
    svc = _service(deps)
    wid = svc.submit_intent(None, _intent(), token=_token())

    result = svc.resolve(None, wid, "approve", approver="cfo@firm")

    assert result["status"] == APPROVED
    assert result["committed"] is True
    assert result["bill_id"] == "bill-123"
    assert len(deps.audit_calls) == 1
    assert deps.audit_calls[0]["action_type"] == "approval.approve"
    assert len(deps.commit_calls) == 1


def test_approve_with_real_intact_chain_validates_and_commits():
    # Build a real 2-row intact chain so the REAL validate_chain runs on approve.
    sid = "11111111-1111-1111-1111-111111111111"
    r1 = make_record(row_id=1, session_id=sid, action_type="a", actor="x", prev_hash="0" * 64)
    r2 = make_record(row_id=2, session_id=sid, action_type="b", actor="x", prev_hash=r1.row_hash)
    deps = RecordingDeps(chain=[r1, r2])
    svc = _service(deps)
    wid = svc.submit_intent(None, _intent(), token=_token())

    result = svc.resolve(None, wid, "approve", approver="cfo@firm")
    assert result["committed"] is True


# -- reject path -------------------------------------------------------------

def test_reject_appends_audit_and_does_not_commit():
    deps = RecordingDeps()
    svc = _service(deps)
    wid = svc.submit_intent(None, _intent(), token=_token())

    result = svc.resolve(None, wid, "reject", approver="cfo@firm")

    assert result["status"] == REJECTED
    assert result["committed"] is False
    assert deps.audit_calls[0]["action_type"] == "approval.reject"
    assert deps.commit_calls == []  # no canonical write on reject


# -- fail-closed AIVS gate ---------------------------------------------------

def test_approve_blocks_commit_when_chain_broken():
    # A tampered chain: row_id reused -> REAL validate_chain raises AuditChainBroken.
    sid = "22222222-2222-2222-2222-222222222222"
    r1 = make_record(row_id=1, session_id=sid, action_type="a", actor="x", prev_hash="0" * 64)
    r2 = make_record(row_id=1, session_id=sid, action_type="b", actor="x", prev_hash=r1.row_hash)
    deps = RecordingDeps(chain=[r1, r2])
    svc = _service(deps)
    wid = svc.submit_intent(None, _intent(), token=_token())

    with pytest.raises(AuditChainBroken):
        svc.resolve(None, wid, "approve", approver="cfo@firm")

    # Decision row was recorded, but the irreversible commit was blocked.
    assert deps.commit_calls == []
    assert svc.engine.get_state(wid).status == BLOCKED  # not marked approved


# -- idempotent resolve ------------------------------------------------------

def test_resolve_twice_does_not_double_apply():
    deps = RecordingDeps()
    svc = _service(deps)
    wid = svc.submit_intent(None, _intent(), token=_token())

    first = svc.resolve(None, wid, "approve", approver="cfo@firm")
    second = svc.resolve(None, wid, "approve", approver="cfo@firm")

    assert first == second
    assert len(deps.commit_calls) == 1  # committed once
    assert len(deps.audit_calls) == 1  # audited once


def test_resolve_unknown_workflow_raises():
    svc = _service(RecordingDeps())
    with pytest.raises(WorkflowNotFound):
        svc.resolve(None, "no-such-id", "approve", approver="cfo@firm")
