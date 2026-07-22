"""Operator approval UI — GET /approve (list verified bills) + POST /approve/{workflow_id}.

Auth: Bearer APPROVAL_UI_TOKEN (env var). Callers must supply this in the Authorization
header. An unset or empty token env var results in 401 for every request — no route
is ever accessible without a valid token. The operator browser (internal network / VPN)
must inject the token via a reverse proxy Authorization header or a JS fetch header.

Must-not-break guarantees enforced here:

  G4  No automated approvals — form POST requires a human reason note (min 10 chars,
      validated both client-side and server-side).  The endpoint never self-approves.
  G6  Proof bundle gate checked before advancing bill status → 'approved' (fails closed:
      missing or un-passed bundle returns an error page, never silently approves).
  G7  No QBWC write initiated — only bill.status in the canonical store is advanced.
  G2  bank_change_risk flag surfaced in the UI table; rows with bank_change_risk=True
      are labelled BLOCKED and their Approve button is disabled. NULL bank_change_risk
      (missing proof field) is treated as True — fails closed.

Database: System B only (fdnwlcomuddzmluvbylg) via app.db.get_session.
Rendering: Jinja2 template at app/dashboard/templates/approve.html (extends base.html).
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.dashboard import SHADOW_BANNER, SHADOW_SUBTEXT, modules
from app.db import get_session
from app.integration.intents_router import _fire_bill_synced_callback, _resolve_bill_approval

router = APIRouter(tags=["approval-ui"])
SessionDep = Depends(get_session)

_TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "dashboard" / "templates")
)
# Inject the same globals that dashboard/router.py sets so base.html renders correctly.
_TEMPLATES.env.globals["SHADOW_BANNER"] = SHADOW_BANNER
_TEMPLATES.env.globals["SHADOW_SUBTEXT"] = SHADOW_SUBTEXT
_TEMPLATES.env.globals["APP_VERSION"] = __version__
_TEMPLATES.env.globals["WORK_QUEUE_GROUPS"] = modules.grouped_modules()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _ui_token() -> str:
    """Read APPROVAL_UI_TOKEN from the environment."""
    return os.environ.get("APPROVAL_UI_TOKEN", "")


def _require_ui_auth(authorization: str = Header(default="")) -> None:
    """FastAPI dependency: validate Bearer APPROVAL_UI_TOKEN.

    Raises HTTPException 401 immediately if the token is absent, empty, or wrong.
    This fires before any handler logic — no partial processing on auth failure.
    """
    expected = _ui_token()
    scheme, _, token = authorization.partition(" ")
    if (
        not expected
        or scheme.lower() != "bearer"
        or not token
        or token != expected
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing APPROVAL_UI_TOKEN bearer token",
        )


_AuthDep = Depends(_require_ui_auth)


# ---------------------------------------------------------------------------
# Data query — bills WHERE status='verified'
# ---------------------------------------------------------------------------

def _fetch_verified_bills(session: Session) -> list[dict[str, Any]]:
    """Return bills with status='verified', joined to vendor name.

    Fields extracted from raw_extensions JSONB:
      - project_label     → project column
      - workflow_id       → used for the POST /approve/{workflow_id} action
      - gmail_invoiceproof.final_decision → mike_email_detected derivation
      - gmail_invoiceproof.bank_change_risk → surface BLOCKED flag
    """
    rows = session.execute(
        text(
            """
            SELECT
                b.id                                                AS bill_id,
                b.amount,
                b.status,
                b.created_at                                        AS draft_date,
                b.invoiceproof_bundle_id,
                b.raw_extensions,
                v.name                                              AS vendor_name,
                b.raw_extensions->>'workflow_id'                    AS workflow_id,
                b.raw_extensions->>'project_label'                  AS project_label,
                b.raw_extensions->'gmail_invoiceproof'->>'final_decision'
                                                                    AS invoiceproof_decision,
                (b.raw_extensions->'gmail_invoiceproof'->>'bank_change_risk')::boolean
                                                                    AS bank_change_risk
            FROM bills b
            JOIN vendors v ON v.id = b.vendor_id
            WHERE b.status = 'verified'
            ORDER BY b.created_at DESC
            """
        )
    ).mappings().all()

    result: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row["mike_email_detected"] = row.get("invoiceproof_decision") == "approved"
        row["proof_status"] = (
            "Gate 1 passed" if row.get("invoiceproof_bundle_id") else "Gate 1 pending"
        )
        row["bank_change_risk"] = bool(row.get("bank_change_risk"))
        # Normalise draft_date to a YYYY-MM-DD string regardless of DB driver type.
        d = row.get("draft_date")
        if isinstance(d, _dt.date | _dt.datetime):
            row["draft_date_str"] = d.strftime("%Y-%m-%d")
        elif d is not None:
            row["draft_date_str"] = str(d)[:10]
        else:
            row["draft_date_str"] = ""
        result.append(row)
    return result


# ---------------------------------------------------------------------------
# GET /approve — list verified bills
# ---------------------------------------------------------------------------

@router.get("/approve")
def approval_queue(
    request: Request,
    msg: str | None = None,
    session: Session = SessionDep,
    _auth: None = _AuthDep,
) -> Response:
    """Human-approval queue: shows all bills with status='verified'."""
    bills = _fetch_verified_bills(session)
    return _TEMPLATES.TemplateResponse(
        request, "approve.html", {"bills": bills, "msg": msg}
    )


# ---------------------------------------------------------------------------
# POST /approve/{workflow_id} — process manual approval
# ---------------------------------------------------------------------------

@router.post("/approve/{workflow_id}")
async def approve_bill(
    request: Request,
    workflow_id: str,
    background_tasks: BackgroundTasks,
    note: str = Form(default=""),
    session: Session = SessionDep,
    _auth: None = _AuthDep,
) -> Response:
    """Process a manual approval submitted from the /approve operator UI.

    Server-side enforcement of all must-not-break guarantees:
      G4  Requires explicit human note (min 10 chars) — no automated approvals.
      G6  Proof bundle must exist and have passed=True (Gate 1 fails closed).
      G7  No QBWC write; only bill.status → 'approved' in canonical store.
      G2  bank_change_risk re-checked here as defence in depth (UI-only guard —
          the JSON API path does not recheck it; see Fix 4 report).

    Fix 4 (spec-compliance-audit-stv-integration-layer-2026-06-30.md): the actual
    approve/reject state transition — engine signal, bill status update, AIVS
    audit_rows ('approval_signal_received', 'bill_approved'), and the AuditProof
    canonical commit — is delegated to ``intents_router._resolve_bill_approval``,
    the SAME function ``POST /approvals/{workflow_id}`` uses. A bill approved
    from this UI now gets an IDENTICAL audit trail to one approved via the JSON
    API — this handler no longer does a bare
    ``UPDATE bills SET status='approved'`` with no audit chain.

    On success: redirects to /approve?msg=approved.
    On any gate failure: redirects to /approve?msg=<reason> (never silently passes).
    """
    # --- G4: server-side note length validation (min 10 chars) ------------------
    if not note or len(note.strip()) < 10:
        return RedirectResponse(url="/approve?msg=note-too-short", status_code=303)

    # --- Locate bill by workflow_id (stored in raw_extensions at create time) ---
    # This UI-only lookup exists solely to run the G2 bank_change_risk pre-check
    # below, which _resolve_bill_approval does not perform (see its docstring).
    bill_row = session.execute(
        text(
            """
            SELECT id, status, invoiceproof_bundle_id,
                   (raw_extensions->'gmail_invoiceproof'->>'bank_change_risk')::boolean
                       AS bank_change_risk,
                   raw_extensions->>'gmail_tracker_id' AS gmail_tracker_id
            FROM bills
            WHERE raw_extensions->>'workflow_id' = :wf_id
            LIMIT 1
            """
        ),
        {"wf_id": workflow_id},
    ).mappings().first()

    if bill_row is None:
        return RedirectResponse(url="/approve?msg=bill-not-found", status_code=303)

    # --- Idempotency: already approved → safe redirect -------------------------
    if bill_row["status"] == "approved":
        return RedirectResponse(url="/approve?msg=already-approved", status_code=303)

    # --- G2: bank_change_risk re-check — fails closed (defence in depth) -------
    # NULL means the proof field is absent, which is itself a gate failure.
    # True means the risk was detected. Both must block approval.
    bcr = bill_row.get("bank_change_risk")
    if bcr is None or bcr is True:
        return RedirectResponse(url="/approve?msg=bank-risk-blocked", status_code=303)

    # --- Shared approve logic (Fix 4) — identical audit trail to the JSON API ---
    outcome = _resolve_bill_approval(
        session,
        workflow_id=workflow_id,
        decision="approve",
        source="manual_ui",
        note=note.strip(),
        evidence_email_id=None,
    )

    if outcome.code == "BILL_NOT_FOUND":
        return RedirectResponse(url="/approve?msg=bill-not-found", status_code=303)
    if outcome.code == "IDEMPOTENT":
        return RedirectResponse(url="/approve?msg=already-approved", status_code=303)
    if outcome.code == "PROOF_BUNDLE_MISSING":
        return RedirectResponse(url="/approve?msg=proof-missing", status_code=303)
    if outcome.code == "PROOF_BUNDLE_NOT_PASSED":
        return RedirectResponse(url="/approve?msg=proof-not-passed", status_code=303)

    # --- outcome.code == "OK" (approved) ----------------------------------------
    # Fire System B → System A callback (Fix 8 — scheduled on background_tasks so
    # it never blocks this response). Advances payment_request_tracker.aihub_status
    # → 'synced' on System A.
    _fire_bill_synced_callback(
        background_tasks, outcome.tracker_id, outcome.bill_id or "", "approved"
    )

    return RedirectResponse(url="/approve?msg=approved", status_code=303)
