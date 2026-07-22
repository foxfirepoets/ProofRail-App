"""Unit tests for app.integration.outbox_writer (SPEC §10).

No live DB required — all SQLAlchemy I/O is patched at the helper-function
level.  Tests mirror the must-not-break guarantees enforced in outbox_writer.py.

Must-not-break coverage:
  [2] bank_change_risk P0 fires BEFORE any bill_intent INSERT.
  [3] STV CM LLC guard fires BEFORE any draw_intent INSERT (blocked=True → None).
  [4] No automated approvals — this module only enqueues outbox rows.
  [5] System A DB only — no System B references in this module.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.integration import outbox_writer as _ow_module
from app.integration.outbox_writer import (
    BLOCKED_STATES,
    _insert_outbox,
    write_bill_intent,
    write_draw_intent,
)

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

_TRACKER_ID = str(uuid.uuid4())
_FEE_OP_ID = str(uuid.uuid4())
_OUTBOX_ID = str(uuid.uuid4())

_GMAIL_INVOICEPROOF: dict = {
    "risk_level": "low",
    "final_decision": "approved",
    "checks_passed": 7,
    "bank_change_risk": False,
    "duplicate_detected": False,
    "vendor_confidence": 0.95,
}

_RAW_EXT: dict = {
    "project_label": "Madison Park",
    "gmail_thread_id": "thread-abc",
    "gmail_message_id": "msg-xyz",
    "requested_by_email": "aubrey@summaterraventures.com",
}

_ELIGIBLE_TRACKER: dict = {
    "id": _TRACKER_ID,
    "bank_change_risk_flag": False,
    "current_status": "Pending Review",
}


def _mock_session() -> MagicMock:
    """Return a fresh MagicMock that quacks like an SQLAlchemy Session."""
    return MagicMock()


def _bill_intent_kwargs(**overrides) -> dict:
    base = dict(
        tracker_id=_TRACKER_ID,
        vendor_name="Makers Line",
        amount=50_000.00,
        po_ref="PO-001",
        due_date=None,
        raw_extensions=_RAW_EXT,
        gmail_invoiceproof=_GMAIL_INVOICEPROOF,
        db_session=_mock_session(),
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# SPEC §10 — test_bill_intent_written_when_eligible
# ---------------------------------------------------------------------------


def test_bill_intent_written_when_eligible():
    """Tracker with bank_change_risk=False and status not in BLOCKED_STATES →
    INSERT bill_intent outbox row; returned value is the new outbox UUID.
    """
    with (
        patch.object(_ow_module, "_get_tracker", return_value=_ELIGIBLE_TRACKER),
        patch.object(_ow_module, "_insert_outbox", return_value=_OUTBOX_ID) as mock_insert,
        patch.object(_ow_module, "_audit_log"),
    ):
        result = write_bill_intent(**_bill_intent_kwargs())

    assert result == _OUTBOX_ID, "Expected the new outbox row UUID"
    mock_insert.assert_called_once()
    _, kwargs = mock_insert.call_args
    assert kwargs["event_type"] == "bill_intent"
    assert kwargs["tracker_id"] == _TRACKER_ID


# ---------------------------------------------------------------------------
# SPEC §10 — test_no_bill_intent_when_bank_change_risk
# ---------------------------------------------------------------------------


def test_no_bill_intent_when_bank_change_risk():
    """Tracker with bank_change_risk_flag=True → bank_block written INSTEAD OF bill_intent.

    Must-not-break guarantee [2]: bank_change_risk P0 fires BEFORE any bill_intent INSERT.
    The function must call _insert_outbox with event_type='bank_block', never 'bill_intent'.
    """
    risky_tracker = {
        "id": _TRACKER_ID,
        "bank_change_risk_flag": True,
        "current_status": "Pending Review",
    }
    bank_block_id = str(uuid.uuid4())

    with (
        patch.object(_ow_module, "_get_tracker", return_value=risky_tracker),
        patch.object(_ow_module, "_insert_outbox", return_value=bank_block_id) as mock_insert,
        patch.object(_ow_module, "_audit_log"),
    ):
        result = write_bill_intent(**_bill_intent_kwargs())

    # Returns bank_block outbox id (not None) — the bank alert IS written.
    assert result == bank_block_id
    mock_insert.assert_called_once()
    _, kwargs = mock_insert.call_args
    assert kwargs["event_type"] == "bank_block", (
        f"bank_change_risk guard must redirect to 'bank_block', got {kwargs['event_type']!r}"
    )
    # Verify 'bill_intent' was never passed to _insert_outbox.
    all_event_types = [c[1].get("event_type") for c in mock_insert.call_args_list]
    assert "bill_intent" not in all_event_types, (
        "bill_intent must NEVER be written when bank_change_risk_flag=True (guarantee [2])"
    )


# ---------------------------------------------------------------------------
# SPEC §10 — test_no_draw_intent_when_stv_cm_llc
# ---------------------------------------------------------------------------


def test_no_draw_intent_when_stv_cm_llc():
    """fee_opportunities.blocked=True → NO draw_intent row; audit log records the block.

    Must-not-break guarantee [3]: STV CM LLC guard fires before any INSERT.
    """
    audit_events: list[str] = []

    def capture_audit(db_session, event: str, details: dict) -> None:
        audit_events.append(event)

    with (
        patch.object(_ow_module, "_insert_outbox") as mock_insert,
        patch.object(_ow_module, "_audit_log", side_effect=capture_audit),
    ):
        result = write_draw_intent(
            fee_opportunity_id=_FEE_OP_ID,
            project_canonical="Madison Park",
            draw_amount=500_000.00,
            draw_number=1,
            estimated_fee_hint=25_000.00,
            fee_payee_hint="STV CM LLC",
            fee_payee_status="BLOCKED",
            raw_extensions=None,
            db_session=_mock_session(),
            blocked=True,
        )

    assert result is None, "STV CM LLC guard must return None — no draw_intent written"
    mock_insert.assert_not_called()

    # Audit log must contain an event naming the STV CM LLC block.
    assert any("stv_cm_llc" in ev.lower() for ev in audit_events), (
        f"Expected audit event mentioning stv_cm_llc, got: {audit_events}"
    )


# ---------------------------------------------------------------------------
# SPEC §10 — test_outbox_idempotency
# ---------------------------------------------------------------------------


def test_outbox_idempotency():
    """Calling write_bill_intent twice for the same (tracker_id, event_type) → one row.

    The first call returns the new UUID; the second returns None (ON CONFLICT DO NOTHING
    semantics — _insert_outbox returns None when the row already exists).
    """
    # Simulate DB behaviour: first INSERT succeeds, second hits the unique constraint.
    insert_side_effects = [_OUTBOX_ID, None]

    kwargs = _bill_intent_kwargs()

    with (
        patch.object(_ow_module, "_get_tracker", return_value=_ELIGIBLE_TRACKER),
        patch.object(
            _ow_module, "_insert_outbox", side_effect=insert_side_effects
        ) as mock_insert,
        patch.object(_ow_module, "_audit_log"),
    ):
        result1 = write_bill_intent(**kwargs)
        # Re-use the same kwargs (db_session mock is reused — fine for this unit test).
        result2 = write_bill_intent(**kwargs)

    assert result1 == _OUTBOX_ID, "First call must return the new outbox row UUID"
    assert result2 is None, "Second call must return None (idempotency no-op)"
    assert mock_insert.call_count == 2, (
        "Both calls reach _insert_outbox; the DB uniqueness constraint does the dedup"
    )


# ---------------------------------------------------------------------------
# SPEC §10 — test_bill_intent_payload_structure
# ---------------------------------------------------------------------------


def test_bill_intent_payload_structure():
    """bill_intent payload JSONB contains all required fields including gmail_invoiceproof."""
    captured_payload: dict = {}

    def capture_insert(db_session, *, tracker_id, event_type, payload):
        captured_payload.update(payload)
        return _OUTBOX_ID

    proof = {**_GMAIL_INVOICEPROOF, "bank_change_risk": False}

    with (
        patch.object(_ow_module, "_get_tracker", return_value=_ELIGIBLE_TRACKER),
        patch.object(_ow_module, "_insert_outbox", side_effect=capture_insert),
        patch.object(_ow_module, "_audit_log"),
    ):
        write_bill_intent(
            tracker_id=_TRACKER_ID,
            vendor_name="Makers Line",
            amount=12_345.67,
            po_ref="PO-STRUCT-TEST",
            due_date=None,
            raw_extensions=_RAW_EXT,
            gmail_invoiceproof=proof,
            db_session=_mock_session(),
        )

    required_keys = {
        "vendor_name",
        "amount",
        "amount_missing",
        "po_ref",
        "due_date",
        "raw_extensions",
        "gmail_invoiceproof",
    }
    missing = required_keys - set(captured_payload.keys())
    assert not missing, f"Payload missing required keys: {missing}"

    assert captured_payload["gmail_invoiceproof"] == proof, (
        "gmail_invoiceproof must be forwarded verbatim"
    )
    assert captured_payload["vendor_name"] == "Makers Line"
    assert captured_payload["amount"] == pytest.approx(12_345.67)
    assert captured_payload["amount_missing"] is False

    # Security: filtered raw_extensions must not expose secrets.
    raw_in_payload = captured_payload["raw_extensions"]
    assert isinstance(raw_in_payload, dict)
    # Only allowlisted keys may appear.
    from app.integration.outbox_writer import _BILL_INTENT_RAW_EXT_ALLOWLIST

    for key in raw_in_payload:
        assert key in _BILL_INTENT_RAW_EXT_ALLOWLIST, (
            f"Key {key!r} in payload raw_extensions is not allowlisted — security violation"
        )


# ---------------------------------------------------------------------------
# SPEC §10 — test_blocked_tracker_status_guard
# ---------------------------------------------------------------------------


def test_blocked_tracker_status_guard():
    """Tracker with current_status in BLOCKED_STATES → NO outbox row of any type.

    'Bank Change Risk' status means the tracker is already flagged; no further
    outbox rows (bill_intent OR bank_block) are written by this function.
    """
    blocked_status = "Bank Change Risk"
    assert blocked_status in BLOCKED_STATES, (
        "Test precondition: 'Bank Change Risk' must be in BLOCKED_STATES"
    )

    blocked_tracker = {
        "id": _TRACKER_ID,
        "bank_change_risk_flag": False,  # Flag is cleared — status alone is the guard.
        "current_status": blocked_status,
    }

    with (
        patch.object(_ow_module, "_get_tracker", return_value=blocked_tracker),
        patch.object(_ow_module, "_insert_outbox") as mock_insert,
        patch.object(_ow_module, "_audit_log"),
    ):
        result = write_bill_intent(**_bill_intent_kwargs())

    assert result is None, (
        f"current_status={blocked_status!r} is in BLOCKED_STATES — must return None"
    )
    mock_insert.assert_not_called()


# ---------------------------------------------------------------------------
# Extra: all BLOCKED_STATES halt processing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(BLOCKED_STATES))
def test_all_blocked_states_halt_processing(status):
    """Every status in BLOCKED_STATES must prevent any outbox INSERT."""
    tracker = {
        "id": _TRACKER_ID,
        "bank_change_risk_flag": False,
        "current_status": status,
    }
    with (
        patch.object(_ow_module, "_get_tracker", return_value=tracker),
        patch.object(_ow_module, "_insert_outbox") as mock_insert,
        patch.object(_ow_module, "_audit_log"),
    ):
        result = write_bill_intent(**_bill_intent_kwargs())

    assert result is None
    mock_insert.assert_not_called()


# ---------------------------------------------------------------------------
# DB Layer — _insert_outbox SQL coverage (patches session.execute, not _insert_outbox)
# ---------------------------------------------------------------------------


def test_insert_outbox_sql_contains_on_conflict_and_returning():
    """_insert_outbox emits SQL with ON CONFLICT DO NOTHING and RETURNING id.

    This test patches session.execute() at the SQLAlchemy boundary rather than
    patching _insert_outbox itself, so the actual SQL text and the RETURNING id
    logic are verified rather than mocked away.
    """
    session = MagicMock()

    # Simulate a successful INSERT: fetchone() returns a row with the new id.
    inserted_id = str(uuid.uuid4())
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (inserted_id,)
    session.execute.return_value = mock_result

    result = _insert_outbox(
        session,
        tracker_id=_TRACKER_ID,
        event_type="bill_intent",
        payload={"vendor_name": "Test Vendor", "amount": 100.00},
    )

    assert result == inserted_id, (
        f"_insert_outbox must return the RETURNING id on success, got {result!r}"
    )

    # Inspect the SQL string passed to session.execute().
    assert session.execute.call_count == 1
    sql_arg = session.execute.call_args[0][0]
    # text() objects store the SQL in their .text attribute.
    sql_text: str = str(sql_arg)
    assert "ON CONFLICT" in sql_text.upper(), (
        "_insert_outbox SQL must contain ON CONFLICT DO NOTHING clause"
    )
    assert "RETURNING" in sql_text.upper(), (
        "_insert_outbox SQL must contain RETURNING id clause"
    )


def test_insert_outbox_returns_none_on_conflict():
    """_insert_outbox returns None when fetchone() is None (ON CONFLICT DO NOTHING fired)."""
    session = MagicMock()

    # Simulate ON CONFLICT DO NOTHING: fetchone() returns None.
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    session.execute.return_value = mock_result

    result = _insert_outbox(
        session,
        tracker_id=_TRACKER_ID,
        event_type="bill_intent",
        payload={"vendor_name": "Test Vendor", "amount": 100.00},
    )

    assert result is None, (
        "_insert_outbox must return None when ON CONFLICT DO NOTHING fires (duplicate insert)"
    )
