"""FIN-2 tests: cross-entity search + "what needs my attention today" (read-only, shadow mode).

Offline tests invoke the endpoint functions directly with a minimal Starlette Request and a
monkeypatched service/search layer (session=None), so they touch no live database — matching the
test_dashboard.py convention. Live render proofs are gated by RUN_INTEGRATION=1 and roll back.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from starlette.requests import Request

from app.dashboard import SHADOW_BANNER, service
from app.dashboard import router as dash
from app.dashboard import search as dash_search

DASH_DIR = Path(__file__).resolve().parents[1] / "app" / "dashboard"


def _req(path: str = "/ui/search") -> Request:
    return Request({"type": "http", "method": "GET", "path": path,
                    "headers": [], "query_string": b""})


def _html(resp) -> str:
    return resp.body.decode("utf-8")


# ---------------------------------------------------------------------------
# normalize_query: empty / short -> friendly prompt (None), not an error
# ---------------------------------------------------------------------------
def test_normalize_query_empty_and_short_return_none():
    assert dash_search.normalize_query(None) is None
    assert dash_search.normalize_query("") is None
    assert dash_search.normalize_query("   ") is None
    assert dash_search.normalize_query("a") is None


def test_normalize_query_trims_and_caps():
    assert dash_search.normalize_query("  Hunter  ") == "Hunter"
    assert len(dash_search.normalize_query("x" * 500)) == dash_search.MAX_Q_LEN


# ---------------------------------------------------------------------------
# /ui/search — grouped results, banner, friendly empty-state
# ---------------------------------------------------------------------------
def test_search_groups_results_with_banner(monkeypatch):
    monkeypatch.setattr(dash_search, "search", lambda s, q: {
        "q": q,
        "groups": [
            {"kind": "Draws", "count": 1, "hits": [
                {"label": "Draw #29", "sublabel": "Hunter's Landing",
                 "status": "needs_review", "link": "/ui/draws/d29"}]},
            {"kind": "Vendors", "count": 1, "hits": [
                {"label": "K CARTER", "sublabel": "", "status": None,
                 "link": "/ui/vendors/v1"}]},
        ],
        "total": 2,
    })
    resp = dash.search(_req(), q="Hunter", session=None)
    assert resp.status_code == 200
    body = _html(resp)
    assert SHADOW_BANNER in body
    assert "Draws" in body and "Vendors" in body
    assert "Draw #29" in body
    assert "Hunter" in body
    assert "/ui/draws/d29" in body
    assert "/ui/vendors/v1" in body


def test_search_empty_query_renders_prompt_not_error(monkeypatch):
    called = []
    monkeypatch.setattr(dash_search, "search", lambda s, q: called.append(q) or {})
    resp = dash.search(_req(), q="", session=None)
    assert resp.status_code == 200
    body = _html(resp)
    assert SHADOW_BANNER in body
    assert "at least 2 characters" in body
    assert called == []  # short query never runs a DB search


def test_search_no_matches_is_graceful(monkeypatch):
    monkeypatch.setattr(dash_search, "search",
                        lambda s, q: {"q": q, "groups": [], "total": 0})
    resp = dash.search(_req(), q="zzzznomatch", session=None)
    assert resp.status_code == 200
    body = _html(resp)
    assert SHADOW_BANNER in body
    assert "No matches" in body


# ---------------------------------------------------------------------------
# /ui/attention — grouped action rollup, banner, counts
# ---------------------------------------------------------------------------
def _seeded_attention() -> dict:
    return {
        "groups": [
            {"kind": "Open exceptions (close-blocking)", "urgency": "high", "count": 1,
             "rows": [{"label": "DRAW_NEEDS_REVIEW — Draw #29",
                        "sublabel": "Draw Review: Hunter's Landing", "link": "/ui/draws/d29"}]},
            {"kind": "Vendor bank-change warnings", "urgency": "high", "count": 1,
             "rows": [{"label": "INV-1", "sublabel": "Vendor Bills: ACME",
                        "link": "/ui/vendor-bills/b1"}]},
            {"kind": "Missing coding (Customer:Job / Class / Item)", "urgency": "medium",
             "count": 1, "rows": [{"label": "Missing Class — INV-2",
                                    "sublabel": "Vendor Bills: ACME",
                                    "link": "/ui/vendor-bills/b2"}]},
            {"kind": "Needs info / needs review", "urgency": "medium", "count": 1,
             "rows": [{"label": "INV-2", "sublabel": "Vendor Bills: ACME",
                        "link": "/ui/vendor-bills/b2"}]},
            {"kind": "Pending approvals", "urgency": "low", "count": 0, "rows": []},
        ],
        "total": 4, "shadow_mode": True, "qb_write_back": "DISABLED",
    }


def test_attention_renders_grouped_with_banner_and_counts(monkeypatch):
    monkeypatch.setattr(service, "attention_overview", lambda s: _seeded_attention())
    resp = dash.attention(_req(path="/ui/attention"), session=None)
    assert resp.status_code == 200
    body = _html(resp)
    assert SHADOW_BANNER in body
    assert "What Needs My Attention Today" in body
    assert "Open exceptions" in body
    assert "Vendor bank-change warnings" in body
    assert "Missing coding" in body
    assert "Needs info / needs review" in body
    assert "DRAW_NEEDS_REVIEW — Draw #29" in body
    assert "/ui/vendor-bills/b1" in body
    assert "high" in body and "medium" in body  # urgency labels rendered


# ---------------------------------------------------------------------------
# Shadow-safety: the new search module imports/calls no QB write path
# ---------------------------------------------------------------------------
def test_search_module_has_no_qb_write_path():
    forbidden_modules = ("transport", "qbwc", "draw_engine", "payments", "verify.execution")
    forbidden_calls = {"BillAdd", "bill_add", "process_draw", "add_bill", "execute_payment"}
    tree = ast.parse((DASH_DIR / "search.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not any(m in mod for m in forbidden_modules), mod
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            assert name not in forbidden_calls, name


# ---------------------------------------------------------------------------
# Live render proof (gated by RUN_INTEGRATION=1, read-only)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_live_search_and_attention_render_with_banner():
    from sqlalchemy.orm import Session

    from app.db import get_engine

    with Session(get_engine()) as s:
        # Attention surfaces real action items with a non-negative total.
        att = service.attention_overview(s)
        assert att["total"] >= 0
        assert {g["kind"] for g in att["groups"]} >= {
            "Open exceptions (close-blocking)", "Vendor bank-change warnings",
            "Missing coding (Customer:Job / Class / Item)",
        }
        resp = dash.attention(_req(path="/ui/attention"), session=s)
        assert resp.status_code == 200
        assert SHADOW_BANNER in _html(resp)

        # A broad search term returns 200 with the banner; grouped output is read-only.
        out = dash_search.search(s, "a")
        assert "groups" in out
        resp2 = dash.search(_req(), q="a", session=s)
        assert resp2.status_code == 200
        assert SHADOW_BANNER in _html(resp2)
