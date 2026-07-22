"""Router tests for the gated intent pipeline — no live DB, no TestClient.

Endpoint functions are invoked directly with a dummy session and an injected
in-memory service (via ``router._service``). Error paths return a JSONResponse
whose enveloped body and status code are asserted; happy paths return the plain
envelope dict — never FastAPI's default ``{"detail": ...}`` shape.
"""
from __future__ import annotations

import json

from fastapi.responses import JSONResponse

from app.workflow import router as workflow_router
from app.workflow.capability import mint_capability
from app.workflow.engine import InMemoryEventBus, InMemoryWorkflowEngine
from app.workflow.service import WorkflowService

SECRET = "router-test-secret"


class FakeBill:
    id = "bill-9"


def _install_service(monkeypatch, chain=None):
    audit_calls: list[dict] = []
    commit_calls: list[dict] = []

    def append_audit(session, **kwargs):
        audit_calls.append(kwargs)
        return object()

    def load_chain(session, session_id):
        return chain or []

    def commit_canonical(session, intent):
        commit_calls.append(intent)
        return FakeBill()

    svc = WorkflowService(
        event_bus=InMemoryEventBus(),
        engine=InMemoryWorkflowEngine(),
        append_audit=append_audit,
        load_chain=load_chain,
        commit_canonical=commit_canonical,
        capability_secret=SECRET,
    )
    monkeypatch.setattr(workflow_router, "_service", svc)
    return svc, audit_calls, commit_calls


def _envelope(resp) -> dict:
    if isinstance(resp, JSONResponse):
        body = json.loads(bytes(resp.body))
    else:
        body = resp
    assert set(body) == {"data", "error", "meta"}
    return body


def _token(actions=("create_bill",)):
    return mint_capability(agent_id="a", allowed_actions=actions, secret=SECRET)


def _intent_body(**extra):
    body = {"intent": "create_bill", "company_id": "co-1", "vendor_id": "v-1", "amount": 100}
    body.update(extra)
    return body


# -- /intents ----------------------------------------------------------------

def test_post_intent_happy_returns_workflow_id(monkeypatch):
    _install_service(monkeypatch)
    resp = workflow_router.submit_intent_endpoint(
        payload=_intent_body(), x_agent_capability=_token(), session=None
    )
    body = _envelope(resp)
    assert body["error"] is None
    assert body["data"]["workflow_id"]


def test_post_intent_invalid_body_enveloped_400(monkeypatch):
    _install_service(monkeypatch)
    resp = workflow_router.submit_intent_endpoint(
        payload={"company_id": "co-1"}, x_agent_capability=_token(), session=None
    )
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert _envelope(resp)["error"]["code"] == "invalid_intent"


def test_post_intent_out_of_scope_enveloped_403(monkeypatch):
    _install_service(monkeypatch)
    resp = workflow_router.submit_intent_endpoint(
        payload=_intent_body(),
        x_agent_capability=_token(actions=("something_else",)),
        session=None,
    )
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 403
    assert _envelope(resp)["error"]["code"] == "forbidden"


# -- /approvals/{id} ---------------------------------------------------------

def test_post_approval_happy(monkeypatch):
    _install_service(monkeypatch)
    submit = workflow_router.submit_intent_endpoint(
        payload=_intent_body(), x_agent_capability=_token(), session=None
    )
    wid = _envelope(submit)["data"]["workflow_id"]

    resp = workflow_router.resolve_endpoint(
        workflow_id=wid, payload={"decision": "approve", "approver": "cfo"}, session=None
    )
    body = _envelope(resp)
    assert body["data"]["committed"] is True


def test_post_approval_bad_decision_enveloped_400(monkeypatch):
    _install_service(monkeypatch)
    resp = workflow_router.resolve_endpoint(
        workflow_id="x", payload={"decision": "maybe", "approver": "cfo"}, session=None
    )
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert _envelope(resp)["error"]["code"] == "invalid_decision"


def test_post_approval_unknown_workflow_enveloped_404(monkeypatch):
    _install_service(monkeypatch)
    resp = workflow_router.resolve_endpoint(
        workflow_id="missing", payload={"decision": "approve", "approver": "cfo"}, session=None
    )
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    assert _envelope(resp)["error"]["code"] == "not_found"


def test_post_approval_broken_chain_enveloped_409(monkeypatch):
    from app.audit.chain import make_record

    sid_r1 = make_record(row_id=1, session_id="s", action_type="a", actor="x", prev_hash="0" * 64)
    dup = make_record(row_id=1, session_id="s", action_type="b", actor="x", prev_hash=sid_r1.row_hash)
    _install_service(monkeypatch, chain=[sid_r1, dup])

    submit = workflow_router.submit_intent_endpoint(
        payload=_intent_body(), x_agent_capability=_token(), session=None
    )
    wid = _envelope(submit)["data"]["workflow_id"]

    resp = workflow_router.resolve_endpoint(
        workflow_id=wid, payload={"decision": "approve", "approver": "cfo"}, session=None
    )
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 409
    assert _envelope(resp)["error"]["code"] == "audit_chain_broken"
