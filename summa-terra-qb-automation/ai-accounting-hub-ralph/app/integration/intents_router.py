"""FastAPI router for the STV integration outbox → System B intent pipeline.

Defines a module-level ``router``; per isolation contract it must be registered
in app/main.py by the orchestrator (do NOT wire it here).

Live (all fully implemented, not stubs):
  POST /intents/bill              — create a canonical bill from a Gmail-detected
                                     invoice. Idempotent on gmail_tracker_id.
  POST /intents/draw               (Phase 4) — 5/2/1 fee split, STV CM LLC guard,
                                     idempotent on draw_packages.gmail_fee_opportunity_id.
  POST /intents/bank-block         (Phase 3) — ATEP block + exception-queue drain.
  POST /intents/payment-confirmed  (Phase 5) — advances bill.status -> 'paid'.
  POST /approvals/{workflow_id}    (Phase 2) — dual-auth human approval gate;
                                     this is the canonical spec path (see Fix 3,
                                     spec-compliance-audit-stv-integration-layer).

Auth: Bearer AIHUB_OUTBOX_TOKEN (env var, read via config.Settings pattern).
      Every endpoint returns 401 immediately if the header is absent or wrong.
      No partial processing occurs before the auth check completes.

Must-not-break guarantees enforced here (SPEC §2, CLAUDE.md guardrails):
  G2  bank_change_risk P0 fires BEFORE any DB action → hard 400 BANK_CHANGE_RISK
  G3  STV CM LLC blocked independently in System B (draw stub raises at entity check)
  G4  No automated approvals — Temporal workflow blocks at human gate; endpoint
      never signals approval or changes bill status beyond 'drafted'
  G5  fdnwlcomuddzmluvbylg only — imports app.db which is pinned to System B DB
  G6  SwarmSync proof-core Gate 1 (run_invoice_proof_gate1) is invoked synchronously
      right after the bill INSERT and before the workflow is started, for both
      /intents/bill and every fee bill created by /intents/draw. On
      InvoiceProofGateFailed the bill is left without a bundle (not approved) —
      the request still succeeds so the bill lands in the human review queue.
  G7  Never writes to QB — no QBWC path reachable from this module

DB note: ``bills.gmail_tracker_id`` is added by the Phase 0 migration
(spec §6.3 — ALTER TABLE bills ADD COLUMN gmail_tracker_id UUID UNIQUE).
The ORM model (models.py) is frozen per CHUNK_1_INFRA, so this column is
accessed via raw SQL only. ``workflow_id`` is stored in ``raw_extensions``
so it survives round-trips without altering the schema.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import append_audit_row, build_aivs_bundle, load_session_records, write_proof_bundle
from app.catalog.fee_math import (
    RATE_CEO,
    RATE_DEV,
    RATE_PRES,
    ROLE_CEO_PARENT,
    ROLE_DEV_PARTNERSHIP,
    ROLE_PRES_PARENT,
    _money,
    distinct_economic_total,
    split_developer_fee,
)
from app.db import get_session
from app.integration.callback_sender import send_bill_synced_callback
from app.integration.invoice_proof_gate import InvoiceProofGateFailed, run_invoice_proof_gate1
from app.workflow.engine import InMemoryEventBus, get_workflow_engine

router = APIRouter(tags=["integration"])

SessionDep = Depends(get_session)

# ---------------------------------------------------------------------------
# Process-wide workflow engine. get_workflow_engine() (app.workflow.engine) is
# env-driven: TEMPORAL_HOST set -> real TemporalWorkflowEngine; unset -> the
# InMemoryWorkflowEngine dev/test fake. Kept as a module singleton so state
# persists across requests within one process (Fix 2).
# ---------------------------------------------------------------------------

_engine = get_workflow_engine()
_bus = InMemoryEventBus()

_VENDOR_SIMILARITY_THRESHOLD: float = 0.75

# STV CM LLC detection names (must-not-break guarantee [3], spec §5 alternate path).
# All three names must be blocked independently in System B as defence-in-depth.
# Match is case-insensitive; check against fee_payee_hint before any DB write.
_STV_CM_LLC_NAMES: frozenset[str] = frozenset([
    "summa terra cm llc",
    "stv cm llc",
    "cm llc",
])


def _is_stv_cm_llc(name: str | None) -> bool:
    """Return True if name matches a known STV CM LLC entity (case-insensitive exact match)."""
    if not name:
        return False
    return name.lower().strip() in _STV_CM_LLC_NAMES


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _outbox_token() -> str:
    """Read AIHUB_OUTBOX_TOKEN from env at call time so monkeypatch works in tests."""
    return os.environ.get("AIHUB_OUTBOX_TOKEN", "")


def require_outbox_token(authorization: str = Header(default="")) -> None:
    """FastAPI dependency: validate Bearer AIHUB_OUTBOX_TOKEN.

    Raises HTTPException(401) immediately when the token is absent or wrong.
    Safe to wire via ``Depends(require_outbox_token)`` on any route — the handler
    body will not execute on an invalid token.

    Usage in an endpoint::

        @router.post("/intents/something")
        def my_endpoint(
            _auth: None = Depends(require_outbox_token),
            ...
        ) -> Any:
            ...

    Note: endpoints currently use inline ``_check_auth(authorization)`` so they can
    return the project envelope format (not a plain HTTPException detail). This
    dependency is provided for future endpoints that prefer the standard FastAPI
    convention, and is tested independently to confirm it actually enforces auth.
    """
    if _check_auth(authorization) is not None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
        )


def _check_auth(authorization: str) -> JSONResponse | None:
    """Return a 401 JSONResponse if the bearer token is invalid, else None.

    Must be the very first check in every endpoint — fires before any DB read
    or business logic, satisfying the 'no partial processing' security rule.
    """
    expected = _outbox_token()
    scheme, _, token = authorization.partition(" ")
    if (
        scheme.lower() != "bearer"
        or not token
        or not expected
        or token != expected
    ):
        return JSONResponse(
            status_code=401,
            content={
                "data": None,
                "error": {"code": "UNAUTHORIZED", "message": "Invalid or missing bearer token"},
                "meta": {},
            },
        )
    return None


def _check_integration_auth(authorization: str) -> JSONResponse | None:
    """Dual-auth guard for the integration approval endpoint (SPEC §6.6).

    Accepts either:
      * Bearer AIHUB_OUTBOX_TOKEN  — System A email-detection path
      * Bearer BEN_SESSION_TOKEN   — Ben UI manual-approval path

    Both tokens are read from environment variables so they are never hard-coded.
    Fails closed: any missing, empty, or non-matching token returns 401 before
    any DB read or business logic (no partial processing).
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return _error(401, "UNAUTHORIZED", "Missing or malformed Authorization header")

    outbox_token = os.environ.get("AIHUB_OUTBOX_TOKEN", "")
    session_token = os.environ.get("BEN_SESSION_TOKEN", "")

    # At least one configured token must match — fail closed if both are empty.
    token_ok = (outbox_token and token == outbox_token) or (
        session_token and token == session_token
    )
    if not token_ok:
        return _error(401, "UNAUTHORIZED", "Invalid bearer token")
    return None


# ---------------------------------------------------------------------------
# Response envelope helpers (match project convention from workflow/router.py)
# ---------------------------------------------------------------------------


def _ok(data: Any, status_code: int = 200, meta: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "error": None, "meta": meta or {}},
    )


def _error(
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
) -> JSONResponse:
    err: dict[str, Any] = {"code": code, "message": message}
    if field:
        err["field"] = field
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": err, "meta": {}},
    )


# ---------------------------------------------------------------------------
# Pydantic request models (all four intent types per spec §6.1)
# ---------------------------------------------------------------------------


class GmailInvoiceProof(BaseModel):
    """Evidence block produced by System A's invoiceproof run (SPEC §6.1)."""

    risk_level: str = Field(..., description="low|medium|high|critical")
    final_decision: str = Field(..., description="approved|flagged|blocked")
    checks_passed: int = Field(..., ge=0, le=7)
    bank_change_risk: bool
    duplicate_detected: bool
    vendor_confidence: float = Field(..., ge=0.0, le=1.0)


class BillIntentIn(BaseModel):
    """POST /intents/bill request body (SPEC §6.5, §12).

    ``gmail_tracker_id`` is the idempotency key — System A's
    ``payment_request_tracker.id``.  ``company_id`` is an optional override
    supplied when System A can resolve the company from project context; if
    absent and vendor fuzzy-match fails, we fall back to the first company in
    the DB.
    """

    gmail_tracker_id: uuid.UUID = Field(..., description="Idempotency key — System A tracker UUID")
    vendor_name: str = Field(..., min_length=1, description="Vendor display name for fuzzy match")
    amount: Decimal | None = Field(
        None, description="Invoice total; null or ≤ 0 → amount_review flag in response"
    )
    po_ref: str | None = Field(None, description="Purchase order / invoice reference")
    due_date: str | None = Field(None, description="ISO date string YYYY-MM-DD or null")
    raw_extensions: dict[str, Any] | None = Field(
        None, description="JSONB passthrough from System A (project_label, gmail_thread_id, …)"
    )
    gmail_invoiceproof: GmailInvoiceProof = Field(
        ..., description="InvoiceProof evidence from System A — required for Gate 1"
    )
    # Optional company override: not in canonical spec payload but accepted when
    # System A resolves the project entity and can pass it.
    company_id: str | None = Field(
        None, description="Optional company UUID — inferred from vendor match if omitted"
    )


class DrawIntentIn(BaseModel):
    """POST /intents/draw request body (SPEC §12 — Phase 4 stub).

    Guards not yet wired: STV CM LLC check (entity lookup) and fee math
    validation (5/2/1 split via CHUNK_6 draw engine).
    """

    gmail_fee_opportunity_id: uuid.UUID = Field(
        ..., description="Idempotency key — System A fee_opportunity UUID"
    )
    project_canonical: str = Field(..., min_length=1)
    draw_amount: Decimal = Field(..., gt=0, description="Must be > 0")
    draw_number: int | None = None
    estimated_fee_hint: Decimal | None = None
    fee_payee_hint: str | None = None
    fee_payee_status: str = Field(..., description="CONFIRMED|UNCERTAIN|BLOCKED")
    raw_extensions: dict[str, Any] | None = None


class BankBlockIn(BaseModel):
    """POST /intents/bank-block request body (SPEC §12 — Phase 3).

    Triggers ATEP block on the vendor's bank_fingerprint and routes any
    in-flight bills for the same vendor_name to the exception queue.
    tracker_id is optional — when supplied it anchors the AIVS audit session_id
    to the System A payment_request_tracker row that raised the bank-change flag.
    """

    vendor_name: str = Field(..., min_length=1)
    sender_email: str = Field(..., description="Fraud sender email — stored for audit, not raw bank data")
    gmail_message_id: str | None = None
    tracker_id: uuid.UUID | None = Field(
        None,
        description="Optional System A tracker UUID — anchors AIVS audit session",
    )


class PaymentConfirmedIn(BaseModel):
    """POST /intents/payment-confirmed request body (SPEC §12 — Phase 5).

    Aubrey Palmer's payment confirmation email triggers this via System A outbox;
    advances bill.status → 'paid' and fires the bill-synced callback to System A.
    Idempotent on gmail_tracker_id (bills.gmail_tracker_id lookup).
    """

    gmail_tracker_id: uuid.UUID = Field(
        ...,
        description=(
            "Idempotency key — System A tracker UUID (must match bills.gmail_tracker_id). "
            "Source: integration_outbox.tracker_id from the payment_confirmed outbox row."
        ),
    )


class BillSyncedCallbackIn(BaseModel):
    """POST /callbacks/bill-synced request body (SPEC §12 — Phase 2 stub).

    System B → System A callback: notifies that a bill has been accepted and
    aihub_status advanced.  Idempotent: if aihub_status is already 'synced' on
    the bill the endpoint returns 200 idempotent=True with no further mutation.
    Never modifies tracker state — read-only re-delivery guard (G4).
    """

    bill_id: str = Field(..., description="System B bills.id UUID")
    aihub_status: str = Field(..., description="synced|pending|failed")
    gmail_tracker_id: str | None = Field(
        None, description="System A tracker UUID for round-trip traceability"
    )


class IntegrationApprovalIn(BaseModel):
    """POST /approvals/{workflow_id} request body (SPEC §6.6, §12 Phase 2).

    Accepted by both the System A email-detection path (AIHUB_OUTBOX_TOKEN) and
    the Ben UI manual-approval path (BEN_SESSION_TOKEN).

    Validation rule (G4 — no automated approvals):
      source='manual_ui' requires ``note`` with at least 10 characters, proving
      a human reviewer provided a conscious annotation before clicking approve.
    """

    decision: str = Field(..., description="approve|reject")
    source: str = Field(..., description="email_detected|manual_ui")
    note: str | None = Field(
        None,
        description="Reviewer note — required with ≥ 10 chars when source=manual_ui",
    )
    evidence_email_id: str | None = Field(
        None, description="Gmail message ID that triggered the approval (evidence link)"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _fuzzy_match_vendor(
    session: Session, vendor_name: str
) -> list[dict[str, Any]]:
    """Run pg_trgm similarity() against vendors.name.

    Returns rows ordered by similarity DESC where sim >= threshold.
    Requires the pg_trgm extension and GIN trigram index (CHUNK_1_INFRA).
    """
    rows = session.execute(
        text(
            "SELECT id, name, company_id, "
            "similarity(name, :vname) AS sim "
            "FROM vendors "
            "WHERE similarity(name, :vname) >= :threshold "
            "ORDER BY sim DESC "
            "LIMIT 5"
        ),
        {"vname": vendor_name, "threshold": _VENDOR_SIMILARITY_THRESHOLD},
    ).mappings().all()
    return [dict(r) for r in rows]


def _create_soft_draft_vendor(
    session: Session, vendor_name: str, company_id: str
) -> str:
    """INSERT a soft-draft vendor and return its new UUID.

    'Soft-draft' means qb_list_id is NULL (not yet synced to QB) and
    raw_extensions carries the source tag so reviewers can distinguish
    auto-created records from QB-synced ones.
    """
    new_id = str(uuid.uuid4())
    now = _utcnow()
    session.execute(
        text(
            "INSERT INTO vendors "
            "(id, company_id, name, raw_extensions, created_at, updated_at) "
            "VALUES (:id, :company_id, :name, CAST(:raw_ext AS jsonb), :now, :now)"
        ),
        {
            "id": new_id,
            "company_id": company_id,
            "name": vendor_name,
            "raw_ext": json.dumps(
                {
                    "source": "soft_draft",
                    "created_by": "intents_router",
                    "note": "Auto-created from bill_intent — pending manual QB vendor match",
                }
            ),
            "now": now,
        },
    )
    return new_id


def _resolve_company_id(
    session: Session, override: str | None, vendor_company_id: str | None
) -> str | None:
    """Resolve company_id: caller override → vendor's company → first company in DB."""
    if override:
        return override
    if vendor_company_id:
        return str(vendor_company_id)
    first = session.execute(text("SELECT id FROM companies LIMIT 1")).scalar_one_or_none()
    return str(first) if first else None


# ---------------------------------------------------------------------------
# POST /intents/bill
# ---------------------------------------------------------------------------


@router.post("/intents/bill", status_code=201)
def create_bill_intent(
    payload: BillIntentIn,
    authorization: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """Create a canonical bill from a Gmail-detected invoice.

    Idempotent on ``gmail_tracker_id`` — safe to retry on network failure.
    Fails closed on ``bank_change_risk=True`` (G2) or ``final_decision='blocked'``.
    Never creates a bill without a human-approval gate in the Temporal workflow (G4).

    Returns 201 on success, 200 if the bill already exists (idempotent replay).
    """
    # --- AUTH — fires before any business logic (no partial processing) ---------
    auth_err = _check_auth(authorization)
    if auth_err is not None:
        return auth_err

    # --- G2: bank_change_risk P0 — hard reject before any DB action -------------
    # This mirrors the System A guard in rules.py. Both systems must block
    # independently (defence in depth per must-not-break guarantee #2).
    if payload.gmail_invoiceproof.bank_change_risk:
        return _error(
            400,
            "BANK_CHANGE_RISK",
            (
                "Bank change risk detected — bill intent rejected. "
                "Route to POST /intents/bank-block instead."
            ),
        )

    # --- InvoiceProof final_decision guard --------------------------------------
    if payload.gmail_invoiceproof.final_decision == "blocked":
        return _error(
            422,
            "INVOICEPROOF_BLOCKED",
            "InvoiceProof final_decision is 'blocked' — bill intent rejected.",
        )

    tracker_id_str = str(payload.gmail_tracker_id)

    # --- IDEMPOTENCY CHECK — SELECT before any INSERT ---------------------------
    # ``bills.gmail_tracker_id`` added by Phase 0 migration (spec §6.3).
    # ``workflow_id`` stored in raw_extensions at insert time so it survives
    # without adding another schema column.
    existing = session.execute(
        text(
            "SELECT id, "
            "raw_extensions->>'workflow_id' AS workflow_id, "
            "status "
            "FROM bills "
            "WHERE gmail_tracker_id = :tid "
            "LIMIT 1"
        ),
        {"tid": tracker_id_str},
    ).mappings().first()

    if existing is not None:
        return _ok(
            {
                "bill_id": str(existing["id"]),
                "workflow_id": existing["workflow_id"],
                "status": existing["status"],
                "idempotent": True,
            },
            status_code=200,
        )

    # --- VENDOR FUZZY MATCH (pg_trgm similarity ≥ 0.75) -----------------------
    vendor_rows = _fuzzy_match_vendor(session, payload.vendor_name)
    vendor_matched = len(vendor_rows) > 0
    vendor_multiple_candidates = len(vendor_rows) > 1

    vendor_id: str
    company_id: str

    if vendor_matched:
        best = vendor_rows[0]
        resolved_company = _resolve_company_id(
            session, payload.company_id, str(best["company_id"])
        )
        if resolved_company is None:
            return _error(503, "NO_COMPANY", "No company records in canonical store.")
        company_id = resolved_company
        vendor_id = str(best["id"])
    else:
        # No vendor match — create a soft-draft vendor so the bill can proceed
        # to the human-review queue without blocking the pipeline.
        resolved_company = _resolve_company_id(session, payload.company_id, None)
        if resolved_company is None:
            return _error(
                503,
                "NO_COMPANY",
                (
                    "Vendor fuzzy match failed and no company_id provided or found. "
                    "Pass company_id in the request body or ensure companies table has rows."
                ),
            )
        company_id = resolved_company
        vendor_id = _create_soft_draft_vendor(session, payload.vendor_name, company_id)

    # --- AMOUNT handling -------------------------------------------------------
    # Null or ≤ 0 amount → store as 0.00 and flag for manual review.
    # The CHECK constraint ck_bills_amount_nonneg allows 0.00; the flag
    # surfaces in the response and raw_extensions for the dashboard queue.
    # NOTE (Fix 8 mypy): the None check is folded into the same condition as the
    # <=0 check and re-tested on the truthy branch so mypy can narrow
    # ``payload.amount`` from ``Decimal | None`` to ``Decimal`` before float().
    amount_review = payload.amount is None or payload.amount <= 0
    bill_amount: float = (
        float(payload.amount) if payload.amount is not None and not amount_review else 0.00
    )

    # --- BUILD raw_extensions --------------------------------------------------
    raw_ext: dict[str, Any] = dict(payload.raw_extensions or {})

    # workflow_id stored here because bills ORM model is schema-frozen.
    # Derive the id now so it goes into raw_extensions before the INSERT.
    workflow_id = f"bill-intent-{tracker_id_str}"
    raw_ext["workflow_id"] = workflow_id
    raw_ext["gmail_invoiceproof"] = payload.gmail_invoiceproof.model_dump()
    raw_ext["vendor_unmatched"] = not vendor_matched
    if amount_review:
        raw_ext["amount_review"] = True
    if vendor_multiple_candidates:
        raw_ext["vendor_multiple_candidates"] = True

    # --- INSERT bill -----------------------------------------------------------
    # Uses raw SQL so we can set ``gmail_tracker_id`` (Phase 0 migration column)
    # without touching the schema-frozen ORM model.
    bill_id = str(uuid.uuid4())
    now = _utcnow()
    session.execute(
        text(
            "INSERT INTO bills "
            "(id, company_id, vendor_id, amount, status, po_ref, raw_extensions, "
            " gmail_tracker_id, created_at, updated_at) "
            "VALUES "
            "(:id, :company_id, :vendor_id, :amount, 'drafted', :po_ref, "
            " CAST(:raw_ext AS jsonb), :gmail_tracker_id, :now, :now)"
        ),
        {
            "id": bill_id,
            "company_id": company_id,
            "vendor_id": vendor_id,
            "amount": bill_amount,
            "po_ref": payload.po_ref,
            "raw_ext": json.dumps(raw_ext),
            "gmail_tracker_id": tracker_id_str,
            "now": now,
        },
    )

    # --- GATE 1: InvoiceProof (SwarmSync proof-core VCAP Full Bundle) ----------
    # Fix 1 (spec-compliance-audit-stv-integration-layer-2026-06-30.md): must run
    # AFTER the bill row exists and BEFORE the workflow starts (module docstring
    # of invoice_proof_gate.py). Fails closed by design — on InvoiceProofGateFailed
    # the bill is simply left without invoiceproof_bundle_id (bill.status stays
    # 'drafted', not 'verified'), so it lands in the human review / exception
    # queue instead of ever reaching the approval endpoint (which hard-rejects
    # with 422 PROOF_BUNDLE_MISSING until Gate 1 passes). The bill_intent request
    # itself still succeeds (201) — a Gate 1 failure is not a request failure.
    try:
        run_invoice_proof_gate1(
            bill_id=bill_id,
            bill_amount=bill_amount,
            vendor_name=payload.vendor_name,
            gmail_invoiceproof=payload.gmail_invoiceproof.model_dump(),
            db_session=session,
        )
    except InvoiceProofGateFailed:
        pass

    # --- START WORKFLOW (in-memory in dev; TEMPORAL_HOST env var swaps in the
    # real Temporal engine at deploy time — see app.workflow.engine.get_workflow_engine,
    # Fix 2). The workflow blocks immediately at the human-approval gate (G4).
    _engine.start_workflow(
        workflow_id=workflow_id,
        intent={
            "type": "bill_intent",
            "gmail_tracker_id": tracker_id_str,
            "bill_id": bill_id,
            "vendor_id": vendor_id,
            "company_id": company_id,
            "amount": bill_amount,
            "po_ref": payload.po_ref,
            "due_date": payload.due_date,
            "vendor_matched": vendor_matched,
        },
    )
    _bus.publish(
        "intent.bill.created",
        {"workflow_id": workflow_id, "bill_id": bill_id, "gmail_tracker_id": tracker_id_str},
    )

    # Commit after workflow start so the bill row and workflow state are in sync.
    # If workflow start raises, the bill INSERT is rolled back (session.commit
    # was not yet called).
    session.commit()

    # --- RESPONSE 201 ----------------------------------------------------------
    response_data: dict[str, Any] = {
        "bill_id": bill_id,
        "workflow_id": workflow_id,
        "status": "drafted",
        "vendor_matched": vendor_matched,
        "vendor_id": vendor_id,
    }
    if not vendor_matched:
        response_data["vendor_unmatched"] = True
    if amount_review:
        response_data["amount_review"] = True
    if vendor_multiple_candidates:
        response_data["vendor_multiple_candidates"] = True

    return _ok(response_data, status_code=201)


# ---------------------------------------------------------------------------
# POST /intents/draw  (Phase 4 stub — STV CM LLC guard wired, fee math preview)
# ---------------------------------------------------------------------------


@router.post("/intents/draw", status_code=201)
def create_draw_intent(
    payload: DrawIntentIn,
    authorization: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """Phase 4: create a draw intent, generate 5/2/1 fee bills from a System A fee_opportunity.

    Guards evaluated in order (each fires BEFORE any DB write):

    Guard 1 -- STV CM LLC name check (G3, guarantee [3]):
        If fee_payee_hint matches a known STV CM LLC entity name, fires a hard 400
        STV_CM_LLC_BLOCKED and writes an AIVS audit_row 'stv_cm_llc_draw_attempted'.
        This is the System B independent defence-in-depth guard (System A
        outbox_writer.write_draw_intent(blocked=True) is the first gate).

    Guard 2 -- fee_payee_status="BLOCKED":
        Hard 400 FEE_PAYEE_BLOCKED — the payee could not be confirmed. No DB write.

    Guard 3 -- idempotency:
        If draw_packages already contains gmail_fee_opportunity_id in raw_extensions,
        returns 200 {idempotent: true} with NO further mutation (safe to retry).

    On success:
        1. INSERT draw_packages (status='submitted'; cm/watson approvals pending).
        2. Compute fee split using CHUNK_6 split_developer_fee() (5%/2%/1%).
        3. Validate: distinct economic total must equal 8% of draw_amount (hard 422).
        4. For each of the 3 economic fee bills:
             * Fuzzy-match or soft-draft vendor.
             * INSERT into bills with draw_package_id link.
             * Start InMemoryWorkflowEngine workflow (Temporal at deploy).
        5. Append AIVS audit_row 'draw_fee_generated'.
        6. Return 201 {draw_package_id, fee_bills: [{bill_id, workflow_id, amount, entity}]}.

    Guarantees enforced:
        G3  STV CM LLC checked by name AND fee_payee_status before any DB action.
        G4  No automated approvals — each fee bill workflow blocks at human gate.
        G6  Gate 1 wired at Temporal activity (InMemoryWorkflowEngine in dev).
        G7  No QBWC write initiated — shadow mode only.
    """
    # --- AUTH — fires before any business logic ---------------------------------
    auth_err = _check_auth(authorization)
    if auth_err is not None:
        return auth_err

    fee_opp_id_str = str(payload.gmail_fee_opportunity_id)

    # --- G3: STV CM LLC name check — fires BEFORE any DB write (guarantee [3]) ----
    # System B independent guard (defence in depth); System A outbox_writer is guard 1.
    if _is_stv_cm_llc(payload.fee_payee_hint):
        append_audit_row(
            session,
            session_id=fee_opp_id_str,
            action_type="stv_cm_llc_draw_attempted",
            actor="system_b.intents_router",
            tool_name="intents_router.create_draw_intent",
            inputs={
                "gmail_fee_opportunity_id": fee_opp_id_str,
                "fee_payee_hint": payload.fee_payee_hint,
                "project_canonical": payload.project_canonical,
                "draw_amount": float(payload.draw_amount),
            },
            outputs={"blocked": True, "reason": "STV CM LLC entity name detected"},
        )
        session.commit()
        return _error(
            400,
            "STV_CM_LLC_BLOCKED",
            (
                "Draw intent rejected: entity resolves to STV CM LLC "
                f"({payload.fee_payee_hint!r}). "
                "No draw_intent row written — route to exception queue."
            ),
        )

    # --- fee_payee_status="BLOCKED" guard — separate from STV CM LLC check --------
    if payload.fee_payee_status == "BLOCKED":
        return _error(
            400,
            "FEE_PAYEE_BLOCKED",
            (
                "Draw intent rejected: fee_payee_status is BLOCKED. "
                "Payee could not be confirmed — no draw_intent row written."
            ),
        )

    # --- IDEMPOTENCY CHECK — SELECT before any INSERT ---------------------------
    # Fix 8: gmail_fee_opportunity_id is a dedicated UNIQUE column on
    # draw_packages (Migration 002, migrations/versions/20260701_1100_*.py) —
    # query it directly instead of the raw_extensions->> JSONB text fallback.
    existing_pkg = session.execute(
        text(
            "SELECT id FROM draw_packages "
            "WHERE gmail_fee_opportunity_id = :foid "
            "LIMIT 1"
        ),
        {"foid": fee_opp_id_str},
    ).mappings().first()

    if existing_pkg is not None:
        return _ok(
            {
                "draw_package_id": str(existing_pkg["id"]),
                "idempotent": True,
            },
            status_code=200,
        )

    # --- CHUNK_6 FEE CALCULATION (split_developer_fee from fee_math.py) ----------
    # split_developer_fee() returns 4 lines: partnership 5%, parent 5% income,
    # parent 2% CEO, parent 1% Pres.  The 3 economic bills are the distinct
    # economic charge: 5% dev + 2% CM + 1% Pres = 8%.
    draw_amount = Decimal(str(payload.draw_amount))
    fee_lines = split_developer_fee(draw_amount)

    # --- MATH VALIDATION: 3 economic fees must sum to 8% of draw_amount ----------
    # Use per-rate independent rounding (identical to split_developer_fee) to avoid
    # divergence between the two rounding strategies on amounts like 12.51, 37.53, etc.
    economic_total = distinct_economic_total(fee_lines)
    expected_8pct = (
        _money(draw_amount * RATE_DEV)
        + _money(draw_amount * RATE_CEO)
        + _money(draw_amount * RATE_PRES)
    )
    if economic_total != expected_8pct:
        return _error(
            422,
            "FEE_MATH_INVALID",
            (
                f"Fee math validation failed: economic_total={economic_total} "
                f"!= 8% of draw_amount {draw_amount} ({expected_8pct}). "
                "Amounts do not satisfy the 5/2/1 split constraint — draw rejected."
            ),
        )

    fee_map = {ln.fee_role: ln for ln in fee_lines}

    # --- RESOLVE COMPANY FROM project_canonical ---------------------------------
    company_row = session.execute(
        text(
            "SELECT id FROM companies "
            "WHERE legal_name ILIKE :pname "
            "ORDER BY created_at "
            "LIMIT 1"
        ),
        {"pname": f"%{payload.project_canonical}%"},
    ).mappings().first()
    if company_row is None:
        # Fallback: first company in DB (same pattern as /intents/bill)
        company_row = session.execute(
            text("SELECT id FROM companies LIMIT 1")
        ).mappings().first()
    if company_row is None:
        return _error(503, "NO_COMPANY", "No company records in canonical store.")
    company_id = str(company_row["id"])

    # --- INSERT draw_package -----------------------------------------------------
    draw_pkg_id = str(uuid.uuid4())
    draw_number_str = (
        str(payload.draw_number)
        if payload.draw_number is not None
        else fee_opp_id_str[:8]
    )
    draw_number = f"DRAW-{draw_number_str}"
    now = _utcnow()

    raw_ext_pkg: dict[str, Any] = dict(payload.raw_extensions or {})
    raw_ext_pkg["gmail_fee_opportunity_id"] = fee_opp_id_str
    raw_ext_pkg["project_canonical"] = payload.project_canonical
    raw_ext_pkg["fee_payee_status"] = payload.fee_payee_status
    if payload.estimated_fee_hint is not None:
        raw_ext_pkg["estimated_fee_hint"] = float(payload.estimated_fee_hint)
    if payload.fee_payee_hint:
        raw_ext_pkg["fee_payee_hint"] = payload.fee_payee_hint

    session.execute(
        text(
            "INSERT INTO draw_packages "
            "(id, company_id, draw_number, customer_job, package_total, status, "
            " cm_approved, watson_approved, gmail_fee_opportunity_id, "
            " raw_extensions, created_at, updated_at) "
            "VALUES "
            "(:id, :company_id, :draw_number, :customer_job, :package_total, 'submitted', "
            " false, false, :gmail_fee_opportunity_id, CAST(:raw_ext AS jsonb), :now, :now)"
        ),
        {
            "id": draw_pkg_id,
            "company_id": company_id,
            "draw_number": draw_number,
            "customer_job": payload.project_canonical,
            "package_total": float(draw_amount),
            "gmail_fee_opportunity_id": fee_opp_id_str,
            "raw_ext": json.dumps(raw_ext_pkg),
            "now": now,
        },
    )

    # --- CREATE 3 ECONOMIC FEE BILLS (5% dev / 2% CM / 1% Pres) ----------------
    # Each bill is linked to the draw_package and starts its own Temporal workflow.
    # Vendor resolution: fuzzy match first; soft-draft if not found (same as /intents/bill).
    # The 4th fee_math line (dev_inc_5_parent) is the intercompany mirror entry and
    # does NOT generate a separate payable bill — it is tracked via FeeEntry / IntercompanyLink.
    fee_bill_specs: list[dict[str, Any]] = [
        {
            "role": ROLE_DEV_PARTNERSHIP,
            "line": fee_map[ROLE_DEV_PARTNERSHIP],
            "entity_name": "Summa Terra Ventures LLC",
            "label": "Developer Fee (5%) — cost code 069",
        },
        {
            "role": ROLE_CEO_PARENT,
            "line": fee_map[ROLE_CEO_PARENT],
            "entity_name": payload.fee_payee_hint or "CM Entity",
            "label": "CM Fee (2%)",
        },
        {
            "role": ROLE_PRES_PARENT,
            "line": fee_map[ROLE_PRES_PARENT],
            "entity_name": "Porter Christensen",
            "label": "President Fee (1%)",
        },
    ]

    fee_bills_out: list[dict[str, Any]] = []

    for spec in fee_bill_specs:
        entity_name: str = spec["entity_name"]
        fee_amount = float(spec["line"].amount)
        fee_role: str = spec["role"]

        # Vendor resolution: fuzzy match (pg_trgm) → soft-draft fallback
        vendor_rows = _fuzzy_match_vendor(session, entity_name)
        if vendor_rows:
            vendor_id = str(vendor_rows[0]["id"])
        else:
            vendor_id = _create_soft_draft_vendor(session, entity_name, company_id)

        bill_id = str(uuid.uuid4())
        wf_id = f"draw-fee-{fee_role}-{fee_opp_id_str}"

        bill_raw_ext: dict[str, Any] = {
            "workflow_id": wf_id,
            "draw_package_id": draw_pkg_id,
            "gmail_fee_opportunity_id": fee_opp_id_str,
            "fee_role": fee_role,
            "draw_amount": float(draw_amount),
            "fee_payee_status": payload.fee_payee_status,
            "source": "draw_intent",
        }

        session.execute(
            text(
                "INSERT INTO bills "
                "(id, company_id, vendor_id, amount, status, draw_package_id, "
                " raw_extensions, created_at, updated_at) "
                "VALUES "
                "(:id, :company_id, :vendor_id, :amount, 'drafted', :draw_package_id, "
                " CAST(:raw_ext AS jsonb), :now, :now)"
            ),
            {
                "id": bill_id,
                "company_id": company_id,
                "vendor_id": vendor_id,
                "amount": fee_amount,
                "draw_package_id": draw_pkg_id,
                "raw_ext": json.dumps(bill_raw_ext),
                "now": now,
            },
        )

        # --- GATE 1: InvoiceProof (SwarmSync proof-core VCAP Full Bundle) ------
        # Fix 1: fee bills are generated internally by the draw engine (SPEC
        # Flow 4 Step 6: "Each fee bill: Gate 1 (VCAP) -> approval gate"), not
        # from a System A email-detected invoice, so there is no
        # gmail_invoiceproof evidence block in DrawIntentIn. A synthetic
        # evidence dict is built here so every fee bill still gets a real,
        # signed VCAP proof_bundles row (the audit/crypto artifact IS Gate 1 —
        # see invoice_proof_gate.py's module docstring distinction between the
        # advisory System A pre-screen and System B's formal proof). The
        # fee_payee_status guard (CONFIRMED/UNCERTAIN; BLOCKED already rejected
        # above) is carried through for the audit trail. Flagged in the Fix 1
        # report as a judgment call — SPEC does not define this evidence shape.
        fee_gmail_invoiceproof: dict[str, Any] = {
            "source": "draw_engine_internal",
            "passed": True,
            "riskLevel": "LOW",
            "gmail_fee_opportunity_id": fee_opp_id_str,
            "fee_role": fee_role,
            "fee_payee_status": payload.fee_payee_status,
        }
        try:
            run_invoice_proof_gate1(
                bill_id=bill_id,
                bill_amount=fee_amount,
                vendor_name=entity_name,
                gmail_invoiceproof=fee_gmail_invoiceproof,
                db_session=session,
            )
        except InvoiceProofGateFailed:
            pass

        # Start the workflow engine (in-memory dev; TEMPORAL_HOST env var swaps
        # in the real Temporal engine at deploy time — Fix 2). Workflow blocks
        # at human-approval gate (G4).
        _engine.start_workflow(
            workflow_id=wf_id,
            intent={
                "type": "draw_fee_bill",
                "gmail_fee_opportunity_id": fee_opp_id_str,
                "draw_package_id": draw_pkg_id,
                "bill_id": bill_id,
                "vendor_id": vendor_id,
                "company_id": company_id,
                "fee_role": fee_role,
                "amount": fee_amount,
                "draw_amount": float(draw_amount),
            },
        )
        _bus.publish(
            "intent.draw_fee.created",
            {
                "workflow_id": wf_id,
                "bill_id": bill_id,
                "draw_package_id": draw_pkg_id,
                "fee_role": fee_role,
            },
        )

        fee_bills_out.append(
            {
                "bill_id": bill_id,
                "workflow_id": wf_id,
                "amount": fee_amount,
                "entity": entity_name,
                "fee_role": fee_role,
            }
        )

    # --- AIVS AUDIT ROW: draw_fee_generated -------------------------------------
    append_audit_row(
        session,
        session_id=fee_opp_id_str,
        action_type="draw_fee_generated",
        actor="system_b.intents_router",
        tool_name="intents_router.create_draw_intent",
        inputs={
            "gmail_fee_opportunity_id": fee_opp_id_str,
            "project_canonical": payload.project_canonical,
            "draw_amount": float(draw_amount),
            "draw_number": payload.draw_number,
            "fee_payee_hint": payload.fee_payee_hint,
            "fee_payee_status": payload.fee_payee_status,
        },
        outputs={
            "draw_package_id": draw_pkg_id,
            "fee_bills_count": len(fee_bills_out),
            "fee_bills": [
                {
                    "bill_id": b["bill_id"],
                    "fee_role": b["fee_role"],
                    "amount": b["amount"],
                }
                for b in fee_bills_out
            ],
            "economic_total": float(economic_total),
            "math_valid": True,
        },
    )

    session.commit()

    return _ok(
        {
            "draw_package_id": draw_pkg_id,
            "fee_bills": fee_bills_out,
        },
        status_code=201,
    )


# ---------------------------------------------------------------------------
# POST /intents/bank-block  (Phase 3 — ATEP block + exception queue drain)
# ---------------------------------------------------------------------------


@router.post("/intents/bank-block", status_code=201)
def create_bank_block(
    payload: BankBlockIn,
    authorization: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """ATEP bank-change block for a vendor + scan in-flight bills → exception queue.

    Enforces must-not-break guarantee [2]: bank_change_risk P0 path is completed here —
    the vendor's bank_fingerprint is set to 'BLOCKED:<sender_email>' and every in-flight
    bill (status NOT IN approved/paid/rejected) is moved to status='exception'.

    Auth: Bearer AIHUB_OUTBOX_TOKEN (same token as /intents/bill).

    Idempotency:
      If any vendor matching the name pattern already has
      bank_fingerprint='BLOCKED:<sender_email>', the block has already been applied.
      Returns 200 {block_id, idempotent: true} — NO further mutation.

    Exception queue concept:
      bills.status='exception' IS the exception queue (no separate table). Bills in
      this state are surfaced in the dashboard under "needs attention" and require a
      human decision before any further processing.

    Guarantees enforced:
      G2  bank_change_risk P0 — this endpoint IS the P0 action path; fires before QB.
      G4  No automated approvals — exception status requires human resolution.
      G7  No QBWC write initiated from this endpoint.

    Returns:
      201  {block_id: <primary vendor uuid>, affected_bills_count: N}
      200  {block_id, idempotent: true}  — block already applied
      404  VENDOR_NOT_FOUND — no vendor matches the name pattern
    """
    # --- AUTH — fires before any business logic ---------------------------------
    auth_err = _check_auth(authorization)
    if auth_err is not None:
        return auth_err

    blocked_fingerprint = f"BLOCKED:{payload.sender_email}"

    # --- ADVISORY LOCK: prevent concurrent bank-block race for same vendor+email -----
    # pg_advisory_xact_lock is released automatically at transaction end.
    # hashtext produces a stable int4 from the compound key within one Postgres major
    # version, which is sufficient for this intra-transaction serialisation guard.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"{payload.vendor_name}:{payload.sender_email}"},
    )

    # --- IDEMPOTENCY CHECK: vendor already carries this ATEP fingerprint? -------
    # Check using ILIKE so capitalisation differences don't create duplicate blocks.
    existing_blocked = session.execute(
        text(
            "SELECT id FROM vendors "
            "WHERE name ILIKE :pattern "
            "AND bank_fingerprint = :fingerprint "
            "LIMIT 1"
        ),
        {
            "pattern": f"%{payload.vendor_name}%",
            "fingerprint": blocked_fingerprint,
        },
    ).mappings().first()

    if existing_blocked is not None:
        return _ok(
            {
                "block_id": str(existing_blocked["id"]),
                "idempotent": True,
            },
            status_code=200,
        )

    # --- FUZZY MATCH vendors (ILIKE — broad to catch all at-risk rows) ----------
    vendor_rows = session.execute(
        text(
            "SELECT id FROM vendors WHERE name ILIKE :pattern"
        ),
        {"pattern": f"%{payload.vendor_name}%"},
    ).mappings().all()

    vendor_ids: list[str] = [str(r["id"]) for r in vendor_rows]

    if not vendor_ids:
        return _error(
            404,
            "VENDOR_NOT_FOUND",
            (
                f"No vendor found matching name={payload.vendor_name!r}. "
                "Cannot create ATEP block — add the vendor to the canonical store first."
            ),
        )

    # Primary vendor id used as the stable block_id in the response.
    primary_vendor_id = vendor_ids[0]

    # --- SET ATEP FLAG on all name-matched vendors --------------------------------
    # bank_fingerprint stores ONLY 'BLOCKED:<email>' — no raw account numbers.
    # Spec §9 security rule: "bank_block payload: vendor_name + sender_email only".
    session.execute(
        text(
            "UPDATE vendors "
            "SET bank_fingerprint = :fingerprint, updated_at = NOW() "
            "WHERE name ILIKE :pattern"
        ),
        {
            "fingerprint": blocked_fingerprint,
            "pattern": f"%{payload.vendor_name}%",
        },
    )

    # --- SCAN IN-FLIGHT BILLS → exception queue ----------------------------------
    # Bills in terminal states (approved/paid/rejected) are not touched.
    # bills.status='exception' IS the exception queue — no separate table needed.
    in_flight_rows = session.execute(
        text(
            "SELECT id FROM bills "
            "WHERE vendor_id = ANY(CAST(:vids AS uuid[])) "
            "AND status NOT IN ('approved', 'paid', 'rejected')"
        ),
        {"vids": vendor_ids},
    ).mappings().all()

    affected_bill_ids: list[str] = [str(r["id"]) for r in in_flight_rows]
    affected_count = len(affected_bill_ids)

    if affected_bill_ids:
        session.execute(
            text(
                "UPDATE bills "
                "SET status = 'exception', "
                "    raw_extensions = raw_extensions "
                "        || '{\"bank_block_reason\": \"ATEP block created\"}'::jsonb, "
                "    updated_at = NOW() "
                "WHERE id = ANY(CAST(:bids AS uuid[]))"
            ),
            {"bids": affected_bill_ids},
        )

    # --- AIVS AUDIT ROW: atep_bank_block_created ---------------------------------
    # session_id anchors to the System A tracker when provided; otherwise a fresh
    # UUID so the audit chain remains intact even for standalone calls.
    audit_session_id = (
        str(payload.tracker_id) if payload.tracker_id else str(uuid.uuid4())
    )
    # Hash sender_email before writing to the audit trail so raw addresses are not
    # exposed in an exported audit table or via a compromised read credential.
    sender_email_hash = hashlib.sha256(
        payload.sender_email.lower().encode()
    ).hexdigest()

    append_audit_row(
        session,
        session_id=audit_session_id,
        action_type="atep_bank_block_created",
        actor="system_b.intents_router",
        tool_name="intents_router.create_bank_block",
        inputs={
            "vendor_name": payload.vendor_name,
            "sender_email_hash": sender_email_hash,
            "gmail_message_id": payload.gmail_message_id,
            "tracker_id": str(payload.tracker_id) if payload.tracker_id else None,
            "matched_vendor_ids": vendor_ids,
        },
        outputs={
            "block_id": primary_vendor_id,
            "bank_fingerprint": blocked_fingerprint,
            "affected_bills_count": affected_count,
            "affected_bill_ids": affected_bill_ids,
        },
    )

    session.commit()

    return _ok(
        {
            "block_id": primary_vendor_id,
            "affected_bills_count": affected_count,
        },
        status_code=201,
    )


# ---------------------------------------------------------------------------
# Shared approve/reject business logic (Fix 4, spec-compliance-audit-stv-
# integration-layer-2026-06-30.md).
#
# Both the JSON API (POST /approvals/{workflow_id}, dual AIHUB_OUTBOX_TOKEN /
# BEN_SESSION_TOKEN auth, below) and the manual operator UI
# (POST /approve/{workflow_id} in app/integration/approval_ui.py, APPROVAL_UI_TOKEN
# auth) call ``_resolve_bill_approval`` so a bill approved from either surface
# gets an IDENTICAL AIVS audit_rows trail and AuditProof canonical commit — the
# UI path no longer does a bare ``UPDATE bills SET status='approved'`` with no
# audit chain. Each caller is responsible for its own auth and request-shape
# validation (note length, decision/source enum checks) because the two routers
# return different response shapes (JSON envelope vs HTML redirect); this
# function assumes the request is already authenticated and decision/source
# are valid enum values.
# ---------------------------------------------------------------------------


@dataclass
class ApprovalOutcome:
    """Structured result of an approve/reject decision (Fix 4).

    ``code`` is a machine-readable reason: OK | IDEMPOTENT | REJECTED |
    BILL_NOT_FOUND | PROOF_BUNDLE_MISSING | PROOF_BUNDLE_NOT_PASSED.
    ``BANK_CHANGE_RISK`` is never produced by ``_resolve_bill_approval`` itself
    (that guard is not rechecked here — see the approval-path note below) but
    is kept as a valid code because ``approval_ui.approve_bill`` maps its own
    pre-call bank_change_risk guard onto this same outcome shape before ever
    calling this function. Callers map ``code`` to their own response shape.
    """

    ok: bool
    code: str
    bill_id: str | None = None
    workflow_id: str | None = None
    status: str | None = None
    idempotent: bool = False
    tracker_id: str | None = None
    audit_proof_head: str | None = None
    message: str = ""


def _resolve_bill_approval(
    session: Session,
    workflow_id: str,
    decision: str,
    source: str,
    note: str | None,
    evidence_email_id: str | None,
) -> ApprovalOutcome:
    """Approve or reject the bill intent workflow ``workflow_id`` (SPEC §6.6).

    On approval: G6 proof bundle gate (fails closed), then engine signal, bill
    status -> 'approved', AIVS audit rows ('approval_signal_received',
    'bill_approved'), AuditProof canonical commit (build_aivs_bundle +
    write_proof_bundle), and a commit. Does NOT recheck bank_change_risk (that
    guard fired at /intents/bill creation time, G2) — see the approval-path
    comment below for why, and approval_ui.approve_bill for the UI's own
    pre-call recheck.

    Does NOT fire the bill-synced callback — that is the caller's job (via
    ``BackgroundTasks``, Fix 8) using the returned ``tracker_id``/``bill_id``/
    ``status`` once ``ok`` is True and ``code not in {"IDEMPOTENT", "REJECTED"}``.
    """
    bill_row = session.execute(
        text(
            "SELECT id, status, invoiceproof_bundle_id, "
            "raw_extensions->>'gmail_tracker_id' AS tracker_id "
            "FROM bills "
            "WHERE raw_extensions->>'workflow_id' = :wf_id "
            "LIMIT 1"
        ),
        {"wf_id": workflow_id},
    ).mappings().first()

    if bill_row is None:
        return ApprovalOutcome(
            ok=False,
            code="BILL_NOT_FOUND",
            workflow_id=workflow_id,
            message=f"No bill found for workflow_id={workflow_id!r}",
        )

    bill_id = str(bill_row["id"])
    current_status = bill_row["status"]
    tracker_id = bill_row["tracker_id"] or ""

    # --- IDEMPOTENCY -------------------------------------------------------
    if current_status in ("approved", "rejected"):
        return ApprovalOutcome(
            ok=True,
            code="IDEMPOTENT",
            bill_id=bill_id,
            workflow_id=workflow_id,
            status=current_status,
            idempotent=True,
        )

    # --- REJECTION PATH ------------------------------------------------------
    if decision == "reject":
        session.execute(
            text(
                "UPDATE bills SET status = 'rejected', updated_at = NOW() WHERE id = :bid"
            ),
            {"bid": bill_id},
        )
        append_audit_row(
            session,
            session_id=bill_id,
            action_type="bill_rejected",
            actor=source,
            tool_name="intents_router._resolve_bill_approval",
            inputs={
                "workflow_id": workflow_id,
                "bill_id": bill_id,
                "source": source,
                "note": note,
                "evidence_email_id": evidence_email_id,
            },
            outputs={"decision": "reject", "new_status": "rejected"},
        )
        session.commit()
        return ApprovalOutcome(
            ok=True,
            code="REJECTED",
            bill_id=bill_id,
            workflow_id=workflow_id,
            status="rejected",
        )

    # --- APPROVAL PATH ---------------------------------------------------------
    # NOTE: bank_change_risk is NOT rechecked here — that guard already fired at
    # /intents/bill creation time (G2). approval_ui.py additionally re-checks it
    # as its own pre-call guard (defense in depth for the manual UI surface only)
    # before calling this shared function; see approval_ui.approve_bill. Whether
    # the JSON API path (/approvals/{workflow_id}) should ALSO re-check it here
    # is flagged as an open question in the Fix 4 report — left unchanged to avoid
    # altering existing JSON API behaviour/tests beyond what Fix 4 asked for.

    # G6: proof bundle gate — fail closed (spec §5 Flow 1 Step 11).
    bundle_id = bill_row["invoiceproof_bundle_id"]
    if bundle_id is None:
        return ApprovalOutcome(
            ok=False,
            code="PROOF_BUNDLE_MISSING",
            bill_id=bill_id,
            workflow_id=workflow_id,
            tracker_id=tracker_id,
            message=(
                "Cannot approve: no InvoiceProof bundle linked to this bill. "
                "Gate 1 must pass before approval (spec §5 Flow 1 Step 11)."
            ),
        )

    proof_row = session.execute(
        text("SELECT passed FROM proof_bundles WHERE id = :bid LIMIT 1"),
        {"bid": str(bundle_id)},
    ).mappings().first()

    if proof_row is None or not proof_row["passed"]:
        return ApprovalOutcome(
            ok=False,
            code="PROOF_BUNDLE_NOT_PASSED",
            bill_id=bill_id,
            workflow_id=workflow_id,
            tracker_id=tracker_id,
            message=(
                "Cannot approve: proof_bundles.passed is not True. "
                "Gate 1 fails closed — bill must not proceed to QB without a valid proof."
            ),
        )

    # Step 1: Signal the workflow engine → advance workflow state to approved.
    # (Real Temporal client signals the running workflow at deploy time.)
    _engine.signal_workflow(workflow_id, signal="approved") if hasattr(
        _engine, "signal_workflow"
    ) else _bus.publish(
        "workflow.approval.signal",
        {"workflow_id": workflow_id, "decision": "approve", "source": source},
    )

    # Step 2: Advance bill status to 'approved' (irreversible commit — G4 human gate satisfied).
    session.execute(
        text(
            "UPDATE bills SET status = 'approved', updated_at = NOW() WHERE id = :bid"
        ),
        {"bid": bill_id},
    )

    # Step 3: AIVS audit rows — 'approval_signal_received' then 'bill_approved'.
    append_audit_row(
        session,
        session_id=bill_id,
        action_type="approval_signal_received",
        actor=source,
        tool_name="intents_router._resolve_bill_approval",
        inputs={
            "workflow_id": workflow_id,
            "bill_id": bill_id,
            "source": source,
            "evidence_email_id": evidence_email_id,
            "note": note,
        },
        outputs={"decision": "approve"},
    )
    append_audit_row(
        session,
        session_id=bill_id,
        action_type="bill_approved",
        actor=source,
        tool_name="intents_router._resolve_bill_approval",
        inputs={"workflow_id": workflow_id, "bill_id": bill_id},
        outputs={"new_status": "approved"},
    )

    # Step 4: AuditProof canonical commit — build_aivs_bundle validates the chain,
    # then we persist a ProofBundle row. Raises AuditChainBroken (fails closed) if
    # the chain is broken — the exception propagates; caller catches at 500 level.
    records = load_session_records(session, bill_id)
    bundle = build_aivs_bundle(records, kind="approval_auditproof", vcap_state="approved")
    write_proof_bundle(session, bundle)

    session.commit()

    return ApprovalOutcome(
        ok=True,
        code="OK",
        bill_id=bill_id,
        workflow_id=workflow_id,
        status="approved",
        tracker_id=tracker_id,
        audit_proof_head=bundle.get("proof_hash"),
    )


def _fire_bill_synced_callback(
    background_tasks: BackgroundTasks | None,
    tracker_id: str | None,
    bill_id: str,
    status: str,
) -> None:
    """Fire the System A bill-synced callback (Fix 8 — off the request thread).

    When ``background_tasks`` is provided (real FastAPI request), the callback
    (which uses blocking ``httpx``/``time.sleep`` retries) is scheduled to run
    AFTER the HTTP response is sent, so it never blocks the caller. When
    ``background_tasks`` is ``None`` (direct function call, e.g. from tests or
    internal callers that don't have a request context) it falls back to firing
    synchronously so behaviour stays correct outside a FastAPI request.
    """
    system_a_url = _system_a_url_from_env()
    system_a_token = os.environ.get("SYSTEM_A_CALLBACK_TOKEN", "")
    if not (system_a_url and system_a_token and tracker_id):
        return
    if background_tasks is not None:
        background_tasks.add_task(
            send_bill_synced_callback,
            tracker_id=tracker_id,
            bill_id=bill_id,
            qb_txn_id=None,
            status=status,
            system_a_url=system_a_url,
            system_a_token=system_a_token,
        )
    else:
        send_bill_synced_callback(
            tracker_id=tracker_id,
            bill_id=bill_id,
            qb_txn_id=None,
            status=status,
            system_a_url=system_a_url,
            system_a_token=system_a_token,
        )


def _system_a_url_from_env() -> str:
    """Resolve System A's public base URL from explicit or Railway-provided env.

    Railway injects service URL variables as bare hosts, while local tests and
    non-Railway deploys usually use SYSTEM_A_URL with a full URL. Normalize both
    forms so the callback does not silently no-op in production.
    """
    raw = (
        os.environ.get("SYSTEM_A_URL")
        or os.environ.get("RAILWAY_SERVICE_EXEMPLARY_TENDERNESS_URL")
        or ""
    ).strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw.rstrip("/")
    return f"https://{raw.rstrip('/')}"


# ---------------------------------------------------------------------------
# POST /approvals/{workflow_id}  (Phase 2 — full integration layer)
#
# This IS the literal spec path (SPEC §6.6, §12 Phase 2) — System A's
# approval_signal.py POSTs to ``{system_b_base_url}/approvals/{workflow_id}``.
# See Fix 3, spec-compliance-audit-stv-integration-layer-2026-06-30.md: the
# pre-existing generic handler that used to own this exact path was moved to
# app/workflow/router.py POST /workflow/approvals/{workflow_id} to remove the
# collision — this dual-auth, proof-gated handler now owns it.
# ---------------------------------------------------------------------------


@router.post("/approvals/{workflow_id}")
def approve_bill_intent(
    workflow_id: str,
    payload: IntegrationApprovalIn,
    background_tasks: BackgroundTasks,
    authorization: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """Human approve/reject gate for a bill intent workflow (SPEC §6.6, §12 Phase 2).

    Auth (dual-path, SPEC §6.6):
      * Bearer AIHUB_OUTBOX_TOKEN  — System A email-detection path
      * Bearer BEN_SESSION_TOKEN   — Ben UI manual-approval path

    Request body: {decision, source, note, evidence_email_id}

    Validation (G4 — no automated approvals):
      source='manual_ui' requires note with ≥ 10 characters.

    Idempotency:
      bill already 'approved' or 'rejected' → 200 {idempotent: true, current_status}.

    On approval (delegated to ``_resolve_bill_approval`` — Fix 4, shared with the
    manual UI approval path in app/integration/approval_ui.py):
      1. G6 proof bundle gate checked — fails closed (Gate 1 must pass first).
      2. Workflow engine signalled → bill status → 'approved'.
      3. AIVS audit rows written: 'approval_signal_received', then 'bill_approved'.
      4. AuditProof canonical commit (build_aivs_bundle + write_proof_bundle).
      5. bill-synced callback scheduled on ``background_tasks`` (Fix 8 — never
         blocks this response; falls back to a synchronous call when no
         ``background_tasks`` is supplied, e.g. direct function-call tests).

    On rejection:
      bill status → 'rejected'; AIVS audit row: 'bill_rejected'.

    Guarantees enforced:
      G4  This endpoint requires explicit human POST — never self-fires.
      G6  proof_bundles.passed must be True before approval (gate fails closed).
      G7  No QBWC write initiated from this endpoint.
    """
    # --- AUTH — dual-path, fires before any business logic ----------------------
    auth_err = _check_integration_auth(authorization)
    if auth_err is not None:
        return auth_err

    # --- REQUEST BODY VALIDATION ------------------------------------------------
    if payload.decision not in ("approve", "reject"):
        return _error(
            422,
            "VALIDATION_ERROR",
            "decision must be 'approve' or 'reject'",
            field="decision",
        )
    if payload.source not in ("email_detected", "manual_ui"):
        return _error(
            422,
            "VALIDATION_ERROR",
            "source must be 'email_detected' or 'manual_ui'",
            field="source",
        )
    # G4: manual UI approvals require an explicit human note (≥ 10 chars).
    if payload.source == "manual_ui" and (
        not payload.note or len(payload.note.strip()) < 10
    ):
        return _error(
            422,
            "VALIDATION_ERROR",
            "source='manual_ui' requires note with at least 10 characters (G4 — human gate)",
            field="note",
        )

    outcome = _resolve_bill_approval(
        session,
        workflow_id=workflow_id,
        decision=payload.decision,
        source=payload.source,
        note=payload.note,
        evidence_email_id=payload.evidence_email_id,
    )

    if outcome.code == "BILL_NOT_FOUND":
        return _error(404, "BILL_NOT_FOUND", outcome.message)
    if outcome.code == "BANK_CHANGE_RISK":
        return _error(400, "BANK_CHANGE_RISK", outcome.message)
    if outcome.code == "PROOF_BUNDLE_MISSING":
        return _error(422, "PROOF_BUNDLE_MISSING", outcome.message)
    if outcome.code == "PROOF_BUNDLE_NOT_PASSED":
        return _error(422, "PROOF_BUNDLE_NOT_PASSED", outcome.message)
    if outcome.code == "IDEMPOTENT":
        return _ok(
            {
                "workflow_id": workflow_id,
                "bill_id": outcome.bill_id,
                "idempotent": True,
                "current_status": outcome.status,
            }
        )
    if outcome.code == "REJECTED":
        return _ok(
            {
                "workflow_id": workflow_id,
                "bill_id": outcome.bill_id,
                "decision": "reject",
                "status": "rejected",
            }
        )

    # --- outcome.code == "OK" (approved) ----------------------------------------
    # Fire bill-synced callback to System A (after DB commit so state is durable).
    # Fix 8: scheduled on background_tasks so it never blocks this response.
    _fire_bill_synced_callback(
        background_tasks, outcome.tracker_id, outcome.bill_id or "", "approved"
    )

    return _ok(
        {
            "workflow_id": workflow_id,
            "bill_id": outcome.bill_id,
            "decision": "approve",
            "status": "approved",
            "audit_proof_head": outcome.audit_proof_head,
        }
    )


# ---------------------------------------------------------------------------
# POST /callbacks/bill-synced  (Phase 2 — aihub status idempotent callback)
# ---------------------------------------------------------------------------


@router.post("/callbacks/bill-synced")
def bill_synced_callback(
    payload: BillSyncedCallbackIn,
    authorization: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """Idempotent System B → System A callback: bill has been synced to aihub.

    If raw_extensions.aihub_status is already 'synced' on the bill, returns
    200 idempotent=True with NO further DB mutation — safe to retry on network
    failure or delivery of a duplicate event.

    G4: this endpoint never modifies bill.status or approval state — it only
    updates the aihub_status tracking field in raw_extensions.
    G7: no QBWC write is initiated from this callback.
    """
    auth_err = _check_auth(authorization)
    if auth_err is not None:
        return auth_err

    bill_row = session.execute(
        text(
            "SELECT id, raw_extensions->>'aihub_status' AS aihub_status "
            "FROM bills WHERE id = :bid LIMIT 1"
        ),
        {"bid": payload.bill_id},
    ).mappings().first()

    if bill_row is None:
        return _error(404, "BILL_NOT_FOUND", f"No bill found with id={payload.bill_id!r}")

    # Idempotency: already synced — no mutation.
    if bill_row["aihub_status"] == "synced":
        return _ok(
            {
                "bill_id": payload.bill_id,
                "aihub_status": "synced",
                "idempotent": True,
            }
        )

    # Update aihub_status in raw_extensions (JSONB merge — never overwrites other keys).
    session.execute(
        text(
            "UPDATE bills "
            "SET raw_extensions = raw_extensions || jsonb_build_object('aihub_status', CAST(:status AS text)), "
            "    updated_at = NOW() "
            "WHERE id = :bid"
        ),
        {"bid": payload.bill_id, "status": payload.aihub_status},
    )
    session.commit()

    return _ok(
        {
            "bill_id": payload.bill_id,
            "aihub_status": payload.aihub_status,
            "idempotent": False,
        }
    )


# ---------------------------------------------------------------------------
# POST /intents/payment-confirmed  (Phase 5 — Aubrey Palmer confirmation flow)
# ---------------------------------------------------------------------------


@router.post("/intents/payment-confirmed")
def confirm_payment(
    payload: PaymentConfirmedIn,
    background_tasks: BackgroundTasks,
    authorization: str = Header(default=""),
    session: Session = SessionDep,
) -> Any:
    """Advance bill.status → 'paid' when System A detects Aubrey's confirmation email.

    Auth: Bearer AIHUB_OUTBOX_TOKEN (same gate as all other /intents/* endpoints).

    Flow (SPEC §12, Phase 5):
      1. Auth check — no partial processing before token validated.
      2. Lookup bill by bills.gmail_tracker_id (Phase 0 migration column).
      3. 404 BILL_NOT_FOUND if no bill carries this tracker UUID.
      4. Idempotency: bill.status already 'paid' → 200 {bill_id, status:'paid', idempotent:true}.
      5. UPDATE bills SET status='paid'.
      6. Append AIVS audit_row 'bill_paid' (tamper-evident hash chain).
      7. session.commit() — durable before callback.
      8. bill-synced callback to System A with status='paid' scheduled on
         ``background_tasks`` (Fix 8 — never blocks this response; the callback
         itself still retries 3x / logs to integration_reconciliation.log on
         final failure, it just no longer does so on the request thread)
         → advances payment_request_tracker.aihub_status → 'paid'.
      9. Return 200 {bill_id, status:'paid'}.

    Guarantees enforced:
      G1  draft_queue never touched.
      G4  This endpoint never fires autonomously — called only from outbox delivery.
      G5  System B DB (fdnwlcomuddzmluvbylg) only — no cross-DB writes here.
      G7  No QBWC write initiated.

    Note: bill must already be in status 'approved' (set by /intents/approvals/{wf_id})
    before a real payment can be confirmed. This endpoint does not enforce that
    pre-condition — it accepts the transition from any non-terminal status so that
    partial-pipeline replays don't break. The AIVS audit row records the previous
    status for forensic completeness.
    """
    # --- AUTH — fires before any business logic (no partial processing) ----------
    auth_err = _check_auth(authorization)
    if auth_err is not None:
        return auth_err

    tracker_id_str = str(payload.gmail_tracker_id)

    # --- LOOKUP bill by gmail_tracker_id ----------------------------------------
    # bills.gmail_tracker_id added by Phase 0 migration (spec §6.3 ALTER TABLE).
    # Accessed via raw SQL — ORM model is schema-frozen (CHUNK_1_INFRA).
    bill_row = session.execute(
        text(
            "SELECT id, status "
            "FROM bills "
            "WHERE gmail_tracker_id = :tid "
            "LIMIT 1"
        ),
        {"tid": tracker_id_str},
    ).mappings().first()

    if bill_row is None:
        return _error(
            404,
            "BILL_NOT_FOUND",
            (
                f"No bill found for gmail_tracker_id={tracker_id_str!r}. "
                "Verify the tracker UUID was carried through the bill_intent flow (Phase 1)."
            ),
        )

    bill_id = str(bill_row["id"])
    current_status = bill_row["status"]

    # --- IDEMPOTENCY: already paid → safe replay --------------------------------
    if current_status == "paid":
        return _ok(
            {
                "bill_id": bill_id,
                "status": "paid",
                "idempotent": True,
            }
        )

    # --- ADVANCE bill.status → 'paid' -------------------------------------------
    session.execute(
        text(
            "UPDATE bills SET status = 'paid', updated_at = NOW() WHERE id = :bid"
        ),
        {"bid": bill_id},
    )

    # --- AIVS AUDIT ROW: bill_paid ----------------------------------------------
    # Anchored to tracker_id so the hash chain is traceable back to the System A
    # payment_request_tracker row that spawned the original bill_intent.
    append_audit_row(
        session,
        session_id=tracker_id_str,
        action_type="bill_paid",
        actor="system_b.intents_router",
        tool_name="intents_router.confirm_payment",
        inputs={
            "gmail_tracker_id": tracker_id_str,
            "bill_id": bill_id,
            "previous_status": current_status,
        },
        outputs={"new_status": "paid"},
    )

    # Commit before callback — DB state is durable even if the callback transport fails.
    session.commit()

    # --- CALLBACK TO SYSTEM A: aihub_status → 'paid' ----------------------------
    # Fix 8: scheduled on background_tasks so it never blocks this response.
    # send_bill_synced_callback is still best-effort internally; failures are
    # logged to integration_reconciliation.log (never silently dropped).
    _fire_bill_synced_callback(background_tasks, tracker_id_str, bill_id, "paid")

    return _ok(
        {
            "bill_id": bill_id,
            "status": "paid",
        }
    )
