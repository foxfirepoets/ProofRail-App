"""FastAPI entrypoint. CHUNK_1 exposes only health/readiness.

Later chunks register their routers here (transport, intents, verify, payments).
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.canonical.router import router as canonical_router
from app.dashboard.router import router as dashboard_router
from app.db import get_engine
from app.integration.approval_ui import router as approval_ui_router
from app.integration.intents_router import router as intents_router
from app.payments.router import router as payments_router
from app.scale.router import router as scale_router
from app.transport.router import router as transport_router
from app.workflow.router import router as workflow_router

app = FastAPI(title="AI Accounting Hub", version=__version__)

# ---------------------------------------------------------------------------
# CORS — explicit allowlist; never allow wildcard on an app with write endpoints.
# Override the default origin via CORS_ALLOWED_ORIGIN env var for each deployment.
# ---------------------------------------------------------------------------
_cors_origin = os.environ.get(
    "CORS_ALLOWED_ORIGIN",
    "https://your-dashboard.railway.app",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_cors_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


# ---------------------------------------------------------------------------
# Generic 500 handler — never leak internal exception messages to callers.
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def _generic_500_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: return a generic 500 body so internal details never reach the client."""
    import logging

    logging.getLogger(__name__).exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
    )


# CHUNK_2_TRANSPORT — QBWC SOAP endpoint (/qbwc) + sync health (/sync/health).
# Absolute paths per SPEC §10; no prefix.
app.include_router(transport_router)

# CHUNK_3_CANONICAL — unified cross-company search + read API.
# /search, /vendors/{id}, /bills/{id}, /dashboard. Absolute paths; no prefix.
app.include_router(canonical_router)

# CHUNK_5_WORKFLOW — async intent pipeline + human-approval commit boundary
# (generic capability-token pipeline, e.g. app.scale.pipeline).
# POST /intents, POST /workflow/approvals/{workflow_id}. Absolute paths; no prefix.
# NOTE: the literal spec path POST /approvals/{workflow_id} is NOT this router —
# see app/integration/intents_router.py (registered below) and Fix 3 of
# spec-compliance-audit-stv-integration-layer-2026-06-30.md.
app.include_router(workflow_router)

# CHUNK_7_PAYMENTS — InvoiceProof (Gate 1) + ATEP bank-change (Gate 4) + OCR intake.
# POST /ap/intake, GET /bills/{bill_id}/proof. Absolute paths; no prefix.
app.include_router(payments_router)

# CHUNK_8_SCALE — 10-company sync + QBO adapter seam + end-to-end pipeline.
# GET /sync/companies. Absolute paths; no prefix.
app.include_router(scale_router)

# DASHBOARD — Accounting Work Queue / Operator Dashboard (FinalSpec Phase 1).
# Server-rendered HTML at /ui. Read-mostly; actions transition canonical status ONLY.
# Shadow mode is absolute — no QBWC write-back, BillAdd, or payment path is reachable.
app.include_router(dashboard_router)

# INTEGRATION — STV outbox → System B intent pipeline (spec-stv-integration-layer §12).
# POST /intents/bill, /intents/draw, /intents/bank-block, /intents/payment-confirmed
# (all fully implemented — not stubs) + POST /approvals/{workflow_id} (the canonical
# spec path for the dual-auth human-approval gate; see Fix 3). Bearer AIHUB_OUTBOX_TOKEN
# (or BEN_SESSION_TOKEN for /approvals) auth on every route. Absolute paths; no prefix.
app.include_router(intents_router)

# APPROVAL UI — Human operator approval queue (spec §5 Flow 2, Phase 2).
# GET /approve  — lists verified bills pending manual approval.
# POST /approve/{workflow_id} — processes a manual approval with required note.
# No bearer token (operator UI; auth at infrastructure layer).  Gate 1 + G4 enforced.
app.include_router(approval_ui_router)

# NOTE: callback_router.py (POST /integration/bill-synced) is intentionally NOT
# registered here. It is a System A reference implementation that must be deployed
# on the System A Railway service (ejxrbxoncsgglrqvjulg), NOT on System B.
# See app/integration/callback_router.py module docstring for deployment instructions.


@app.get("/health")
def health() -> dict:
    """Liveness — process is up. Does not touch the database."""
    return {"status": "ok", "version": __version__}


@app.get("/ready")
def ready() -> dict:
    """Readiness — confirms a live connection to the Supabase canonical store."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready", "canonical_store": "connected"}
