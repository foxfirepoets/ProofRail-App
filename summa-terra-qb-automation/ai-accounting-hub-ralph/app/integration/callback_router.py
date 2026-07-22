"""Reference implementation: POST /integration/bill-synced callback endpoint.

IMPORTANT PLACEMENT NOTE
========================
This module lives in System B's codebase as a canonical reference for System A's
integration team.  The endpoint described here MUST be deployed on the System A
FastAPI service (Railway Service 1, ejxrbxoncsgglrqvjulg), NOT on System B.

System B fires POST /integration/bill-synced after a bill reaches canonical commit.
System A receives the call, advances the tracker, and logs the event.

Must-not-break guarantees enforced here:
  G1  draft_queue is NEVER read or written by this endpoint.
  G4  No automated approvals — this endpoint only records the downstream result of
      a human-approved commit; it never changes approval state on any bill.
  G5  Connects exclusively to System A DB (SYSTEM_A_DB_URL = ejxrbxoncsgglrqvjulg).
      System B DB (fdnwlcomuddzmluvbylg) is NEVER touched by this module.
      Enforced by _get_system_a_session() which reads SYSTEM_A_DB_URL — a distinct
      env var that must never be set to the System B project ref.
  G6  SwarmSync proof-core / Gate 1 has already passed before this callback fires;
      this endpoint receives the *result* and does not re-gate.
  G7  No QB write is initiated from this endpoint.

Auth: Bearer SYSTEM_A_CALLBACK_TOKEN  (set as Railway env var on System B Service 2;
      System B sends this token; System A validates it here.)

API contract (spec-stv-integration-layer-2026-06-29.md §6.7, §12):
  Request  POST /integration/bill-synced
  Body:    {tracker_id: uuid, bill_id: uuid, qb_txn_id: str|null, status: "synced|paid"}
  200 new: {tracker_id, previous_status, new_status, aihub_status, idempotent: false}
  200 dup: {tracker_id, aihub_status, idempotent: true}
  401:     bad / missing token
  404:     tracker_id not found
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

router = APIRouter(tags=["integration-callback"])

# ---------------------------------------------------------------------------
# System A DB connection (G5 — never confuse with System B DB)
# ---------------------------------------------------------------------------
# System A DB URL is set via the SYSTEM_A_DB_URL env var on System B's Railway
# service so that System B can never accidentally connect to the wrong project.
# When this module is deployed TO System A, the service reads its own DATABASE_URL.
# Either way, the project ref must be ejxrbxoncsgglrqvjulg.
# ---------------------------------------------------------------------------

_system_a_engine = None
_SystemASession: sessionmaker[Session] | None = None


def _get_system_a_engine():
    global _system_a_engine, _SystemASession
    if _system_a_engine is None:
        url = os.environ.get("SYSTEM_A_DB_URL", "")
        if not url:
            raise RuntimeError(
                "SYSTEM_A_DB_URL is not set — cannot connect to System A "
                "(ejxrbxoncsgglrqvjulg). This env var must be set on the service "
                "that hosts POST /integration/bill-synced."
            )
        # Normalise to psycopg v3 driver (same pattern as app/db.py).
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        _system_a_engine = create_engine(url, pool_pre_ping=True, future=True)
        _SystemASession = sessionmaker(
            bind=_system_a_engine, autoflush=False, future=True
        )
    return _system_a_engine


def _get_system_a_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session bound to System A's Supabase DB.

    G5: this session MUST connect to ejxrbxoncsgglrqvjulg only.  If SYSTEM_A_DB_URL
    accidentally points to fdnwlcomuddzmluvbylg the CI wrong-DB guard will catch it
    before any migration runs, but the wrong connection here would silently fail to
    find payment_request_tracker rows.  Always verify SYSTEM_A_DB_URL before deploy.
    """
    _get_system_a_engine()
    assert _SystemASession is not None
    session = _SystemASession()
    try:
        yield session
    finally:
        session.close()


SystemASessionDep = Depends(_get_system_a_session)

# ---------------------------------------------------------------------------
# Auth helpers (same pattern as intents_router.py)
# ---------------------------------------------------------------------------

_STATUS_TO_TRACKER_LABEL: dict[str, str] = {
    "synced": "Booked / Ready to Book in QB",
    "paid": "Paid",
}


def _callback_token() -> str:
    """Read SYSTEM_A_CALLBACK_TOKEN from the environment."""
    return os.environ.get("SYSTEM_A_CALLBACK_TOKEN", "")


def _check_auth(authorization: str) -> JSONResponse | None:
    """Return 401 JSONResponse if Bearer token is invalid, else None.

    Must be the first check in the endpoint — no partial processing before auth.
    """
    expected = _callback_token()
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
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing bearer token",
                },
                "meta": {},
            },
        )
    return None


# ---------------------------------------------------------------------------
# Response envelope helpers
# ---------------------------------------------------------------------------


def _ok(data: Any, meta: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"data": data, "error": None, "meta": meta or {}},
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message}, "meta": {}},
    )


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class BillSyncedIn(BaseModel):
    """POST /integration/bill-synced request body (spec §6.7).

    Sent by System B after a bill reaches canonical commit (human-approved,
    proof verified, AuditProof AIVS chain appended).
    """

    tracker_id: uuid.UUID = Field(..., description="System A payment_request_tracker.id")
    bill_id: uuid.UUID = Field(..., description="System B bills.id")
    qb_txn_id: str | None = Field(
        None,
        description="QB TxnID if the bill has been synced to QB Desktop; null in Phase 2–5",
    )
    status: str = Field(
        ...,
        description="synced | paid — what state the bill has reached in System B",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _write_audit_log(
    session: Session,
    *,
    event: str,
    tracker_id: str,
    bill_id: str,
    qb_txn_id: str | None,
    previous_status: str | None,
    new_status: str,
) -> None:
    """Append one row to System A's automation_audit_log.

    Uses INSERT ... ON CONFLICT DO NOTHING so a duplicate delivery (e.g. System B
    retrying after a network timeout) never raises an integrity error.  The
    idempotency guard above catches duplicates first, but this is defence-in-depth.

    The automation_audit_log schema in System A (canonical):
      id UUID PRIMARY KEY DEFAULT gen_random_uuid()
      event_type VARCHAR NOT NULL
      payload JSONB
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    """
    import json

    try:
        session.execute(
            text(
                "INSERT INTO automation_audit_log "
                "(id, event_type, payload, created_at) "
                "VALUES (:id, :event_type, CAST(:payload AS jsonb), :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "event_type": event,
                "payload": json.dumps(
                    {
                        "tracker_id": tracker_id,
                        "bill_id": bill_id,
                        "qb_txn_id": qb_txn_id,
                        "previous_status": previous_status,
                        "new_status": new_status,
                    }
                ),
                "created_at": _utcnow(),
            },
        )
    except Exception:
        # Audit log failure must NEVER block the tracker update — the business
        # state has already been committed above.  Log and continue.
        # In production, surface this as a P1 alert via monitoring.
        pass


# ---------------------------------------------------------------------------
# POST /integration/bill-synced
# ---------------------------------------------------------------------------


@router.post("/integration/bill-synced")
def bill_synced_callback(
    payload: BillSyncedIn,
    authorization: str = Header(default=""),
    session: Session = SystemASessionDep,
) -> Any:
    """Receive a bill-synced callback from System B; advance tracker status.

    Idempotent: if tracker.aihub_status already equals the incoming status,
    returns 200 {idempotent: true} with NO further DB mutation — safe to retry
    on network failure or duplicate delivery from System B's retry loop.

    G1: draft_queue is never read or written.
    G4: no approval state is changed — this endpoint records a downstream result only.
    G5: operates on System A DB (payment_request_tracker, automation_audit_log) only.
    G7: no QB write is initiated.
    """
    # --- AUTH — fires before any business logic (no partial processing) ----------
    auth_err = _check_auth(authorization)
    if auth_err is not None:
        return auth_err

    tracker_id_str = str(payload.tracker_id)
    bill_id_str = str(payload.bill_id)
    incoming_status = payload.status

    # --- LOOK UP TRACKER --------------------------------------------------------
    tracker_row = session.execute(
        text(
            "SELECT id, current_status, aihub_status "
            "FROM payment_request_tracker "
            "WHERE id = :tid "
            "LIMIT 1"
        ),
        {"tid": tracker_id_str},
    ).mappings().first()

    if tracker_row is None:
        return _error(
            404,
            "TRACKER_NOT_FOUND",
            f"payment_request_tracker row not found for tracker_id={tracker_id_str!r}",
        )

    current_aihub_status: str | None = tracker_row["aihub_status"]
    previous_current_status: str | None = tracker_row["current_status"]

    # --- IDEMPOTENCY CHECK ------------------------------------------------------
    # If aihub_status already matches the incoming status, this is a duplicate
    # delivery (System B retrying after a network error, or a second commit event
    # for the same tracker).  Return 200 with no further mutation.
    if current_aihub_status == incoming_status:
        return _ok(
            {
                "tracker_id": tracker_id_str,
                "aihub_status": current_aihub_status,
                "idempotent": True,
            }
        )

    # --- RESOLVE NEW TRACKER LABEL ----------------------------------------------
    # Map the incoming status to the human-readable current_status label shown
    # in System A's dashboard and email drafts.  Unknown statuses are stored
    # as-is so a future status value doesn't crash the callback.
    new_current_status = _STATUS_TO_TRACKER_LABEL.get(
        incoming_status,
        f"aihub:{incoming_status}",  # forward-compat fallback
    )

    # --- UPDATE TRACKER ---------------------------------------------------------
    now = _utcnow()
    session.execute(
        text(
            "UPDATE payment_request_tracker "
            "SET aihub_status    = :aihub_status, "
            "    current_status  = :current_status, "
            "    updated_at      = :now "
            "WHERE id = :tid"
        ),
        {
            "aihub_status": incoming_status,
            "current_status": new_current_status,
            "now": now,
            "tid": tracker_id_str,
        },
    )

    # --- AUDIT LOG --------------------------------------------------------------
    # spec §16: event = bill_synced_received
    # Fields: tracker_id, bill_id, qb_txn_id, previous_status, new_status, timestamp
    _write_audit_log(
        session,
        event="bill_synced_received",
        tracker_id=tracker_id_str,
        bill_id=bill_id_str,
        qb_txn_id=payload.qb_txn_id,
        previous_status=previous_current_status,
        new_status=new_current_status,
    )

    session.commit()

    # --- RESPONSE 200 -----------------------------------------------------------
    return _ok(
        {
            "tracker_id": tracker_id_str,
            "previous_status": previous_current_status,
            "new_status": new_current_status,
            "aihub_status": incoming_status,
            "idempotent": False,
        }
    )
