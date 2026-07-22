"""System A outbox delivery background job (STV Integration Layer Phase 1).

Picks up pending rows from ``integration_outbox`` (System A DB —
ejxrbxoncsgglrqvjulg) and delivers each event to the correct System B
endpoint via HTTP POST.

This module is a **System A reference implementation** that lives in the
System B codebase for co-location with the integration layer spec.  The
``db_session`` parameter is always a System A database session; System B's
Postgres (fdnwlcomuddzmluvbylg) is never touched here — only HTTP.

MUST-NOT-BREAK GUARANTEES upheld here
--------------------------------------
1. ``draft_queue.status`` — this module never reads or writes ``draft_queue``.
2. ``bank_change_risk`` P0 — enforced by ``outbox_writer`` before the row is
   inserted; this job trusts the row type already in the table.
3. STV CM LLC guard — this job never creates a ``draw_intent`` row; it only
   delivers rows that the outbox_writer already decided to create.  System B
   applies an independent STV CM LLC check on POST /intents/draw.
4. No automated approvals — this job delivers bill_intent / draw_intent /
   bank_block / payment_confirmed only.  It NEVER calls
   POST /approvals/{workflow_id}.
5. System A DB vs System B DB — the injected ``db_session`` is System A; System B
   is HTTP-only from this module.
6. SwarmSync Gate 1 — happens inside System B after /intents/bill; this job
   has no visibility into or control over it.
7. Never write to QB — this module has no QB path.

Retry/alert policy
------------------
- Exponential backoff applied WITHIN each call: attempt N is preceded by a
  ``backoff_seconds(N - 1)`` sleep (attempt 1 has no sleep).
- Attempt counter is cumulative across job runs (persisted in DB column
  ``attempts``).
- Attempt ≥ 3: P1 dashboard warning logged.
- Attempt ≥ 5: row marked ``status='failed'``; email-alert entry written to
  ``automation_audit_log``.
- Non-retryable 4xx responses are marked ``status='failed'`` immediately.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Mapping from integration_outbox.event_type → System B endpoint path.
_ENDPOINT_MAP: dict[str, str] = {
    "bill_intent": "/intents/bill",
    "draw_intent": "/intents/draw",
    "bank_block": "/intents/bank-block",
    "payment_confirmed": "/intents/payment-confirmed",
}

# P1 alert fires at this cumulative attempt number (inclusive).
_P1_ALERT_ATTEMPT: int = 3
# Row is marked status='failed' at this cumulative attempt number (inclusive).
_FAIL_ATTEMPT: int = 5

# HTTP timeout in seconds for each delivery POST.
_HTTP_TIMEOUT_S: float = 10.0


# ---------------------------------------------------------------------------
# Public helper functions (importable / testable individually)
# ---------------------------------------------------------------------------


def backoff_seconds(attempt: int) -> float:
    """Return the exponential backoff wait time for a given attempt number.

    ``attempt`` is 1-indexed: the number of PRIOR failures before the next try.

    Mapping:
        attempt 1 → 1s  (first retry after 1 failure)
        attempt 2 → 2s
        attempt 3 → 4s
        attempt 4 → 8s
        attempt 5 → 16s

    Clamps at attempt ≥ 5 to avoid unbounded growth.
    """
    clamped = max(1, min(attempt, 5))
    return float(2 ** (clamped - 1))


def get_system_b_endpoint(event_type: str, base_url: str) -> str:
    """Return the full System B URL for a given ``event_type``.

    Args:
        event_type: One of ``bill_intent``, ``draw_intent``, ``bank_block``,
                    ``payment_confirmed``.
        base_url:   System B base URL (e.g. ``https://aihub.railway.app``).

    Returns:
        Full URL string, e.g. ``https://aihub.railway.app/intents/bill``.

    Raises:
        ValueError: if ``event_type`` is not in the allowed set.
    """
    path = _ENDPOINT_MAP.get(event_type)
    if path is None:
        allowed = ", ".join(sorted(_ENDPOINT_MAP))
        raise ValueError(
            f"Unknown event_type {event_type!r}. Allowed: {allowed}"
        )
    return base_url.rstrip("/") + path


# ---------------------------------------------------------------------------
# Private DB helpers
# ---------------------------------------------------------------------------


def _mark_delivered(db_session: Session, outbox_id: str) -> None:
    """Set status='delivered' and sent_at=NOW() on the outbox row."""
    try:
        db_session.execute(
            text(
                """
                UPDATE integration_outbox
                   SET status  = 'delivered',
                       sent_at = NOW()
                 WHERE id = CAST(:id AS uuid)
                   AND status = 'pending'
                """
            ),
            {"id": outbox_id},
        )
        db_session.commit()
    except Exception:
        logger.exception("Failed to mark outbox row %s as delivered", outbox_id)
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            pass


def _increment_attempts(
    db_session: Session,
    outbox_id: str,
    error_message: str = "",
) -> None:
    """Increment ``attempts`` by 1 and store the latest error message."""
    try:
        db_session.execute(
            text(
                """
                UPDATE integration_outbox
                   SET attempts      = attempts + 1,
                       error_message = :error_message
                 WHERE id = CAST(:id AS uuid)
                   AND status = 'pending'
                """
            ),
            {"id": outbox_id, "error_message": error_message[:2000]},
        )
        db_session.commit()
    except Exception:
        logger.exception("Failed to increment attempts for outbox row %s", outbox_id)
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            pass


def _mark_failed(
    db_session: Session,
    outbox_id: str,
    error_message: str = "",
) -> None:
    """Set status='failed' (terminal state) on the outbox row."""
    try:
        db_session.execute(
            text(
                """
                UPDATE integration_outbox
                   SET status        = 'failed',
                       error_message = :error_message
                 WHERE id = CAST(:id AS uuid)
                """
            ),
            {"id": outbox_id, "error_message": error_message[:2000]},
        )
        db_session.commit()
    except Exception:
        logger.exception("Failed to mark outbox row %s as failed", outbox_id)
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            pass


def _log_audit(
    db_session: Session,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Append a row to ``automation_audit_log`` (System A table).

    Canonical schema: (id UUID, event_type VARCHAR, payload JSONB, created_at TIMESTAMPTZ).
    Failures are swallowed and logged — audit writes must never block delivery.
    """
    import uuid as _uuid
    try:
        db_session.execute(
            text(
                """
                INSERT INTO automation_audit_log (id, event_type, payload, created_at)
                VALUES (:id, :event_type, CAST(:payload AS jsonb), NOW())
                """
            ),
            {
                "id": str(_uuid.uuid4()),
                "event_type": event_type,
                "payload": json.dumps(payload),
            },
        )
        db_session.commit()
    except Exception:
        logger.exception(
            "Failed to write automation_audit_log entry event_type=%s (non-fatal)",
            event_type,
        )
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Private tracker update (called after successful bill_intent delivery)
# ---------------------------------------------------------------------------


async def _update_tracker_workflow_id(
    db_session: Session,
    tracker_id: str,
    workflow_id: str,
    bill_id: str,
) -> None:
    """Store the System B workflow_id and bill_id on the System A tracker row.

    Called only after a confirmed 2xx bill_intent delivery where the response
    body contains both ``workflow_id`` and ``bill_id``.  Failures are logged
    but do NOT re-raise — delivery is already confirmed at this point.
    """
    try:
        db_session.execute(
            text(
                """
                UPDATE payment_request_tracker
                   SET aihub_workflow_id = :workflow_id,
                       aihub_bill_id     = CAST(:bill_id AS uuid),
                       aihub_status      = 'active'
                 WHERE id = CAST(:tracker_id AS uuid)
                """
            ),
            {
                "workflow_id": workflow_id,
                "bill_id": bill_id,
                "tracker_id": tracker_id,
            },
        )
        db_session.commit()
        logger.info(
            "Tracker %s updated: aihub_workflow_id=%s aihub_bill_id=%s aihub_status=active",
            tracker_id,
            workflow_id,
            bill_id,
        )
    except Exception:
        logger.exception(
            "Failed to update payment_request_tracker for tracker_id=%s "
            "workflow_id=%s (non-fatal — delivery already confirmed)",
            tracker_id,
            workflow_id,
        )
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Private HTTP delivery helper
# ---------------------------------------------------------------------------


async def _post_to_system_b(
    endpoint_url: str,
    payload: dict[str, Any],
    token: str,
) -> tuple[int, dict[str, Any]]:
    """POST ``payload`` to ``endpoint_url`` with bearer auth.

    Returns ``(status_code, response_body)`` where response_body is a dict
    (falls back to ``{"_raw": text}`` if JSON decoding fails).

    Network / timeout errors are re-raised to the caller as ``httpx.HTTPError``
    subclasses so the caller can treat them as transient 5xx equivalents.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
        resp = await client.post(
            endpoint_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    try:
        body: dict[str, Any] = resp.json()
        if not isinstance(body, dict):
            body = {"_raw": body}
    except Exception:
        body = {"_raw": resp.text}
    return resp.status_code, body


# ---------------------------------------------------------------------------
# Main async coroutine
# ---------------------------------------------------------------------------


async def deliver_pending_outbox_rows(
    db_session: Session,
    system_b_base_url: str,
    aihub_outbox_token: str,
) -> None:
    """Deliver all ``integration_outbox`` rows with ``status='pending'``.

    Designed to be called from a FastAPI background task, a startup lifespan
    loop, or an APScheduler/Celery beat job.  Each invocation attempts at most
    one HTTP POST per pending row; exponential backoff is enforced between rows
    that have prior failures so callers can invoke this in a tight loop without
    hammering System B.

    Args:
        db_session:         SQLAlchemy session bound to **System A** Supabase
                            (ejxrbxoncsgglrqvjulg).  Never used for System B.
        system_b_base_url:  Base URL of the System B FastAPI service, e.g.
                            ``https://aihub.railway.app``.
        aihub_outbox_token: Bearer token for System B endpoints
                            (``AIHUB_OUTBOX_TOKEN`` env var on System A).

    Side-effects per row:
        2xx  → ``status='delivered'``, ``sent_at=NOW()``;
               ``automation_audit_log`` row ``outbox_delivered``;
               if bill_intent + workflow_id in response:
                 ``payment_request_tracker`` updated with workflow_id.
        5xx  → ``attempts += 1``, error_message stored;
               if attempts ≥ 3: P1 warning logged;
               if attempts ≥ 5: ``status='failed'``;
                 ``automation_audit_log`` row ``outbox_delivery_failed`` (email alert).
        4xx  → ``status='failed'`` immediately (non-retryable);
               ``automation_audit_log`` row ``outbox_delivery_failed``.
        network error → treated as 5xx for retry purposes.
    """
    rows = (
        db_session.execute(
            text(
                """
                SELECT id,
                       tracker_id,
                       event_type,
                       payload,
                       attempts
                  FROM integration_outbox
                 WHERE status = 'pending'
                 ORDER BY created_at ASC
                """
            )
        )
        .mappings()
        .all()
    )

    if not rows:
        logger.debug("outbox_delivery_job: no pending rows — nothing to do")
        return

    logger.info("outbox_delivery_job: %d pending row(s) queued for delivery", len(rows))

    for row in rows:
        outbox_id: str = str(row["id"])
        tracker_id: str | None = (
            str(row["tracker_id"]) if row["tracker_id"] else None
        )
        event_type: str = str(row["event_type"])
        payload: dict[str, Any] = (
            row["payload"] if isinstance(row["payload"], dict) else {}
        )
        current_attempts: int = int(row["attempts"])
        next_attempt: int = current_attempts + 1

        # Guard: row should have been marked failed already; fix it now.
        if current_attempts >= _FAIL_ATTEMPT:
            logger.warning(
                "outbox row %s already at %d attempts but still pending — marking failed now",
                outbox_id,
                current_attempts,
            )
            _mark_failed(
                db_session,
                outbox_id,
                f"re-queued at {current_attempts} attempts — forced to failed",
            )
            _log_audit(
                db_session,
                "outbox_delivery_failed",
                {
                    "outbox_id": outbox_id,
                    "attempt": current_attempts,
                    "error": "exceeded max attempts on re-query (guard)",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            continue

        # Resolve endpoint URL; unknown event_type → immediate failure.
        try:
            endpoint_url = get_system_b_endpoint(event_type, system_b_base_url)
        except ValueError as exc:
            logger.error(
                "outbox row %s: unrecognized event_type %r — %s",
                outbox_id,
                event_type,
                exc,
            )
            _mark_failed(
                db_session, outbox_id, f"unrecognized event_type: {event_type}"
            )
            _log_audit(
                db_session,
                "outbox_delivery_failed",
                {
                    "outbox_id": outbox_id,
                    "attempt": next_attempt,
                    "error": f"unrecognized event_type: {event_type}",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            continue

        # Exponential backoff: sleep before re-attempting a row with prior failures.
        # Rows on their first attempt (current_attempts == 0) proceed immediately.
        if current_attempts > 0:
            wait_s = backoff_seconds(current_attempts)
            logger.debug(
                "outbox row %s: attempt %d of %d — sleeping %.1fs (backoff)",
                outbox_id,
                next_attempt,
                _FAIL_ATTEMPT,
                wait_s,
            )
            await asyncio.sleep(wait_s)

        # Attempt HTTP delivery.
        status_code: int
        body: dict[str, Any]
        try:
            status_code, body = await _post_to_system_b(
                endpoint_url, payload, aihub_outbox_token
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
            # Treat transport errors as transient server errors.
            error_str = f"transport error: {exc.__class__.__name__}: {exc}"
            logger.warning(
                "outbox row %s: attempt %d — %s", outbox_id, next_attempt, error_str
            )
            status_code = 503
            body = {"_error": error_str}

        # ---- 2xx: successful delivery ----------------------------------------
        if 200 <= status_code < 300:
            _mark_delivered(db_session, outbox_id)

            workflow_id: str | None = (
                str(body["workflow_id"]) if body.get("workflow_id") else None
            )
            bill_id: str | None = (
                str(body["bill_id"]) if body.get("bill_id") else None
            )

            logger.info(
                "outbox row %s delivered — status=%d event_type=%s "
                "workflow_id=%s bill_id=%s",
                outbox_id,
                status_code,
                event_type,
                workflow_id,
                bill_id,
            )

            _log_audit(
                db_session,
                "outbox_delivered",
                {
                    "outbox_id": outbox_id,
                    "system_b_response_status": status_code,
                    "bill_id": bill_id,
                    "workflow_id": workflow_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            # After successful bill_intent delivery: update tracker with workflow_id.
            if (
                event_type == "bill_intent"
                and workflow_id
                and bill_id
                and tracker_id
            ):
                await _update_tracker_workflow_id(
                    db_session, tracker_id, workflow_id, bill_id
                )

        # ---- 5xx / transport error: retryable failure ------------------------
        elif status_code >= 500:
            error_body = (
                body.get("_error")
                or body.get("detail")
                or body.get("error")
                or str(body)
            )
            error_str = f"5xx status={status_code}: {error_body}"

            # Increment attempts first so the DB reflects the true count.
            _increment_attempts(db_session, outbox_id, error_str)

            # P1 alert at attempts 3 and 4 only; suppressed at attempt 5 where
            # the permanent-failure email-level audit entry fires instead.
            if _P1_ALERT_ATTEMPT <= next_attempt < _FAIL_ATTEMPT:
                logger.warning(
                    "P1 ALERT — outbox delivery attempt %d: "
                    "outbox_id=%s event_type=%s endpoint=%s error=%s",
                    next_attempt,
                    outbox_id,
                    event_type,
                    endpoint_url,
                    error_str,
                )

            # Mark failed and log email-alert at attempt 5.
            if next_attempt >= _FAIL_ATTEMPT:
                _mark_failed(
                    db_session,
                    outbox_id,
                    f"5xx after {next_attempt} attempts: {error_str}",
                )
                _log_audit(
                    db_session,
                    "outbox_delivery_failed",
                    {
                        "outbox_id": outbox_id,
                        "attempt": next_attempt,
                        "error": (
                            f"EMAIL ALERT: outbox row permanently failed after "
                            f"{next_attempt} attempts. Last error: {error_str}"
                        ),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
                logger.error(
                    "outbox row %s: PERMANENTLY FAILED after %d attempts "
                    "(status=%d). Email alert written to automation_audit_log.",
                    outbox_id,
                    next_attempt,
                    status_code,
                )
            else:
                _log_audit(
                    db_session,
                    "outbox_delivery_failed",
                    {
                        "outbox_id": outbox_id,
                        "attempt": next_attempt,
                        "error": error_str,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
                logger.warning(
                    "outbox row %s: attempt %d returned %d — will retry on next cycle",
                    outbox_id,
                    next_attempt,
                    status_code,
                )

        # ---- 4xx: non-retryable client error ---------------------------------
        else:
            error_str = (
                str(body.get("error") or body.get("detail") or body)
            )
            logger.error(
                "outbox row %s: non-retryable response %d from %s — %s",
                outbox_id,
                status_code,
                endpoint_url,
                error_str,
            )
            _mark_failed(
                db_session,
                outbox_id,
                f"non-retryable {status_code}: {error_str}",
            )
            _log_audit(
                db_session,
                "outbox_delivery_failed",
                {
                    "outbox_id": outbox_id,
                    "attempt": next_attempt,
                    "error": f"non-retryable {status_code}: {error_str}",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
