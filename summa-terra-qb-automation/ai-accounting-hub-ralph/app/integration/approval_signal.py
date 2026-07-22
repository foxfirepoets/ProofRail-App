"""approval_signal.py -- System A approval signal delivery (reference implementation).

IMPORTANT: This is a REFERENCE IMPLEMENTATION for System A.
System A is a separate Railway service (Supabase: ejxrbxoncsgglrqvjulg).
This file lives in ai-accounting-hub-ralph/app/integration/ so it is
version-controlled alongside System B and can be handed off to the System A
team as a drop-in module. It must NOT import System B models or connect to
fdnwlcomuddzmluvbylg.

Spec references:
  Section 5 Flow 1 Steps 12-13  -- Mike approval email detected → POST /approvals/{wf_id}
  Section 7 edge cases           -- signal after workflow confirmed (aihub_workflow_id precondition)
  Section 4 data flow map        -- MIKE APPROVAL SIGNAL (Path A — email)
  Section 6.6                    -- POST /approvals/{workflow_id} request/response contract

Must-not-break guarantees enforced in this module:
  [2] bank_change_risk P0 -- this module only fires AFTER the outbox delivery job has
      already stored aihub_workflow_id; the risk guard ran before bill_intent was
      written. No bill_intent → no workflow_id → precondition guard blocks signal.
  [4] No automated approvals -- this function fires ONLY after detect_mike_approval()
      returns True in System A's classify path. No polling, no auto-approval, no
      approval from System A logic alone; the human approval is Mike's email.
  [5] This module targets System A DB (ejxrbxoncsgglrqvjulg) ONLY for audit logging.
      System B is reached via HTTP POST to system_b_base_url -- never via DB.

Security rules:
  - Bearer token (aihub_outbox_token) is passed as a parameter; never read from env
    here — callers are responsible for injecting from Railway env vars.
  - Body payload contains ONLY decision, source, and evidence_email_id (Gmail message
    ID). No raw email body, no bank data, no internal tokens.
  - Auth: Bearer {aihub_outbox_token} -- same token as outbox delivery job (scoped A→B).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tracker statuses where the approval signal MUST NOT fire.
# These match BLOCKED_STATES in outbox_writer.py. If the tracker is in any of
# these states, firing a signal to System B would be incorrect — no bill was
# ever created via the outbox (bank_change_risk or other block condition fired).
BLOCKED_STATES: frozenset[str] = frozenset(
    [
        "Bank Change Risk",
        "Duplicate Detected",
        "Blocked - Manual Review",
        "Failed to Process",
    ]
)

# Retry policy for approval signal delivery (spec Section 4 integration table:
# "3× with 30s delay").
_MAX_RETRIES: int = 3
_RETRY_DELAY_SECONDS: float = 30.0

# HTTP timeout per attempt in seconds.
_HTTP_TIMEOUT_S: float = 10.0


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class WorkflowIdNotYetAssigned(Exception):
    """Raised when fire_approval_signal() is called before aihub_workflow_id is set.

    This enforces the spec Section 7 edge case: "Signal delivery waits until
    aihub_workflow_id is stored. Signal only fires AFTER workflow_id confirmed
    on tracker."

    The caller (System A classify/approval path) must check tracker.aihub_workflow_id
    before calling this function and wait / schedule a retry if it is None.
    """

    def __init__(self, tracker_id: str) -> None:
        self.tracker_id = tracker_id
        super().__init__(
            f"tracker_id={tracker_id!r} does not have aihub_workflow_id set. "
            "The outbox delivery job must complete bill_intent delivery and store "
            "workflow_id before the approval signal can fire."
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_tracker_for_signal(
    db_session: Session,
    tracker_id: str,
) -> dict[str, Any] | None:
    """Fetch the tracker columns required for approval signal precondition checks.

    Returns a mapping with keys:
      id, current_status, aihub_workflow_id, latest_email_id

    Returns None if the tracker row is not found.
    Targets System A ejxrbxoncsgglrqvjulg — db_session must be scoped there.
    """
    row = (
        db_session.execute(
            text(
                "SELECT id, current_status, aihub_workflow_id, latest_email_id "
                "FROM payment_request_tracker "
                "WHERE id = :tracker_id"
            ),
            {"tracker_id": str(tracker_id)},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _audit_log_signal(
    db_session: Session,
    event: str,
    details: dict[str, Any],
) -> None:
    """Write an audit event to automation_audit_log in System A.

    Follows the same non-fatal pattern as outbox_writer._audit_log: if the
    write fails, the error is surfaced in the application log but never re-raised.
    The HTTP delivery result is the durable record; audit is supplementary.
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
        db_session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "approval_signal: audit_log write failed event=%s error=%s",
            event,
            exc,
        )
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _post_approval_signal(
    workflow_id: str,
    evidence_email_id: str | None,
    system_b_base_url: str,
    aihub_outbox_token: str,
) -> tuple[int, dict[str, Any]]:
    """POST the approval decision to System B /approvals/{workflow_id}.

    Async HTTP call — does not block the event loop during I/O or retries.
    Returns (status_code, response_body).
    Network/timeout errors are re-raised to the caller as httpx exceptions so
    the retry loop can treat them as transient 5xx equivalents.

    Body per spec Section 6.6:
      {decision: "approve", source: "email_detected", evidence_email_id: <id>}
    """
    url = system_b_base_url.rstrip("/") + f"/approvals/{workflow_id}"
    body: dict[str, Any] = {
        "decision": "approve",
        "source": "email_detected",
        "evidence_email_id": evidence_email_id,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
        resp = await client.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {aihub_outbox_token}",
                "Content-Type": "application/json",
            },
        )
    try:
        resp_body: dict[str, Any] = resp.json()
        if not isinstance(resp_body, dict):
            resp_body = {"_raw": resp_body}
    except Exception:  # noqa: BLE001
        resp_body = {"_raw": resp.text}
    return resp.status_code, resp_body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fire_approval_signal(
    tracker_id: str,
    db_session: Session,
    system_b_base_url: str,
    aihub_outbox_token: str,
) -> dict[str, Any]:
    """Fire the Mike-approval signal to System B after email detection.

    This function implements Steps 12-13 of Flow 1 (spec Section 5) on the
    System A side: after detect_mike_approval() returns True, System A calls
    this function to POST the approval decision to System B.

    Async: uses ``await asyncio.sleep`` (not ``time.sleep``) for retry delays and
    ``httpx.AsyncClient`` for HTTP so the event loop is never blocked.

    PRECONDITION (spec Section 7 edge case):
        tracker.aihub_workflow_id MUST be set (not None). If None, the outbox
        delivery job has not yet completed bill_intent delivery and System B
        has not yet assigned a workflow_id. Raises WorkflowIdNotYetAssigned.
        Callers must wait/retry until the workflow_id is available.

    BLOCKED_STATES guard:
        If tracker.current_status is in BLOCKED_STATES, the signal is not
        fired. This can happen if a bank_change_risk event raced the approval
        detection. Logs to audit and returns immediately with a sentinel dict.

    Retry policy (spec Section 4 integration table):
        Up to 3 attempts; 30s delay between each attempt on 5xx or transport
        error. Non-retryable 4xx errors fail immediately.

    Audit logging:
        - approval_signal_fired: on first 2xx response
        - approval_signal_failed: on each attempt failure; also on final failure

    Args:
        tracker_id:          UUID of the payment_request_tracker row (System A).
        db_session:          SQLAlchemy Session pointed at ejxrbxoncsgglrqvjulg.
        system_b_base_url:   Base URL of the System B FastAPI service.
        aihub_outbox_token:  Bearer token for System B /approvals/* endpoint.

    Returns:
        dict -- the System B approval response body on success.
        On BLOCKED_STATES: {"blocked": True, "reason": "blocked_status",
                            "current_status": <status>}

    Raises:
        WorkflowIdNotYetAssigned: tracker.aihub_workflow_id is None.
        RuntimeError: all retry attempts exhausted without a 2xx response.
    """
    tracker = _get_tracker_for_signal(db_session, tracker_id)

    if tracker is None:
        logger.error(
            "approval_signal: tracker_id=%s not found — cannot fire signal",
            tracker_id,
        )
        _audit_log_signal(
            db_session,
            "approval_signal_failed",
            {
                "tracker_id": str(tracker_id),
                "reason": "tracker_not_found",
            },
        )
        raise RuntimeError(
            f"fire_approval_signal: tracker_id={tracker_id!r} not found in "
            "payment_request_tracker."
        )

    # PRECONDITION: aihub_workflow_id must be set (spec Section 7 edge case).
    # The outbox delivery job stores this after a confirmed 2xx /intents/bill
    # response. Signal must not fire before that completes.
    workflow_id: str | None = tracker.get("aihub_workflow_id")
    if not workflow_id:
        logger.warning(
            "approval_signal: tracker_id=%s aihub_workflow_id is None "
            "— WorkflowIdNotYetAssigned raised",
            tracker_id,
        )
        _audit_log_signal(
            db_session,
            "approval_signal_failed",
            {
                "tracker_id": str(tracker_id),
                "reason": "workflow_id_not_yet_assigned",
            },
        )
        raise WorkflowIdNotYetAssigned(tracker_id)

    # BLOCKED_STATES guard: do not fire if tracker is in a blocked state.
    # This guards against a bank_change_risk event that raced the approval.
    current_status: str = str(tracker.get("current_status") or "")
    if current_status in BLOCKED_STATES:
        logger.warning(
            "approval_signal: tracker_id=%s current_status=%r is in BLOCKED_STATES "
            "— signal NOT fired",
            tracker_id,
            current_status,
        )
        _audit_log_signal(
            db_session,
            "approval_signal_failed",
            {
                "tracker_id": str(tracker_id),
                "reason": "blocked_status",
                "current_status": current_status,
                "aihub_workflow_id": workflow_id,
            },
        )
        return {
            "blocked": True,
            "reason": "blocked_status",
            "current_status": current_status,
        }

    evidence_email_id: str | None = tracker.get("latest_email_id")

    logger.info(
        "approval_signal: firing signal tracker_id=%s workflow_id=%s "
        "evidence_email_id=%s",
        tracker_id,
        workflow_id,
        evidence_email_id,
    )

    last_error: str = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        # 30s delay between retries (not before the first attempt).
        if attempt > 1:
            logger.debug(
                "approval_signal: attempt %d/%d — sleeping %.0fs before retry "
                "tracker_id=%s workflow_id=%s",
                attempt,
                _MAX_RETRIES,
                _RETRY_DELAY_SECONDS,
                tracker_id,
                workflow_id,
            )
            await asyncio.sleep(_RETRY_DELAY_SECONDS)

        try:
            status_code, resp_body = await _post_approval_signal(
                workflow_id=workflow_id,
                evidence_email_id=evidence_email_id,
                system_b_base_url=system_b_base_url,
                aihub_outbox_token=aihub_outbox_token,
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
            # Treat transport errors as transient — retry.
            last_error = f"transport error attempt {attempt}: {exc.__class__.__name__}: {exc}"
            logger.warning(
                "approval_signal: attempt %d/%d transport error tracker_id=%s "
                "workflow_id=%s — %s",
                attempt,
                _MAX_RETRIES,
                tracker_id,
                workflow_id,
                last_error,
            )
            _audit_log_signal(
                db_session,
                "approval_signal_failed",
                {
                    "tracker_id": str(tracker_id),
                    "aihub_workflow_id": workflow_id,
                    "attempt": attempt,
                    "error": last_error,
                },
            )
            continue

        # 2xx: success.
        if 200 <= status_code < 300:
            logger.info(
                "approval_signal: SUCCESS tracker_id=%s workflow_id=%s "
                "status=%d response=%s",
                tracker_id,
                workflow_id,
                status_code,
                resp_body,
            )
            _audit_log_signal(
                db_session,
                "approval_signal_fired",
                {
                    "tracker_id": str(tracker_id),
                    "aihub_workflow_id": workflow_id,
                    "evidence_email_id": evidence_email_id,
                    "attempt": attempt,
                    "system_b_response_status": status_code,
                    "system_b_response": resp_body,
                },
            )
            return resp_body

        # 5xx: retryable server error.
        if status_code >= 500:
            error_detail = (
                resp_body.get("error")
                or resp_body.get("detail")
                or str(resp_body)
            )
            last_error = f"5xx status={status_code}: {error_detail}"
            logger.warning(
                "approval_signal: attempt %d/%d 5xx tracker_id=%s workflow_id=%s "
                "— %s",
                attempt,
                _MAX_RETRIES,
                tracker_id,
                workflow_id,
                last_error,
            )
            _audit_log_signal(
                db_session,
                "approval_signal_failed",
                {
                    "tracker_id": str(tracker_id),
                    "aihub_workflow_id": workflow_id,
                    "attempt": attempt,
                    "error": last_error,
                    "system_b_response": resp_body,
                },
            )
            continue

        # 4xx: non-retryable client error. Fail immediately.
        error_detail = (
            resp_body.get("error")
            or resp_body.get("detail")
            or str(resp_body)
        )
        last_error = f"non-retryable {status_code}: {error_detail}"
        logger.error(
            "approval_signal: non-retryable %d tracker_id=%s workflow_id=%s "
            "— %s",
            status_code,
            tracker_id,
            workflow_id,
            last_error,
        )
        _audit_log_signal(
            db_session,
            "approval_signal_failed",
            {
                "tracker_id": str(tracker_id),
                "aihub_workflow_id": workflow_id,
                "attempt": attempt,
                "error": last_error,
                "system_b_response": resp_body,
            },
        )
        raise RuntimeError(
            f"fire_approval_signal: non-retryable {status_code} from System B "
            f"workflow_id={workflow_id!r}: {last_error}"
        )

    # All retries exhausted without a 2xx.
    logger.error(
        "approval_signal: PERMANENTLY FAILED after %d attempts tracker_id=%s "
        "workflow_id=%s last_error=%s",
        _MAX_RETRIES,
        tracker_id,
        workflow_id,
        last_error,
    )
    _audit_log_signal(
        db_session,
        "approval_signal_failed",
        {
            "tracker_id": str(tracker_id),
            "aihub_workflow_id": workflow_id,
            "attempt": _MAX_RETRIES,
            "error": f"PERMANENTLY FAILED after {_MAX_RETRIES} attempts: {last_error}",
        },
    )
    raise RuntimeError(
        f"fire_approval_signal: all {_MAX_RETRIES} attempts failed for "
        f"tracker_id={tracker_id!r} workflow_id={workflow_id!r}. "
        f"Last error: {last_error}"
    )
