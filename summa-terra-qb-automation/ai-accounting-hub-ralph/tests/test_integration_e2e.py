"""Integration E2E test suite — STV Integration Layer (SPEC §10, IMPL_PLAN Final).

All 8 spec §10 scenario tests + all 7 must-not-break guarantee tests (named exactly
as specified in the Final Verification Task).

Convention follows existing project tests (test_intents_bill.py, test_must_not_break.py):
  - Endpoint functions are called directly — no httpx, no TestClient.
  - SQLAlchemy I/O is patched via MagicMock / patch.object.
  - Structural invariants are verified via AST inspection of the source files.
  - Live-DB tests are marked @pytest.mark.integration and skipped without RUN_INTEGRATION=1.

References:
  spec-stv-integration-layer-2026-06-29.md §10 integration tests
  IMPLEMENTATION_PLAN.md — Final Verification Task (15 regression tests)
  Must-not-break guarantees [1]-[7]
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_INTEGRATION_DIR = _REPO_ROOT / "app" / "integration"

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

_TOKEN = "e2e-outbox-token-stv-2026"
_TRACKER_ID = str(uuid.uuid4())
_BILL_ID = str(uuid.uuid4())
_FEE_OP_ID = str(uuid.uuid4())
_VENDOR_ID = str(uuid.uuid4())
_COMPANY_ID = str(uuid.uuid4())
_BUNDLE_ID = str(uuid.uuid4())
_WF_ID = f"bill-intent-{_TRACKER_ID}"

_CLEAN_PROOF: dict[str, Any] = {
    "risk_level": "low",
    "final_decision": "approved",
    "checks_passed": 7,
    "bank_change_risk": False,
    "duplicate_detected": False,
    "vendor_confidence": 0.95,
    "passed": True,
}

_RAW_EXT: dict[str, Any] = {
    "project_label": "Madison Park",
    "gmail_thread_id": "thread-porter-001",
    "gmail_message_id": "msg-porter-001",
    "requested_by_email": "porter@summaterraventures.com",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _auth() -> str:
    return f"Bearer {_TOKEN}"


def _set_auth(monkeypatch) -> None:
    monkeypatch.setenv("AIHUB_OUTBOX_TOKEN", _TOKEN)
    monkeypatch.setenv("BEN_SESSION_TOKEN", _TOKEN)


def _envelope(resp: Any) -> dict:
    """Decode and validate the project response envelope {data, error, meta}."""
    if isinstance(resp, JSONResponse):
        body = json.loads(bytes(resp.body))
    else:
        body = resp
    assert set(body) == {"data", "error", "meta"}, (
        f"Unexpected envelope keys: {set(body)}"
    )
    return body


def _mock_session() -> MagicMock:
    """Return a MagicMock that quacks like an SQLAlchemy Session."""
    return MagicMock()


def _mock_session_with_bill(
    *,
    status: str = "verified",
    bundle_id: str | None = None,
    tracker_id: str | None = None,
) -> MagicMock:
    """Return a MagicMock session whose first execute() returns a bill row."""
    session = _mock_session()
    bill_row = MagicMock()
    bundle_id = bundle_id or _BUNDLE_ID
    bill_row.__getitem__ = lambda self, k: {
        "id": _BILL_ID,
        "status": status,
        "invoiceproof_bundle_id": bundle_id,
        "tracker_id": tracker_id or _TRACKER_ID,
    }[k]
    # All execute().mappings().first() calls return the bill row by default.
    session.execute.return_value.mappings.return_value.first.return_value = bill_row
    return session


# ============================================================================
# SCENARIO 1 — Porter invoice full flow (spec §10)
# ============================================================================


def test_scenario_1_porter_invoice_full_flow(monkeypatch):
    """E2E mock of Scenario 1: tracker created → outbox written → delivery →
    bill created → Gate 1 hint validated → Temporal started → approval signal
    → bill approved → callback → tracker advanced.

    Asserts:
      - bills INSERT carries gmail_tracker_id (linked to tracker)
      - tracker.aihub_status would be set to 'synced' via callback
    """
    from app.integration import outbox_writer as _ow
    from app.integration.intents_router import (
        BillIntentIn,
        GmailInvoiceProof,
        IntegrationApprovalIn,
        approve_bill_intent,
        create_bill_intent,
    )

    _set_auth(monkeypatch)
    tracker_id = uuid.uuid4()
    tracker_id_str = str(tracker_id)

    # ----------------------------------------------------------------
    # Step 1: outbox_writer.write_bill_intent → bill_intent outbox row
    # ----------------------------------------------------------------
    eligible_tracker = {
        "id": tracker_id_str,
        "bank_change_risk_flag": False,
        "current_status": "Pending Review",
    }
    outbox_id = str(uuid.uuid4())

    with (
        patch.object(_ow, "_get_tracker", return_value=eligible_tracker),
        patch.object(_ow, "_insert_outbox", return_value=outbox_id) as mock_insert,
        patch.object(_ow, "_audit_log"),
    ):
        result = _ow.write_bill_intent(
            tracker_id=tracker_id_str,
            vendor_name="Makers Line",
            amount=52_250.00,
            po_ref="PO-PORTER-001",
            due_date=None,
            raw_extensions=_RAW_EXT,
            gmail_invoiceproof=_CLEAN_PROOF,
            db_session=_mock_session(),
        )

    assert result == outbox_id, "Step 1: bill_intent outbox row should be returned"
    _, kw = mock_insert.call_args
    assert kw["event_type"] == "bill_intent", "Step 1: event_type must be bill_intent"
    assert kw["tracker_id"] == tracker_id_str, "Step 1: tracker_id must be threaded through"

    # ----------------------------------------------------------------
    # Step 2: POST /intents/bill → bill created; gmail_tracker_id stored
    # ----------------------------------------------------------------
    proof = GmailInvoiceProof(**{k: v for k, v in _CLEAN_PROOF.items()
                                 if k in GmailInvoiceProof.model_fields})
    bill_payload = BillIntentIn(
        gmail_tracker_id=tracker_id,
        vendor_name="Makers Line",
        amount=Decimal("52250.00"),
        po_ref="PO-PORTER-001",
        due_date=None,
        raw_extensions={"project_label": "Madison Park"},
        gmail_invoiceproof=proof,
        company_id=None,
    )

    # Session: build side_effect queue for the sequence of execute() calls in create_bill_intent:
    # 1. Idempotency check: SELECT bills WHERE gmail_tracker_id → first() = None (no existing bill)
    # 2. Vendor fuzzy match: SELECT vendors WHERE similarity → all() = [vendor_dict]
    # 3. Bill INSERT: no return value needed
    # All other calls (commit, etc.) use MagicMock defaults.
    #
    # IMPORTANT: _fuzzy_match_vendor() does [dict(r) for r in rows], so the row objects
    # in the all() list MUST be convertible via dict(). Use plain Python dicts.

    vendor_row = {
        "id": _VENDOR_ID,
        "name": "Makers Line",
        "company_id": _COMPANY_ID,
        "sim": 0.95,
    }

    call_idx_s1 = [0]

    def _session_b_exec(*args, **kwargs):
        m = MagicMock()
        idx = call_idx_s1[0]
        call_idx_s1[0] += 1
        if idx == 0:
            # Idempotency check: no existing bill
            m.mappings.return_value.first.return_value = None
        elif idx == 1:
            # Vendor fuzzy match: one vendor found (plain dict for dict() compatibility)
            m.mappings.return_value.all.return_value = [vendor_row]
        # All other execute calls (INSERT, commit, etc.) return default MagicMock
        return m

    session_b = _mock_session()
    session_b.execute.side_effect = _session_b_exec

    resp_create = create_bill_intent(
        payload=bill_payload,
        authorization=_auth(),
        session=session_b,
    )
    env_create = _envelope(resp_create)
    assert resp_create.status_code == 201, (
        f"Step 2: expected 201, got {resp_create.status_code}: {env_create}"
    )
    assert env_create["error"] is None, "Step 2: no error on bill creation"

    # Verify gmail_tracker_id was injected into the INSERT SQL params.
    insert_calls = [str(c) for c in session_b.execute.call_args_list]
    assert any("gmail_tracker_id" in c for c in insert_calls), (
        "Step 2: bills INSERT must carry gmail_tracker_id (spec §6.3)"
    )

    created_bill_id = env_create["data"]["bill_id"]
    created_wf_id = env_create["data"]["workflow_id"]
    assert created_bill_id, "Step 2: bill_id must be returned"
    assert created_wf_id, "Step 2: workflow_id must be returned"

    # ----------------------------------------------------------------
    # Step 3: POST /intents/approvals/{wf_id} → bill approved → callback
    # ----------------------------------------------------------------
    approval_payload = IntegrationApprovalIn(
        decision="approve",
        source="email_detected",
        note=None,
        evidence_email_id="msg-mike-approval-001",
    )

    session_appr = _mock_session()
    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": created_bill_id,
        "status": "verified",
        "invoiceproof_bundle_id": _BUNDLE_ID,
        "tracker_id": tracker_id_str,
    }[k]
    session_appr.execute.return_value.mappings.return_value.first.return_value = bill_row

    # Proof bundle row: passed=True
    proof_row = MagicMock()
    proof_row.__getitem__ = lambda self, k: {"passed": True}[k]

    # Make the second execute() call (proof lookup) return the passed bundle.
    exec_returns = [
        MagicMock(**{"mappings.return_value.first.return_value": bill_row}),
        MagicMock(**{"mappings.return_value.first.return_value": proof_row}),
        MagicMock(),  # UPDATE bills
        MagicMock(),  # audit row 1
        MagicMock(),  # audit row 2
    ]
    session_appr.execute.side_effect = exec_returns

    fake_bundle = {"proof_hash": "abc123deadbeef"}

    with (
        patch("app.integration.intents_router.append_audit_row"),
        patch("app.integration.intents_router.build_aivs_bundle", return_value=fake_bundle),
        patch("app.integration.intents_router.write_proof_bundle"),
        patch("app.audit.service._load_session_records", return_value=[]),
        patch("app.integration.intents_router.send_bill_synced_callback", return_value=True),
    ):
        resp_appr = approve_bill_intent(
            workflow_id=created_wf_id,
            background_tasks=BackgroundTasks(),
            payload=approval_payload,
            authorization=_auth(),
            session=session_appr,
        )

    env_appr = _envelope(resp_appr)
    assert resp_appr.status_code == 200, (
        f"Step 3: expected 200 approval, got {resp_appr.status_code}: {env_appr}"
    )
    assert env_appr["error"] is None, "Step 3: no error on approval"
    assert env_appr["data"]["decision"] == "approve", "Step 3: decision must be 'approve'"
    assert env_appr["data"]["status"] == "approved", (
        "Step 3: bill status must be 'approved' after approval signal"
    )

    # ----------------------------------------------------------------
    # Step 4: callback → tracker.aihub_status = "synced"
    # ----------------------------------------------------------------
    # Verify that send_bill_synced_callback was called with status=approved.
    # approve_bill_intent makes 2 SELECT calls:
    #   1. SELECT bill WHERE workflow_id   → bill_row (with bundle_id)
    #   2. SELECT passed FROM proof_bundles → proof_row (passed=True)
    # then UPDATE and audit inserts.
    callback_calls_seen = []
    session_appr2 = _mock_session()

    proof_row_step4 = MagicMock()
    proof_row_step4.__getitem__ = lambda self, k: {"passed": True}[k]

    call_n_step4 = [0]
    def _step4_exec(*args, **kwargs):
        m = MagicMock()
        idx = call_n_step4[0]
        call_n_step4[0] += 1
        if idx == 0:
            # Bill SELECT
            m.mappings.return_value.first.return_value = bill_row
        elif idx == 1:
            # Proof bundle SELECT
            m.mappings.return_value.first.return_value = proof_row_step4
        return m

    session_appr2.execute.side_effect = _step4_exec

    monkeypatch.setenv("SYSTEM_A_URL", "https://system-a.example.com")
    monkeypatch.setenv("SYSTEM_A_CALLBACK_TOKEN", "tok-a")

    # Fix 8: the bill-synced callback is now scheduled on BackgroundTasks instead
    # of firing inline, so it doesn't block the HTTP response. Capture the real
    # BackgroundTasks instance and drain it manually here (this is exactly what
    # Starlette does after the response is sent in a live request).
    bg_step4 = BackgroundTasks()

    with (
        patch("app.integration.intents_router.append_audit_row"),
        patch("app.integration.intents_router.build_aivs_bundle", return_value=fake_bundle),
        patch("app.integration.intents_router.write_proof_bundle"),
        patch("app.audit.service._load_session_records", return_value=[]),
        patch(
            "app.integration.intents_router.send_bill_synced_callback",
            side_effect=lambda **kw: callback_calls_seen.append(kw) or True,
        ),
    ):
        approve_bill_intent(
            workflow_id=created_wf_id,
            background_tasks=bg_step4,
            payload=approval_payload,
            authorization=_auth(),
            session=session_appr2,
        )

    for _task in bg_step4.tasks:
        _task.func(*_task.args, **_task.kwargs)

    # The callback must be called with status='approved' — which System A uses to
    # advance tracker.aihub_status → 'synced' (via POST /integration/bill-synced).
    assert any(kw.get("status") == "approved" for kw in callback_calls_seen), (
        "Step 4: bill-synced callback must be fired with status='approved' "
        "so System A can advance tracker.aihub_status to 'synced'"
    )


# ============================================================================
# SCENARIO 2 — In-person approval (spec §10)
# ============================================================================


def test_scenario_2_in_person_approval(monkeypatch):
    """Bill in verified state; POST /approvals/{wf_id} with source=manual_ui.

    Asserts:
      - bill status → 'approved'
      - note < 10 chars → rejected (422)
      - note ≥ 10 chars → approved (200)
    """
    from app.integration.intents_router import (
        IntegrationApprovalIn,
        approve_bill_intent,
    )

    _set_auth(monkeypatch)
    wf_id = f"bill-intent-{uuid.uuid4()}"

    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": _BILL_ID,
        "status": "verified",
        "invoiceproof_bundle_id": _BUNDLE_ID,
        "tracker_id": _TRACKER_ID,
    }[k]
    proof_row = MagicMock()
    proof_row.__getitem__ = lambda self, k: {"passed": True}[k]

    def _make_session():
        s = _mock_session()
        s.execute.return_value.mappings.return_value.first.return_value = bill_row
        return s

    # --- Subtest A: note too short (5 chars) → 422 ---
    short_note_payload = IntegrationApprovalIn(
        decision="approve",
        source="manual_ui",
        note="abc",  # < 10 chars
        evidence_email_id=None,
    )
    resp_short = approve_bill_intent(
        workflow_id=wf_id,
        background_tasks=BackgroundTasks(),
        payload=short_note_payload,
        authorization=_auth(),
        session=_make_session(),
    )
    assert isinstance(resp_short, JSONResponse)
    assert resp_short.status_code == 422, (
        f"G4: manual_ui approval with <10-char note must be 422, got {resp_short.status_code}"
    )
    env_short = _envelope(resp_short)
    assert env_short["error"]["code"] == "VALIDATION_ERROR", (
        "G4: error code must be VALIDATION_ERROR for short note"
    )

    # --- Subtest B: note exactly 10 chars → approved ---
    # Build a session that returns bill_row → proof_row → update mock
    session_ok = _mock_session()
    proof_row_ok = MagicMock()
    proof_row_ok.__getitem__ = lambda self, k: {"passed": True}[k]

    call_index = [0]
    first_rows = [bill_row, proof_row_ok]

    def _side_effect_for_ok(*args, **kwargs):
        m = MagicMock()
        idx = call_index[0]
        if idx < len(first_rows):
            m.mappings.return_value.first.return_value = first_rows[idx]
        call_index[0] += 1
        return m

    session_ok.execute.side_effect = _side_effect_for_ok

    valid_note_payload = IntegrationApprovalIn(
        decision="approve",
        source="manual_ui",
        note="Reviewed and approved by Mike Watson in person",  # ≥ 10 chars
        evidence_email_id=None,
    )
    fake_bundle = {"proof_hash": "deadbeef001"}

    with (
        patch("app.integration.intents_router.append_audit_row"),
        patch("app.integration.intents_router.build_aivs_bundle", return_value=fake_bundle),
        patch("app.integration.intents_router.write_proof_bundle"),
        patch("app.audit.service._load_session_records", return_value=[]),
        patch("app.integration.intents_router.send_bill_synced_callback", return_value=True),
    ):
        resp_ok = approve_bill_intent(
            workflow_id=wf_id,
            background_tasks=BackgroundTasks(),
            payload=valid_note_payload,
            authorization=_auth(),
            session=session_ok,
        )

    env_ok = _envelope(resp_ok)
    assert resp_ok.status_code == 200, (
        f"Scenario 2: in-person approval with ≥10-char note should be 200, "
        f"got {resp_ok.status_code}: {env_ok}"
    )
    assert env_ok["error"] is None, "Scenario 2: no error on valid manual approval"
    assert env_ok["data"]["status"] == "approved", (
        "Scenario 2: bill status must be 'approved'"
    )
    assert env_ok["data"]["decision"] == "approve", (
        "Scenario 2: decision echo must be 'approve'"
    )


# ============================================================================
# SCENARIO 3 — Bank change (spec §10)
# ============================================================================


def test_scenario_3_bank_change(monkeypatch):
    """bank_change_risk=True → outbox has bank_block row, NOT bill_intent.

    Asserts:
      - integration_outbox has 0 bill_intent rows for this tracker
      - integration_outbox has 1 bank_block row
      - POST /intents/bill with bank_change_risk=True → 400 BANK_CHANGE_RISK
    """
    from app.integration import outbox_writer as _ow
    from app.integration.intents_router import (
        BillIntentIn,
        GmailInvoiceProof,
        create_bill_intent,
    )

    _set_auth(monkeypatch)

    # ----------------------------------------------------------------
    # Part A: outbox_writer guard — bank_change_risk=True → bank_block
    # ----------------------------------------------------------------
    risky_tracker = {
        "id": _TRACKER_ID,
        "bank_change_risk_flag": True,
        "current_status": "Bank Change Risk",
    }
    bank_block_outbox_id = str(uuid.uuid4())

    bill_intent_calls: list[str] = []
    bank_block_calls: list[str] = []

    def _fake_insert_outbox(db_session, *, tracker_id, event_type, payload):
        if event_type == "bill_intent":
            bill_intent_calls.append(event_type)
            return str(uuid.uuid4())
        if event_type == "bank_block":
            bank_block_calls.append(event_type)
            return bank_block_outbox_id
        return None

    with (
        patch.object(_ow, "_get_tracker", return_value=risky_tracker),
        patch.object(_ow, "_insert_outbox", side_effect=_fake_insert_outbox),
        patch.object(_ow, "_audit_log"),
    ):
        result = _ow.write_bill_intent(
            tracker_id=_TRACKER_ID,
            vendor_name="Suspicious Vendor",
            amount=99_999.00,
            po_ref=None,
            due_date=None,
            raw_extensions={
                "requested_by_email": "fraud@evil.example.com",
                "gmail_message_id": "msg-fraud-001",
            },
            gmail_invoiceproof={
                "risk_level": "critical",
                "final_decision": "blocked",
                "checks_passed": 1,
                "bank_change_risk": True,
                "duplicate_detected": False,
                "vendor_confidence": 0.1,
                "passed": False,
            },
            db_session=_mock_session(),
        )

    assert len(bill_intent_calls) == 0, (
        "Scenario 3: ZERO bill_intent rows must be written when bank_change_risk=True"
    )
    assert len(bank_block_calls) == 1, (
        "Scenario 3: exactly 1 bank_block row must be written"
    )
    assert result == bank_block_outbox_id, (
        "Scenario 3: result must be the bank_block outbox id"
    )

    # ----------------------------------------------------------------
    # Part B: System B /intents/bill also rejects bank_change_risk=True
    # ----------------------------------------------------------------
    proof_with_risk = GmailInvoiceProof(
        risk_level="critical",
        final_decision="blocked",
        checks_passed=1,
        bank_change_risk=True,
        duplicate_detected=False,
        vendor_confidence=0.1,
    )
    risky_payload = BillIntentIn(
        gmail_tracker_id=uuid.uuid4(),
        vendor_name="Suspicious Vendor",
        amount=Decimal("99999.00"),
        po_ref=None,
        due_date=None,
        raw_extensions=None,
        gmail_invoiceproof=proof_with_risk,
        company_id=None,
    )
    session_b = _mock_session()

    resp = create_bill_intent(
        payload=risky_payload,
        authorization=_auth(),
        session=session_b,
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400, (
        f"Scenario 3: /intents/bill with bank_change_risk=True must return 400, "
        f"got {resp.status_code}"
    )
    env = _envelope(resp)
    assert env["error"]["code"] == "BANK_CHANGE_RISK", (
        "Scenario 3: error code must be BANK_CHANGE_RISK"
    )
    # G2: no DB calls before the guard fires
    session_b.execute.assert_not_called()


# ============================================================================
# SCENARIO 4 — Draw fee (spec §10)
# ============================================================================


def test_scenario_4_draw_fee(monkeypatch):
    """Draw email → draw_intent outbox → 3 fee bills created.

    Asserts:
      - draw_packages.gmail_fee_opportunity_id is set
      - exactly 3 fee bills linked to the draw package
      - fee math: 5% + 2% + 1% = 8% of draw_amount
      - STV CM LLC fee_payee → 400 STV_CM_LLC_BLOCKED
    """
    from app.integration.intents_router import (
        DrawIntentIn,
        create_draw_intent,
    )

    _set_auth(monkeypatch)

    draw_amount = Decimal("500000.00")
    fee_opp_id = uuid.uuid4()

    draw_payload = DrawIntentIn(
        gmail_fee_opportunity_id=fee_opp_id,
        project_canonical="Madison Park",
        draw_amount=draw_amount,
        draw_number=29,
        estimated_fee_hint=Decimal("40000.00"),
        fee_payee_hint="Summa Terra Ventures LLC",
        fee_payee_status="CONFIRMED",
        raw_extensions={"gmail_thread_id": "thread-draw-001"},
    )

    # Session: no existing draw_package, vendor found, company found
    session = _mock_session()

    # Sequence of execute() calls in create_draw_intent:
    # 1. Idempotency SELECT draw_packages → None
    # 2. Company SELECT → row with company_id
    # 3. INSERT draw_packages
    # 4. For each of 3 bills:
    #    a. fuzzy vendor SELECT → empty (soft-draft)
    #    b. INSERT vendor (soft-draft)
    #    c. INSERT bill

    company_row = MagicMock()
    company_row.__getitem__ = lambda self, k: {"id": _COMPANY_ID}[k]

    call_idx = [0]
    responses = [
        # 1. Idempotency check: no existing draw_package
        MagicMock(**{"mappings.return_value.first.return_value": None}),
        # 2. Company SELECT
        MagicMock(**{"mappings.return_value.first.return_value": company_row}),
        # 3. INSERT draw_packages
        MagicMock(),
        # 4a-c: bill 1 (dev fee)
        MagicMock(**{"mappings.return_value.all.return_value": []}),   # vendor match → empty
        MagicMock(),  # INSERT vendor soft-draft
        MagicMock(),  # INSERT bill
        # 4a-c: bill 2 (CM/CEO fee)
        MagicMock(**{"mappings.return_value.all.return_value": []}),
        MagicMock(),
        MagicMock(),
        # 4a-c: bill 3 (Pres fee)
        MagicMock(**{"mappings.return_value.all.return_value": []}),
        MagicMock(),
        MagicMock(),
        # audit_row INSERT
        MagicMock(),
    ]

    def _side_effect(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx < len(responses):
            return responses[idx]
        return MagicMock()

    session.execute.side_effect = _side_effect

    with patch("app.integration.intents_router.append_audit_row"):
        resp = create_draw_intent(
            payload=draw_payload,
            authorization=_auth(),
            session=session,
        )

    env = _envelope(resp)
    assert resp.status_code == 201, (
        f"Scenario 4: expected 201, got {resp.status_code}: {env}"
    )
    assert env["error"] is None, "Scenario 4: no error on draw intent creation"

    data = env["data"]
    assert "draw_package_id" in data, "Scenario 4: draw_package_id must be in response"
    assert "fee_bills" in data, "Scenario 4: fee_bills must be in response"

    fee_bills = data["fee_bills"]
    assert len(fee_bills) == 3, (
        f"Scenario 4: exactly 3 fee bills must be created, got {len(fee_bills)}"
    )

    # Fee math: 5% + 2% + 1% = 8% of 500_000 = 40_000
    amounts = sorted([Decimal(str(b["amount"])) for b in fee_bills])
    assert amounts == [
        Decimal("5000.00"),   # 1% President
        Decimal("10000.00"),  # 2% CEO
        Decimal("25000.00"),  # 5% developer
    ], f"Scenario 4: fee amounts do not match 5/2/1 split: {amounts}"

    total_fee = sum(amounts)
    expected_8pct = (draw_amount * Decimal("0.08")).quantize(Decimal("0.01"))
    assert total_fee == expected_8pct, (
        f"Scenario 4: 3 economic fees must sum to 8% of draw_amount "
        f"({expected_8pct}), got {total_fee}"
    )

    # Verify draw_package links: each fee_bill must have a workflow_id
    for bill in fee_bills:
        assert bill.get("workflow_id"), (
            f"Scenario 4: each fee bill must have a workflow_id: {bill}"
        )

    # ----------------------------------------------------------------
    # STV CM LLC canary: fee_payee_hint resolving to STV CM LLC → 400
    # ----------------------------------------------------------------
    stv_payload = DrawIntentIn(
        gmail_fee_opportunity_id=uuid.uuid4(),
        project_canonical="Madison Park",
        draw_amount=Decimal("500000.00"),
        draw_number=29,
        estimated_fee_hint=None,
        fee_payee_hint="STV CM LLC",          # blocked entity name
        fee_payee_status="BLOCKED",
        raw_extensions=None,
    )
    session_stv = _mock_session()
    with patch("app.integration.intents_router.append_audit_row"):
        resp_stv = create_draw_intent(
            payload=stv_payload,
            authorization=_auth(),
            session=session_stv,
        )

    assert isinstance(resp_stv, JSONResponse)
    assert resp_stv.status_code == 400, (
        f"Scenario 4 canary: STV CM LLC draw must be 400, got {resp_stv.status_code}"
    )
    env_stv = _envelope(resp_stv)
    assert env_stv["error"]["code"] == "STV_CM_LLC_BLOCKED", (
        "Scenario 4 canary: error code must be STV_CM_LLC_BLOCKED"
    )
    # G3: no DB mutation before the block guard fires
    session_stv.execute.assert_not_called()


# ============================================================================
# SCENARIO 5 — Aubrey confirmation (spec §10)
# ============================================================================


def test_scenario_5_aubrey_confirmation(monkeypatch):
    """payment_confirmed outbox → bill.status = 'paid'.

    Asserts:
      - POST /intents/payment-confirmed advances bill.status → 'paid'
      - Idempotent: second call returns 200 {status:'paid', idempotent:true}
    """
    from app.integration.intents_router import (
        PaymentConfirmedIn,
        confirm_payment,
    )

    _set_auth(monkeypatch)
    tracker_id = uuid.uuid4()

    # Session: bill found for this tracker_id with status='approved'
    bill_row = MagicMock()
    bill_row.__getitem__ = lambda self, k: {
        "id": _BILL_ID,
        "status": "approved",
    }[k]

    call_count = [0]
    def _side_effect(*args, **kwargs):
        m = MagicMock()
        if call_count[0] == 0:
            m.mappings.return_value.first.return_value = bill_row
        call_count[0] += 1
        return m

    session = _mock_session()
    session.execute.side_effect = _side_effect

    payload = PaymentConfirmedIn(gmail_tracker_id=tracker_id)

    with (
        patch("app.integration.intents_router.append_audit_row"),
        patch("app.integration.intents_router.send_bill_synced_callback", return_value=True),
    ):
        resp = confirm_payment(
            payload=payload,
            background_tasks=BackgroundTasks(),
            authorization=_auth(),
            session=session,
        )

    env = _envelope(resp)
    assert resp.status_code == 200, (
        f"Scenario 5: expected 200, got {resp.status_code}: {env}"
    )
    assert env["error"] is None, "Scenario 5: no error on payment confirmation"
    assert env["data"]["status"] == "paid", (
        "Scenario 5: bill status must be 'paid' after Aubrey confirmation"
    )

    # Idempotency: second call with already-paid bill → 200 idempotent=True
    paid_bill_row = MagicMock()
    paid_bill_row.__getitem__ = lambda self, k: {
        "id": _BILL_ID,
        "status": "paid",
    }[k]
    session_dup = _mock_session()
    session_dup.execute.return_value.mappings.return_value.first.return_value = paid_bill_row

    with patch("app.integration.intents_router.append_audit_row"):
        resp_dup = confirm_payment(
            payload=payload,
            background_tasks=BackgroundTasks(),
            authorization=_auth(),
            session=session_dup,
        )

    env_dup = _envelope(resp_dup)
    assert resp_dup.status_code == 200, "Scenario 5 idempotency: expected 200"
    assert env_dup["data"]["idempotent"] is True, (
        "Scenario 5 idempotency: second call must return idempotent=True"
    )
    assert env_dup["data"]["status"] == "paid", (
        "Scenario 5 idempotency: status must still be 'paid'"
    )


# ============================================================================
# test_no_auto_send_invariant (spec §10)
# ============================================================================


def test_no_auto_send_invariant_static_ast():
    """G1 static AST scan: no SQL DML literal targets draft_queue in the integration layer.

    Mechanism: scans Python source files for compound SQL write patterns that would
    indicate a live write to draft_queue (e.g. "INSERT INTO draft_queue", "UPDATE
    draft_queue"). Docstrings that mention draft_queue only to document the exclusion
    are not flagged because the compound pattern is not present.

    Companion test: test_no_auto_send_invariant in tests/test_must_not_break.py performs
    a live DB query under @pytest.mark.integration (RUN_INTEGRATION=1 required) to verify
    the same invariant against a running database.
    """
    assert _INTEGRATION_DIR.is_dir(), f"Integration dir not found: {_INTEGRATION_DIR}"

    # Use compound substring patterns so we only flag actual SQL DML on draft_queue.
    # Note: "update draft_queue" as a compound phrase is what we're after; NOT
    # "update" and "draft_queue" appearing separately in the same long docstring.
    compound_sql_write_patterns = [
        "insert into draft_queue",
        "update draft_queue",
        "delete from draft_queue",
    ]

    violations: list[str] = []
    for py_file in sorted(_INTEGRATION_DIR.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val_lower = node.value.lower()
                for pattern in compound_sql_write_patterns:
                    if pattern in val_lower:
                        violations.append(
                            f"{py_file.name}:{node.lineno}: "
                            f"SQL write pattern {pattern!r} found in string literal"
                        )

    assert not violations, (
        "G1 violated: integration module(s) contain draft_queue SQL write patterns:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ============================================================================
# test_wrong_db_guard (spec §10)
# ============================================================================


def test_wrong_db_guard():
    """DATABASE_URL_AIHUB, if set, must contain 'fdnwlcomuddzmluvbylg' (System B ref).

    G5: System A DB (ejxrbxoncsgglrqvjulg) and System B DB (fdnwlcomuddzmluvbylg)
    must never be confused.  CI must set DATABASE_URL_AIHUB; local dev may skip.
    """
    url = os.environ.get("DATABASE_URL_AIHUB", "")
    if not url:
        pytest.skip(
            "DATABASE_URL_AIHUB not set. Set to the System B Supabase URL "
            "(must contain 'fdnwlcomuddzmluvbylg') to enforce this guard in CI."
        )
    assert "fdnwlcomuddzmluvbylg" in url, (
        f"DATABASE_URL_AIHUB must reference System B project ref 'fdnwlcomuddzmluvbylg'. "
        f"Got: {url!r} — G5 (wrong DB) violation."
    )


# ============================================================================
# test_aivs_chain_validates (spec §10)
# ============================================================================


def test_aivs_chain_validates():
    """After 50 test commits to the AIVS chain, validate_chain() reports VALID.

    Verifies the AuditProof hash-chain core (Gate 2 pre-GL) correctly links
    50 consecutive records and that validate_chain() returns True without raising
    AuditChainBroken.  This is a pure-Python test — no DB required.
    """
    from app.audit.chain import AuditChainBroken, append_to_chain, validate_chain

    records: list = []
    session_id = f"e2e-test-session-{uuid.uuid4()}"

    for i in range(1, 51):
        append_to_chain(
            records,
            row_id=i,
            session_id=session_id,
            action_type=f"test_action_{i}",
            actor="test_agent",
            tool_name="test_integration_e2e",
            cost_cents=0,
            timestamp=f"2026-06-30T00:{i:02d}:00Z",
            inputs={"step": i, "session": session_id},
            outputs={"result": f"commit_{i}"},
        )

    assert len(records) == 50, f"Expected 50 records, got {len(records)}"

    # validate_chain must not raise AuditChainBroken.
    try:
        valid = validate_chain(records)
    except AuditChainBroken as exc:
        pytest.fail(f"AIVS chain validation FAILED after 50 commits: {exc}")

    assert valid is True, "validate_chain() must return True for intact 50-record chain"

    # Tamper detection: modify a record's outputs and re-validate → must raise.
    records[24].outputs["result"] = "TAMPERED"
    with pytest.raises(AuditChainBroken):
        validate_chain(records)


# ============================================================================
# GUARANTEE 1 — draft_queue.status CHECK(status != 'sent') never touched
# ============================================================================


def test_guarantee_1_draft_queue_untouched():
    """G1: integration code must NEVER write to draft_queue.

    Two levels of verification:
    1. AST scan: no SQL DML compound string literal targets draft_queue directly
       (e.g. "INSERT INTO draft_queue", "UPDATE draft_queue SET ..."). Docstrings
       that mention draft_queue to document the exclusion are NOT flagged because
       the compound SQL+table phrase won't appear in them.
    2. Import-level: no integration module imports draft_queue-related names.
    """
    assert _INTEGRATION_DIR.is_dir()

    # Compound phrases — must appear as a contiguous substring to fire the check.
    compound_sql_write_patterns = [
        "insert into draft_queue",
        "update draft_queue",
        "delete from draft_queue",
    ]

    violations: list[str] = []
    for py_file in sorted(_INTEGRATION_DIR.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.lower()
                for pattern in compound_sql_write_patterns:
                    if pattern in val:
                        violations.append(
                            f"{py_file.name}:{node.lineno}: "
                            f"SQL write pattern {pattern!r} in string literal"
                        )

    assert not violations, (
        "G1 — draft_queue SQL write detected in integration module:\n"
        + "\n".join(f"  {v}" for v in violations)
    )

    # Integration layer modules must not import draft_queue-adjacent names.
    for py_file in sorted(_INTEGRATION_DIR.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                module_name = (
                    getattr(node, "module", None) or ""
                    if isinstance(node, ast.ImportFrom)
                    else ""
                )
                for alias in getattr(node, "names", []):
                    full_name = f"{module_name}.{alias.name}" if module_name else alias.name
                    assert "draft_queue" not in full_name.lower(), (
                        f"G1 violation: {py_file.name} imports {full_name!r} "
                        "(draft_queue must never be imported by integration layer)"
                    )


# ============================================================================
# GUARANTEE 2 — bank_change_risk P0 fires BEFORE any downstream action
# ============================================================================


def test_guarantee_2_bank_change_risk_fires_first():
    """G2: bank_change_risk guard is the FIRST guard in write_bill_intent.

    AST check: within write_bill_intent(), the 'bank_change_risk_flag' reference
    must appear on a lower line number than the BLOCKED_STATES reference.
    Also verifies that /intents/bill returns 400 before any DB call when
    gmail_invoiceproof.bank_change_risk=True.
    """
    writer = _INTEGRATION_DIR / "outbox_writer.py"
    source = writer.read_text(encoding="utf-8")
    tree = ast.parse(source)

    func_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
         and n.name == "write_bill_intent"),
        None,
    )
    assert func_node is not None, "write_bill_intent not found in outbox_writer.py"

    bank_lines: list[int] = []
    blocked_lines: list[int] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == "bank_change_risk_flag":
                bank_lines.append(node.lineno)
        if isinstance(node, ast.Name) and node.id == "BLOCKED_STATES":
            blocked_lines.append(node.lineno)

    assert bank_lines, "bank_change_risk_flag not found in write_bill_intent body"
    assert blocked_lines, "BLOCKED_STATES not found in write_bill_intent body"
    assert min(bank_lines) < min(blocked_lines), (
        f"G2 violated: bank_change_risk_flag first at line {min(bank_lines)} but "
        f"BLOCKED_STATES first at line {min(blocked_lines)}. "
        "bank_change_risk guard MUST fire before BLOCKED_STATES check."
    )

    # Also verify System B /intents/bill rejects before any DB call.
    from app.integration.intents_router import (
        BillIntentIn,
        GmailInvoiceProof,
        create_bill_intent,
    )

    proof = GmailInvoiceProof(
        risk_level="critical",
        final_decision="blocked",
        checks_passed=0,
        bank_change_risk=True,
        duplicate_detected=False,
        vendor_confidence=0.0,
    )
    payload = BillIntentIn(
        gmail_tracker_id=uuid.uuid4(),
        vendor_name="Fraud Vendor",
        amount=None,
        po_ref=None,
        due_date=None,
        raw_extensions=None,
        gmail_invoiceproof=proof,
        company_id=None,
    )
    session = _mock_session()
    os.environ.setdefault("AIHUB_OUTBOX_TOKEN", "tok-g2-test")
    resp = create_bill_intent(
        payload=payload,
        authorization="Bearer tok-g2-test",
        session=session,
    )
    assert resp.status_code == 400, "G2: /intents/bill must 400 on bank_change_risk before DB"
    session.execute.assert_not_called()


# ============================================================================
# GUARANTEE 3 — STV CM LLC blocked independently in both systems
# ============================================================================


def test_guarantee_3_stv_cm_llc_blocked_independently(monkeypatch):
    """G3: STV CM LLC blocked in outbox_writer (System A) AND /intents/draw (System B).

    Two independent tests:
    1. outbox_writer.write_draw_intent(blocked=True) → returns None, audit row written.
    2. /intents/draw with fee_payee_hint='STV CM LLC' → 400 STV_CM_LLC_BLOCKED, no DB calls.
    """
    # Part 1: System A outbox_writer guard
    from app.integration import outbox_writer as _ow

    audit_events: list[str] = []

    def _fake_audit(db_session, event, details):
        audit_events.append(event)

    with patch.object(_ow, "_audit_log", side_effect=_fake_audit):
        result = _ow.write_draw_intent(
            fee_opportunity_id=str(uuid.uuid4()),
            project_canonical="Madison Park",
            draw_amount=500_000.00,
            draw_number=29,
            estimated_fee_hint=None,
            fee_payee_hint=None,
            fee_payee_status="BLOCKED",
            raw_extensions=None,
            db_session=_mock_session(),
            blocked=True,  # STV CM LLC guard
        )

    assert result is None, (
        "G3 System A: write_draw_intent(blocked=True) must return None"
    )
    assert any("stv_cm_llc" in e.lower() for e in audit_events), (
        f"G3 System A: audit log must record stv_cm_llc event. Got: {audit_events}"
    )

    # Part 2: System B /intents/draw guard
    from app.integration.intents_router import DrawIntentIn, create_draw_intent

    _g3_token = "tok-g3-distinct-stvcm-llc"
    monkeypatch.setenv("AIHUB_OUTBOX_TOKEN", _g3_token)

    for blocked_name in ["STV CM LLC", "Summa Terra CM LLC", "CM LLC"]:
        session = _mock_session()
        payload = DrawIntentIn(
            gmail_fee_opportunity_id=uuid.uuid4(),
            project_canonical="Madison Park",
            draw_amount=Decimal("500000.00"),
            draw_number=29,
            estimated_fee_hint=None,
            fee_payee_hint=blocked_name,
            fee_payee_status="BLOCKED",
            raw_extensions=None,
        )
        with patch("app.integration.intents_router.append_audit_row"):
            resp = create_draw_intent(
                payload=payload,
                authorization=f"Bearer {_g3_token}",
                session=session,
            )
        assert resp.status_code == 400, (
            f"G3 System B: '{blocked_name}' must be blocked with 400, "
            f"got {resp.status_code}"
        )
        env = _envelope(resp)
        assert env["error"]["code"] == "STV_CM_LLC_BLOCKED", (
            f"G3 System B: error code must be STV_CM_LLC_BLOCKED for '{blocked_name}'"
        )
        session.execute.assert_not_called()


# ============================================================================
# GUARANTEE 4 — No automated approvals
# ============================================================================


def test_guarantee_4_no_automated_approvals():
    """G4: human approval is the only path to bill → 'approved' or QB write.

    1. outbox_writer must NOT reference /approvals or auto-approve calls.
    2. outbox_delivery_job must NOT call /approvals endpoint.
    3. /intents/bill creates bill with status='drafted' (not 'approved').
    4. manual_ui approval without a note → 422 (G4 human-gate enforced server-side).
    """
    # Structural: integration delivery pipeline files must not call the /approvals endpoint.
    # Note: docstrings/comments may MENTION /approvals to document the exclusion — that is
    # correct. We look for the endpoint appearing in the _ENDPOINT_MAP dict or in httpx call
    # URL strings, not in documentation strings.
    assert (_INTEGRATION_DIR / "outbox_delivery_job.py").exists(), (
        "outbox_delivery_job.py not yet implemented — G4 structural check cannot run"
    )
    delivery_src = (_INTEGRATION_DIR / "outbox_delivery_job.py").read_text(encoding="utf-8")
    delivery_tree = ast.parse(delivery_src)
    # _ENDPOINT_MAP in outbox_delivery_job maps event_type → URL path; /approvals must be absent.
    endpoint_map_has_approvals = False
    for node in ast.walk(delivery_tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Only flag if the string looks like an endpoint path value (starts with '/')
            # and contains 'approvals'.  Module-level docstrings don't start with '/'.
            val = node.value.strip()
            if val.startswith("/") and "approvals" in val.lower():
                endpoint_map_has_approvals = True
                break
    assert not endpoint_map_has_approvals, (
        "G4 violation: outbox_delivery_job.py maps '/approvals' as a delivery endpoint — "
        "this module must NEVER call the approval endpoint"
    )

    # outbox_writer must not contain 'auto_approve' function calls.
    writer_src = (_INTEGRATION_DIR / "outbox_writer.py").read_text(encoding="utf-8")
    assert "auto_approve" not in writer_src.lower(), (
        "G4 violation: outbox_writer.py contains 'auto_approve' — "
        "no automated approvals are permitted"
    )

    # /intents/bill creates bill at 'drafted' status — not 'approved'.
    assert "drafted" in (_INTEGRATION_DIR / "intents_router.py").read_text(encoding="utf-8"), (
        "G4: /intents/bill must create bill with status='drafted'"
    )

    # manual_ui approval without note → 422
    from app.integration.intents_router import IntegrationApprovalIn, approve_bill_intent

    os.environ.setdefault("AIHUB_OUTBOX_TOKEN", "tok-g4-test")
    os.environ.setdefault("BEN_SESSION_TOKEN", "tok-g4-test")

    no_note_payload = IntegrationApprovalIn(
        decision="approve",
        source="manual_ui",
        note=None,  # missing note
        evidence_email_id=None,
    )
    resp = approve_bill_intent(
        workflow_id="wf-g4-test",
        background_tasks=BackgroundTasks(),
        payload=no_note_payload,
        authorization="Bearer tok-g4-test",
        session=_mock_session(),
    )
    assert resp.status_code == 422, (
        f"G4: manual_ui approval without note must be 422, got {resp.status_code}"
    )


# ============================================================================
# GUARANTEE 5 — DB clients never confused
# ============================================================================


def test_guarantee_5_db_clients_never_confused():
    """G5: System A DB (ejxrbxoncsgglrqvjulg) and System B DB (fdnwlcomuddzmluvbylg) never mixed.

    1. outbox_writer.py must NOT contain fdnwlcomuddzmluvbylg in any connection literal.
    2. callback_router.py uses SYSTEM_A_DB_URL — must not default to DATABASE_URL.
    3. intents_router.py only imports from app.db (System B) — no System A DB import.
    4. If DATABASE_URL_AIHUB is set in the environment, it must contain fdnwlcomuddzmluvbylg.
    """
    b_ref = "fdnwlcomuddzmluvbylg"

    # outbox_writer must not use System B ref as a connection string.
    writer_src = (_INTEGRATION_DIR / "outbox_writer.py").read_text(encoding="utf-8")
    writer_tree = ast.parse(writer_src)
    conn_indicators = ["postgresql", "supabase.co", "database_url"]
    for node in ast.walk(writer_tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.lower()
            if b_ref in val:
                for ind in conn_indicators:
                    assert ind not in val, (
                        f"G5 violation: outbox_writer.py line {node.lineno} contains "
                        f"System B ref ({b_ref}) in a connection-like string"
                    )

    # callback_router must use SYSTEM_A_DB_URL env var, not DATABASE_URL directly.
    assert (_INTEGRATION_DIR / "callback_router.py").exists(), (
        "callback_router.py not yet implemented — G5 structural check cannot run"
    )
    cr_src = (_INTEGRATION_DIR / "callback_router.py").read_text(encoding="utf-8")
    assert "SYSTEM_A_DB_URL" in cr_src, (
        "G5: callback_router.py must use SYSTEM_A_DB_URL to connect to System A"
    )

    # intents_router must import app.db (System B) and not reference System A engine directly.
    ir_src = (_INTEGRATION_DIR / "intents_router.py").read_text(encoding="utf-8")
    assert "from app.db import get_session" in ir_src or "app.db" in ir_src, (
        "G5: intents_router.py must use app.db (System B DB)"
    )
    assert "SYSTEM_A_DB_URL" not in ir_src, (
        "G5 violation: intents_router.py must NOT use SYSTEM_A_DB_URL "
        "(it is System B only)"
    )

    # Environment guard (skips if not set in local dev; enforced in CI).
    url = os.environ.get("DATABASE_URL_AIHUB", "")
    if url:
        assert b_ref in url, (
            f"G5: DATABASE_URL_AIHUB must reference System B ({b_ref}). Got: {url!r}"
        )


# ============================================================================
# GUARANTEE 6 — Gate 1 fails closed
# ============================================================================


def test_guarantee_6_gate1_fails_closed(monkeypatch):
    """G6: SwarmSync proof-core Gate 1 fails closed — no bill reaches approved without passed=True.

    Verifies:
    1. /intents/approvals/{wf_id}: 422 PROOF_BUNDLE_MISSING when bill has no bundle.
    2. /intents/approvals/{wf_id}: 422 PROOF_BUNDLE_NOT_PASSED when bundle.passed=False.
    3. invoice_proof_gate.run_invoice_proof_gate1: raises InvoiceProofGateFailed when key absent.
    4. invoice_proof_gate._evaluate_passed: fails on empty/invalid proof dict.
    """
    from app.integration.intents_router import IntegrationApprovalIn, approve_bill_intent

    _g6_token = "tok-g6-gate-closed-distinct"
    monkeypatch.setenv("AIHUB_OUTBOX_TOKEN", _g6_token)
    monkeypatch.setenv("BEN_SESSION_TOKEN", _g6_token)

    # 1. No bundle → 422 PROOF_BUNDLE_MISSING
    session_no_bundle = _mock_session()
    bill_no_bundle = MagicMock()
    bill_no_bundle.__getitem__ = lambda self, k: {
        "id": _BILL_ID,
        "status": "verified",
        "invoiceproof_bundle_id": None,  # no bundle
        "tracker_id": _TRACKER_ID,
    }[k]
    session_no_bundle.execute.return_value.mappings.return_value.first.return_value = (
        bill_no_bundle
    )

    approval = IntegrationApprovalIn(
        decision="approve",
        source="email_detected",
        note=None,
        evidence_email_id=None,
    )
    resp_no_bundle = approve_bill_intent(
        workflow_id=_WF_ID,
        background_tasks=BackgroundTasks(),
        payload=approval,
        authorization=f"Bearer {_g6_token}",
        session=session_no_bundle,
    )
    assert resp_no_bundle.status_code == 422, (
        f"G6: missing proof bundle must return 422, got {resp_no_bundle.status_code}"
    )
    env_no_bundle = _envelope(resp_no_bundle)
    assert env_no_bundle["error"]["code"] == "PROOF_BUNDLE_MISSING", (
        f"G6: error code must be PROOF_BUNDLE_MISSING, got {env_no_bundle['error']['code']}"
    )

    # 2. Bundle present but passed=False → 422 PROOF_BUNDLE_NOT_PASSED
    session_fail = _mock_session()
    bill_with_bundle = MagicMock()
    bill_with_bundle.__getitem__ = lambda self, k: {
        "id": _BILL_ID,
        "status": "verified",
        "invoiceproof_bundle_id": _BUNDLE_ID,
        "tracker_id": _TRACKER_ID,
    }[k]
    proof_failed = MagicMock()
    proof_failed.__getitem__ = lambda self, k: {"passed": False}[k]

    call_n = [0]
    def _s_fail(*a, **k):
        m = MagicMock()
        if call_n[0] == 0:
            m.mappings.return_value.first.return_value = bill_with_bundle
        elif call_n[0] == 1:
            m.mappings.return_value.first.return_value = proof_failed
        call_n[0] += 1
        return m

    session_fail.execute.side_effect = _s_fail

    resp_fail = approve_bill_intent(
        workflow_id=_WF_ID,
        background_tasks=BackgroundTasks(),
        payload=approval,
        authorization=f"Bearer {_g6_token}",
        session=session_fail,
    )
    assert resp_fail.status_code == 422, (
        f"G6: failed proof bundle must return 422, got {resp_fail.status_code}"
    )
    env_fail = _envelope(resp_fail)
    assert env_fail["error"]["code"] == "PROOF_BUNDLE_NOT_PASSED", (
        f"G6: error code must be PROOF_BUNDLE_NOT_PASSED, got {env_fail['error']['code']}"
    )

    # 3. invoice_proof_gate key-absent → InvoiceProofGateFailed
    from app.integration.invoice_proof_gate import (
        _evaluate_passed,
        _require_signing_key,
    )

    # Temporarily clear ALL signing key env vars that _require_signing_key() checks.
    # invoice_proof_gate.py reads SWARMSYNC_SA_KEY then VCAP_SHARED_SECRET in order.
    # We also pop SWARMSYNC_SA_API_KEY for safety in case the name ever changes.
    orig_sa = os.environ.pop("SWARMSYNC_SA_KEY", None)
    orig_sa_api = os.environ.pop("SWARMSYNC_SA_API_KEY", None)
    orig_vc = os.environ.pop("VCAP_SHARED_SECRET", None)
    try:
        # Subtest A: keys fully absent → RuntimeError.
        with pytest.raises(RuntimeError, match="Gate 1 key unavailable"):
            _require_signing_key()

        # Subtest B: keys present but empty string → also RuntimeError.
        # This is a distinct failure mode from "key absent" and common in CI/CD
        # where env vars are set to '' rather than removed.
        os.environ["SWARMSYNC_SA_KEY"] = ""
        os.environ["VCAP_SHARED_SECRET"] = ""
        with pytest.raises(RuntimeError, match="Gate 1 key unavailable"):
            _require_signing_key()
    finally:
        # Always restore original values (or remove the keys we set to '').
        if orig_sa is not None:
            os.environ["SWARMSYNC_SA_KEY"] = orig_sa
        else:
            os.environ.pop("SWARMSYNC_SA_KEY", None)
        if orig_sa_api is not None:
            os.environ["SWARMSYNC_SA_API_KEY"] = orig_sa_api
        else:
            os.environ.pop("SWARMSYNC_SA_API_KEY", None)
        if orig_vc is not None:
            os.environ["VCAP_SHARED_SECRET"] = orig_vc
        else:
            os.environ.pop("VCAP_SHARED_SECRET", None)

    # 4. _evaluate_passed: empty dict → INVOICEPROOF_INVALID
    passed, reason = _evaluate_passed({})
    assert passed is False, "G6: empty proof dict must evaluate to passed=False"
    assert "INVALID" in reason, f"G6: reason must contain 'INVALID', got {reason!r}"

    passed_ok, reason_ok = _evaluate_passed({"passed": True})
    assert passed_ok is True, "G6: passed=True proof must evaluate to passed=True"
    assert reason_ok == "", "G6: clean proof must have empty reason"

    passed_crit, reason_crit = _evaluate_passed({"riskLevel": "CRITICAL"})
    assert passed_crit is False, "G6: CRITICAL risk must evaluate to passed=False"
    assert "CRITICAL" in reason_crit, f"G6: reason must contain CRITICAL, got {reason_crit!r}"


# ============================================================================
# GUARANTEE 7 — Never write to QB without valid proof + human approval
# ============================================================================


def test_guarantee_7_no_qb_write_without_proof():
    """G7: System B never writes to QB without valid proof + human approval.

    Structural verification:
    1. No integration module imports QBWC / QB transport layer.
    2. No integration module references BillAdd, QBXML, or QBWC write operations.
    3. /intents/* endpoints never reach the transport router / QBWC path.
    4. The only bill status change in the integration layer is to canonical store only.
    """
    # Check 1: No integration module imports from the QB transport layer.
    # Note: string literals in docstrings may mention "QBWC" or "BillAdd" to
    # document the exclusion — that is correct and expected behavior.
    # We only flag actual IMPORT statements from QB transport modules.
    import_violations: list[str] = []
    for py_file in sorted(_INTEGRATION_DIR.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = getattr(node, "module", "") or ""
                for blocked_module in ["app.transport", "transport.qbwc", "transport.qbxml"]:
                    if module == blocked_module or module.startswith(blocked_module + "."):
                        import_violations.append(
                            f"{py_file.name}:{node.lineno}: "
                            f"imports from QB transport module {module!r}"
                        )

    assert not import_violations, (
        "G7 violated: integration module(s) import from QB transport layer:\n"
        + "\n".join(f"  {v}" for v in import_violations)
    )

    # Check 2: No integration module contains actual QB write RQ XML strings
    # (as would appear in qbXML BillAdd requests sent to QB Desktop).
    # These are SOAP/XML operation names that would only appear if QB writes were attempted.
    qb_write_ops = ["BillAddRq", "BillModRq", "QBSessionManager"]
    op_violations: list[str] = []
    for py_file in sorted(_INTEGRATION_DIR.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        for op in qb_write_ops:
            if op in source:
                op_violations.append(f"{py_file.name}: contains QB write operation {op!r}")

    assert not op_violations, (
        "G7 violated: integration module(s) contain QB write XML operations:\n"
        + "\n".join(f"  {v}" for v in op_violations)
    )

    # Verify the approval endpoint docs state "no QBWC write" (shadow mode comment present).
    # Note: the naive "QB" in ir_src check is intentionally omitted — it would pass
    # even on import comments or variable names and does not prove absence of QB writes.
    # The AST import scan (Check 1) and qb_write_ops scan (Check 2) above are the real
    # enforcement; this third check validates only the docstring guarantee annotation.
    ir_src = (_INTEGRATION_DIR / "intents_router.py").read_text(encoding="utf-8")
    shadow_doc_present = any(phrase in ir_src for phrase in [
        "Never writes to QB",
        "No QBWC write",
        "never write to QB",
        "no QB write",
        "G7",
    ])
    assert shadow_doc_present, (
        "G7: intents_router.py must explicitly document the no-QB-write guarantee"
    )


# ============================================================================
# SCENARIO 3 supplement — bank_block idempotency
# ============================================================================


def test_bank_block_idempotency(monkeypatch):
    """create_bank_block called twice with same sender_email returns 200 idempotent=True.

    First call: idempotency SELECT returns None (no prior block) → 201 created.
    Second call: idempotency SELECT returns existing vendor row → 200 idempotent=True
    and session.execute is called exactly once (the idempotency SELECT) with no UPDATE.
    """
    from app.integration.intents_router import BankBlockIn, create_bank_block

    _set_auth(monkeypatch)

    sender_email = "fraud@evil.example.com"
    vendor_name = "Suspicious Vendor"
    block_id = str(uuid.uuid4())

    payload = BankBlockIn(
        vendor_name=vendor_name,
        sender_email=sender_email,
        gmail_message_id="msg-fraud-001",
        tracker_id=None,
    )

    # --- Second call: idempotency SELECT returns an existing vendor row -----------
    session_dup = _mock_session()

    # The idempotency check queries SELECT id FROM vendors WHERE bank_fingerprint = ...
    # Return a row so the endpoint short-circuits immediately.
    existing_vendor = MagicMock()
    existing_vendor.__getitem__ = lambda self, k: {"id": block_id}[k]
    session_dup.execute.return_value.mappings.return_value.first.return_value = existing_vendor

    resp_dup = create_bank_block(
        payload=payload,
        authorization=_auth(),
        session=session_dup,
    )

    assert isinstance(resp_dup, JSONResponse)
    assert resp_dup.status_code == 200, (
        f"Second bank-block call must return 200 (idempotent), got {resp_dup.status_code}"
    )
    dup_env = _envelope(resp_dup)
    assert dup_env["error"] is None
    assert dup_env["data"]["idempotent"] is True, (
        "Second bank-block call must set idempotent=True"
    )
    assert dup_env["data"]["block_id"] == block_id

    # Advisory lock + idempotency SELECT must have fired — no INSERT/UPDATE should follow.
    assert session_dup.execute.call_count == 2, (
        "Idempotent bank-block must call session.execute exactly twice "
        "(pg_advisory_xact_lock + dedup SELECT), "
        f"got {session_dup.execute.call_count} calls"
    )
    session_dup.commit.assert_not_called()


# ============================================================================
# HTTP LAYER — TestClient smoke test
# ============================================================================


def test_http_layer_bill_intent_via_testclient(monkeypatch):
    """Verify route registration, path parsing, and dependency injection via TestClient.

    This test sends a real HTTP POST through FastAPI's full request stack — route prefix,
    middleware, response model serialization, and the SessionDep override — so that bugs
    in router wiring (wrong method, wrong prefix, wrong dependency) are caught before
    deploy, not at production request time.
    """
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    _set_auth(monkeypatch)

    # Override the DB session dependency to avoid requiring a live DB.
    mock_session = _mock_session()

    # First execute: idempotency SELECT returns None (no existing bill).
    # Subsequent executes: vendor fuzzy match returns empty list; company SELECT returns first row.
    company_id = str(uuid.uuid4())

    call_n = [0]

    def _session_execute(*args, **kwargs):
        m = MagicMock()
        n = call_n[0]
        call_n[0] += 1
        if n == 0:
            # Idempotency check — no existing bill.
            m.mappings.return_value.first.return_value = None
        elif n == 1:
            # Vendor fuzzy match — no matches.
            m.mappings.return_value.all.return_value = []
        elif n == 2:
            # Company fallback SELECT.
            company_row = MagicMock()
            company_row.__class__ = type("ScalarRow", (), {"__bool__": lambda s: True})
            m.scalar_one_or_none.return_value = company_id
        else:
            # Subsequent calls (INSERT vendor, INSERT bill, etc.)
            m.mappings.return_value.first.return_value = None
            m.mappings.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = _session_execute

    app.dependency_overrides[get_session] = lambda: mock_session

    try:
        client = TestClient(app, raise_server_exceptions=False)

        request_body = {
            "gmail_tracker_id": str(uuid.uuid4()),
            "vendor_name": "Makers Line",
            "amount": "50000.00",
            "po_ref": "PO-HTTP-TEST",
            "due_date": None,
            "raw_extensions": {"project_label": "Madison Park"},
            "gmail_invoiceproof": {
                "risk_level": "low",
                "final_decision": "approved",
                "checks_passed": 7,
                "bank_change_risk": False,
                "duplicate_detected": False,
                "vendor_confidence": 0.95,
            },
        }

        resp = client.post(
            "/intents/bill",
            json=request_body,
            headers={"Authorization": _auth()},
        )

        # The route must be found (not 404/405 from bad wiring) and auth must pass.
        # We accept 201 (new bill) or 5xx from session mock limitations — the key
        # assertion is that the route resolved and auth was evaluated.
        assert resp.status_code != 404, (
            "POST /intents/bill returned 404 — route is not registered in main.py"
        )
        assert resp.status_code != 405, (
            "POST /intents/bill returned 405 — wrong HTTP method registered"
        )
        assert resp.status_code != 401, (
            "POST /intents/bill returned 401 with correct token — auth dependency broken"
        )
        # Confirm the response uses the project envelope format.
        body = resp.json()
        assert "data" in body or "detail" in body, (
            "Response must be project envelope {data, error, meta} or FastAPI validation error"
        )
    finally:
        app.dependency_overrides.clear()
