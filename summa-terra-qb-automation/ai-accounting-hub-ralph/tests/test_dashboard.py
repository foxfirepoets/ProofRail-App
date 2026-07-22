"""Operator dashboard tests (DASH-7).

Following the project convention (see test_canonical_router.py): no httpx / TestClient. The
endpoint functions are invoked directly with a minimal Starlette Request and a monkeypatched
service layer, so offline tests touch no live database. The shadow-safety scan parses the
dashboard package with ``ast`` and proves no import of, or call into, the QB transport / QBWC /
BillAdd / payment / fee-engine path exists. Live render tests are gated by RUN_INTEGRATION=1 and
read-only (the one mutating assertion rolls its transaction back).
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from starlette.requests import Request

from app.dashboard import SHADOW_BANNER, modules, service
from app.dashboard import router as dash
from app.dashboard import vendor_bills as vb
from app.dashboard import work_queue as wq

DASH_DIR = Path(__file__).resolve().parents[1] / "app" / "dashboard"


def _req(method: str = "GET", path: str = "/ui") -> Request:
    return Request({"type": "http", "method": method, "path": path,
                    "headers": [], "query_string": b""})


def _html(resp) -> str:
    return resp.body.decode("utf-8")


# ---------------------------------------------------------------------------
# Pure guard + fee-panel unit tests (no DB, no request)
# ---------------------------------------------------------------------------
def test_assert_postable_blocks_historical():
    ok, reason = service.assert_postable({"flags": {"not_for_posting": True}})
    assert ok is False
    assert "not_for_posting" in reason or "historical" in reason


def test_assert_postable_allows_normal():
    ok, _ = service.assert_postable({"flags": {}})
    assert ok is True


def test_is_historical_variants():
    assert service.is_historical({"not_for_posting": True}) is True
    assert service.is_historical({"historical_example": True}) is True
    assert service.is_historical({"already_paid": True}) is True
    assert service.is_historical({}) is False
    assert service.is_historical(None) is False


def test_fee_panel_draw29_5_2_1_split_and_anti_13pct():
    panel = service.fee_panel(Decimal("962845.68"))
    amounts = {ln["fee_role"]: ln["amount"] for ln in panel["lines"]}
    assert amounts["dev_5_partnership"] == "48142.28"
    assert amounts["dev_inc_5_parent"] == "48142.28"
    assert amounts["ceo_2_parent"] == "19256.91"
    assert amounts["pres_1_parent"] == "9628.46"
    assert panel["partnership_total"] == "48142.28"
    assert panel["distinct_economic_total_8pct"] == "77027.65"
    assert panel["naive_double_counted_13pct"] == "125169.93"
    assert panel["posted"] is False


# ---------------------------------------------------------------------------
# Read pages render with the persistent shadow banner
# ---------------------------------------------------------------------------
def test_home_renders_work_queue_landing_and_banner(monkeypatch):
    monkeypatch.setattr(service, "work_queue_overview", lambda s: {
        "groups": [{"group": "Construction", "modules": [
            {"key": "draw_review", "title": "Draw Review", "status": "functional",
             "route": "/ui/draws", "description": "GC draws", "pending_count": 2,
             "count_label": "2 to review"},
        ]}],
        "module_count": 15, "draw_count": 2, "shadow_mode": True, "qb_write_back": "DISABLED",
    })
    resp = dash.home(_req(), session=None)
    assert resp.status_code == 200
    body = _html(resp)
    assert SHADOW_BANNER in body
    assert "QB WRITE-BACK DISABLED" in body
    assert "Accounting Work Queue" in body
    assert "Draw Review" in body
    assert "Functional" in body


# ---------------------------------------------------------------------------
# Module registry: every module functional except the single QB write-back item
# ---------------------------------------------------------------------------
def test_registry_only_qb_sync_pending():
    # FIN-1: all modules are functional in shadow mode except the one explicit
    # "QuickBooks Sync / Write-back" item, which stays pending (write-back disabled).
    pending = {m.key for m in modules.MODULES if m.status == "pending"}
    assert pending == {"qb_sync"}
    # Draw Review and Vendor Bills remain functional (non-regressed).
    functional = {m.key for m in modules.MODULES if m.status == "functional"}
    assert {"draw_review", "vendor_bills"} <= functional
    # every group is in GROUP_ORDER and every module key is unique
    assert {m.group for m in modules.MODULES} <= set(modules.GROUP_ORDER)
    assert len({m.key for m in modules.MODULES}) == len(modules.MODULES)


@pytest.mark.parametrize("m", modules.MODULES, ids=lambda m: m.key)
def test_every_module_route_renders_with_banner(monkeypatch, m):
    """Drive each module's REAL registered route and assert HTTP 200 + SHADOW banner.

    Closes the advisory that vendor_bills and every /ui/m/* module were never actually
    exercised — the old code called dash.draws() for all functional modules regardless of
    the module's actual route field.
    """
    if m.status == "pending":
        # qb_sync: placeholder page (not redirected because not functional).
        resp = dash.module_queue(_req(method="GET", path=m.route), m.key, session=None)
        assert resp.status_code == 200, f"{m.key}: expected 200, got {resp.status_code}"
        body = _html(resp)
        assert SHADOW_BANNER in body, f"{m.key}: SHADOW_BANNER missing"
        assert "Module pending" in body, f"{m.key}: 'Module pending' missing"
        assert m.title in body, f"{m.key}: module title missing"
        return

    # Functional modules: invoke the router function that owns the module's registered route.
    if m.route == "/ui/draws":
        monkeypatch.setattr(service, "list_draws", lambda *a, **k: [])
        resp = dash.draws(_req(path=m.route), session=None)
    elif m.route == "/ui/vendor-bills":
        monkeypatch.setattr(vb, "list_vendor_bills", lambda *a, **k: [])
        monkeypatch.setattr(service, "list_companies", lambda *a, **k: [])
        resp = dash.vendor_bills_list(_req(path=m.route), session=None)
    elif m.route.startswith("/ui/m/"):
        module_key = m.key
        if module_key == "month_end":
            monkeypatch.setattr(wq, "month_end_exceptions", lambda s: [])
        elif module_key == "missing_dimensions":
            monkeypatch.setattr(wq, "missing_dimensions_items", lambda s: [])
        else:
            monkeypatch.setattr(wq, "list_work_items", lambda *a, **k: [])
            monkeypatch.setattr(service, "list_companies", lambda *a, **k: [])
            monkeypatch.setattr(wq, "work_item_count", lambda *a, **k: 0)
        resp = dash.work_queue_list(_req(path=m.route), module_key, session=None)
    else:
        pytest.fail(f"Unhandled route pattern for module {m.key!r}: {m.route!r}")

    assert resp.status_code == 200, f"{m.key} ({m.route}): expected 200, got {resp.status_code}"
    body = _html(resp)
    assert SHADOW_BANNER in body, f"{m.key} ({m.route}): SHADOW_BANNER missing from body"


def test_module_queue_functional_redirects_to_own_route():
    resp = dash.module_queue(_req(path="/ui/queue/draw_review"), "draw_review", session=None)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui/draws"


def test_module_queue_unknown_key_404():
    resp = dash.module_queue(_req(path="/ui/queue/nope"), "nope", session=None)
    assert resp.status_code == 404


def test_vendor_bills_module_now_functional_redirects():
    # Vendor Bills was activated (VB module): the queue route now redirects to its own page.
    resp = dash.module_queue(_req(path="/ui/queue/vendor_bills"), "vendor_bills", session=None)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui/vendor-bills"


@pytest.mark.parametrize("fn,svc", [
    ("companies", "list_companies"),
    ("vendors", "list_vendors"),
    ("bills", "list_bills"),
    ("draws", "list_draws"),
])
def test_list_pages_render_with_banner(monkeypatch, fn, svc):
    monkeypatch.setattr(service, svc, lambda *a, **k: [])
    resp = getattr(dash, fn)(_req(), session=None)
    assert resp.status_code == 200
    assert SHADOW_BANNER in _html(resp)


def test_sync_page_shows_phase1_tracking(monkeypatch):
    monkeypatch.setattr(service, "sync_overview", lambda s: {
        "counts": {"companies": 1, "vendors": 1, "bills": 1, "draws": 1},
        "qbwc_poll_cadence": {"status": "pending spike #1", "detail": "x", "value_seconds": None},
        "rightworks_persistent_poller": {"status": "pending written approval — spike #2",
                                         "detail": "y", "ticket": None},
        "auditproof_runs": {"passed_bundles": 0},
        "shadow_mode": True, "qb_write_back": "DISABLED",
    })
    body = _html(dash.sync(_req(), session=None))
    assert "pending spike #1" in body
    assert "spike #2" in body
    assert "DISABLED" in body
    assert "AuditProof" in body


def _draw29_detail() -> dict:
    return {
        "id": "d29", "draw_number": "29", "project": "Hunter's Landing",
        "company_id": "p1", "package_total": "962845.68", "status": "needs_review",
        "borrower": "Summa Terra Ventures", "lender": "UFirst", "collateral_address": "407 W 12th",
        "draw_date": "09.10.2025", "source_doc_ref": "Draw #29.pdf",
        "cm_approved": False, "watson_approved": False,
        "flags": {"not_for_posting": True}, "historical": True,
        "lines": [{"line_no": 1, "item_code": "048", "invoice_no": "402", "payable_to": "K CARTER",
                   "description": "x", "inv_amount": "100.00", "retainage": "0.00",
                   "amount_due": "100.00", "row_confidence": "exact", "needs_review": False,
                   "mapped_cost_code": True, "id": "ln1"}],
        "coverage": {"authoritative_total": "962845.68", "parsed_amount_due_total": "962845.68",
                     "reconstructed_amount_due_total": "962845.68", "unresolved_delta": "0.00",
                     "pct_coverage": "100.00", "fully_reconciled": True,
                     "confidence_breakdown": {"exact": 1}, "summary_pages": [9, 10]},
        "retainage_exceptions": [], "cost_code_gaps": [], "warnings": [],
        "fee_panel": service.fee_panel(Decimal("962845.68")), "fee_entries": [],
        "proof": {"bundles": [], "count": 0},
    }


def test_draw_detail_renders_review(monkeypatch):
    monkeypatch.setattr(service, "get_draw_detail", lambda s, i: _draw29_detail())
    body = _html(dash.draw_detail(_req(), "d29", session=None))
    assert "Hunter" in body and "Landing" in body
    assert "historical / not-for-posting" in body
    assert "SHADOW DRAFT" in body
    assert "48142.28" in body  # 5% line
    assert "77027.65" in body  # distinct 8% total


def test_unknown_draw_404(monkeypatch):
    monkeypatch.setattr(service, "get_draw_detail", lambda s, i: None)
    resp = dash.draw_detail(_req(), "missing", session=None)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Actions: canonical-status-only, and the not_for_posting guard
# ---------------------------------------------------------------------------
def test_approve_historical_draw_is_refused_and_does_not_write(monkeypatch):
    monkeypatch.setattr(service, "get_draw_detail", lambda s, i: _draw29_detail())
    calls = []
    monkeypatch.setattr(service, "transition_draw_status", lambda *a, **k: calls.append(a))
    resp = dash.approve_draw(_req("POST"), "d29", session=None)
    assert resp.status_code == 400
    assert "never be approved" in _html(resp)
    assert calls == []  # no status write occurred


def test_approve_normal_draw_transitions_status_only(monkeypatch):
    monkeypatch.setattr(service, "get_draw_detail", lambda s, i: {"flags": {}, "id": "d1"})
    calls = []
    monkeypatch.setattr(service, "transition_draw_status",
                        lambda s, i, status: calls.append((i, status)) or {"id": i, "status": status})
    resp = dash.approve_draw(_req("POST"), "d1", session=None)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ui/draws/d1?msg=approved-for-accounting"
    assert calls == [("d1", "approved_for_accounting")]


def test_reject_and_mark_historical_call_only_canonical_writers(monkeypatch):
    monkeypatch.setattr(service, "get_draw_detail", lambda s, i: {"flags": {}, "id": "d1"})
    transitions, historicals = [], []
    monkeypatch.setattr(service, "transition_draw_status",
                        lambda s, i, status: transitions.append((i, status)))
    monkeypatch.setattr(service, "mark_draw_historical", lambda s, i: historicals.append(i))
    assert dash.reject_draw(_req("POST"), "d1", session=None).status_code == 303
    assert dash.mark_historical(_req("POST"), "d1", session=None).status_code == 303
    assert transitions == [("d1", "rejected")]
    assert historicals == ["d1"]


# ---------------------------------------------------------------------------
# Shadow-safety: no QB write / BillAdd / payment / fee-engine path in the package
# ---------------------------------------------------------------------------
def test_dashboard_package_has_no_qb_write_path():
    forbidden_modules = ("transport", "qbwc", "draw_engine", "payments", "verify.execution")
    forbidden_calls = {"BillAdd", "bill_add", "process_draw", "add_bill", "execute_payment"}
    py_files = sorted(DASH_DIR.rglob("*.py"))
    assert py_files, "expected dashboard python files"
    for pf in py_files:
        tree = ast.parse(pf.read_text(encoding="utf-8"), filename=str(pf))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert not any(m in n.name for m in forbidden_modules), f"{pf}: import {n.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not any(m in mod for m in forbidden_modules), f"{pf}: from {mod}"
            elif isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                assert name not in forbidden_calls, f"{pf}: call {name}"


# ---------------------------------------------------------------------------
# Live render proof (gated by RUN_INTEGRATION=1)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_live_render_all_pages_have_banner():
    from sqlalchemy.orm import Session

    from app.db import get_engine

    pages = [("home", ()), ("companies", ()), ("vendors", ()), ("bills", ()),
             ("draws", ()), ("sync", ())]
    with Session(get_engine()) as s:
        for fn, extra in pages:
            resp = getattr(dash, fn)(_req(), *extra, session=s)
            assert resp.status_code == 200, fn
            assert SHADOW_BANNER in _html(resp), fn


@pytest.mark.integration
def test_live_draw29_historical_and_post_refused_rolled_back():
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db import get_engine
    from app.models import DrawPackage

    with Session(get_engine()) as s:
        trans = s.begin()
        try:
            d = s.scalars(select(DrawPackage).where(DrawPackage.draw_number == "29")).first()
            if d is None:
                pytest.skip("Draw #29 not present in canonical store")
            detail = service.get_draw_detail(s, d.id)
            assert detail is not None
            assert detail["historical"] is True
            ok, _ = service.assert_postable(detail)
            assert ok is False
            with pytest.raises(service.ShadowGuardError):
                service.transition_draw_status(s, d.id, "approved_for_accounting")
        finally:
            trans.rollback()
