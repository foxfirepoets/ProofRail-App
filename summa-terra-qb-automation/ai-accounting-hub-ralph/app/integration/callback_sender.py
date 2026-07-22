"""System B → System A bill-synced callback sender (SPEC §6.6, §12 Phase 2).

Fires POST {system_a_url}/integration/bill-synced after a bill is approved or
rejected in System B. Retries 3× with 30-second back-off on 5xx responses.
On three consecutive failures the event is written to integration_reconciliation.log
(never silently dropped — G4 no-automated-approval, G7 no-silent-loss principle).

Must-not-break guarantees honoured here:
  G1  Never touches draft_queue.
  G4  This module never changes bill.status or approval state — caller does.
  G7  No QBWC path reachable from this module.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

_log = logging.getLogger(__name__)
# Dedicated reconciliation logger so Railway / log-drain filters can target it.
_recon_log = logging.getLogger("integration.reconciliation")

_MAX_RETRIES = 3
_RETRY_DELAY_S = 30


def _log_reconciliation_failure(
    tracker_id: str,
    bill_id: str,
    qb_txn_id: str | None,
    status: str,
    last_error: str,
) -> None:
    """Emit a structured RECONCILIATION_FAILURE log record (never raises, never lost).

    Uses the ``integration.reconciliation`` logger so Railway's log drain captures
    it across container restarts.  No local file is written; the log drain is the
    durable store.
    """
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "event": "bill_synced_callback_failed",
        "tracker_id": tracker_id,
        "bill_id": bill_id,
        "qb_txn_id": qb_txn_id,
        "status": status,
        "last_error": last_error,
        "retries_exhausted": _MAX_RETRIES,
    }
    _recon_log.error("RECONCILIATION_FAILURE %s", json.dumps(record))


def send_bill_synced_callback(
    tracker_id: str,
    bill_id: str,
    qb_txn_id: str | None,
    status: str,
    system_a_url: str,
    system_a_token: str,
) -> bool:
    """POST the bill-synced callback to System A (SPEC §12 Phase 2).

    Retries 3× with 30-second delays on 5xx responses.  4xx responses are
    logged as warnings and are NOT retried (caller error, not transient).
    On three consecutive 5xx or network failures the event is written to
    ``integration_reconciliation.log`` and False is returned.

    Args:
        tracker_id:     System A payment_request_tracker.id (UUID string).
        bill_id:        System B bills.id (UUID string).
        qb_txn_id:      QuickBooks TxnID, or None if not yet synced to QB.
        status:         Bill status string ('approved', 'rejected', 'paid', …).
        system_a_url:   Base URL of System A (e.g. ``https://aihub.example.com``).
        system_a_token: Bearer token System A expects (``SYSTEM_A_CALLBACK_TOKEN``).

    Returns:
        True on success (2xx), False if all retries exhausted (logged).
    """
    url = f"{system_a_url.rstrip('/')}/integration/bill-synced"
    body: dict[str, Any] = {
        "tracker_id": tracker_id,
        "bill_id": bill_id,
        "qb_txn_id": qb_txn_id,
        "status": status,
    }
    headers = {
        "Authorization": f"Bearer {system_a_token}",
        "Content-Type": "application/json",
    }

    last_error = "no attempt made"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=10.0)

            if 200 <= resp.status_code < 300:
                _log.info(
                    "bill-synced callback delivered: tracker_id=%s bill_id=%s status=%s http=%s",
                    tracker_id,
                    bill_id,
                    status,
                    resp.status_code,
                )
                return True

            if 400 <= resp.status_code < 500:
                # 4xx: client/caller error — not retried per spec.
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                _log.warning(
                    "bill-synced callback: System A returned %s (4xx — not retrying): %s",
                    resp.status_code,
                    last_error,
                )
                break

            # 5xx — transient, retry.
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            _log.warning(
                "bill-synced callback 5xx (attempt %s/%s): %s",
                attempt,
                _MAX_RETRIES,
                last_error,
            )

        except httpx.RequestError as exc:
            last_error = str(exc)
            _log.warning(
                "bill-synced callback network error (attempt %s/%s): %s",
                attempt,
                _MAX_RETRIES,
                exc,
            )

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_DELAY_S)

    _log.error(
        "bill-synced callback failed after %s attempts for tracker_id=%s — writing to reconciliation log",
        _MAX_RETRIES,
        tracker_id,
    )
    _log_reconciliation_failure(tracker_id, bill_id, qb_txn_id, status, last_error)
    return False
