"""Unit tests for the STV integration layer intent endpoints (SPEC §10).

Calls endpoint functions directly — no TestClient, no live DB.
Follows the pattern established in tests/test_workflow_router.py.

Coverage:
  POST /intents/bill       — bank_change_risk reject, idempotency
  POST /intents/draw       — STV CM LLC reject, fee math
  POST /intents/approvals  — idempotency, proof-bundle gate
  POST /callbacks/bill-synced — idempotent aihub_status callback
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse

from app.integration.intents_router import (
    BillIntentIn,
    BillSyncedCallbackIn,
    DrawIntentIn,
    GmailInvoiceProof,
    _system_a_url_from_env,
    approve_bill_intent,
    bill_synced_callback,
    create_bill_intent,
    create_draw_intent,
)

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_TOKEN = "test-outbox-token-abc123"


def _set_token(monkeypatch) -> None:
    """Patch _outbox_token so auth passes with _TOKEN."""
    monkeypatch.setenv("AIHUB_OUTBOX_TOKEN", _TOKEN)


def _auth() -> str:
    return f"Bearer {_TOKEN}"


def _envelope(resp: Any) -> dict:
    """Decode and validate the project response envelope."""
    if isinstance(resp, JSONResponse):
        body = json.loads(bytes(resp.body))
    else:
        body = resp
    assert set(body) == {"data", "error", "meta"}, f"Unexpected envelope keys: {set(body)}"
    return body


def _mock_session() -> MagicMock:
    return MagicMock()


def _proof(**overrides) -> GmailInvoiceProof:
    data = dict(
        risk_level="low",
        final_decision="approved",
        checks_passed=7,
        bank_change_risk=False,
        duplicate_detected=False,
        vendor_confidence=0.95,
    )
    data.update(overrides)
    return GmailInvoiceProof(**data)


def _bill_payload(**overrides) -> BillIntentIn:
    data = dict(
        gmail_tracker_id=uuid.uuid4(),
        vendor_name="Makers Line",
        amount=Decimal("50000.00"),
        po_ref="PO-TEST",
        due_date=None,
        raw_extensions={"project_label": "Madison Park"},
        gmail_invoiceproof=_proof(),
        company_id=None,
    )
    data.update(overrides)
    return BillIntentIn(**data)


# ---------------------------------------------------------------------------
# SPEC §10 — test_bill_intent_bank_change_rejected
# ---------------------------------------------------------------------------


def test_bill_intent_bank_change_rejected(monkeypatch):
    """POST /intents/bill with gmail_invoiceproof.bank_change_risk=True → 400 BANK_CHANGE_RISK.

    G2: bank_change_risk P0 fires BEFORE any DB action (no session calls).
    """
    _set_token(monkeypatch)
    payload = _bill_payload(gmail_invoiceproof=_proof(bank_change_risk=True))
    session = _mock_session()

    resp = create_bill_intent(
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    env = _envelope(resp)
    assert env["error"]["code"] == "BANK_CHANGE_RISK"
    assert env["data"] is None
    # G2: No DB interaction should have happened before the guard.
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# SPEC §10 — test_bill_intent_idempotent
# ---------------------------------------------------------------------------


def test_bill_intent_idempotent(monkeypatch):
    """POST /intents/bill with existing gmail_tracker_id → 200 idempotent=True."""
    _set_token(monkeypatch)
    tracker_id = uuid.uuid4()
    bill_id = str(uuid.uuid4())
    workflow_id = f"bill-intent-{tracker_id}"

    # Session returns an existing bill row on the idempotency SELECT.
    session = _mock_session()
    existing_row = MagicMock()
    existing_row.__getitem__ = lambda self, k: {
        "id": bill_id,
        "workflow_id": workflow_id,
        "status": "drafted",
    }[k]
    session.execute.return_value.mappings.return_value.first.return_value = existing_row

    payload = _bill_payload(gmail_tracker_id=tracker_id)

    resp = create_bill_intent(
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    env = _envelope(resp)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    assert env["error"] is None
    assert env["data"]["idempotent"] is True
    assert env["data"]["bill_id"] == bill_id


# ---------------------------------------------------------------------------
# SPEC §10 — test_draw_intent_stv_cm_llc_rejected
# ---------------------------------------------------------------------------


def test_draw_intent_stv_cm_llc_rejected(monkeypatch):
    """POST /intents/draw where entity resolves to STV CM LLC → 400 STV_CM_LLC_BLOCKED.

    G3: independent STV CM LLC block in System B (defence in depth with outbox_writer).
    fee_payee_status='BLOCKED' is the signal that the fee payee resolved to STV CM LLC.
    """
    _set_token(monkeypatch)
    payload = DrawIntentIn(
        gmail_fee_opportunity_id=uuid.uuid4(),
        project_canonical="Madison Park",
        draw_amount=Decimal("500000"),
        draw_number=1,
        estimated_fee_hint=Decimal("25000"),
        fee_payee_hint="STV CM LLC",
        fee_payee_status="BLOCKED",
        raw_extensions=None,
    )
    session = _mock_session()

    resp = create_draw_intent(
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    env = _envelope(resp)
    assert env["error"]["code"] == "STV_CM_LLC_BLOCKED"
    assert env["data"] is None
    # G3: no draw_packages / bills DML happens — the only DB write on this path
    # is the AIVS audit row documenting the blocked attempt (append_audit_row,
    # via a raw SELECT nextval(...) + ORM insert), which is intentional per this
    # function's docstring ("writes an AIVS audit_row 'stv_cm_llc_draw_attempted'").
    for call in session.execute.call_args_list:
        sql_text = str(call.args[0]) if call.args else ""
        assert "draw_packages" not in sql_text.lower(), (
            f"G3: no draw_packages DML must happen before/at the guard: {sql_text}"
        )
        assert "insert into bills" not in sql_text.lower(), (
            f"G3: no bills DML must happen before/at the guard: {sql_text}"
        )


# ---------------------------------------------------------------------------
# SPEC §10 — test_draw_fee_math
# ---------------------------------------------------------------------------


def test_draw_fee_math():
    """draw_amount=500000 → developer_fee=25000 (5%), cm_fee=10000 (2%), president_fee=5000 (1%).

    Pure arithmetic test of the canonical 5/2/1 fee split (SPEC_SUMMA_TERRA_BINDING §5.3).
    Skipped cleanly when app/catalog/fee_math.py is not yet implemented (CHUNK_6).
    """
    pytest.importorskip(
        "app.catalog.fee_math",
        reason="app.catalog.fee_math not yet implemented (CHUNK_6); skipping test_draw_fee_math",
    )
    from app.catalog.fee_math import (
        ROLE_CEO_PARENT,
        ROLE_DEV_PARTNERSHIP,
        ROLE_PRES_PARENT,
        split_developer_fee,
    )

    lines = split_developer_fee(Decimal("500000"))
    by_role = {ln.fee_role: ln.amount for ln in lines}

    assert by_role[ROLE_DEV_PARTNERSHIP] == Decimal("25000.00"), (
        f"Developer fee (5%) must be 25000.00, got {by_role[ROLE_DEV_PARTNERSHIP]}"
    )
    assert by_role[ROLE_CEO_PARENT] == Decimal("10000.00"), (
        f"CM/CEO fee (2%) must be 10000.00, got {by_role[ROLE_CEO_PARENT]}"
    )
    assert by_role[ROLE_PRES_PARENT] == Decimal("5000.00"), (
        f"President fee (1%) must be 5000.00, got {by_role[ROLE_PRES_PARENT]}"
    )

    # Distinct economic total (not double-counted) = 5% + 2% + 1% = 8% = 40000.
    from app.catalog.fee_math import distinct_economic_total

    assert distinct_economic_total(lines) == Decimal("40000.00")


# ---------------------------------------------------------------------------
# SPEC §10 — test_approval_signal_idempotent
# ---------------------------------------------------------------------------


def test_approval_signal_idempotent(monkeypatch):
    """POST /approvals/{wf_id} when bill already approved → 200 idempotent=True."""
    from app.integration.intents_router import IntegrationApprovalIn

    _set_token(monkeypatch)
    wf_id = f"bill-intent-{uuid.uuid4()}"
    bill_id = str(uuid.uuid4())

    # Session: bill query returns status='approved' (already approved).
    session = _mock_session()
    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": bill_id,
        "status": "approved",
        "invoiceproof_bundle_id": str(uuid.uuid4()),
        "tracker_id": str(uuid.uuid4()),
    }[k]
    session.execute.return_value.mappings.return_value.first.return_value = bill_row

    payload = IntegrationApprovalIn(
        decision="approve",
        source="email_detected",
        note=None,
        evidence_email_id=None,
    )

    resp = approve_bill_intent(
        workflow_id=wf_id,
        background_tasks=BackgroundTasks(),
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    env = _envelope(resp)
    assert env["error"] is None
    assert env["data"]["idempotent"] is True
    assert env["data"]["current_status"] == "approved"


# ---------------------------------------------------------------------------
# SPEC §10 — test_bill_synced_callback_idempotent
# ---------------------------------------------------------------------------


def test_bill_synced_callback_idempotent(monkeypatch):
    """aihub_status already 'synced' → 200 idempotent=True, no tracker mutation."""
    _set_token(monkeypatch)
    bill_id = str(uuid.uuid4())

    # Session: bill query returns aihub_status='synced' (already synced).
    session = _mock_session()
    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": bill_id,
        "aihub_status": "synced",
    }[k]
    session.execute.return_value.mappings.return_value.first.return_value = bill_row

    payload = BillSyncedCallbackIn(
        bill_id=bill_id,
        aihub_status="synced",
        gmail_tracker_id=None,
    )

    resp = bill_synced_callback(
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    env = _envelope(resp)
    assert env["error"] is None
    assert env["data"]["idempotent"] is True
    assert env["data"]["aihub_status"] == "synced"

    # No mutation: session.execute should have been called once (the SELECT),
    # but session.commit must NOT have been called (no UPDATE issued).
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# SPEC §10 — test_proof_bundle_required_before_approve
# ---------------------------------------------------------------------------


def test_proof_bundle_required_before_approve(monkeypatch):
    """Approve bill without proof_bundles.passed=True → gate fails closed (422).

    G6: SwarmSync Gate 1 must pass before approval.  No proof bundle linked →
    approve_bill_intent returns 422 PROOF_BUNDLE_MISSING.
    """
    from app.integration.intents_router import IntegrationApprovalIn

    _set_token(monkeypatch)
    wf_id = f"bill-intent-{uuid.uuid4()}"
    bill_id = str(uuid.uuid4())

    # Session: bill exists with status='drafted' and invoiceproof_bundle_id=None.
    session = _mock_session()
    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": bill_id,
        "status": "drafted",
        "invoiceproof_bundle_id": None,
        "tracker_id": str(uuid.uuid4()),
    }[k]
    session.execute.return_value.mappings.return_value.first.return_value = bill_row

    payload = IntegrationApprovalIn(
        decision="approve",
        source="email_detected",
        note=None,
        evidence_email_id=None,
    )

    resp = approve_bill_intent(
        workflow_id=wf_id,
        background_tasks=BackgroundTasks(),
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 422
    env = _envelope(resp)
    assert env["error"]["code"] == "PROOF_BUNDLE_MISSING"
    assert env["data"] is None

    # Gate fails closed: no UPDATE, no commit.
    session.commit.assert_not_called()


def test_empty_token_rejected(monkeypatch):
    """AIHUB_OUTBOX_TOKEN='' → every /intents/* endpoint returns 401 UNAUTHORIZED.

    _check_auth uses `not expected` to reject empty strings. This test confirms
    that an empty env var can never silently open the auth gate regardless of
    the bearer token supplied by the caller.
    """
    monkeypatch.setenv("AIHUB_OUTBOX_TOKEN", "")
    payload = _bill_payload()
    session = _mock_session()

    # Any bearer token must be rejected when the env var is empty.
    resp = create_bill_intent(
        payload=payload,
        authorization="Bearer some-token-that-should-not-work",
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 401
    env = _envelope(resp)
    assert env["error"]["code"] == "UNAUTHORIZED", (
        "Empty AIHUB_OUTBOX_TOKEN must result in UNAUTHORIZED, not a pass-through"
    )
    # No DB access must have occurred before the auth rejection.
    session.execute.assert_not_called()


def test_system_a_url_prefers_explicit_env(monkeypatch):
    """SYSTEM_A_URL is the canonical override when it is configured."""
    monkeypatch.setenv("SYSTEM_A_URL", "https://system-a.example.com/")
    monkeypatch.setenv(
        "RAILWAY_SERVICE_EXEMPLARY_TENDERNESS_URL",
        "exemplary-tenderness-production.up.railway.app",
    )

    assert _system_a_url_from_env() == "https://system-a.example.com"


def test_system_a_url_uses_railway_service_host(monkeypatch):
    """Railway injects the peer service URL as a host; normalize it to HTTPS."""
    monkeypatch.delenv("SYSTEM_A_URL", raising=False)
    monkeypatch.setenv(
        "RAILWAY_SERVICE_EXEMPLARY_TENDERNESS_URL",
        "exemplary-tenderness-production.up.railway.app",
    )

    assert (
        _system_a_url_from_env()
        == "https://exemplary-tenderness-production.up.railway.app"
    )


def test_proof_bundle_not_passed_before_approve(monkeypatch):
    """proof_bundles.passed=False → 422 PROOF_BUNDLE_NOT_PASSED (gate fails closed)."""
    _set_token(monkeypatch)
    wf_id = f"bill-intent-{uuid.uuid4()}"
    bill_id = str(uuid.uuid4())
    bundle_id = str(uuid.uuid4())

    from app.integration.intents_router import IntegrationApprovalIn

    session = _mock_session()

    # First execute returns bill row with a bundle_id but status=drafted.
    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": bill_id,
        "status": "drafted",
        "invoiceproof_bundle_id": bundle_id,
        "tracker_id": str(uuid.uuid4()),
    }[k]

    # Second execute returns proof bundle with passed=False.
    proof_row = MagicMock()
    proof_row.__getitem__ = lambda self, k: {"passed": False}[k]

    results = [bill_row, proof_row]

    def _first_side_effect(*a, **kw):
        mock = MagicMock()
        if results:
            row = results.pop(0)
            mock.mappings.return_value.first.return_value = row
        return mock

    session.execute.side_effect = _first_side_effect

    payload = IntegrationApprovalIn(
        decision="approve",
        source="email_detected",
        note=None,
        evidence_email_id=None,
    )

    resp = approve_bill_intent(
        workflow_id=wf_id,
        background_tasks=BackgroundTasks(),
        payload=payload,
        authorization=_auth(),
        session=session,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 422
    env = _envelope(resp)
    assert env["error"]["code"] == "PROOF_BUNDLE_NOT_PASSED"
    session.commit.assert_not_called()
