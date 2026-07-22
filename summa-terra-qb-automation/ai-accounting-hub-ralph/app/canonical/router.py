"""FastAPI router for the canonical read layer (CHUNK_3_CANONICAL).

Defines a module-level ``router``; per the isolation contract it must be registered in
app/main.py by the orchestrator (do not wire it here). Does NOT define ``/sync/health`` —
that already exists in app/transport/router.py.

Every response uses the project's standard envelope: ``{"data": ..., "error": ..., "meta": ...}``.
Validation failures (empty/oversized ``q``) return an enveloped 400; unknown ids return an
enveloped 404 — never a bare 500 or FastAPI's default ``{"detail": ...}`` shape.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.canonical import service
from app.db import get_session

router = APIRouter()

# Module-level singleton so the Depends call isn't evaluated in an argument default (ruff B008).
SessionDep = Depends(get_session)


def _ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta or {}}


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message}, "meta": {}},
    )


@router.get("/search")
def search_endpoint(
    q: str = Query(default=""),
    limit: int = Query(default=service.DEFAULT_LIMIT, ge=1, le=service.MAX_LIMIT),
    session: Session = SessionDep,
) -> Any:
    """Unified cross-company search over vendors and bills, namespaced by company_id."""
    try:
        cleaned = service.validate_query(q)
    except service.SearchValidationError as exc:
        return _error(400, "invalid_query", str(exc))

    results = service.search(session, cleaned, limit)
    return _ok(results, {"q": cleaned, "count": len(results)})


@router.get("/vendors/{vendor_id}")
def get_vendor_endpoint(
    vendor_id: str, session: Session = SessionDep
) -> Any:
    """Canonical vendor record including raw_extensions; enveloped 404 if unknown."""
    vendor = service.get_vendor(session, vendor_id)
    if vendor is None:
        return _error(404, "not_found", f"vendor '{vendor_id}' not found")
    return _ok(vendor)


@router.get("/bills/{bill_id}")
def get_bill_endpoint(bill_id: str, session: Session = SessionDep) -> Any:
    """Canonical bill record including raw_extensions; enveloped 404 if unknown."""
    bill = service.get_bill(session, bill_id)
    if bill is None:
        return _error(404, "not_found", f"bill '{bill_id}' not found")
    return _ok(bill)


@router.get("/dashboard")
def dashboard_endpoint(session: Session = SessionDep) -> Any:
    """Per-company synced vendor/bill counts and totals for the operational dashboard."""
    rows = service.dashboard(session)
    return _ok(rows, {"company_count": len(rows)})
