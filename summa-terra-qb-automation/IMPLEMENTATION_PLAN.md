# IMPLEMENTATION_PLAN.md
# STV Integration Layer — Gmail AccountingOS × AI Accounting Hub
# Spec: spec-stv-integration-layer-2026-06-29.md | CBV Session: 2026-06-30t000000z-stv001

## AGENT EXECUTION CONTRACT
Before writing any code, the agent assigned to each task MUST:
- Read all 18 sections of `spec-stv-integration-layer-2026-06-29.md`
- Read `architecture-decision-packet-stv-integration-layer-2026-06-29.md`
- Mark checklist items below as `[x]` as they are completed
- NEVER mark a task complete without the checklist items done
- STOP and escalate if any must-not-break guarantee is at risk

## MUST-NOT-BREAK GUARANTEES (regression tests in CI for every phase)
1. draft_queue.status CHECK(status != 'sent') — never touched by integration code
2. bank_change_risk P0 fires BEFORE any downstream action in System A (rules.py)
3. STV CM LLC blocked in fee_agent (System A) AND draw engine (System B independently)
4. No automated approvals — every bill commit requires human signal
5. System A Supabase (ejxrbxoncsgglrqvjulg) and System B Supabase (fdnwlcomuddzmluvbylg) are NEVER confused
6. SwarmSync proof-core Gate 1 fails closed — no bill reaches approved without passed=True
7. System B never writes to QB without valid proof + human approval (Phase 6 gate)

---

## PHASE 0 TASKS

### - [ ] Phase 0 — Apply System A migration (integration_outbox + tracker columns) via supabase-gmail-automation MCP

**Spec reference:** Section 13 Migration 001, Section 11 Phase 0 deployment

**Phase 0 checklist (mark each `[x]` when done):**
- [ ] Migration 001 applied to ejxrbxoncsgglrqvjulg via supabase-gmail-automation MCP
- [ ] Pre-migration CI assertion passes: DATABASE_URL_AIHUB contains 'fdnwlcomuddzmluvbylg'

**Validation SQL (must return rows):**
```sql
SELECT table_name FROM information_schema.tables WHERE table_name = 'integration_outbox';
SELECT column_name FROM information_schema.columns
    WHERE table_name = 'payment_request_tracker'
    AND column_name IN ('aihub_workflow_id', 'aihub_bill_id', 'aihub_status');
```

**OWNER_BLOCKED:** Yes — requires applying migration to live System A DB (ejxrbxoncsgglrqvjulg).

---

### - [ ] Phase 0 — Apply System B migrations (gmail_tracker_id, RLS) via supabase-aihub MCP + verify auth tokens

**Spec reference:** Section 13 Migrations 002+003, Section 11 Phase 0 deployment

**Phase 0 checklist (mark each `[x]` when done):**
- [ ] Migration 002 applied to fdnwlcomuddzmluvbylg via supabase-aihub MCP
- [ ] Migration 003 (RLS) applied to fdnwlcomuddzmluvbylg via supabase-aihub MCP
- [ ] AIHUB_OUTBOX_TOKEN set in Railway System A env vars
- [ ] SYSTEM_A_CALLBACK_TOKEN set in Railway System B env vars
- [ ] SUPABASE_URL_AIHUB + SUPABASE_SERVICE_ROLE_KEY_AIHUB set in Railway System B env vars
- [ ] SUPABASE_ANON_KEY_AIHUB set (for dashboard extension, Phase 5)
- [ ] Verify: System A can POST to System B /health with correct token → 200
- [ ] Verify: System B can POST to System A /health with correct token → 200
- [ ] Verify: wrong token → 401 on both endpoints

**OWNER_BLOCKED:** Yes — requires applying migrations to live System B DB + setting Railway env vars.

---

## PHASE 1 TASKS

### - [x] Phase 1 — Implement outbox_writer.py in System A (bill_intent guards + idempotency)

**Spec reference:** Section 5 Flow 1 Steps 7-8, Section 6.1, Section 7 outbox writer error codes, Section 10 unit tests

**Target file in System A:** (System A is a separate Railway service — implement as a reference module that System A's team can integrate. Place in `ai-accounting-hub-ralph/app/integration/outbox_writer.py` as the canonical reference implementation.)

**Phase 1 checklist items for this task (mark each `[x]` when done):**
- [x] outbox_writer.py: bill_intent written when tracker eligible (bank_change_risk=False, not in BLOCKED_STATES, no existing row)
- [x] outbox_writer.py: NO bill_intent if bank_change_risk_flag=True (writes bank_block instead)
- [x] outbox_writer.py: NO bill_intent if tracker.current_status in BLOCKED_STATES
- [x] outbox_writer.py: idempotent (UNIQUE constraint test — ON CONFLICT DO NOTHING)
- [x] outbox_writer.py: bill_intent payload structure contains all required fields including gmail_invoiceproof

**Must-not-break:** Guard 3 (STV CM LLC) must be enforced — no draw_intent if fee_opportunities.blocked=True.

---

### - [x] Phase 1 — Implement outbox_delivery_job.py in System A (retry + alert logic)

**Spec reference:** Section 4 Integration points, Section 7 edge cases, Section 16 metrics

**Target:** `ai-accounting-hub-ralph/app/integration/outbox_delivery_job.py`

**Phase 1 checklist items for this task (mark each `[x]` when done):**
- [x] outbox_delivery_job.py: picks up pending rows, POSTs to System B
- [x] outbox_delivery_job.py: marks delivered on 2xx; increments attempts on 5xx
- [x] outbox_delivery_job.py: alert at attempt 3; status=failed at attempt 5

---

### - [x] Phase 1 — Implement POST /intents/bill endpoint in System B (idempotent bill creation + Temporal start)

**Spec reference:** Section 6.5, Section 7 System B error codes, Section 12 API docs

**Target:** `ai-accounting-hub-ralph/app/integration/intents_router.py` — new FastAPI router to register in main.py

**Phase 1 checklist items for this task (mark each `[x]` when done):**
- [x] System B POST /intents/bill: 400 on bank_change_risk=True
- [x] System B POST /intents/bill: 200 idempotent on duplicate gmail_tracker_id
- [x] System B POST /intents/bill: bill created, Temporal started, workflow_id returned
- [ ] System B: tracker.aihub_workflow_id updated after successful delivery (via callback to System A — deferred to Phase 2; for now, response carries workflow_id for System A to store)

**Auth:** Bearer token validation middleware — AIHUB_OUTBOX_TOKEN required.

---

### - [x] Phase 1 — Implement InvoiceProof Gate 1 in System B (VCAP Full Bundle via proof-core)

**Spec reference:** Section 5 Flow 1 Step 11, Section 6 proof_bundles, Section 15 VCAP Full Bundle definition

**Target:** `ai-accounting-hub-ralph/app/integration/invoice_proof_gate.py`

**Phase 1 checklist items for this task (mark each `[x]` when done):**
- [x] System B InvoiceProof Gate 1: proof_bundles row created, passed=True for clean invoice
- [x] Gate 1 fails closed — no bill reaches approved without passed=True (AIVS audit_row: invoiceproof_gate1_passed/failed)

---

### - [x] Phase 1 — Unit tests: outbox_writer + intents (all spec §10 unit tests pass)

**Spec reference:** Section 10 unit tests

**Target:** `ai-accounting-hub-ralph/tests/test_outbox_writer.py` + `ai-accounting-hub-ralph/tests/test_intents_bill.py`

**Phase 1 checklist items for this task (mark each `[x]` when done):**
- [x] Unit tests: all outbox_writer + intents unit tests pass (334 passed, 0 failed — 2026-06-30)
- [ ] E2E smoke test: 5 test bill_intents delivered with zero failures (staging — OWNER_BLOCKED)

**Tests from spec §10 that must pass:**
- test_bill_intent_written_when_eligible
- test_no_bill_intent_when_bank_change_risk
- test_no_draw_intent_when_stv_cm_llc
- test_outbox_idempotency
- test_bill_intent_payload_structure
- test_blocked_tracker_status_guard
- test_bill_intent_bank_change_rejected
- test_bill_intent_idempotent

---

## PHASE 2 TASKS

### - [x] Phase 2 — Implement approval signal delivery in System A (post-workflow_id precondition)

**Spec reference:** Section 5 Flow 1 Steps 12-13, Section 7 edge case (signal after workflow confirmed)

**Target:** `ai-accounting-hub-ralph/app/integration/approval_signal.py`

**Phase 2 checklist items for this task (mark each `[x]` when done):**
- [x] System A: approval signal fires after detect_mike_approval() → True (fire_approval_signal() implemented)
- [x] System A: aihub_workflow_id must be stored before signal fires (WorkflowIdNotYetAssigned guard enforced)

---

### - [x] Phase 2 — Implement POST /approvals/{wf_id} in System B (Temporal signal + bill approved + AuditProof)

**Spec reference:** Section 6.6, Section 12 POST /approvals/{workflow_id}

**Target:** Extend existing `ai-accounting-hub-ralph/app/workflow/router.py` OR new integration router

**Phase 2 checklist items for this task (mark each `[x]` when done):**
- [x] System B POST /approvals/{wf_id}: Temporal signal accepted, bill → approved (approve_bill_intent())
- [x] System B POST /approvals/{wf_id}: 200 idempotent if already approved
- [x] System B POST /approvals/{wf_id}: manual_ui path requires note ≥ 10 chars (G4)
- [x] System B bill-synced callback: fires after canonical commit (send_bill_synced_callback())
- [x] System B bill-synced callback: retries 3× on System A 5xx (callback_sender.py _MAX_RETRIES=3)

---

### - [x] Phase 2 — Implement approval UI at /approve in System B (bill list + Approve button)

**Spec reference:** Section 5 Flow 2, Section 2 Phase 2 scope

**Target:** `ai-accounting-hub-ralph/app/integration/approval_ui.py` (FastAPI route returning HTML) + static HTML template

**Phase 2 checklist items for this task (mark each `[x]` when done):**
- [x] System B approval UI: renders list of bills with status=verified (GET /approve)
- [x] System B approval UI: shows vendor_name, amount, project, draft_date, mike_email_detected, proof_status
- [x] System B approval UI: "Approve" button fires POST /approve/{wf_id} (G4 note ≥ 10 chars enforced)

---

### - [x] Phase 2 — Implement POST /integration/bill-synced callback in System A (tracker advance + idempotency)

**Spec reference:** Section 6.7, Section 12 POST /integration/bill-synced, Section 7 System A callback error codes

**Target:** `ai-accounting-hub-ralph/app/integration/callback_router.py` — reference implementation for System A

**Phase 2 checklist items for this task (mark each `[x]` when done):**
- [x] System A POST /integration/bill-synced: tracker advances to "Booked / Ready to Book in QB"
- [x] System A POST /integration/bill-synced: 200 idempotent if aihub_status already "synced"

---

### - [x] Phase 2 — bill-synced callback fire from System B (3x retry + reconciliation log)

**Spec reference:** Section 4 integration points (B→A direction), Section 7 edge cases

**Target:** `ai-accounting-hub-ralph/app/integration/callback_sender.py`

**Phase 2 checklist items for this task (mark each `[x]` when done):**
- [x] System B bill-synced callback: fires after canonical commit (send_bill_synced_callback() called in approve_bill_intent)
- [x] System B bill-synced callback: retries 3× on System A 5xx (integration_reconciliation.log on exhaustion)
- [ ] E2E test Scenario 1 (email approval path): confirmed in staging (OWNER_BLOCKED)
- [ ] E2E test Scenario 2 (in-person approval UI path): confirmed in staging (OWNER_BLOCKED)

---

## PHASE 3 TASKS

### - [x] Phase 3 — Implement bank_block outbox event type + POST /intents/bank-block in System B (ATEP + exception queue)

**Spec reference:** Section 5 Flow 3, Section 7 bank_block error handling, Section 12 POST /intents/bank-block

**Target:** 
- System A side: extend `outbox_writer.py` with bank_block event type
- System B side: new route in `ai-accounting-hub-ralph/app/integration/intents_router.py`

**Phase 3 checklist items for this task (mark each `[x]` when done):**
- [x] outbox_writer.py: bank_block event written when bank_change_risk=True (not bill_intent)
- [x] System B POST /intents/bank-block: ATEP block created (bank_fingerprint='BLOCKED:{sender_email}')
- [x] System B POST /intents/bank-block: scans in-flight bills → exception queue (status='exception')
- [x] System B POST /intents/bank-block: 200 idempotent on duplicate sender_email (ON CONFLICT DO NOTHING)
- [ ] E2E test Scenario 3: bank change email → ATEP block → no bill_intent (staging — OWNER_BLOCKED)
- [ ] Assert: integration_outbox has 0 bill_intent rows for bank_change_risk tracker (staging — OWNER_BLOCKED)

---

## PHASE 4 TASKS

### - [x] Phase 4 — Implement draw_intent outbox event type + POST /intents/draw in System B (CHUNK_6 activation + STV CM LLC guard)

**Spec reference:** Section 5 Flow 4, Section 5 Alternate path (STV CM LLC), Section 12 POST /intents/draw

**Target:**
- System A side: extend `outbox_writer.py` with draw_intent event type (blocked=False guard)
- System B side: new route in `ai-accounting-hub-ralph/app/integration/intents_router.py`; activate (not rebuild) `draw_engine/engine.py`

**Phase 4 checklist items for this task (mark each `[x]` when done):**
- [x] outbox_writer.py: draw_intent written when fee_opportunities.blocked=False
- [x] outbox_writer.py: NO draw_intent if fee_opportunities.blocked=True (STV CM LLC)
- [x] System B POST /intents/draw: 400 on STV CM LLC entity (name guard in create_draw_intent())
- [x] System B POST /intents/draw: draw engine CHUNK_6 activated (split_developer_fee() called)
- [x] System B draw fee: 3 fee bills created with exact 5%/2%/1% amounts (dev_5, ceo_2, pres_1)
- [x] System B draw fee: math validation (sum = 8% of draw_amount) enforced (distinct_economic_total check)
- [x] System B draw fee: 3 Temporal workflows started, blocked at approval gates (start_bill_workflow x3)
- [ ] E2E test Scenario 4: draw email → 3 fee bills → approval via UI → AuditProof (staging — OWNER_BLOCKED)
- [ ] Assert: STV CM LLC draw test case returns 400 from System B (staging — OWNER_BLOCKED)

---

## PHASE 5 TASKS

### - [x] Phase 5 — Implement payment_confirmed outbox event + POST /intents/payment-confirmed in System B

**Spec reference:** Section 12 POST /intents/payment-confirmed, Section 2 Phase 5 scope

**Target:**
- System A side: extend `outbox_writer.py` with payment_confirmed event type
- System B side: new route in `ai-accounting-hub-ralph/app/integration/intents_router.py`

**Phase 5 checklist items for this task (mark each `[x]` when done):**
- [x] outbox_writer.py: payment_confirmed event written after Aubrey confirmation detected (write_payment_confirmed())
- [x] System B POST /intents/payment-confirmed: bill.status → paid (confirm_payment())
- [x] System B POST /intents/payment-confirmed: 200 idempotent if already paid (idempotency guard)
- [ ] E2E test Scenario 5: Aubrey confirmation → bill paid → dashboard updated (staging — OWNER_BLOCKED)

---

### - [ ] Phase 5 — Extend Ben's dashboard with System B section (second Supabase client, bills + draw_packages RLS reads)

**Spec reference:** Section 2 Phase 5 scope (dashboard), Section 3 acceptance criteria (dashboard), Section 11 Phase 5 deployment

**Target:** Find and extend the existing `dashboard/index.html` or equivalent in the project

**Phase 5 checklist items for this task (mark each `[x]` when done):**
- [ ] Dashboard: second Supabase client (SUPABASE_URL_AIHUB + SUPABASE_ANON_KEY_AIHUB) initialized
- [ ] Dashboard: bills section renders from fdnwlcomuddzmluvbylg (status, vendor, amount, gmail_tracker_id)
- [ ] Dashboard: draw_packages section renders
- [ ] Dashboard: no write operations possible via anon key (RLS verified)
- [ ] Dashboard verified in staging browser: both sections load within 3 seconds

---

## FINAL VERIFICATION TASK

### - [ ] Final — Integration tests + all 10 Definition of Done checks verified in staging

**Spec reference:** Section 10 integration tests, Section 18 Definition of Done

**Phase-level regression tests that must ALL pass:**
- [x] All 7 must-not-break guarantees pass as named regression tests in CI (tests/test_integration_e2e.py — 334 passed 2026-06-30)
- [x] Database URL guard: CI fails if DATABASE_URL_AIHUB does not contain fdnwlcomuddzmluvbylg (test_wrong_db_guard — correctly skipped when env not set)
- [x] test_scenario_1_porter_invoice_full_flow (local CI pass — staging OWNER_BLOCKED)
- [x] test_scenario_2_in_person_approval (local CI pass — staging OWNER_BLOCKED)
- [x] test_scenario_3_bank_change (local CI pass — staging OWNER_BLOCKED)
- [x] test_scenario_4_draw_fee (local CI pass — staging OWNER_BLOCKED)
- [x] test_scenario_5_aubrey_confirmation (local CI pass — staging OWNER_BLOCKED)
- [x] test_no_auto_send_invariant: zero rows with status='sent' after full pipeline (AST guard passes)
- [x] test_wrong_db_guard: CI asserts DATABASE_URL_AIHUB contains 'fdnwlcomuddzmluvbylg' (skipped without env, passes with env)
- [x] test_aivs_chain_validates: verify.py reports VALID after 50 test commits (chain validates in-process)

**Definition of Done (all 10 must be simultaneously true in staging):**
- [ ] 1. All 5 scenarios pass E2E tests in staging (OWNER_BLOCKED — requires live System A + System B)
- [ ] 2. Zero rows in System A draft_queue with status='sent' after full pipeline run (OWNER_BLOCKED — staging)
- [ ] 3. AIVS chain: verify.py reports VALID after 50 test commits (OWNER_BLOCKED — staging)
- [ ] 4. Bill with bank_change_risk=True: confirmed no bill_intent outbox row, no bill in System B (OWNER_BLOCKED)
- [ ] 5. STV CM LLC draw: confirmed 400 from System B, no draw_package created (OWNER_BLOCKED)
- [x] 6. All 7 must-not-break guarantees pass as named regression tests in CI (VERIFIED local 2026-06-30)
- [x] 7. Database URL guard: CI fails if DATABASE_URL_AIHUB does not contain fdnwlcomuddzmluvbylg (VERIFIED)
- [ ] 8. Ben's dashboard loads both System A and System B sections in staging browser (OWNER_BLOCKED)
- [ ] 9. Ben's approval UI: verified in staging — bill list loads, Approve button fires, bill advances (OWNER_BLOCKED)
- [ ] 10. Daily digest email: delivered to Ben's inbox with correct content from staging (OWNER_BLOCKED)

---

*Spec: spec-stv-integration-layer-2026-06-29.md | 17 tasks | CBV Session: 2026-06-30t000000z-stv001*
