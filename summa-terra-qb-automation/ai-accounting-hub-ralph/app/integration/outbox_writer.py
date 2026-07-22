"""outbox_writer.py -- System A outbox writer (reference implementation).

IMPORTANT: This is a REFERENCE IMPLEMENTATION for System A.
System A is a separate Railway service (Supabase: ejxrbxoncsgglrqvjulg).
This file lives in ai-accounting-hub-ralph/app/integration/ so it is
version-controlled alongside System B and can be handed off to the System A
team as a drop-in module. It must NOT import System B models or connect to
fdnwlcomuddzmluvbylg.

Spec references:
  Section 6.1  -- integration_outbox schema + valid payload shapes per event_type
  Section 7    -- outbox writer error codes and guards
  Section 10   -- unit test contract (test_outbox_writer.py)

Must-not-break guarantees enforced in this module:
  [2] bank_change_risk P0 guard fires BEFORE any bill_intent INSERT -- write_bank_block()
      is called instead; no bill_intent row is ever written for a risky tracker.
  [3] STV CM LLC guard fires BEFORE any draw_intent INSERT -- write_draw_intent() with
      blocked=True returns None and logs "stv_cm_llc_draw_blocked".
  [4] This module only enqueues outbox rows; the human approval gate is enforced
      downstream (Temporal) -- no automated approvals here.
  [5] This module targets System A DB (ejxrbxoncsgglrqvjulg) ONLY. The db_session
      passed in must point to ejxrbxoncsgglrqvjulg. System B (fdnwlcomuddzmluvbylg)
      is never referenced.

Security rules (enforced per spec Section 9):
  - Payload JSONB NEVER contains API keys, raw email body, or bank account numbers.
  - bank_block payload: vendor_name + sender_email + gmail_message_id only.
  - raw_extensions: only allowlisted keys are forwarded (no bearer tokens, no secrets).
  - draft_queue: this module has zero access to draft_queue (never reads or writes it).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tracker statuses where NO outbox row of any type is written.
# These states indicate the tracker has already been flagged for manual review
# or is in a terminal error state. Must match System A current_status values.
BLOCKED_STATES: frozenset[str] = frozenset(
    [
        "Bank Change Risk",
        "Duplicate Detected",
        "Blocked - Manual Review",
        "Failed to Process",
    ]
)

# Allowlist of raw_extensions keys safe to carry in bill_intent payload.
# Prevents accidental inclusion of API keys, secrets, or raw email content.
_BILL_INTENT_RAW_EXT_ALLOWLIST: frozenset[str] = frozenset(
    ["project_label", "gmail_thread_id", "gmail_message_id", "requested_by_email"]
)

# Allowlist of raw_extensions keys safe to carry in draw_intent payload.
_DRAW_INTENT_RAW_EXT_ALLOWLIST: frozenset[str] = frozenset(
    ["gmail_thread_id", "gmail_message_id"]
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_tracker(
    db_session: Session,
    tracker_id: str,
) -> dict[str, Any] | None:
    """Fetch the relevant columns from payment_request_tracker.

    Returns a mapping with keys: id, bank_change_risk_flag, current_status.
    Returns None if tracker is not found.

    Targets System A ejxrbxoncsgglrqvjulg -- db_session must be scoped there.
    """
    row = (
        db_session.execute(
            text(
                "SELECT id, bank_change_risk_flag, current_status "
                "FROM payment_request_tracker "
                "WHERE id = :tracker_id "
                "FOR UPDATE"
            ),
            {"tracker_id": str(tracker_id)},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _insert_outbox(
    db_session: Session,
    *,
    tracker_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> str | None:
    """INSERT into integration_outbox with ON CONFLICT DO NOTHING (idempotent).

    The UNIQUE constraint on (tracker_id, event_type) enforces one outbox row
    per tracker per event type. A second call for the same pair is a no-op
    (ON CONFLICT DO NOTHING); returns None in that case.

    Note on draw_intent idempotency: draw_intent rows use tracker_id=NULL and
    PostgreSQL treats all NULLs as distinct in unique constraints, so ON CONFLICT
    does NOT fire for draw_intent duplicates. Callers must guard against
    double-writes by checking fee_opportunities.outbox_written=True before calling
    write_draw_intent(). System B /intents/draw is idempotent on
    gmail_fee_opportunity_id as the second line of defence.

    Returns the new outbox row id (UUID str) on success, None on conflict/no-op.
    """
    outbox_id = str(uuid.uuid4())
    result = db_session.execute(
        text(
            """
            INSERT INTO integration_outbox
                (id, tracker_id, event_type, payload, status, attempts, created_at)
            VALUES
                (:id, :tracker_id, :event_type, CAST(:payload AS jsonb), 'pending', 0, NOW())
            ON CONFLICT (tracker_id, event_type) DO NOTHING
            RETURNING id
            """
        ),
        {
            "id": outbox_id,
            "tracker_id": str(tracker_id) if tracker_id is not None else None,
            "event_type": event_type,
            "payload": json.dumps(payload),
        },
    )
    row = result.fetchone()
    if row is None:
        # ON CONFLICT DO NOTHING fired -- duplicate, not inserted.
        logger.info(
            "outbox_writer: dedup no-op tracker_id=%s event_type=%s",
            tracker_id,
            event_type,
        )
        return None
    db_session.flush()
    inserted_id: str = row[0]
    logger.info(
        "outbox_writer: INSERT outbox id=%s tracker_id=%s event_type=%s",
        inserted_id,
        tracker_id,
        event_type,
    )
    return inserted_id


def _audit_log(
    db_session: Session,
    event: str,
    details: dict[str, Any],
) -> None:
    """Write an audit event to automation_audit_log in System A.

    Canonical schema: (id UUID, event_type VARCHAR, payload JSONB, created_at TIMESTAMPTZ).

    Non-fatal: if the write fails, the error is logged at ERROR level and
    execution continues. The outbox INSERT is the durable record; the audit
    log is supplementary observability. Failure here never silently discards
    the event -- it always surfaces in the application log.
    """
    try:
        db_session.execute(
            text(
                """
                INSERT INTO automation_audit_log
                    (id, event_type, payload, created_at)
                VALUES
                    (:id, :event_type, CAST(:payload AS jsonb), NOW())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "event_type": event,
                "payload": json.dumps(details),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "outbox_writer: audit_log write failed event=%s error=%s",
            event,
            exc,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_bill_intent(
    tracker_id: str,
    vendor_name: str,
    amount: float | None,
    po_ref: str | None,
    due_date: Any | None,
    raw_extensions: dict[str, Any] | None,
    gmail_invoiceproof: dict[str, Any],
    db_session: Session,
) -> str | None:
    """Write a bill_intent outbox row when the tracker is eligible.

    Guards evaluated in order (first match halts processing):

    Guard 1 -- bank_change_risk_flag=True:
        Calls write_bank_block() with sender_email/gmail_message_id extracted
        from raw_extensions. Returns that result (outbox id or None). NO
        bill_intent row is ever written. Audit log: "outbox_bank_change_guard".
        Enforces must-not-break guarantee [2].

    Guard 2 -- tracker.current_status in BLOCKED_STATES:
        No outbox row of any type. Returns None.
        Audit log: "outbox_bill_intent_blocked_status".

    Guard 3 -- idempotency:
        ON CONFLICT (tracker_id, event_type) DO NOTHING. Returns None if the
        row already exists.

    Payload per spec Section 6.1 bill_intent shape. raw_extensions is filtered
    to the allowlist before inclusion. gmail_invoiceproof is passed through
    as-is (advisory pre-screening from System A invoice_proof.py, NOT Gate 1).

    Security:
        Payload NEVER contains API keys, raw email body, or bank account numbers.
        amount_missing=True is set when amount is None so System B can route to
        manual review (spec Section 7: tracker.amount IS NULL -> amount_missing=True).

    Args:
        tracker_id:          UUID of the payment_request_tracker row (System A).
        vendor_name:         Vendor name string.
        amount:              Invoice amount (float) or None if not parsed.
        po_ref:              PO / invoice reference number or None.
        due_date:            Due date as date object, ISO string, or None.
        raw_extensions:      Extension dict (filtered to allowlist before payload).
        gmail_invoiceproof:  Advisory proof dict from System A invoice_proof.py.
                             Required fields per spec: risk_level, final_decision,
                             checks_passed, bank_change_risk, duplicate_detected,
                             vendor_confidence.
        db_session:          SQLAlchemy Session pointed at ejxrbxoncsgglrqvjulg.

    Returns:
        str  -- outbox row UUID on successful INSERT.
        None -- guard triggered (bank_change_risk, blocked status, or dedup no-op).
    """
    tracker = _get_tracker(db_session, tracker_id)

    if tracker is None:
        logger.error(
            "outbox_writer.write_bill_intent: tracker_id=%s not found -- no outbox row",
            tracker_id,
        )
        _audit_log(
            db_session,
            "outbox_bill_intent_tracker_not_found",
            {"tracker_id": str(tracker_id)},
        )
        return None

    # Guard 1: bank_change_risk -- MUST fire BEFORE any bill_intent INSERT (guarantee [2]).
    if tracker.get("bank_change_risk_flag"):
        logger.warning(
            "outbox_writer: bank_change_risk_flag=True tracker_id=%s "
            "-- redirecting to write_bank_block, NOT bill_intent",
            tracker_id,
        )
        _audit_log(
            db_session,
            "outbox_bank_change_guard",
            {
                "tracker_id": str(tracker_id),
                "event_type_blocked": "bill_intent",
            },
        )
        extensions = raw_extensions or {}
        return write_bank_block(
            tracker_id=tracker_id,
            vendor_name=vendor_name,
            sender_email=str(extensions.get("requested_by_email", "")),
            gmail_message_id=str(extensions.get("gmail_message_id", "")),
            db_session=db_session,
        )

    # Guard 2: BLOCKED_STATES -- no outbox row of any type.
    current_status: str = tracker.get("current_status", "")
    if current_status in BLOCKED_STATES:
        logger.warning(
            "outbox_writer: tracker_id=%s current_status=%r in BLOCKED_STATES "
            "-- no outbox row written",
            tracker_id,
            current_status,
        )
        _audit_log(
            db_session,
            "outbox_bill_intent_blocked_status",
            {
                "tracker_id": str(tracker_id),
                "current_status": current_status,
            },
        )
        return None

    # Build payload -- spec Section 6.1 bill_intent shape.
    safe_raw_ext: dict[str, Any] = {}
    if raw_extensions:
        safe_raw_ext = {
            k: v
            for k, v in raw_extensions.items()
            if k in _BILL_INTENT_RAW_EXT_ALLOWLIST
        }

    due_date_str: str | None = None
    if due_date is not None:
        due_date_str = (
            due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)
        )

    payload: dict[str, Any] = {
        "vendor_name": vendor_name,
        "amount": float(amount) if amount is not None else None,
        "amount_missing": amount is None,
        "po_ref": po_ref,
        "due_date": due_date_str,
        "raw_extensions": safe_raw_ext,
        # gmail_invoiceproof is the advisory pre-screening result from System A's
        # invoice_proof.py. It is NOT System B's Gate 1 (VCAP Full Bundle).
        # System B runs Gate 1 independently after receiving the bill_intent.
        "gmail_invoiceproof": gmail_invoiceproof,
    }

    outbox_id = _insert_outbox(
        db_session,
        tracker_id=tracker_id,
        event_type="bill_intent",
        payload=payload,
    )

    if outbox_id is not None:
        _audit_log(
            db_session,
            "outbox_row_written",
            {
                "tracker_id": str(tracker_id),
                "event_type": "bill_intent",
                "outbox_id": outbox_id,
            },
        )

    return outbox_id


def write_bank_block(
    tracker_id: str,
    vendor_name: str,
    sender_email: str,
    gmail_message_id: str,
    db_session: Session,
) -> str | None:
    """Write a bank_block outbox row.

    Called when bank_change_risk_flag=True on a tracker. This path is taken
    INSTEAD of write_bill_intent -- never in addition to it (spec Section 7,
    Section 5 Flow 3 Step 4).

    Security: payload stores ONLY vendor_name, sender_email, and gmail_message_id.
    No raw email body, no bank account numbers, no routing numbers.
    (Spec Section 9: "bank_change_risk payload: store only vendor_name + sender_email;
    no raw email body, no bank account numbers.")

    Idempotency: UNIQUE (tracker_id, event_type) -- a second call for the same
    tracker_id returns None (ON CONFLICT DO NOTHING).

    Args:
        tracker_id:        UUID of the payment_request_tracker row.
        vendor_name:       Vendor name from the classified email.
        sender_email:      Sender email address only -- NOT the email body.
        gmail_message_id:  Gmail message ID for traceability.
        db_session:        SQLAlchemy Session pointed at ejxrbxoncsgglrqvjulg.

    Returns:
        str  -- outbox row UUID on successful INSERT.
        None -- idempotency no-op (bank_block row already exists for tracker_id).
    """
    # SECURITY: only safe identifiers in payload -- no raw email body,
    # no account numbers, no bearer tokens.
    payload: dict[str, Any] = {
        "vendor_name": vendor_name,
        "sender_email": sender_email,
        "gmail_message_id": gmail_message_id,
    }

    outbox_id = _insert_outbox(
        db_session,
        tracker_id=tracker_id,
        event_type="bank_block",
        payload=payload,
    )

    if outbox_id is not None:
        _audit_log(
            db_session,
            "outbox_row_written",
            {
                "tracker_id": str(tracker_id),
                "event_type": "bank_block",
                "outbox_id": outbox_id,
            },
        )

    return outbox_id


def write_draw_intent(
    fee_opportunity_id: str,
    project_canonical: str,
    draw_amount: float,
    draw_number: int | None,
    estimated_fee_hint: float | None,
    fee_payee_hint: str | None,
    fee_payee_status: str,
    raw_extensions: dict[str, Any] | None,
    db_session: Session,
    *,
    blocked: bool = False,
) -> str | None:
    """Write a draw_intent outbox row when fee_opportunities.blocked=False.

    Guard -- STV CM LLC (must-not-break guarantee [3]):
        If blocked=True, NO INSERT is made. Audit log records
        "stv_cm_llc_draw_blocked". Returns None immediately.

    The caller (System A fee_agent) is responsible for reading
    fee_opportunities.blocked and passing it as the `blocked` kwarg.
    System B /intents/draw enforces the same guard independently as a second
    line of defence (defence in depth -- spec Section 5 alternate path).

    Note on idempotency for draw_intent:
        draw_intent rows use tracker_id=NULL (draw events originate from
        fee_opportunities, not from a payment_request_tracker row). PostgreSQL
        treats all NULLs as distinct in UNIQUE constraints, so ON CONFLICT DO
        NOTHING does NOT provide dedup for draw_intent the way it does for
        bill_intent. Callers MUST check fee_opportunities.outbox_written=True
        before calling this function to prevent duplicate rows. System B
        /intents/draw is idempotent on gmail_fee_opportunity_id as the second
        line of defence.

    Payload per spec Section 6.1 draw_intent shape. raw_extensions is filtered
    to the draw_intent allowlist before inclusion.

    Args:
        fee_opportunity_id:   UUID of the fee_opportunities row (System A).
        project_canonical:    Canonical project name (e.g. "Madison Park").
        draw_amount:          Total draw amount (float, must be > 0).
        draw_number:          Draw sequence number or None.
        estimated_fee_hint:   Advisory fee estimate from fee_agent or None.
        fee_payee_hint:       Advisory fee payee name from fee_agent or None.
        fee_payee_status:     "CONFIRMED" | "UNCERTAIN" | "BLOCKED".
        raw_extensions:       Extension dict (filtered to draw_intent allowlist).
        db_session:           SQLAlchemy Session pointed at ejxrbxoncsgglrqvjulg.
        blocked:              Must be fee_opportunities.blocked from System A.
                              If True the STV CM LLC guard fires and returns None.

    Returns:
        str  -- outbox row UUID on successful INSERT.
        None -- STV CM LLC guard triggered (blocked=True), or other error.
    """
    # Guard: STV CM LLC -- must-not-break guarantee [3].
    # fee_opportunities.blocked=True means the fee payee resolved to STV CM LLC.
    if blocked:
        logger.warning(
            "outbox_writer: fee_opportunity_id=%s blocked=True (STV CM LLC) "
            "-- NO draw_intent written (stv_cm_llc_draw_blocked)",
            fee_opportunity_id,
        )
        _audit_log(
            db_session,
            "outbox_stv_cm_llc_guard",
            {
                "fee_opportunity_id": str(fee_opportunity_id),
                "reason": "stv_cm_llc_draw_blocked",
            },
        )
        return None

    safe_raw_ext: dict[str, Any] = {}
    if raw_extensions:
        safe_raw_ext = {
            k: v
            for k, v in raw_extensions.items()
            if k in _DRAW_INTENT_RAW_EXT_ALLOWLIST
        }

    payload: dict[str, Any] = {
        "gmail_fee_opportunity_id": str(fee_opportunity_id),
        "project_canonical": project_canonical,
        "draw_amount": float(draw_amount),
        "draw_number": draw_number,
        "estimated_fee_hint": float(estimated_fee_hint) if estimated_fee_hint is not None else None,
        "fee_payee_hint": fee_payee_hint,
        "fee_payee_status": fee_payee_status,
        "raw_extensions": safe_raw_ext,
    }

    # draw_intent uses tracker_id=NULL because the event originates from
    # fee_opportunities, not payment_request_tracker.
    outbox_id = _insert_outbox(
        db_session,
        tracker_id=None,
        event_type="draw_intent",
        payload=payload,
    )

    if outbox_id is not None:
        _audit_log(
            db_session,
            "outbox_row_written",
            {
                "fee_opportunity_id": str(fee_opportunity_id),
                "event_type": "draw_intent",
                "outbox_id": outbox_id,
            },
        )

    return outbox_id


def write_payment_confirmed(
    tracker_id: str,
    confirmed_by_email: str,
    gmail_message_id: str,
    db_session: Session,
) -> str | None:
    """Write a payment_confirmed outbox row.

    Called when System A detects Aubrey Palmer's payment confirmation email.
    System B /intents/payment-confirmed will advance bill.status to 'paid'.

    Security: payload contains only confirmed_by_email and gmail_message_id --
    no raw email body, no bank account numbers, no bearer tokens.
    (Spec Section 9 data protection rules.)

    Idempotency: UNIQUE (tracker_id, event_type) -- a second call for the same
    tracker_id returns None (ON CONFLICT DO NOTHING).

    Args:
        tracker_id:          UUID of the payment_request_tracker row.
        confirmed_by_email:  Confirmer email address (e.g. aubrey@summaterraventures.com).
        gmail_message_id:    Gmail message ID of the confirmation email.
        db_session:          SQLAlchemy Session pointed at ejxrbxoncsgglrqvjulg.

    Returns:
        str  -- outbox row UUID on successful INSERT.
        None -- idempotency no-op (payment_confirmed row already exists for tracker).
    """
    # SECURITY: email address and message ID only -- no raw body.
    payload: dict[str, Any] = {
        "confirmed_by_email": confirmed_by_email,
        "gmail_message_id": gmail_message_id,
    }

    outbox_id = _insert_outbox(
        db_session,
        tracker_id=tracker_id,
        event_type="payment_confirmed",
        payload=payload,
    )

    if outbox_id is not None:
        _audit_log(
            db_session,
            "outbox_row_written",
            {
                "tracker_id": str(tracker_id),
                "event_type": "payment_confirmed",
                "outbox_id": outbox_id,
            },
        )

    return outbox_id
