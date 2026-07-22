"""Router tests for the canonical read layer — no live DB, no httpx/TestClient.

The endpoint functions are invoked directly with a FakeSession (FastAPI's HTTP layer is
not needed to verify envelope shape and status codes). Validation/not-found paths return a
JSONResponse whose body is inspected; happy paths return the plain envelope dict.
"""
from __future__ import annotations

import json

import pytest
from fastapi.responses import JSONResponse

from app.canonical import router as canonical_router
from app.canonical import service


class FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict]:
        return self._rows


class FakeSession:
    def __init__(self, exec_results: list[list[dict]] | None = None, store: dict | None = None):
        self._exec_results = list(exec_results or [])
        self._store = store or {}

    def execute(self, _stmt):  # noqa: ANN001
        if not self._exec_results:
            return FakeResult([])
        return FakeResult(self._exec_results.pop(0))

    def get(self, model, ident):  # noqa: ANN001
        return self._store.get((model, ident))


def _envelope(resp: object) -> dict:
    """Normalize either a JSONResponse or a plain dict into the envelope dict."""
    if isinstance(resp, JSONResponse):
        body = json.loads(bytes(resp.body))
    else:
        body = resp
    assert set(body) == {"data", "error", "meta"}
    return body


# --- search happy / edge ----------------------------------------------------

def test_search_happy_path_multi_company():
    vendor_rows = [
        {"company_id": "co-1", "id": "v-1", "name": "Acme", "score": 0.9},
        {"company_id": "co-2", "id": "v-2", "name": "Acme", "score": 0.8},
    ]
    session = FakeSession(exec_results=[vendor_rows, []])
    resp = canonical_router.search_endpoint(q="Acme", limit=10, session=session)
    body = _envelope(resp)
    assert body["error"] is None
    assert body["meta"]["count"] == 2
    assert {hit["company_id"] for hit in body["data"]} == {"co-1", "co-2"}


def test_search_empty_q_returns_enveloped_400():
    resp = canonical_router.search_endpoint(q="   ", limit=10, session=FakeSession())
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    body = _envelope(resp)
    assert body["data"] is None
    assert body["error"]["code"] == "invalid_query"


def test_search_missing_q_returns_enveloped_400():
    resp = canonical_router.search_endpoint(q="", limit=10, session=FakeSession())
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert _envelope(resp)["error"]["code"] == "invalid_query"


def test_search_oversized_q_returns_enveloped_400_not_500():
    resp = canonical_router.search_endpoint(
        q="x" * (service.MAX_Q_LEN + 1), limit=10, session=FakeSession()
    )
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert _envelope(resp)["error"]["code"] == "invalid_query"


# --- record reads -----------------------------------------------------------

class _FakeVendor:
    id = "v-1"
    company_id = "co-1"
    qb_list_id = None
    qb_edit_sequence = None
    name = "Acme"
    bank_fingerprint = None
    swarmscore = None
    raw_extensions = {"a": 1}


def test_get_vendor_found_returns_raw_extensions():
    from app.models import Vendor

    session = FakeSession(store={(Vendor, "v-1"): _FakeVendor()})
    body = _envelope(canonical_router.get_vendor_endpoint(vendor_id="v-1", session=session))
    assert body["data"]["raw_extensions"] == {"a": 1}


def test_get_vendor_unknown_returns_enveloped_404():
    resp = canonical_router.get_vendor_endpoint(vendor_id="missing", session=FakeSession())
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    assert _envelope(resp)["error"]["code"] == "not_found"


def test_get_bill_unknown_returns_enveloped_404():
    resp = canonical_router.get_bill_endpoint(bill_id="missing", session=FakeSession())
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    assert _envelope(resp)["error"]["code"] == "not_found"


# --- dashboard --------------------------------------------------------------

def test_dashboard_returns_enveloped_aggregates():
    companies = [{"id": "co-1", "legal_name": "Alpha LLC"}]
    vendor_counts = [{"company_id": "co-1", "n": 4}]
    bill_aggs = [{"company_id": "co-1", "n": 1, "total": 100.0}]
    session = FakeSession(exec_results=[companies, vendor_counts, bill_aggs])
    body = _envelope(canonical_router.dashboard_endpoint(session=session))
    assert body["meta"]["company_count"] == 1
    assert body["data"][0]["vendor_count"] == 4
    assert body["data"][0]["bill_total"] == 100.0


@pytest.mark.integration
def test_search_against_live_db_smoke():
    """Live-DB smoke test (auto-skipped unless RUN_INTEGRATION=1)."""
    from app.db import get_session

    gen = get_session()
    sess = next(gen)
    try:
        hits = service.search(sess, "a", limit=5)
        assert isinstance(hits, list)
    finally:
        gen.close()
