"""Live-DB proof that Gate 1 (InvoiceProof) is genuinely wired into the real
``create_bill_intent`` / ``approve_bill_intent`` code path (SPEC §5 Flow 1 Step 11).

Context — spec-compliance-audit-stv-integration-layer-2026-06-30.md flagged a
SILENT GAP: the pre-existing e2e tests (``tests/test_integration_e2e.py`` Scenario 1
and Guarantee 6) hand-inject ``invoiceproof_bundle_id`` into a MagicMock SQLAlchemy
session instead of exercising the real ``run_invoice_proof_gate1`` call inside
``create_bill_intent`` — so the suite read green even if Gate 1 were never wired.
"Ben" (Fix 1) wired ``run_invoice_proof_gate1`` into ``create_bill_intent`` for
real. This module proves that wiring against a **live Supabase Postgres session**,
calling the real endpoint functions end to end — no mocked session, no manually
set ``invoiceproof_bundle_id``.

Marked ``@pytest.mark.integration`` — skipped unless ``RUN_INTEGRATION=1`` (see
tests/conftest.py), following the same live-DB gating convention as
tests/test_intents_bill.py / tests/test_integration_db.py.

FINDING surfaced while writing these tests (reported in the handoff, not papered
over): ``invoice_proof_gate._evaluate_passed`` looks for camelCase ``"riskLevel"``
and ``"blocked"`` keys (and an explicit ``"passed"`` key) in the evidence dict.
The real ``GmailInvoiceProof`` Pydantic model (as sent by ``BillIntentIn`` /
``create_bill_intent``) only ever produces snake_case keys — ``risk_level``,
``final_decision``, ``checks_passed``, ``bank_change_risk``, ``duplicate_detected``,
``vendor_confidence`` — and never a ``passed``/``riskLevel``/``blocked`` key. So
``_evaluate_passed`` always falls through to its default ``return True, ""`` for
*any* evidence that gets past the two upstream guards in ``create_bill_intent``
(``bank_change_risk`` and ``final_decision == "blocked"``). In practice this means
Gate 1, as wired today, can only fail closed for a *configuration* reason (missing
signing key) when driven through the real ``/intents/bill`` schema — it cannot
currently fail closed on "critical risk but not literally blocked" evidence content
submitted through the public endpoint. ``test_gate1_missing_key_fails_closed_e2e``
exercises the config-failure fail-closed path end to end. ``test_gate1_bad_evidence_fails_closed_direct_call``
exercises the evidence-based fail-closed path by calling ``run_invoice_proof_gate1``
directly (still the real function, still a real DB) to prove the *gate itself*
correctly blocks bad evidence — it is the ``GmailInvoiceProof`` schema round-trip
that currently prevents bad evidence from reaching it via the public endpoint.

TWO ADDITIONAL CRITICAL BUGS were discovered while making these tests exercise a
real Supabase Postgres session (previously invisible because every existing test
in the suite uses a MagicMock session that never actually compiles/executes SQL
against a real database) and were fixed in ``app/integration/intents_router.py``
as a minimal, targeted part of this change:

1. ``:param::jsonb`` cast syntax inside ``text()`` SQL is not parsed correctly by
   SQLAlchemy's named-bindparam extraction when compiled for the psycopg3 dialect
   — the parameter silently fails to bind and the raw ``:name::jsonb`` token is
   sent to Postgres verbatim, which is a syntax error. This broke the bills INSERT
   and the soft-draft vendor INSERT unconditionally — ``create_bill_intent`` could
   not successfully write a single row against a real Postgres session before this
   fix. Changed to ``CAST(:param AS jsonb)`` (SQLAlchemy handles this pattern
   correctly). NOTE: the same ``:param::jsonb`` pattern still exists, unfixed, in
   ``app/integration/callback_router.py``, ``app/integration/outbox_writer.py``,
   ``app/integration/approval_signal.py``, ``app/integration/outbox_delivery_job.py``,
   and in the draw-intent INSERTs (lines ~851/925) of this same file — those were
   left untouched as out of scope for this task, but should be audited/fixed too.
2. The approval path (``_resolve_bill_approval``) threaded ``session_id=workflow_id``
   into ``append_audit_row`` / ``load_session_records`` for the AIVS hash chain.
   ``workflow_id`` is a string like ``"bill-intent-<uuid>"`` — NOT a valid UUID —
   while ``AuditRow.session_id`` is a strict ``UUID`` column. Every real approval
   call crashed with a Postgres ``DataError`` before this fix. Changed the four
   call sites to use ``session_id=bill_id`` (a real uuid), matching the convention
   Gate 1 itself already uses in ``invoice_proof_gate.run_invoice_proof_gate1``, so
   the Gate-1 audit rows and the approval audit rows for the same bill now share
   one coherent AIVS chain. ``workflow_id`` is still recorded in each row's
   ``inputs`` payload for traceability. This is a behavioural change to the AIVS
   chain's "session" boundary (bill-scoped instead of workflow-scoped) — flagged
   here explicitly so the team can confirm this was the intended design.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import text

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TOKEN = "gate1-wiring-live-token"


def _envelope(resp: Any) -> dict:
    import json

    if isinstance(resp, JSONResponse):
        return json.loads(bytes(resp.body))
    return resp


def _set_auth(monkeypatch) -> None:
    monkeypatch.setenv("AIHUB_OUTBOX_TOKEN", _TOKEN)
    monkeypatch.setenv("BEN_SESSION_TOKEN", _TOKEN)


def _set_signing_key(monkeypatch) -> None:
    """Ensure Gate 1 has a signing key available (VCAP_SHARED_SECRET fallback)."""
    monkeypatch.setenv("SWARMSYNC_SA_KEY", "")
    monkeypatch.setenv("VCAP_SHARED_SECRET", "test-gate1-wiring-shared-secret")


def _clean_proof(**overrides: Any):
    from app.integration.intents_router import GmailInvoiceProof

    data: dict[str, Any] = dict(
        risk_level="low",
        final_decision="approved",
        checks_passed=7,
        bank_change_risk=False,
        duplicate_detected=False,
        vendor_confidence=0.95,
    )
    data.update(overrides)
    return GmailInvoiceProof(**data)


def _cleanup_bill(session, bill_id: str | None, vendor_id: str | None, workflow_id: str | None) -> None:
    """Best-effort teardown of rows created by these live-DB tests.

    Note: audit_rows.session_id is cleaned up keyed by bill_id, not workflow_id —
    see the CRITICAL finding in this module's docstring: the AIVS chain is keyed
    by bill_id (a real uuid), not workflow_id (a non-uuid string like
    "bill-intent-<uuid>"), after the fix applied alongside these tests.
    """
    session.rollback()
    if bill_id is not None:
        session.execute(text("DELETE FROM bills WHERE id = :bid"), {"bid": bill_id})
        session.execute(
            text("DELETE FROM proof_bundles WHERE payload->>'bill_id' = :bid"),
            {"bid": bill_id},
        )
        session.execute(text("DELETE FROM audit_rows WHERE session_id = :sid"), {"sid": bill_id})
    if vendor_id is not None:
        session.execute(text("DELETE FROM vendors WHERE id = :vid"), {"vid": vendor_id})
    session.commit()


# ============================================================================
# POSITIVE CASE — real create_bill_intent + real approve_bill_intent, real DB
# ============================================================================


def test_gate1_wires_bundle_and_unblocks_approval_e2e(monkeypatch):
    """Clean evidence through the REAL create_bill_intent() call path must:

    1. Actually execute run_invoice_proof_gate1 (no field is hand-set).
    2. Leave bills.invoiceproof_bundle_id populated in the live DB.
    3. Leave a proof_bundles row with passed=True in the live DB.
    4. Let the REAL approve_bill_intent() succeed (200), not 422 PROOF_BUNDLE_MISSING.
    """
    from app.db import get_engine
    from app.integration.intents_router import (
        BillIntentIn,
        IntegrationApprovalIn,
        approve_bill_intent,
        create_bill_intent,
    )

    _set_auth(monkeypatch)
    _set_signing_key(monkeypatch)

    engine = get_engine()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    session = Session()

    bill_id: str | None = None
    vendor_id: str | None = None
    workflow_id: str | None = None

    try:
        tracker_id = uuid.uuid4()
        vendor_name = f"GATE1 WIRING TEST VENDOR {uuid.uuid4()}"

        payload = BillIntentIn(
            gmail_tracker_id=tracker_id,
            vendor_name=vendor_name,
            amount=Decimal("1234.56"),
            po_ref="PO-GATE1-WIRING-001",
            due_date=None,
            raw_extensions={"project_label": "Gate1 Wiring Test"},
            gmail_invoiceproof=_clean_proof(),
            company_id=None,
        )

        # --- Step 1: call the REAL endpoint function against a REAL session ---
        resp_create = create_bill_intent(
            payload=payload,
            authorization=f"Bearer {_TOKEN}",
            session=session,
        )
        env_create = _envelope(resp_create)
        assert resp_create.status_code == 201, (
            f"create_bill_intent must return 201, got {resp_create.status_code}: {env_create}"
        )
        bill_id = env_create["data"]["bill_id"]
        workflow_id = env_create["data"]["workflow_id"]
        vendor_id = env_create["data"]["vendor_id"]
        assert bill_id and workflow_id, "bill_id/workflow_id must be returned"

        # --- Step 2: verify DB state directly — NO manual field injection ------
        # This is the crux of the audit gap: read straight from Postgres what
        # run_invoice_proof_gate1 actually wrote, rather than trusting the
        # response envelope alone.
        row = session.execute(
            text(
                "SELECT status, invoiceproof_bundle_id FROM bills WHERE id = :bid"
            ),
            {"bid": bill_id},
        ).mappings().first()
        assert row is not None, "bill row must exist in the live DB"
        assert row["invoiceproof_bundle_id"] is not None, (
            "Gate 1 did not populate bills.invoiceproof_bundle_id — "
            "run_invoice_proof_gate1 was NOT effectively wired (real bug, not a test artifact)"
        )
        assert row["status"] == "verified", (
            f"Gate 1 pass must advance bill.status to 'verified', got {row['status']!r}"
        )

        bundle_id = str(row["invoiceproof_bundle_id"])
        proof_row = session.execute(
            text("SELECT passed, kind, vcap_state FROM proof_bundles WHERE id = :bid"),
            {"bid": bundle_id},
        ).mappings().first()
        assert proof_row is not None, "proof_bundles row referenced by the bill must exist"
        assert proof_row["passed"] is True, "proof_bundles.passed must be True for clean evidence"
        assert proof_row["kind"] == "invoice"
        assert proof_row["vcap_state"] == "VCAP_FULL_BUNDLE"

        # --- Step 3: call the REAL approval endpoint on the SAME bill ----------
        approval_payload = IntegrationApprovalIn(
            decision="approve",
            source="email_detected",
            note=None,
            evidence_email_id="msg-gate1-wiring-001",
        )
        resp_appr = approve_bill_intent(
            workflow_id=workflow_id,
            background_tasks=BackgroundTasks(),
            payload=approval_payload,
            authorization=f"Bearer {_TOKEN}",
            session=session,
        )
        env_appr = _envelope(resp_appr)
        assert resp_appr.status_code == 200, (
            f"approve_bill_intent must return 200 once Gate 1 has passed, "
            f"got {resp_appr.status_code}: {env_appr}"
        )
        assert env_appr["error"] is None
        assert env_appr["data"]["status"] == "approved"
        assert env_appr["data"]["decision"] == "approve"

        # Confirm no lingering 422 PROOF_BUNDLE_MISSING code anywhere in this path.
        if env_appr.get("error"):
            assert env_appr["error"]["code"] != "PROOF_BUNDLE_MISSING"

        # Verify bill status truly advanced in the live DB (not just the envelope).
        final_row = session.execute(
            text("SELECT status FROM bills WHERE id = :bid"), {"bid": bill_id}
        ).mappings().first()
        assert final_row["status"] == "approved"

    finally:
        _cleanup_bill(session, bill_id, vendor_id, workflow_id)
        session.close()


# ============================================================================
# NEGATIVE CASE 1 — Gate 1 config fail-closed (missing signing key), real E2E
# ============================================================================


def test_gate1_missing_key_fails_closed_e2e(monkeypatch):
    """With NO signing key configured, the REAL create_bill_intent() call path
    must leave bills.invoiceproof_bundle_id NULL, and the REAL approve_bill_intent()
    call must then return 422 PROOF_BUNDLE_MISSING — confirming Gate 1 fails
    closed for real, with no bundle_id ever hand-set.
    """
    from app.db import get_engine
    from app.integration.intents_router import (
        BillIntentIn,
        IntegrationApprovalIn,
        approve_bill_intent,
        create_bill_intent,
    )

    _set_auth(monkeypatch)
    # Deliberately withhold BOTH signing keys — Gate 1's documented fail-closed
    # invariant ("Key is required... gate raises before any DB write").
    monkeypatch.setenv("SWARMSYNC_SA_KEY", "")
    monkeypatch.setenv("VCAP_SHARED_SECRET", "")

    engine = get_engine()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    session = Session()

    bill_id: str | None = None
    vendor_id: str | None = None
    workflow_id: str | None = None

    try:
        tracker_id = uuid.uuid4()
        vendor_name = f"GATE1 WIRING NEG TEST VENDOR {uuid.uuid4()}"

        payload = BillIntentIn(
            gmail_tracker_id=tracker_id,
            vendor_name=vendor_name,
            amount=Decimal("999.00"),
            po_ref="PO-GATE1-WIRING-NEG-001",
            due_date=None,
            raw_extensions={"project_label": "Gate1 Wiring Negative Test"},
            gmail_invoiceproof=_clean_proof(),
            company_id=None,
        )

        resp_create = create_bill_intent(
            payload=payload,
            authorization=f"Bearer {_TOKEN}",
            session=session,
        )
        env_create = _envelope(resp_create)
        # create_bill_intent catches InvoiceProofGateFailed and still returns 201 —
        # the bill lands unverified, per the module's documented design (Fix 1).
        assert resp_create.status_code == 201, (
            f"expected 201 (bill created but unverified), got {resp_create.status_code}: "
            f"{env_create}"
        )
        bill_id = env_create["data"]["bill_id"]
        workflow_id = env_create["data"]["workflow_id"]
        vendor_id = env_create["data"]["vendor_id"]

        row = session.execute(
            text("SELECT status, invoiceproof_bundle_id FROM bills WHERE id = :bid"),
            {"bid": bill_id},
        ).mappings().first()
        assert row is not None
        assert row["invoiceproof_bundle_id"] is None, (
            "Gate 1 key-missing must leave invoiceproof_bundle_id NULL (fail closed)"
        )
        assert row["status"] == "drafted", (
            f"bill must stay 'drafted' (never 'verified') without a passing Gate 1, "
            f"got {row['status']!r}"
        )

        # No proof_bundles row at all is written on a key-missing failure (the key
        # check happens before any DB write — see invoice_proof_gate.py step 1).
        proof_count = session.execute(
            text("SELECT count(*) FROM proof_bundles WHERE payload->>'bill_id' = :bid"),
            {"bid": bill_id},
        ).scalar()
        assert proof_count == 0

        # --- Now attempt the REAL approval endpoint — must fail closed (422) ---
        approval_payload = IntegrationApprovalIn(
            decision="approve",
            source="email_detected",
            note=None,
            evidence_email_id="msg-gate1-wiring-neg-001",
        )
        resp_appr = approve_bill_intent(
            workflow_id=workflow_id,
            background_tasks=BackgroundTasks(),
            payload=approval_payload,
            authorization=f"Bearer {_TOKEN}",
            session=session,
        )
        env_appr = _envelope(resp_appr)
        assert resp_appr.status_code == 422, (
            f"approval of an unverified bill must be 422, got {resp_appr.status_code}: "
            f"{env_appr}"
        )
        assert env_appr["error"]["code"] == "PROOF_BUNDLE_MISSING", (
            f"expected PROOF_BUNDLE_MISSING, got {env_appr['error']['code']!r}"
        )

        # Bill status must remain untouched by the rejected approval attempt.
        final_row = session.execute(
            text("SELECT status FROM bills WHERE id = :bid"), {"bid": bill_id}
        ).mappings().first()
        assert final_row["status"] == "drafted"

    finally:
        _cleanup_bill(session, bill_id, vendor_id, workflow_id)
        session.close()


# ============================================================================
# NEGATIVE CASE 2 — Gate 1 evidence fail-closed, direct call to the real gate
# ============================================================================


def test_gate1_bad_evidence_fails_closed_direct_call(monkeypatch):
    """Prove the underlying gate function itself fails closed on bad evidence.

    Calls the REAL run_invoice_proof_gate1() (not mocked) against a REAL bill row
    in the live DB with an explicit ``passed: False`` evidence dict. This is a
    direct call rather than going through create_bill_intent()'s Pydantic
    GmailInvoiceProof schema, because (finding, see module docstring above) that
    schema currently strips the evidence down to snake_case keys that
    ``_evaluate_passed`` never inspects — so bad *evidence content* cannot
    currently reach the gate via the public /intents/bill endpoint. This test
    still exercises the real gate function end-to-end against the real DB, and
    confirms:

      1. InvoiceProofGateFailed is raised.
      2. A proof_bundles row IS written with passed=False (evidence trail).
      3. bills.invoiceproof_bundle_id stays NULL — the bill is never marked
         'verified' on failing evidence.
    """
    from app.db import get_engine
    from app.integration.invoice_proof_gate import InvoiceProofGateFailed, run_invoice_proof_gate1

    _set_signing_key(monkeypatch)

    engine = get_engine()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    session = Session()

    bill_id: str | None = None
    vendor_id: str | None = None
    company_id: str | None = None

    try:
        company_id = session.execute(text("SELECT id FROM companies LIMIT 1")).scalar_one()
        vendor_id = str(uuid.uuid4())
        session.execute(
            text(
                "INSERT INTO vendors (id, company_id, name, created_at, updated_at) "
                "VALUES (:id, :cid, :name, NOW(), NOW())"
            ),
            {"id": vendor_id, "cid": str(company_id), "name": f"GATE1 DIRECT TEST VENDOR {uuid.uuid4()}"},
        )
        bill_id = str(uuid.uuid4())
        session.execute(
            text(
                "INSERT INTO bills (id, company_id, vendor_id, amount, status, created_at, updated_at) "
                "VALUES (:id, :cid, :vid, 500.00, 'drafted', NOW(), NOW())"
            ),
            {"id": bill_id, "cid": str(company_id), "vid": vendor_id},
        )
        session.flush()

        bad_evidence = {
            "passed": False,
            "riskLevel": "CRITICAL",
            "final_decision": "flagged",
        }

        with pytest.raises(InvoiceProofGateFailed) as exc_info:
            run_invoice_proof_gate1(
                bill_id=bill_id,
                bill_amount=500.00,
                vendor_name="GATE1 DIRECT TEST VENDOR",
                gmail_invoiceproof=bad_evidence,
                db_session=session,
            )
        assert exc_info.value.reason.startswith("INVOICEPROOF_")
        session.commit()

        row = session.execute(
            text("SELECT status, invoiceproof_bundle_id FROM bills WHERE id = :bid"),
            {"bid": bill_id},
        ).mappings().first()
        assert row["invoiceproof_bundle_id"] is None, (
            "bad evidence must NOT populate invoiceproof_bundle_id"
        )
        assert row["status"] == "drafted"

        proof_row = session.execute(
            text(
                "SELECT passed FROM proof_bundles WHERE payload->>'bill_id' = :bid "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"bid": bill_id},
        ).mappings().first()
        assert proof_row is not None, "a failing proof_bundles row must still be written (evidence trail)"
        assert proof_row["passed"] is False

    finally:
        _cleanup_bill(session, bill_id, vendor_id, None)
        session.close()
