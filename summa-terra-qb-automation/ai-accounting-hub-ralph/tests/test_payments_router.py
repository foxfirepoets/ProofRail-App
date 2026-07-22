"""Router tests for /ap/intake and /bills/{id}/proof — no live DB, no TestClient.

Endpoint coroutines are driven with ``asyncio.run`` against a fake Request and an
injected in-memory service (``router._service`` / ``router._fetch_proof``). Responses
must use the enveloped ``{"data","error","meta"}`` shape, never FastAPI's default.
"""
from __future__ import annotations

import asyncio
import json

from fastapi.responses import JSONResponse

from app.payments import router as payments_router
from app.payments.service import PaymentsService, VendorContext

SECRET = "router-test-vcap-secret-long-enough-value"


class FakeRequest:
    def __init__(self, body: dict, content_type: str = "application/json"):
        self.headers = {"content-type": content_type}
        self._body = body

    async def json(self):
        return self._body


def _envelope(resp):
    body = json.loads(bytes(resp.body)) if isinstance(resp, JSONResponse) else resp
    assert set(body) == {"data", "error", "meta"}
    return body


def _install(monkeypatch, ctx=None):
    bills: list[dict] = []

    def write_bundle(session, bundle):
        return "bundle-1"

    def commit_bill(session, draft, bundle_id):
        bills.append({"id": "bill-1", "draft": draft, "bundle_id": bundle_id})
        return type("Bill", (), {"id": "bill-1"})()

    svc = PaymentsService(
        load_context=lambda s, c, v: ctx or VendorContext(swarmscore=900),
        write_bundle=write_bundle,
        commit_bill=commit_bill,
        append_audit=lambda s, **k: None,
        release_fn=lambda s, bid: True,
        vcap_secret=SECRET,
    )
    monkeypatch.setattr(payments_router, "_service", svc)
    return bills


def _invoice_body(**over):
    inv = {
        "company_id": "co-1",
        "vendor_id": "v-1",
        "invoice_number": "INV-3001",
        "po_ref": "PO-7",
        "amount": 4321.99,
        "line_items": [{"amount": 4321.99}],
    }
    inv.update(over)
    return {"invoice": inv}


def test_intake_json_happy_returns_envelope_and_approved(monkeypatch):
    _install(monkeypatch)
    resp = asyncio.run(payments_router.intake_endpoint(FakeRequest(_invoice_body()), session=None))
    body = _envelope(resp)
    assert resp.status_code == 200
    assert body["error"] is None
    assert body["data"]["decision"] == "APPROVED"
    assert body["data"]["proof_signature"]


def test_intake_duplicate_blocked_returns_202(monkeypatch):
    ctx = VendorContext(
        swarmscore=900,
        existing_bills=[{"company_id": "co-1", "invoice_number": "INV-3001", "amount": 4321.99}],
    )
    _install(monkeypatch, ctx=ctx)
    resp = asyncio.run(payments_router.intake_endpoint(FakeRequest(_invoice_body()), session=None))
    body = _envelope(resp)
    assert resp.status_code == 202
    assert body["data"]["decision"] == "BLOCKED"
    assert body["data"]["reason"] == "INVOICEPROOF_FAILED"


def test_intake_invalid_body_enveloped_400(monkeypatch):
    _install(monkeypatch)
    # Missing required vendor_id.
    bad = {"invoice": {"company_id": "co-1", "amount": 10.0}}
    resp = asyncio.run(payments_router.intake_endpoint(FakeRequest(bad), session=None))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert _envelope(resp)["error"]["code"] == "invalid_invoice"


def test_get_proof_happy(monkeypatch):
    def fake_fetch(session, bill_id):
        return {"bundle_id": "bundle-1", "bill_id": bill_id, "passed": True, "kind": "invoiceproof"}

    monkeypatch.setattr(payments_router, "_fetch_proof", fake_fetch)
    body = _envelope(payments_router.get_proof_endpoint("bill-1", session=None))
    assert body["data"]["bundle_id"] == "bundle-1"


def test_get_proof_unknown_enveloped_404(monkeypatch):
    monkeypatch.setattr(payments_router, "_fetch_proof", lambda s, b: None)
    resp = payments_router.get_proof_endpoint("missing", session=None)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    assert _envelope(resp)["error"]["code"] == "not_found"
