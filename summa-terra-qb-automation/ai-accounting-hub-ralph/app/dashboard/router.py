"""FastAPI router for the operator dashboard (server-rendered HTML, mounted at /ui).

Read routes render the canonical store. Action routes (approve / reject / mark-historical /
resolve-vendor / remap-cost-code) transition canonical status or mappings ONLY — there is no
import of, or call into, the QB transport / QBWC / BillAdd / payment path anywhere in this
package. Shadow mode is shown on every page via the base layout banner.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.dashboard import SHADOW_BANNER, SHADOW_SUBTEXT, modules, service
from app.dashboard import search as dash_search
from app.dashboard import vendor_bills as vb
from app.dashboard import work_queue as wq
from app.db import get_session

router = APIRouter(prefix="/ui", tags=["dashboard"])
SessionDep = Depends(get_session)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.globals["SHADOW_BANNER"] = SHADOW_BANNER
_TEMPLATES.env.globals["SHADOW_SUBTEXT"] = SHADOW_SUBTEXT
_TEMPLATES.env.globals["APP_VERSION"] = __version__
# Static module registry drives the grouped left-nav on every page (no DB needed for nav).
_TEMPLATES.env.globals["WORK_QUEUE_GROUPS"] = modules.grouped_modules()


def _render(request: Request, name: str, ctx: dict, status_code: int = 200) -> Response:
    return _TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)


def _not_found(request: Request, what: str) -> Response:
    return _render(request, "not_found.html", {"what": what}, status_code=404)


# ---------------------------------------------------------------------------
# Read pages
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = SessionDep) -> Response:
    """Work-queue landing — all accounting modules grouped, with live pending counts."""
    return _render(request, "home.html", {"overview": service.work_queue_overview(session)})


@router.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str | None = None, session: Session = SessionDep) -> Response:
    """Cross-entity search (read-only). Empty/short q renders a friendly prompt, not an error."""
    cleaned = dash_search.normalize_query(q)
    if cleaned is None:
        return _render(request, "search.html", {"q": (q or ""), "results": None})
    return _render(request, "search.html",
                   {"q": cleaned, "results": dash_search.search(session, cleaned)})


@router.get("/attention", response_class=HTMLResponse)
def attention(request: Request, session: Session = SessionDep) -> Response:
    """"What needs my attention today" — cross-module action rollup (read-only)."""
    return _render(request, "attention.html", {"attention": service.attention_overview(session)})


@router.get("/queue/{module_key}", response_class=HTMLResponse)
def module_queue(request: Request, module_key: str, session: Session = SessionDep) -> Response:
    """Placeholder work-queue section for a not-yet-wired module. Functional modules redirect
    to their own route. Unknown keys 404. No QuickBooks side effects."""
    m = modules.get_module(module_key)
    if m is None:
        return _not_found(request, "module")
    if m.status == "functional":
        return RedirectResponse(url=m.route, status_code=307)
    related = "/ui/bills" if m.key == "vendor_bills" else None
    return _render(request, "module_placeholder.html", {"m": m, "related": related})


@router.get("/companies", response_class=HTMLResponse)
def companies(request: Request, session: Session = SessionDep) -> Response:
    return _render(request, "companies.html", {"companies": service.list_companies(session)})


@router.get("/companies/{company_id}", response_class=HTMLResponse)
def company_detail(request: Request, company_id: str, session: Session = SessionDep) -> Response:
    company = service.get_company(session, company_id)
    if company is None:
        return _not_found(request, "company")
    return _render(request, "company_detail.html", {
        "company": company,
        "vendors": service.list_vendors(session, company_id),
        "bills": service.list_bills(session, company_id),
        "draws": service.list_draws(session, company_id),
        "candidates": service.list_vendor_candidates(session, company_id),
    })


@router.get("/vendors", response_class=HTMLResponse)
def vendors(request: Request, session: Session = SessionDep) -> Response:
    return _render(request, "vendors.html", {"vendors": service.list_vendors(session)})


@router.get("/vendors/{vendor_id}", response_class=HTMLResponse)
def vendor_detail(request: Request, vendor_id: str, session: Session = SessionDep) -> Response:
    vendor = service.get_vendor(session, vendor_id)
    if vendor is None:
        return _not_found(request, "vendor")
    return _render(request, "vendor_detail.html", {"vendor": vendor})


@router.get("/bills", response_class=HTMLResponse)
def bills(request: Request, session: Session = SessionDep) -> Response:
    return _render(request, "bills.html", {"bills": service.list_bills(session)})


@router.get("/bills/{bill_id}", response_class=HTMLResponse)
def bill_detail(request: Request, bill_id: str, session: Session = SessionDep) -> Response:
    bill = service.get_bill(session, bill_id)
    if bill is None:
        return _not_found(request, "bill")
    return _render(request, "bill_detail.html", {"bill": bill})


@router.get("/vendor-bills", response_class=HTMLResponse)
def vendor_bills_list(request: Request, session: Session = SessionDep, msg: str | None = None) -> Response:
    return _render(request, "vendor_bills.html", {
        "bills": vb.list_vendor_bills(session),
        "companies": service.list_companies(session),
        "msg": msg,
    })


@router.get("/vendor-bills/{bill_id}", response_class=HTMLResponse)
def vendor_bill_detail(
    request: Request, bill_id: str, session: Session = SessionDep, msg: str | None = None,
) -> Response:
    detail = vb.get_vendor_bill(session, bill_id)
    if detail is None:
        return _not_found(request, "vendor bill")
    return _render(request, "vendor_bill_detail.html", {"b": detail, "msg": msg})


@router.get("/draws", response_class=HTMLResponse)
def draws(request: Request, session: Session = SessionDep) -> Response:
    return _render(request, "draws.html", {"draws": service.list_draws(session)})


@router.get("/draws/{draw_id}", response_class=HTMLResponse)
def draw_detail(
    request: Request, draw_id: str, session: Session = SessionDep, msg: str | None = None,
) -> Response:
    detail = service.get_draw_detail(session, draw_id)
    if detail is None:
        return _not_found(request, "draw package")
    return _render(request, "draw_detail.html", {"d": detail, "msg": msg})


@router.get("/sync", response_class=HTMLResponse)
def sync(request: Request, session: Session = SessionDep) -> Response:
    return _render(request, "sync.html", {"sync": service.sync_overview(session)})


@router.get("/system-b", response_class=HTMLResponse)
def system_b(request: Request) -> Response:
    """System B (AI Accounting Hub) read-only bill + draw-package view.

    Renders a client-side page that initialises a *second* Supabase JS client
    against fdnwlcomuddzmluvbylg using the anon RLS key (SELECT-only).
    Credentials are injected as window globals — never hardcoded in HTML.
    Spec refs: spec-stv-integration-layer §6.4 (RLS), §9 (SUPABASE_ANON_KEY_AIHUB),
    Phase 5 dashboard acceptance criterion.
    No DB session needed — all data is fetched client-side via RLS-gated anon key.
    G5 enforced: this route never touches System A DB (ejxrbxoncsgglrqvjulg).
    """
    return _render(request, "system_b.html", {
        # Public anon credentials for System B (fdnwlcomuddzmluvbylg).
        # RLS policies enforce SELECT-only for the anon role (spec §6.4).
        # Values come from env — empty strings if not yet configured.
        "supabase_url_aihub":     settings.supabase_url_aihub,
        "supabase_anon_key_aihub": settings.supabase_anon_key_aihub,
    })


# ---------------------------------------------------------------------------
# Action routes — canonical status / mapping ONLY (no QuickBooks side effects)
# ---------------------------------------------------------------------------
def _draw_redirect(draw_id: str, msg: str) -> Response:
    return RedirectResponse(url=f"/ui/draws/{draw_id}?msg={msg}", status_code=303)


@router.post("/draws/{draw_id}/approve")
def approve_draw(request: Request, draw_id: str, session: Session = SessionDep) -> Response:
    detail = service.get_draw_detail(session, draw_id)
    if detail is None:
        return _not_found(request, "draw package")
    ok, reason = service.assert_postable(detail)
    if not ok:
        return _render(request, "draw_detail.html", {"d": detail, "error": reason}, status_code=400)
    service.transition_draw_status(session, draw_id, "approved_for_accounting")
    return _draw_redirect(draw_id, "approved-for-accounting")


@router.post("/draws/{draw_id}/reject")
def reject_draw(request: Request, draw_id: str, session: Session = SessionDep) -> Response:
    detail = service.get_draw_detail(session, draw_id)
    if detail is None:
        return _not_found(request, "draw package")
    service.transition_draw_status(session, draw_id, "rejected")
    return _draw_redirect(draw_id, "rejected")


@router.post("/draws/{draw_id}/mark-historical")
def mark_historical(request: Request, draw_id: str, session: Session = SessionDep) -> Response:
    detail = service.get_draw_detail(session, draw_id)
    if detail is None:
        return _not_found(request, "draw package")
    service.mark_draw_historical(session, draw_id)
    return _draw_redirect(draw_id, "marked-historical")


@router.post("/vendor-candidates/{candidate_id}/resolve")
async def resolve_candidate(
    request: Request, candidate_id: str, session: Session = SessionDep,
) -> Response:
    form = await request.form()
    vendor_id = str(form.get("vendor_id") or "")
    result = service.resolve_vendor_candidate(session, candidate_id, vendor_id)
    return RedirectResponse(url=f"/ui/vendors/{result['vendor_id']}", status_code=303)


@router.post("/draw-lines/{line_id}/remap-cost-code")
async def remap_cost_code(request: Request, line_id: str, session: Session = SessionDep) -> Response:
    form = await request.form()
    draw_id = str(form.get("draw_id") or "")
    cost_code_id = str(form.get("cost_code_id") or "")
    service.remap_draw_line_cost_code(session, line_id, cost_code_id)
    return _draw_redirect(draw_id, "cost-code-remapped")


# ---------------------------------------------------------------------------
# Vendor Bills actions — intake + canonical status ONLY (no QuickBooks side effects)
# ---------------------------------------------------------------------------
@router.post("/vendor-bills/intake")
async def vendor_bill_intake(request: Request, session: Session = SessionDep) -> Response:
    form = await request.form()

    def _f(key: str) -> str | None:
        v = str(form.get(key) or "").strip()
        return v or None

    result = vb.intake_vendor_bill(
        session,
        company_id=str(form.get("company_id") or ""),
        vendor_name=str(form.get("vendor_name") or ""),
        invoice_no=_f("invoice_no"),
        amount=str(form.get("amount") or "0"),
        due_date=_f("due_date"),
        customer_job=_f("customer_job"),
        class_ref=_f("class_ref"),
        item_cost_code=_f("item_cost_code"),
        bank_detail=_f("bank_detail"),
    )
    if result.get("bill_id"):
        return RedirectResponse(
            url=f"/ui/vendor-bills/{result['bill_id']}?msg=intaken", status_code=303
        )
    return RedirectResponse(
        url="/ui/vendor-bills?msg=vendor-unmatched-candidate-queued", status_code=303
    )


@router.post("/vendor-bills/{bill_id}/{action}")
async def vendor_bill_action(
    request: Request, bill_id: str, action: str, session: Session = SessionDep,
) -> Response:
    if action not in ("approve", "reject", "needs-info"):
        return _not_found(request, "vendor bill action")
    vb.set_vendor_bill_status(session, bill_id, action)
    return RedirectResponse(url=f"/ui/vendor-bills/{bill_id}?msg={action}", status_code=303)


# ---------------------------------------------------------------------------
# Generic work-queue modules (/ui/m/{module_key}) — WorkItem-backed + aggregation views.
# Intake + canonical status ONLY; no QuickBooks side effects anywhere on this path.
# ---------------------------------------------------------------------------
@router.get("/m/{module_key}", response_class=HTMLResponse)
def work_queue_list(
    request: Request, module_key: str, session: Session = SessionDep, msg: str | None = None,
) -> Response:
    # Read-only cross-module aggregation views.
    if module_key == "month_end":
        return _render(request, "month_end.html",
                       {"rows": wq.month_end_exceptions(session), "msg": msg})
    if module_key == "missing_dimensions":
        return _render(request, "missing_dimensions.html",
                       {"rows": wq.missing_dimensions_items(session), "msg": msg})
    m = modules.get_module(module_key)
    if m is None or not wq.is_workitem_module(module_key):
        return _not_found(request, "module")
    return _render(request, "work_queue_list.html", {
        "m": m,
        "items": wq.list_work_items(session, module_key),
        "companies": service.list_companies(session),
        "open_count": wq.work_item_count(session, module_key),
        "bank_module": wq.WORKITEM_MODULES.get(module_key, False),
        "msg": msg,
    })


@router.get("/m/{module_key}/{item_id}", response_class=HTMLResponse)
def work_queue_detail(
    request: Request, module_key: str, item_id: str,
    session: Session = SessionDep, msg: str | None = None,
) -> Response:
    m = modules.get_module(module_key)
    if m is None or not wq.is_workitem_module(module_key):
        return _not_found(request, "module")
    detail = wq.get_work_item(session, item_id)
    if detail is None or detail["module_key"] != module_key:
        return _not_found(request, "work item")
    return _render(request, "work_queue_detail.html", {"m": m, "it": detail, "msg": msg})


@router.post("/m/{module_key}/intake")
async def work_queue_intake(
    request: Request, module_key: str, session: Session = SessionDep,
) -> Response:
    if not wq.is_workitem_module(module_key):
        return _not_found(request, "module")
    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload: dict[str, Any] = (
        dict(await request.json()) if is_json else {k: v for k, v in (await request.form()).items()}
    )

    def _g(key: str) -> str | None:
        v = payload.get(key)
        s = str(v).strip() if v is not None else ""
        return s or None

    result = wq.intake_work_item(
        session,
        module_key,
        company_id=str(payload.get("company_id") or ""),
        title=(_g("title") or "(untitled)"),
        reference=_g("reference"),
        counterparty=_g("counterparty"),
        amount=payload.get("amount"),
        txn_date=_g("txn_date"),
        project_ref=_g("project_ref"),
        customer_job=_g("customer_job"),
        class_ref=_g("class_ref"),
        item_cost_code=_g("item_cost_code"),
        bank_detail=_g("bank_detail"),
    )
    if is_json:
        return JSONResponse({"data": result})
    return RedirectResponse(
        url=f"/ui/m/{module_key}/{result['item_id']}?msg=intaken", status_code=303
    )


@router.post("/m/{module_key}/{item_id}/{action}")
async def work_queue_action(
    request: Request, module_key: str, item_id: str, action: str,
    session: Session = SessionDep,
) -> Response:
    if not wq.is_workitem_module(module_key):
        return _not_found(request, "module")
    if action not in ("approve", "reject", "needs-info"):
        return _not_found(request, "work item action")
    wq.set_work_item_status(session, item_id, action)
    return RedirectResponse(url=f"/ui/m/{module_key}/{item_id}?msg={action}", status_code=303)
