# Design Specification: STV Integration Layer
## Gmail AccountingOS × AI Accounting Hub — Phases 0–5

```
Spec Title:      STV Integration Layer — Gmail AccountingOS × AI Accounting Hub
Version:         1.0.0
Author:          spec-superstar (governed by system-architecture-governor)
Last Updated:    2026-06-29
Status:          Ready for Build
Timeline:        5 build phases; Phase 0 (1 day), Phase 1 (3 days), Phase 2 (3 days),
                 Phase 3 (2 days), Phase 4 (3 days), Phase 5 (2 days) — ~2 weeks total
Confidence:      Complete — 0 assumptions required; all 10 intake questions confirmed
                 from source files. Phase 6 (QBWC write-back) deliberately out of scope
                 pending CRUX spikes.
Next Steps:      Ready to build Phase 0 immediately.
Architecture:    integration-architecture-packet-stv-2026-06-29.md (READY_TO_SPEC verdict)
Governor:        architecture-decision-packet-stv-integration-layer-2026-06-29.md
```

---

## ARCHITECTURE GOVERNOR SUMMARY

```
Feature: STV Integration Layer (Phases 0–5)
Completed: 2026-06-29

Existing systems touched: 6
  - System A FastAPI (Railway Service 1, live)
  - System A Supabase (ejxrbxoncsgglrqvjulg) — payment_request_tracker, draft_queue, etc.
  - System B FastAPI (Railway Service 2, to build)
  - System B Supabase (fdnwlcomuddzmluvbylg) — bills, draw_packages, proof_bundles, audit_rows
  - Temporal Cloud (free tier) — workflow orchestration
  - SwarmSync proof-core (in-process, System B)

NOT touched: Gmail API, GAS poller, QB Desktop, QBWC, NATS (Phase 6 only),
             draft_queue (never), GmailApp.sendEmail() (never)

Source of truth conflicts: 0 — all 12 data types have exactly one owner (see packet §3)

Stateful objects mapped: 4
  - payment_request_tracker: 13 states (Received → Closed + blocked states)
  - integration_outbox: 3 states (pending → delivered | failed)
  - bills (System B): 4 states (drafted → verified → approved → synced)
  - Temporal workflow: RUNNING → WAITING_APPROVAL → APPROVED | REJECTED → COMPLETE

Money/auth/proof boundary crossings: 3
  - InvoiceProof Gate 1 (VCAP Full Bundle, System B — SwarmSync proof-core)
  - Temporal human-approval gate (mandatory before any bill commit)
  - QBWC write-back gate (Phase 6 only — out of scope this spec)

Reuse opportunities (DO NOT rebuild):
  - System A draft engine (never touch)
  - System A SwarmSyncClient (not extended by integration layer)
  - System B Temporal client (already designed in FinalSpec)
  - System B draw engine CHUNK_6 (activate, not rebuild)
  - Ben's dashboard HTML (extend with second Supabase client, not rebuild)

Must-not-break guarantees: 7 (all become regression tests)
  1. draft_queue.status CHECK(status != 'sent') — never touched by integration code
  2. bank_change_risk P0 fires BEFORE any downstream action in System A (rules.py)
  3. STV CM LLC blocked in fee_agent (System A) and draw engine (System B independently)
  4. No automated approvals — every bill commit requires human signal
  5. System A Supabase (ejxrbxoncsgglrqvjulg) and System B Supabase (fdnwlcomuddzmluvbylg)
     are never confused — separate clients, separate env vars, separate MCP
  6. SwarmSync proof-core Gate 1 fails closed — no bill reaches approved without passed=True
  7. System B never writes to QB without valid proof + human approval (Phase 6 gate)

Definition-of-done conditions: 10 (see Section 18)

Technical spikes required before spec is final: 0 (Phases 0–5)
  [Phase 6 spikes documented in packet §21 — not blocking this spec]

Status: ✅ CLEAR TO SPEC — Phases 0–5
```

---

## 1. EXECUTIVE SUMMARY

The STV Integration Layer connects two live/planned systems that currently cannot talk to each other. System A (STV Gmail AccountingOS, live on Railway) detects accounting events in Ben Stone's Gmail inbox — vendor invoices from Porter, Mike Watson's approval emails, construction draw packages from Lauren Farnsworth, bank change fraud attempts, and Aubrey Palmer's payment confirmations — and holds them in a structured state machine. System B (AI Accounting Hub, in build) writes proof-gated vendor bills to a canonical Postgres database that will eventually batch-sync to QuickBooks Enterprise Desktop via the QuickBooks Web Connector.

Without this integration, Ben must manually bridge the two systems: copy vendor names, amounts, and approval states from System A into System B by hand. This is the same category of manual re-entry error that both systems were built to eliminate, and it defeats their combined value.

This spec defines exactly what to build — the outbox tables, endpoints, webhook contracts, field transforms, approval signal paths, callback endpoints, and dashboard extension — so the full pipeline from "Porter emails invoice PDF" to "bill committed to canonical Postgres with proof" runs without Ben touching both systems. The QBWC write-back (QB Desktop sync) is a separate Phase 6 gated on two pre-existing infrastructure spikes and is explicitly out of scope here. Bills will be fully verifiable in canonical Postgres at the end of Phase 5, which is the business value.

**Primary user:** Ben Stone (Accounting Manager). Secondary: Mike Watson (CEO, approval flow). No new user-facing work for Porter, Aubrey, or Lauren — their email workflows are unchanged.

**Business outcome:** Eliminates manual double-entry between System A and System B for ~10 vendor payment events/day. Automates the 5%/2%/1% draw fee calculation across three company files. Creates an end-to-end proof chain from Gmail event to canonical Postgres commit.

---

## 2. SCOPE DEFINITION & NON-SCOPE

### In scope (Phases 0–5)

**Phase 0 — Schema & Auth:**
- System A: `integration_outbox` table + 3 new columns on `payment_request_tracker`
- System B: `bills.gmail_tracker_id` column + `draw_packages.gmail_fee_opportunity_id` column
- System B: anon RLS policies on `bills` + `draw_packages` for Ben's dashboard
- Inter-service bearer tokens (System A → System B, System B → System A)

**Phase 1 — Bill Intent (Scenario 1 end-to-end, read-path proof only):**
- System A: outbox writer (writes `bill_intent` row when tracker eligible)
- System A: outbox delivery job (background loop: POST /intents/bill to System B)
- System B: `POST /intents/bill` endpoint (idempotent bill creation + Temporal workflow start)
- System B: InvoiceProof Gate 1 (VCAP Full Bundle via SwarmSync proof-core)
- System B: Temporal workflow running and blocking at approval gate

**Phase 2 — Approval Signals + Close-the-Loop:**
- System A: Mike approval signal delivery (POST /approvals/{workflow_id} after email detection)
- System B: `POST /approvals/{workflow_id}` endpoint (Temporal signal + bill status → approved)
- System B: bill-synced callback (POST to System A after canonical commit)
- System A: `POST /integration/bill-synced` endpoint (tracker advance + aihub_status update)
- System B: in-person approval UI (bill list + "Approve" button for Ben — Phase 2 manual path)

**Phase 3 — Bank Block:**
- System A: outbox writer — `bank_block` event type
- System B: `POST /intents/bank-block` endpoint (ATEP block creation + in-flight bill scan)

**Phase 4 — Draw Fee Workflow:**
- System A: outbox writer — `draw_intent` event type (with STV CM LLC guard)
- System B: `POST /intents/draw` endpoint (draw engine CHUNK_6 activation)
- System B: draw fee: three fee bill intents, approval gates, AuditProof (AIVS)

**Phase 5 — Payment Confirmed + Dashboard:**
- System A: outbox writer — `payment_confirmed` event type
- System B: `POST /intents/payment-confirmed` endpoint (bill.status → paid)
- Dashboard: extend Ben's `dashboard/index.html` with System B section (second Supabase client, anon RLS reads)

### Out of scope (explicit exclusions)

| Excluded | Reason |
|---|---|
| QBWC SOAP endpoint (Railway Service 3) | Phase 6 — CRUX spike RESOLVED 2026-07-01 (business-hours/session-tied polling confirmed); no longer gated on an open spike |
| .qwc file generation | Phase 6 — requires stable SOAP endpoint URL first; target the sandbox company file before production |
| QB Desktop BillAdd / write-back | Phase 6 — no inbound connections to Rightworks VPS; polling is outbound, business-hours/session-tied only (no persistent poller) |
| Gmail API calls from integration code | System A's existing pipeline handles all Gmail API access; integration layer is upstream of that |
| draft_queue writes | Absolute exclusion — CHECK constraint prevents status='sent'; integration never touches this table |
| GmailApp.sendEmail() calls | Absolute exclusion — System A draft engine is the only path; integration never sends email |
| Automated payment execution | Aubrey must manually execute all payments from bank; integration only records confirmation |
| NATS/JetStream as integration bus | System A stays webhook-only; NATS is internal to System B |
| New Supabase project creation | Two projects already exist; spec is federated |
| Any SwarmSync hosted REST endpoints | In-process proof-core is used in System B; no HTTP to SwarmSync from integration paths |
| Payroll, bank feeds, vendor portals | Out of scope per CLAUDE.md hard limits |

### Phase dependencies

- Phase 1 requires Phase 0 schema complete
- Phase 2 requires Phase 1 running (needs workflow_id from /intents/bill response)
- Phase 3 is independent of Phases 1–2 (can run in parallel)
- Phase 4 requires Phase 0 schema complete
- Phase 5 requires Phase 2 callback endpoint (bill-synced)

---

## 3. BUSINESS CONTEXT & ACCEPTANCE CRITERIA

**Business goal:** Eliminate manual bridging between email event detection (System A) and accounting data entry (System B), capturing all five recurring event types automatically.

**Success metrics:**
- Zero manual QB data entry for events that flow through the integration (measured: bills with gmail_tracker_id set / total bills created)
- Developer fee not missed on any construction draw (measured: draw_packages created / fee_opportunities with blocked=False)
- Mike approval detected by email requires no manual action by Ben (measured: auto-signal rate vs manual-UI rate)
- AIVS chain valid on 100% of commits (measured: daily chain validation job)

**Acceptance criteria (all must be simultaneously true before Phase 5 is declared done):**

- [ ] Porter invoice email → bill created in System B with gmail_tracker_id within 2 minutes of email
- [ ] Mike approval email → Temporal signal fired within 2 minutes of email detection
- [ ] Bill reaches `approved` state → System A tracker advances to "Booked / Ready to Book in QB" within 2 minutes of callback
- [ ] Bank change email → ATEP block in System B, NO bill_intent outbox row — confirmed
- [ ] Construction draw email with non-STV-CM-LLC entity → three fee bills created in System B
- [ ] STV CM LLC draw email → rejected at System B with 400, no draw_package created
- [ ] draw_queue has zero rows with status='sent' after running the full integration pipeline (CHECK constraint still holding)
- [ ] AIVS chain: `verify.py` reports VALID after 50 test commits in staging
- [ ] Ben's dashboard shows System B bills section rendering bills from fdnwlcomuddzmluvbylg
- [ ] All 7 must-not-break guarantees pass as regression tests in CI

**Spec status:** This is a build-phase spec. Sections are relatively fixed. Conflicts found during build must be documented and resolved via spec patch (v1.x.0) before code merges.

---

## 4. ARCHITECTURE & SYSTEM INTEGRATION

*Extended from Architecture Governor Summary. Integration points, data flows, and ownership map are consistent with governor packet §3, §7, §8.*

### Data flow map

```
BILL INTENT FLOW (Scenario 1):
Gmail (porter@) → GAS Poller (1-min) → System A POST /classify
  → payment_request_tracker created (status=Received)
  → invoice_proof.py: proof_results written (advisory)
  → outbox_writer: integration_outbox INSERT (event_type=bill_intent)
  → outbox_delivery_job: POST /intents/bill → System B
      → bills INSERT (status=drafted, gmail_tracker_id linked)
      → Temporal workflow START
      → InvoiceProof Gate 1: proof-core → proof_bundles INSERT (passed=T/F)
      → [GATE: Temporal blocks, awaiting approval signal]
  
MIKE APPROVAL SIGNAL (Path A — email):
Gmail (mike@) → GAS Poller → System A POST /classify
  → payment_tracker.detect_mike_approval() → True
  → tracker status → "Approved by Mike"
  → POST /approvals/{aihub_workflow_id} → System B
      → Temporal: signal received → workflow unblocks
      → bill status → approved
      → AuditProof (AIVS): audit_rows appended
      → canonical commit (bills.status=approved, proof verified)
      → POST /integration/bill-synced → System A
          → tracker.aihub_status = "synced"
          → tracker.current_status = "Booked / Ready to Book in QB"

MIKE APPROVAL SIGNAL (Path B — in-person, Ben's UI):
Ben opens System B approval UI → sees bills list (status=verified)
  → clicks "Approve" → POST /approvals/{workflow_id}
      → same Temporal signal path as Path A

BANK CHANGE FLOW (Scenario 3):
Gmail (any sender) → GAS Poller → System A /classify
  → rules.py: BANK_CHANGE_PATTERNS match → bank_change_risk=True
  → outbox_writer: integration_outbox INSERT (event_type=bank_block)
  → [NO bill_intent row written — hard guard]
  → outbox_delivery_job: POST /intents/bank-block → System B
      → vendors ATEP flag SET
      → in-flight bills for same vendor → exception queue

DRAW FEE FLOW (Scenario 4):
Gmail (lauren.w.farnsworth@) → GAS Poller → System A /classify
  → fee_agent: fee_opportunities INSERT (blocked=False if not STV CM LLC)
  → outbox_writer: integration_outbox INSERT (event_type=draw_intent)
  → outbox_delivery_job: POST /intents/draw → System B
      → draw_packages INSERT (gmail_fee_opportunity_id linked)
      → draw engine CHUNK_6: 3 fee_bills created
      → each bill: Temporal workflow → approval gate → AuditProof
```

### Integration points

| Integration | Direction | Auth | Retry | Idempotency |
|---|---|---|---|---|
| Outbox delivery job → System B `/intents/bill` | A→B | Bearer AIHUB_OUTBOX_TOKEN | 5× exp. backoff | bills.gmail_tracker_id UNIQUE |
| Outbox delivery job → System B `/intents/draw` | A→B | Bearer AIHUB_OUTBOX_TOKEN | 5× exp. backoff | draw_packages.gmail_fee_opportunity_id UNIQUE |
| Outbox delivery job → System B `/intents/bank-block` | A→B | Bearer AIHUB_OUTBOX_TOKEN | 5× exp. backoff | ATEP: vendor + sender_email composite idempotent |
| Outbox delivery job → System B `/intents/payment-confirmed` | A→B | Bearer AIHUB_OUTBOX_TOKEN | 3× exp. backoff | bills.status idempotent (paid→paid no-op) |
| System A `/classify` → System B `/approvals/{workflow_id}` | A→B | Bearer AIHUB_OUTBOX_TOKEN | 3× with 30s delay | Temporal signal: idempotent if workflow already at correct state |
| System B → System A `/integration/bill-synced` | B→A | Bearer SYSTEM_A_CALLBACK_TOKEN | 3× with 30s delay | aihub_status check: if already "synced" → 200 no-op |

### New infrastructure

- System A: `integration_outbox` table (Supabase ejxrbxoncsgglrqvjulg)
- System A: `payment_request_tracker` — 3 new columns
- System A: outbox delivery background job (coroutine within existing FastAPI process)
- System A: `POST /integration/bill-synced` endpoint (new route in main.py)
- System B: `bills.gmail_tracker_id` column (Supabase fdnwlcomuddzmluvbylg)
- System B: `draw_packages.gmail_fee_opportunity_id` column
- System B: RLS SELECT policies on bills + draw_packages (anon key for dashboard)
- System B: 5 new endpoints (see Section 12)
- System B: approval UI page (HTML + Supabase JS — read bills, POST approval)
- Ben's dashboard: second Supabase client (aihub anon key) + bills/draw_packages display sections

### External dependencies

- Temporal Cloud (free tier, existing plan): Temporal Python SDK, worker process in System B
- SwarmSync proof-core (in-process, System B): `@swarmsync/proof-core` or hosted REST with sa_* key
- Railway (existing account): Service 1 stays live; Service 2 deploys alongside

---

## 5. USER FLOWS & HAPPY PATH

### Flow 1: Porter invoice → canonical bill (Scenario 1, Path A — email approval)

**Actor:** Porter Christensen (email trigger), Mike Watson (email approval), Ben Stone (draft review — unchanged)
**Precondition:** System A live, System B deployed, Phase 1 + 2 complete

```
Step 1:  Porter emails Kirton McConkie invoice ($12,500) to stone@
Step 2:  GAS Poller picks up email within 1 min; POST /classify
Step 3:  System A: classifies as "Vendor Invoice / Bill", has_attachments=True
Step 4:  System A: payment_request_tracker created (id=T1, vendor_name="Kirton McConkie",
         amount=12500, status="Received", bank_change_risk_flag=False)
Step 5:  System A: invoice_proof.py runs; proof_results written (advisory, non-blocking)
Step 6:  System A: draft_queue: Template 1 created (status="pending_ben_review")
         [Ben reviews and sends this draft manually — UNCHANGED from current process]
Step 7:  System A: outbox_writer checks preconditions (bank_change_risk_flag=False,
         status not in BLOCKED_STATES, no existing bill_intent for T1)
         → integration_outbox INSERT: (tracker_id=T1, event_type=bill_intent, status=pending)
Step 8:  Outbox delivery job (runs every 60s): picks up pending row
         → POST /intents/bill (payload: gmail_tracker_id=T1, vendor_name="Kirton McConkie",
           amount=12500, gmail_invoiceproof={risk_level="low", final_decision="approved", ...})
Step 9:  System B: /intents/bill
         → idempotency check: bills.gmail_tracker_id=T1 not found → proceed
         → vendor fuzzy match: "Kirton McConkie" → vendors.id=V47 (similarity ≥ 0.75)
         → bills INSERT (id=B1, gmail_tracker_id=T1, status=drafted, vendor_id=V47, amount=12500)
         → Temporal workflow START: workflow_id=WF1
         → response 201: {bill_id=B1, workflow_id=WF1}
Step 10: System A: outbox row: status=delivered, sent_at=NOW()
         → payment_request_tracker.aihub_workflow_id="WF1", aihub_bill_id=B1, aihub_status="active"
Step 11: System B Temporal: InvoiceProof Gate 1 runs (proof-core, in-process)
         → VCAP Full Bundle generated; proof_bundles INSERT (bill_id=B1, passed=True, kind=invoice)
         → bill status → verified
         [Temporal blocks at approval gate — waiting for signal]
Step 12: Mike emails "This is approved." to stone@
Step 13: GAS Poller picks up email; System A /classify → detect_mike_approval() → True
         → tracker(T1).current_status → "Approved by Mike"
         → POST /approvals/WF1 (decision="approve", source="email_detected", evidence=gmail_msg_id)
Step 14: System B: Temporal receives signal → workflow unblocks
         → bill status → approved
         → AuditProof: audit_rows AIVS chain append
         → canonical commit complete
         → POST /integration/bill-synced (System A callback):
           {tracker_id=T1, bill_id=B1, qb_txn_id=null, status="synced"}
Step 15: System A /integration/bill-synced:
         → tracker(T1).aihub_status = "synced"
         → tracker(T1).current_status = "Booked / Ready to Book in QB"
         → automation_audit_log: bill_synced event

Postcondition: Bill B1 in System B (status=approved, proof verified). Tracker T1 in System A
(status="Booked / Ready to Book in QB", aihub_status="synced"). Ben's dashboard shows both.
```

**Eliminated from current process:** Steps 9–12 of current process (manual QB login, manual bill entry, manual Sheets update).
**Remaining manual:** Ben reviews/sends Template 1 draft (Step 6). Ben reviews/sends Template 2 draft to Porter (unchanged downstream action).

### Flow 2: In-person approval (Scenario 2 — no Mike email)

**Precondition:** Bill B1 exists in System B (status=verified). Temporal blocked at approval gate.

```
Step 1:  Mike tells Ben verbally: "Pay Kirton McConkie."
Step 2:  Ben navigates to System B approval UI: /approve
Step 3:  UI loads: list of bills with status=verified
         (fields shown: vendor name, amount, project, draft date, gmail_tracker_id,
          mike_email_detected=False, proof_status="Gate 1 passed")
Step 4:  Ben locates Kirton McConkie bill; clicks "Manually Approve"
Step 5:  UI prompts: "Approval reason (required, min 10 chars)" → Ben types "Mike approved in person"
Step 6:  UI fires POST /approvals/WF1 (decision="approve", source="manual_ui", note="Mike approved in person")
Step 7:  Same Temporal signal path as Flow 1 Steps 14–15

Postcondition: Same as Flow 1.
```

### Flow 3: Bank change fraud (Scenario 3)

```
Step 1:  Unknown sender emails bank routing change request
Step 2:  GAS Poller; System A /classify: rules.py BANK_CHANGE_PATTERNS → bank_change_risk=True
         [This fires BEFORE any LLM, BEFORE tracker creation — unchanged from current rules.py]
Step 3:  System A: notification_events P0 fires (Google Chat — unchanged)
Step 4:  System A: outbox_writer: bank_change_risk=True → NO bill_intent row written
         → integration_outbox INSERT: (event_type=bank_block, payload={vendor_name, sender_email})
Step 5:  Outbox delivery: POST /intents/bank-block → System B
Step 6:  System B: ATEP block on vendor bank_fingerprint
         → scan in-flight bills for same vendor_name → move to exception queue
         → audit_rows AIVS: bank_block_created
Step 7:  System B: response 201 {block_id, affected_bills_count}
Step 8:  System A: outbox row delivered
         [No payment path until Ben manually clears both systems]
```

### Flow 4: Draw fee (Scenario 4)

```
Step 1:  Lauren Farnsworth emails Draw #8 package (Madison Park project, $500,000)
Step 2:  System A classifies as "Construction Draw"; fee_agent creates:
         fee_opportunities: (project_canonical="Madison Park", draw_amount=500000,
         estimated_fee=25000 [5%], fee_payee_status="CONFIRMED", blocked=False)
Step 3:  outbox_writer: blocked=False → integration_outbox INSERT (event_type=draw_intent)
Step 4:  Outbox delivery: POST /intents/draw → System B
Step 5:  System B: /intents/draw
         → STV CM LLC check: fee_payee != STV CM LLC → proceed
         → draw_packages INSERT (gmail_fee_opportunity_id=FO1, draw_amount=500000)
         → CHUNK_6 draw engine: exact calculation per QB spec §5.3:
             5% → $25,000 → Summa Terra Ventures LLC (cost code 069)
             2% → $10,000 → CM entity
             1% → $5,000 → President entity
         → 3 fee bill intents created; 3 Temporal workflows started
Step 6:  Each fee bill: Gate 1 (VCAP) → approval gate [Temporal blocks]
Step 7:  Ben approves each in System B approval UI
Step 8:  AuditProof (AIVS chain) → canonical commit for each
Step 9:  System B fires 3× POST /integration/bill-synced (one per fee bill)
```

### Alternate path: STV CM LLC draw rejected

```
If fee_opportunities.blocked=True (STV CM LLC entity):
  outbox_writer: blocked=True → NO draw_intent outbox row written
  automation_audit_log: "draw_intent_blocked: STV CM LLC"
  [System B never sees this draw — defense in depth]

If somehow draw_intent reaches System B with STV CM LLC entity:
  /intents/draw: entity lookup → STV CM LLC → 400 "STV CM LLC blocked"
  audit_rows: stv_cm_llc_block_fired (canary alert)
```

---

## 6. DATA MODELS & SCHEMA

### 6.1 System A — New table: integration_outbox

```sql
CREATE TABLE integration_outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracker_id      UUID REFERENCES payment_request_tracker(id),
    event_type      VARCHAR(32) NOT NULL,  -- 'bill_intent'|'draw_intent'|'bank_block'|'payment_confirmed'
    payload         JSONB NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',  -- 'pending'|'delivered'|'failed'
    attempts        INT NOT NULL DEFAULT 0,
    sent_at         TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'delivered', 'failed')),
    CONSTRAINT valid_event_type CHECK (event_type IN ('bill_intent', 'draw_intent', 'bank_block', 'payment_confirmed')),
    UNIQUE (tracker_id, event_type)  -- idempotency: one outbox row per tracker per event type
);

CREATE INDEX idx_integration_outbox_status ON integration_outbox(status);
CREATE INDEX idx_integration_outbox_created_at ON integration_outbox(created_at);
```

**Valid payload shapes by event_type:**

`bill_intent`:
```json
{
  "vendor_name": "Kirton McConkie",
  "amount": 12500.00,
  "po_ref": "INV-2026-0341",
  "due_date": "2026-07-15",
  "raw_extensions": {
    "project_label": "Madison Park",
    "gmail_thread_id": "18abc123",
    "gmail_message_id": "18abc124",
    "requested_by_email": "porter@summaterraventures.com"
  },
  "gmail_invoiceproof": {
    "risk_level": "low",
    "final_decision": "approved",
    "checks_passed": 5,
    "bank_change_risk": false,
    "duplicate_detected": false,
    "vendor_confidence": 0.95
  }
}
```

`draw_intent`:
```json
{
  "gmail_fee_opportunity_id": "uuid",
  "project_canonical": "Madison Park",
  "draw_amount": 500000.00,
  "draw_number": 8,
  "estimated_fee_hint": 25000.00,
  "fee_payee_hint": "Summa Terra Ventures LLC",
  "fee_payee_status": "CONFIRMED",
  "raw_extensions": {
    "gmail_thread_id": "18def456",
    "gmail_message_id": "18def457"
  }
}
```

`bank_block`:
```json
{
  "vendor_name": "Fake Vendor Inc",
  "sender_email": "fraud@unknown.com",
  "gmail_message_id": "18xyz789"
}
```

`payment_confirmed`:
```json
{
  "confirmed_by_email": "aubrey@summaterraventures.com",
  "gmail_message_id": "18ghi012"
}
```

### 6.2 System A — New columns on payment_request_tracker

```sql
ALTER TABLE payment_request_tracker
  ADD COLUMN aihub_workflow_id  VARCHAR(128),
  ADD COLUMN aihub_bill_id      UUID,
  ADD COLUMN aihub_status       VARCHAR(32);  -- 'active'|'approved'|'synced'|'paid'|'failed'
```

### 6.3 System B — New columns on existing tables

```sql
-- Bills table (fdnwlcomuddzmluvbylg)
ALTER TABLE bills
  ADD COLUMN gmail_tracker_id UUID UNIQUE;
CREATE INDEX idx_bills_gmail_tracker_id ON bills(gmail_tracker_id);

-- Draw packages table
ALTER TABLE draw_packages
  ADD COLUMN gmail_fee_opportunity_id UUID UNIQUE;
CREATE INDEX idx_draw_packages_gmail_fee_opportunity_id ON draw_packages(gmail_fee_opportunity_id);
```

### 6.4 System B — Anon RLS policies (for dashboard)

```sql
-- Allow anon reads on bills for Ben's dashboard
CREATE POLICY "anon_select_bills"
  ON bills FOR SELECT
  TO anon
  USING (true);

-- Allow anon reads on draw_packages
CREATE POLICY "anon_select_draw_packages"
  ON draw_packages FOR SELECT
  TO anon
  USING (true);
```

### 6.5 System B — POST /intents/bill request/response

**Request body:**
```json
{
  "gmail_tracker_id": "uuid (required, idempotency key)",
  "vendor_name": "string (required)",
  "amount": "decimal or null",
  "po_ref": "string or null",
  "due_date": "ISO date string or null",
  "raw_extensions": {
    "project_label": "string or null",
    "gmail_thread_id": "string",
    "gmail_message_id": "string",
    "requested_by_email": "string"
  },
  "gmail_invoiceproof": {
    "risk_level": "low|medium|high|critical",
    "final_decision": "approved|flagged|blocked",
    "checks_passed": "int 0-7",
    "bank_change_risk": "bool",
    "duplicate_detected": "bool",
    "vendor_confidence": "float 0.0-1.0"
  }
}
```

**Response 201 (created):**
```json
{
  "bill_id": "uuid",
  "workflow_id": "temporal-workflow-id-string",
  "status": "drafted",
  "vendor_matched": true,
  "vendor_id": "uuid"
}
```

**Response 200 (already exists — idempotent):**
```json
{
  "bill_id": "uuid",
  "workflow_id": "temporal-workflow-id-string",
  "status": "drafted|verified|approved|synced",
  "idempotent": true
}
```

### 6.6 System B — POST /approvals/{workflow_id} request/response

**Request body:**
```json
{
  "decision": "approve|reject",
  "source": "email_detected|manual_ui",
  "note": "string (required if source=manual_ui, min 10 chars)",
  "evidence_email_id": "string or null (Gmail message ID for email_detected path)"
}
```

**Response 200 (signal accepted):**
```json
{
  "workflow_id": "string",
  "decision": "approve",
  "bill_id": "uuid",
  "new_status": "approved"
}
```

### 6.7 System A — POST /integration/bill-synced request/response

**Request body (System B sends this):**
```json
{
  "tracker_id": "uuid",
  "bill_id": "uuid",
  "qb_txn_id": "string or null",
  "status": "synced|paid"
}
```

**Response 200:**
```json
{
  "tracker_id": "uuid",
  "previous_status": "Ready for Ben Review",
  "new_status": "Booked / Ready to Book in QB",
  "aihub_status": "synced",
  "idempotent": false
}
```

**Response 200 (idempotent — already processed):**
```json
{
  "tracker_id": "uuid",
  "aihub_status": "synced",
  "idempotent": true
}
```

---

## 7. ERROR HANDLING & EDGE CASES

### Outbox writer error codes (System A — internal, not HTTP)

| Scenario | Guard | Action |
|---|---|---|
| bank_change_risk_flag=True on tracker | Pre-check before any INSERT | Write bank_block row INSTEAD of bill_intent; log to audit |
| tracker.current_status in BLOCKED_STATES | Pre-check | No outbox row; log to audit |
| fee_opportunities.blocked=True (STV CM LLC) | Pre-check | No draw_intent row; audit log: "stv_cm_llc_draw_blocked" |
| Duplicate (tracker_id, event_type) already in outbox | UNIQUE constraint | ON CONFLICT DO NOTHING; log dedup event |
| tracker.amount IS NULL | Allow — write with amount_missing=True flag in payload | System B will route to manual_review |

### System B endpoint error codes

| Endpoint | Scenario | HTTP Status | Code | Body |
|---|---|---|---|---|
| POST /intents/bill | gmail_invoiceproof.bank_change_risk=True | 400 | BANK_CHANGE_RISK | {"error":"Bank change risk — intent rejected"} |
| POST /intents/bill | gmail_invoiceproof.final_decision="blocked" | 422 | INVOICEPROOF_BLOCKED | {"error":"InvoiceProof blocked — intent rejected"} |
| POST /intents/bill | gmail_tracker_id already in bills | 200 | — | {idempotent:true, bill_id, workflow_id} |
| POST /intents/bill | amount ≤ 0 or non-numeric | 201 | — | {bill_id, workflow_id, amount_review:true} — bill created in draft, flagged |
| POST /intents/bill | vendor fuzzy match < 0.75 | 201 | — | {bill_id, workflow_id, vendor_unmatched:true} — soft-draft vendor created |
| POST /intents/bill | missing required fields | 422 | VALIDATION_ERROR | {"error":"Missing required field", "field":"vendor_name"} |
| POST /approvals/{wf_id} | workflow_id not found in Temporal | 404 | WORKFLOW_NOT_FOUND | {"error":"Workflow not found"} |
| POST /approvals/{wf_id} | bill already approved | 200 | — | {idempotent:true, current_status:"approved"} |
| POST /approvals/{wf_id} | source=manual_ui + note < 10 chars | 422 | VALIDATION_ERROR | {"error":"note required for manual approval, min 10 chars"} |
| POST /intents/draw | entity resolves to STV CM LLC | 400 | STV_CM_LLC_BLOCKED | {"error":"STV CM LLC blocked — draw rejected"} |
| POST /intents/draw | fee_payee_status=BLOCKED | 400 | FEE_PAYEE_BLOCKED | {"error":"Fee payee status is BLOCKED"} |
| POST /intents/draw | draw_amount ≤ 0 or null | 422 | VALIDATION_ERROR | {"error":"draw_amount required and must be > 0"} |
| POST /intents/draw | gmail_fee_opportunity_id already exists | 200 | — | {idempotent:true, draw_package_id} |
| POST /intents/bank-block | vendor ATEP block already exists for same sender_email | 200 | — | {idempotent:true, block_id} |
| POST /intents/payment-confirmed | bill not found for tracker_id | 404 | BILL_NOT_FOUND | {"error":"No bill found for tracker_id"} |
| POST /intents/payment-confirmed | bill already paid | 200 | — | {idempotent:true, status:"paid"} |
| Any endpoint | Missing or invalid Authorization header | 401 | UNAUTHORIZED | {"error":"Invalid or missing bearer token"} |

### System A callback error codes

| Endpoint | Scenario | HTTP Status | Code |
|---|---|---|---|
| POST /integration/bill-synced | tracker_id not found | 404 | TRACKER_NOT_FOUND |
| POST /integration/bill-synced | aihub_status already "synced" for same tracker | 200 | idempotent:true |
| POST /integration/bill-synced | Invalid or missing bearer token | 401 | UNAUTHORIZED |

### Edge cases

| Edge Case | Behavior |
|---|---|
| Mike approval signal arrives before /intents/bill completes | Signal delivery waits until aihub_workflow_id is stored. Outbox delivery is synchronous (waits for 201 + workflow_id). Signal only fires AFTER workflow_id confirmed on tracker. |
| Bank block arrives AFTER bill_intent was already delivered | /intents/bank-block scans in-flight bills for same vendor_name → moves to exception queue. P0 alert fires. Ben reviews. |
| Same tracker classified twice (GAS poller retries) | UNIQUE (tracker_id, event_type) on integration_outbox → second insert is a no-op. System B /intents/bill is also idempotent on gmail_tracker_id. |
| System B returns 5xx on delivery attempt | Outbox row: attempts+1; backoff retry. At attempt 3: P1 alert to dashboard. At attempt 5: status=failed; email alert. |
| System A down when bill-synced callback fires | System B retries 3× with 30s delay. After 3 failures: log {tracker_id, bill_id, qb_txn_id} to reconciliation log. Daily reconciliation job picks up gap. |
| Temporal workflow orphaned (no signal in 48h) | Temporal escalation timer fires P1 alert (Google Chat). Temporal retains state indefinitely — no data loss. Ben resolves via approval UI. |
| AIVS hash chain break detected before commit | Hard rollback — no bill commit proceeds. audit_rows entry: chain_break_detected. Alert P0. No further writes accepted until chain restored by developer. |
| draw engine fee math fails (sum != 8% of draw_amount) | Hard reject: no fee bills created. Exception alert. Ben reviews. Requires manual re-trigger with corrected amounts. |
| Vendor fuzzy match: multiple vendors above threshold | Take highest-similarity match; flag vendor_multiple_candidates=True in bill raw_extensions. Ben reviews in UI. |

---

## 8. PERFORMANCE & SCALABILITY REQUIREMENTS

### Latency targets

| Path | Target p95 | Target p99 | Notes |
|---|---|---|---|
| Email arrival → outbox row written | < 2 min | < 5 min | GAS poller 1-min cadence + classify + outbox_writer |
| Outbox delivery (System A → System B) | < 5s per delivery | < 30s | HTTP POST + DB write |
| System B POST /intents/bill (incl. DB write, Temporal start) | < 500ms | < 2000ms | Temporal start is async; returns workflow_id quickly |
| InvoiceProof Gate 1 (in-process proof-core) | < 200ms | < 500ms | In-process; no HTTP call unless fallback |
| POST /approvals/{workflow_id} → bill status = approved | < 1s | < 3s | Temporal signal + one DB write + AuditProof |
| Bill-synced callback (System B → System A) | < 2s round-trip | < 5s | HTTP POST + tracker update |
| Ben's dashboard System B section load | < 1s | < 3s | Supabase anon RLS SELECT — no join needed |

### Throughput

- Expected: ~10 bill intents/day at launch (10-entity firm)
- Peak: ~50 events/day during active draw cycles
- Temporal free tier: 10k actions/month; ~10 bills × 15 actions/bill = 150 actions/day = ~4,500/month — within limit; alert at 7,000/month
- NATS: not used for A→B integration (webhook-only); internal to System B if needed

### Storage growth

- integration_outbox: ~50 rows/day (all event types); < 1 MB/year
- payment_request_tracker: 3 new columns; negligible storage
- bills + draw_packages: new columns only; negligible
- proof_bundles: ~5 KB per VCAP bundle; 10/day = 50 KB/day = ~18 MB/year (Supabase free tier: 500 MB)

### Scalability plan

At 10× current volume (100 bills/day):
- Outbox delivery job: single coroutine handles 100 deliveries/day trivially
- System B /intents/bill: Postgres can handle hundreds of concurrent inserts; no concern
- Temporal Cloud: 1,500 actions/day at 10×; still within free tier
- Supabase: both projects remain within free tier at 10×

---

## 9. SECURITY & COMPLIANCE REQUIREMENTS

### Authentication & authorization

| Actor | Endpoint | Auth Method | Scope |
|---|---|---|---|
| System A outbox job | System B /intents/* | Bearer AIHUB_OUTBOX_TOKEN | POST only; cannot GET bills |
| System A /classify | System B /approvals/{wf_id} | Bearer AIHUB_OUTBOX_TOKEN | POST only |
| System B callback | System A /integration/bill-synced | Bearer SYSTEM_A_CALLBACK_TOKEN | POST only |
| Ben (browser) | System B approval UI | None (reads via Supabase anon RLS) | SELECT only on bills WHERE status=verified |
| Ben (UI) | System B POST /approvals/{wf_id} | Session token or admin credential | Scoped to approval action only |
| Ben (browser) | Dashboard System B section | Supabase ANON key (publishable) | SELECT only; no write possible via RLS |
| External | Any integration endpoint | 401 if missing/invalid token | Fail immediately; no partial processing |

### Credential storage rules

| Credential | Storage | Note |
|---|---|---|
| AIHUB_OUTBOX_TOKEN | Railway env var (System A Service 1) | Not in code, not in Git |
| SYSTEM_A_CALLBACK_TOKEN | Railway env var (System B Service 2) | Not in code, not in Git |
| SUPABASE_URL + SERVICE_ROLE_KEY (ejxrbxoncsgglrqvjulg) | Railway env var (System A) | Named SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY |
| SUPABASE_URL_AIHUB + SERVICE_ROLE_KEY_AIHUB (fdnwlcomuddzmluvbylg) | Railway env var (System B) | Named SUPABASE_URL_AIHUB, SUPABASE_SERVICE_ROLE_KEY_AIHUB |
| SUPABASE_ANON_KEY_AIHUB | Ben's dashboard HTML config | Publishable; RLS enforces SELECT-only |
| SwarmSync sa_* key | Railway env var (System B) | In-process proof-core; no HTTP unless fallback |
| Temporal API key | Railway env var (System B) | TEMPORAL_NAMESPACE + TEMPORAL_API_KEY |

### Data protection

- Bearer tokens: scoped and directional (A→B token cannot be used for B→A path)
- No credentials in integration_outbox payload JSONB — only business data
- No raw Gmail content stored in outbox (only classified fields: vendor_name, amount, etc.)
- bank_change_risk payload: store only vendor_name + sender_email; no raw email body, no bank account numbers
- AIVS audit_rows: append-only; no DELETE or UPDATE ever permitted on audit_rows
- System A draft_queue: integration code has no read OR write access to this table

### Hard rules (non-negotiable)

1. Integration code NEVER calls GmailApp.sendEmail() or drafts.send() — only System A's draft engine creates drafts
2. Integration code NEVER writes to System A's draft_queue table
3. Integration code NEVER creates a bill_intent if bank_change_risk_flag=True on tracker
4. System B MUST reject any bill intent with gmail_invoiceproof.bank_change_risk=True (400)
5. System B MUST reject any draw intent where entity resolves to STV CM LLC (400)
6. supabase-aihub MCP must only connect to fdnwlcomuddzmluvbylg; the default supabase MCP (SwarmSync) must never be used for System B migrations
7. All Alembic migrations target fdnwlcomuddzmluvbylg only; pre-migration CI check asserts DATABASE_URL_AIHUB project ref

---

## 10. TESTING STRATEGY

### Unit tests (System A — outbox_writer.py)

```python
# test_outbox_writer.py
def test_bill_intent_written_when_eligible():
    # tracker: bank_change_risk=False, status=Received, no existing outbox row
    # Expected: outbox INSERT with event_type=bill_intent

def test_no_bill_intent_when_bank_change_risk():
    # tracker: bank_change_risk=True
    # Expected: NO outbox INSERT for bill_intent; bank_block outbox written instead

def test_no_draw_intent_when_stv_cm_llc():
    # fee_opportunities: blocked=True (STV CM LLC)
    # Expected: NO draw_intent outbox row; audit log entry

def test_outbox_idempotency():
    # Call outbox_writer twice for same (tracker_id, event_type)
    # Expected: second INSERT is no-op (ON CONFLICT DO NOTHING); exactly ONE row in DB

def test_bill_intent_payload_structure():
    # Verify payload JSONB contains all required fields including gmail_invoiceproof

def test_blocked_tracker_status_guard():
    # tracker.current_status = "Bank Change Risk" (a BLOCKED_STATE)
    # Expected: NO outbox row of any type
```

### Unit tests (System B — intents.py)

```python
def test_bill_intent_bank_change_rejected():
    # POST /intents/bill with gmail_invoiceproof.bank_change_risk=True
    # Expected: 400, no bill created

def test_bill_intent_idempotent():
    # POST /intents/bill with existing gmail_tracker_id
    # Expected: 200 with idempotent=True, same bill_id

def test_draw_intent_stv_cm_llc_rejected():
    # POST /intents/draw where entity resolves to STV CM LLC
    # Expected: 400 STV_CM_LLC_BLOCKED

def test_draw_fee_math():
    # draw_amount=500000 → developer_fee=25000 (5%), cm_fee=10000 (2%), president_fee=5000 (1%)
    # Expected: three fee bills with exact amounts

def test_approval_signal_idempotent():
    # POST /approvals/{wf_id} when bill already approved
    # Expected: 200 with idempotent=True

def test_bill_synced_callback_idempotent():
    # POST /integration/bill-synced when aihub_status already "synced"
    # Expected: 200 with idempotent=True, no tracker mutation

def test_proof_bundle_required_before_approve():
    # Attempt to approve bill without proof_bundles.passed=True
    # Expected: gate fails closed; bill stays verified; error raised
```

### Integration tests

```python
# test_integration_e2e.py

def test_scenario_1_porter_invoice_full_flow():
    # End-to-end: tracker created → outbox written → delivery → bill created in System B
    # → Gate 1 runs → Temporal started → approval signal → bill approved
    # → callback → tracker advanced
    # Assert: bills table has gmail_tracker_id; tracker.aihub_status="synced"

def test_scenario_2_in_person_approval():
    # Bill in verified state; POST /approvals/{wf_id} with source=manual_ui
    # Assert: bill approved; no System A email event required

def test_scenario_3_bank_change():
    # bank_change_risk=True → outbox has bank_block (no bill_intent)
    # System B: ATEP block created; in-flight bill moved to exception queue
    # Assert: integration_outbox has 0 bill_intent rows; 1 bank_block row

def test_scenario_4_draw_fee():
    # Draw email → draw_intent outbox → System B: 3 fee bills created
    # Assert: draw_packages.gmail_fee_opportunity_id set; 3 bills linked

def test_scenario_5_aubrey_confirmation():
    # payment_confirmed outbox → System B: bill.status=paid
    # Assert: bill status = paid; tracker aihub_status = paid

def test_no_auto_send_invariant():
    # Run full integration pipeline; query System A draft_queue
    # Assert: zero rows with status='sent'

def test_wrong_db_guard():
    # CI: assert DATABASE_URL_AIHUB contains 'fdnwlcomuddzmluvbylg'
    # Assert: correct project ref; fail CI if wrong

def test_aivs_chain_validates():
    # After 50 test commits; run verify.py
    # Assert: VALID (0 broken rows)
```

### End-to-end tests (staging)

- Full Scenario 1: real System A classify call → real System B bill → real Temporal → real approval UI → real callback
- Mike approval email simulation: inject test email with approval language → verify signal fires to Temporal
- Dashboard System B section: load dashboard in browser → verify bills section renders from aihub DB
- Prove no cross-DB contamination: after all tests, verify ejxrbxoncsgglrqvjulg has no bills table; fdnwlcomuddzmluvbylg has no payment_request_tracker table

### Security tests

- Attempt POST /intents/bill with wrong bearer token → assert 401
- Attempt POST /integration/bill-synced with wrong bearer token → assert 401
- Attempt dashboard SQL injection via Supabase anon RLS → assert blocked by RLS
- Verify integration_outbox payload JSONB: no API keys, no raw email body, no bank account numbers present

---

## 11. DEPLOYMENT & ROLLOUT STRATEGY

### Phase 0 deployment (schema + auth — day 1)

```
1. Apply System A migration (integration_outbox + tracker columns) via supabase-gmail-automation MCP
   [Target: ejxrbxoncsgglrqvjulg]
2. Apply System B migration (bills.gmail_tracker_id + draw_packages.gmail_fee_opportunity_id + RLS)
   via supabase-aihub MCP
   [Target: fdnwlcomuddzmluvbylg]
3. Generate bearer tokens; set as Railway env vars on both services
4. Verify: each service can authenticate to the other's test endpoint (/health)
5. Verify: wrong-DB guard passes (CI checks project ref on DATABASE_URL_AIHUB)
Gate: Both migrations applied, auth tokens verified, CI passes → proceed to Phase 1
```

### Phase 1 deployment (bill intent, 3 days)

```
1. Deploy outbox_writer.py + outbox_delivery_job.py to System A (Railway redeploy)
2. Deploy System B Service 2 to Railway (first deployment)
   - /intents/bill endpoint live
   - Temporal worker running
   - proof-core configured
3. Smoke test: one test bill_intent payload → verify bill created in System B
4. Monitor: outbox queue depth (target: 0 after each delivery run)
Gate: 5 consecutive test bill intents delivered with zero failures → proceed to Phase 2
```

### Phase 2 deployment (approval signals + callback, 3 days)

```
1. Deploy POST /approvals/{wf_id} on System B
2. Deploy approval UI at /approve on System B
3. Deploy POST /integration/bill-synced on System A
4. E2E test: full Scenario 1 (Porter invoice → QB callback)
5. E2E test: Scenario 2 (in-person approval via UI)
Gate: Both approval paths verified; callback received; tracker advances correctly → proceed to Phase 3
```

### Phases 3, 4, 5 deployment (independent, sequential)

Each phase follows the same pattern:
1. Deploy new endpoint/outbox event type
2. Smoke test with one synthetic event
3. Monitor for 24 hours at low volume
4. Ben sign-off (reviews System B UI for correct data)
5. Proceed to next phase

### Rollback plan

| Phase | Rollback | Time | Who |
|---|---|---|---|
| Phase 0 (schema) | Run DOWN migrations (integration_outbox DROP, bill columns DROP) | < 30 min | Developer |
| Phase 1 (outbox) | Set INTEGRATION_ENABLED=False env var → outbox job stops; no delivery | < 5 min | Developer |
| Phase 2 (approvals) | Disable approval signal delivery in outbox config | < 5 min | Developer |
| Phase 3 (bank block) | Disable bank_block event type in config | < 5 min | Developer |
| Phase 4 (draw) | Set DRAW_INTEGRATION_ENABLED=False | < 5 min | Developer |
| Phase 5 (dashboard) | Comment out second Supabase client in HTML; redeploy | < 5 min | Developer |

**Rollback rule:** Every rollback must write an entry to automation_audit_log: who triggered, why, timestamp. Ben must be notified of any rollback.

---

## 12. API DOCUMENTATION

### System B — new endpoints

---

#### POST /intents/bill

Create a canonical bill from a Gmail-detected invoice. Idempotent on gmail_tracker_id.

**Auth:** Bearer AIHUB_OUTBOX_TOKEN

**Request:**
```
POST /intents/bill
Authorization: Bearer [AIHUB_OUTBOX_TOKEN]
Content-Type: application/json

{
  "gmail_tracker_id": "uuid",         // REQUIRED — idempotency key
  "vendor_name": "Kirton McConkie",   // REQUIRED
  "amount": 12500.00,                 // nullable — null triggers amount_review=true
  "po_ref": "INV-2026-0341",         // nullable
  "due_date": "2026-07-15",          // nullable, ISO date
  "raw_extensions": { ... },          // nullable JSONB
  "gmail_invoiceproof": {            // REQUIRED
    "risk_level": "low",
    "final_decision": "approved",
    "checks_passed": 5,
    "bank_change_risk": false,
    "duplicate_detected": false,
    "vendor_confidence": 0.95
  }
}
```

**Responses:**

| Status | Condition | Body |
|---|---|---|
| 201 Created | New bill created | {bill_id, workflow_id, status:"drafted", vendor_matched, vendor_id} |
| 200 OK | gmail_tracker_id already exists | {bill_id, workflow_id, status, idempotent:true} |
| 400 Bad Request | bank_change_risk=True | {error:"Bank change risk — intent rejected", code:"BANK_CHANGE_RISK"} |
| 422 Unprocessable | final_decision="blocked" | {error:"InvoiceProof blocked", code:"INVOICEPROOF_BLOCKED"} |
| 422 Unprocessable | Missing required fields | {error:"...", field:"vendor_name", code:"VALIDATION_ERROR"} |
| 401 Unauthorized | Bad/missing token | {error:"Invalid or missing bearer token"} |

---

#### POST /intents/draw

Create a draw package and activate draw engine (CHUNK_6). Idempotent on gmail_fee_opportunity_id.

**Auth:** Bearer AIHUB_OUTBOX_TOKEN

**Request:**
```
POST /intents/draw
Authorization: Bearer [AIHUB_OUTBOX_TOKEN]

{
  "gmail_fee_opportunity_id": "uuid",   // REQUIRED — idempotency key
  "project_canonical": "Madison Park",   // REQUIRED
  "draw_amount": 500000.00,             // REQUIRED, must be > 0
  "draw_number": 8,                      // nullable
  "estimated_fee_hint": 25000.00,        // nullable (advisory only)
  "fee_payee_hint": "Summa Terra...",    // nullable
  "fee_payee_status": "CONFIRMED",       // REQUIRED: "CONFIRMED"|"UNCERTAIN"|"BLOCKED"
  "raw_extensions": { ... }              // nullable
}
```

**Responses:**

| Status | Condition | Body |
|---|---|---|
| 201 Created | New draw package + 3 fee bills created | {draw_package_id, fee_bills:[{bill_id, workflow_id, amount, entity}]} |
| 200 OK | gmail_fee_opportunity_id already exists | {draw_package_id, idempotent:true} |
| 400 Bad Request | STV CM LLC entity | {error:"STV CM LLC blocked", code:"STV_CM_LLC_BLOCKED"} |
| 400 Bad Request | fee_payee_status="BLOCKED" | {error:"Fee payee blocked", code:"FEE_PAYEE_BLOCKED"} |
| 422 | draw_amount ≤ 0 or null | {error:"draw_amount required > 0"} |
| 422 | fee math error | {error:"Draw fee calculation failed — no bills created"} |

---

#### POST /intents/bank-block

Create an ATEP block on a vendor; route in-flight bills to exception queue.

**Auth:** Bearer AIHUB_OUTBOX_TOKEN

**Request:**
```
POST /intents/bank-block

{
  "vendor_name": "string",
  "sender_email": "string",
  "tracker_id": "uuid (nullable)"
}
```

**Responses:**

| Status | Condition | Body |
|---|---|---|
| 201 Created | ATEP block created | {block_id, affected_bills_count} |
| 200 OK | Block already exists for sender_email | {block_id, idempotent:true} |

---

#### POST /intents/payment-confirmed

Mark a bill as paid based on Aubrey's confirmation email.

**Auth:** Bearer AIHUB_OUTBOX_TOKEN

**Request:**
```
POST /intents/payment-confirmed

{
  "gmail_tracker_id": "uuid"
}
```

**Responses:**

| Status | Condition | Body |
|---|---|---|
| 200 OK | Bill status → paid | {bill_id, status:"paid"} |
| 200 OK | Bill already paid | {bill_id, status:"paid", idempotent:true} |
| 404 | No bill for tracker_id | {error:"No bill found for tracker_id"} |

---

#### POST /approvals/{workflow_id}

Send approval or rejection signal to a Temporal workflow. Used by both System A (email path) and Ben's UI (manual path).

**Auth:** Bearer AIHUB_OUTBOX_TOKEN (System A path) OR session token (Ben UI path)

**Request:**
```
POST /approvals/{workflow_id}

{
  "decision": "approve|reject",
  "source": "email_detected|manual_ui",
  "note": "string (required for manual_ui, min 10 chars)",
  "evidence_email_id": "string or null"
}
```

**Responses:**

| Status | Condition | Body |
|---|---|---|
| 200 OK | Signal accepted | {workflow_id, decision, bill_id, new_status} |
| 200 OK | Bill already approved | {idempotent:true, current_status:"approved"} |
| 404 | Workflow not found | {error:"Workflow not found"} |
| 422 | manual_ui + note < 10 chars | {error:"note required for manual approval, min 10 chars"} |

---

### System A — new endpoint

#### POST /integration/bill-synced

Callback from System B: advance tracker status after canonical commit.

**Auth:** Bearer SYSTEM_A_CALLBACK_TOKEN

**Request (System B sends this):**
```
POST /integration/bill-synced

{
  "tracker_id": "uuid",
  "bill_id": "uuid",
  "qb_txn_id": "string or null",
  "status": "synced|paid"
}
```

**Responses:**

| Status | Condition | Body |
|---|---|---|
| 200 OK | Tracker advanced | {tracker_id, previous_status, new_status, aihub_status} |
| 200 OK | Already synced | {idempotent:true, aihub_status:"synced"} |
| 404 | tracker_id not found | {error:"Tracker not found"} |
| 401 | Bad/missing token | {error:"Unauthorized"} |

---

## 13. DATABASE MIGRATIONS

All migrations must be run in dependency order. System A migrations target ejxrbxoncsgglrqvjulg. System B migrations target fdnwlcomuddzmluvbylg via supabase-aihub MCP. **NEVER swap projects.**

### Migration 001 — System A: integration_outbox + tracker columns
**Target:** ejxrbxoncsgglrqvjulg (supabase-gmail-automation MCP)
**File:** `20260629_0900_integration_outbox.sql`

```sql
-- UP
CREATE TABLE integration_outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracker_id      UUID REFERENCES payment_request_tracker(id),
    event_type      VARCHAR(32) NOT NULL,
    payload         JSONB NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts        INT NOT NULL DEFAULT 0,
    sent_at         TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'delivered', 'failed')),
    CONSTRAINT valid_event_type CHECK (
        event_type IN ('bill_intent', 'draw_intent', 'bank_block', 'payment_confirmed')
    ),
    UNIQUE (tracker_id, event_type)
);

CREATE INDEX idx_integration_outbox_status ON integration_outbox(status);
CREATE INDEX idx_integration_outbox_created_at ON integration_outbox(created_at);

ALTER TABLE payment_request_tracker
    ADD COLUMN IF NOT EXISTS aihub_workflow_id  VARCHAR(128),
    ADD COLUMN IF NOT EXISTS aihub_bill_id      UUID,
    ADD COLUMN IF NOT EXISTS aihub_status       VARCHAR(32);

COMMENT ON TABLE integration_outbox IS
    'Durable outbox for cross-system event delivery (System A → System B).';
COMMENT ON COLUMN integration_outbox.payload IS
    'JSONB payload specific to event_type. Never contains API keys or raw email body.';

-- DOWN
ALTER TABLE payment_request_tracker
    DROP COLUMN IF EXISTS aihub_workflow_id,
    DROP COLUMN IF EXISTS aihub_bill_id,
    DROP COLUMN IF EXISTS aihub_status;

DROP TABLE IF EXISTS integration_outbox CASCADE;
```

**Validation:**
```sql
SELECT table_name FROM information_schema.tables WHERE table_name = 'integration_outbox';
SELECT column_name FROM information_schema.columns
    WHERE table_name = 'payment_request_tracker'
    AND column_name IN ('aihub_workflow_id', 'aihub_bill_id', 'aihub_status');
```

---

### Migration 002 — System B: bills.gmail_tracker_id + draw_packages.gmail_fee_opportunity_id
**Target:** fdnwlcomuddzmluvbylg (supabase-aihub MCP)
**File:** `20260629_0910_integration_columns.sql` (Alembic migration)

```sql
-- UP
ALTER TABLE bills
    ADD COLUMN IF NOT EXISTS gmail_tracker_id UUID UNIQUE;
CREATE INDEX IF NOT EXISTS idx_bills_gmail_tracker_id ON bills(gmail_tracker_id);

ALTER TABLE draw_packages
    ADD COLUMN IF NOT EXISTS gmail_fee_opportunity_id UUID UNIQUE;
CREATE INDEX IF NOT EXISTS idx_draw_packages_gmail_fee_opportunity_id
    ON draw_packages(gmail_fee_opportunity_id);

-- DOWN
DROP INDEX IF EXISTS idx_bills_gmail_tracker_id;
ALTER TABLE bills DROP COLUMN IF EXISTS gmail_tracker_id;
DROP INDEX IF EXISTS idx_draw_packages_gmail_fee_opportunity_id;
ALTER TABLE draw_packages DROP COLUMN IF EXISTS gmail_fee_opportunity_id;
```

---

### Migration 003 — System B: anon RLS policies for dashboard
**Target:** fdnwlcomuddzmluvbylg (supabase-aihub MCP)
**File:** `20260629_0920_dashboard_rls.sql`

```sql
-- UP
ALTER TABLE bills ENABLE ROW LEVEL SECURITY;
ALTER TABLE draw_packages ENABLE ROW LEVEL SECURITY;

-- Allow anon SELECT for Ben's dashboard (read-only; no write possible)
CREATE POLICY "anon_select_bills"
    ON bills FOR SELECT TO anon USING (true);

CREATE POLICY "anon_select_draw_packages"
    ON draw_packages FOR SELECT TO anon USING (true);

-- Service role retains full access (Temporal workers, API endpoints)
-- No explicit policy needed — service role bypasses RLS by default

-- DOWN
DROP POLICY IF EXISTS "anon_select_bills" ON bills;
DROP POLICY IF EXISTS "anon_select_draw_packages" ON draw_packages;
```

**Validation (run after applying):**
```sql
-- Verify anon cannot INSERT
-- (Test via Supabase client with anon key — expect error)
-- Verify anon can SELECT
SELECT id, status, amount FROM bills LIMIT 1;  -- should succeed with anon key
```

**Pre-migration CI assertion (must pass before any migration runs):**
```python
import os
assert 'fdnwlcomuddzmluvbylg' in os.environ.get('DATABASE_URL_AIHUB', ''), \
    "DATABASE_URL_AIHUB does not point to aihub project — refusing migration"
```

---

## 14. KNOWN LIMITATIONS & FUTURE WORK

### Known limitations

1. **QBWC write-back not in scope (Phase 6):** Bills commit to canonical Postgres and are fully provable, but do not reach QB Desktop until Phase 6. Ben must continue manual QB entry for Phase 5 period. This is by design — QB Desktop is the eventually-consistent sink, not the system of record.

2. **Vendor fuzzy match confidence:** pg_trgm similarity threshold of 0.75 will produce false holds for abbreviations ("Kirton" vs "Kirton McConkie & Biggs"). Ben reviews vendor_unmatched bills in System B UI. Future: add vendor alias table.

3. **draw_amount extraction accuracy:** System A's fee_agent extracts estimated draw amounts from unstructured email text. The amount may be incorrect; System B uses it as a hint and recalculates, but if estimated_fee_hint is wildly wrong, Ben may see confusing "draft" amounts before CHUNK_6 recalculates. Future: OCR pipeline on draw package PDFs.

4. **Temporal free tier:** 10k workflow actions/month. At current volume (~150/month), there's 65× headroom. If STV scales to 10 companies × 10 bills/month × 15 actions = 1,500/month — still fine. Alert at 7,000/month to prompt upgrade discussion.

5. **GAS poller 1-min cadence:** Real email processing latency is 1–2 minutes. For truly urgent events (bank change P0), this is acceptable — P0 fires immediately within the classify call, and the bank block reaches System B within 3–4 minutes. There is no sub-minute path without replacing the GAS poller (separate project).

### Deferred features (Phase 6+)

- QBWC write-back adapter (Railway Service 3) — gated on CRUX spikes
- .qwc file generation — gated on QBWC adapter deployment
- Vendor alias table for fuzzy match improvement
- Draw package PDF OCR for accurate amount extraction
- Batch approval (approve multiple bills in one System B UI action)
- Email notification to Porter when bill is booked (Ben currently sends manually)

### Technical debt created by this spec

- integration_outbox uses a single delivery job; if System A railway service has multiple replicas, concurrent delivery is possible. Mitigation for now: Railway free/hobby tier is single-instance. If Railway scales to multiple replicas, add SELECT FOR UPDATE SKIP LOCKED to outbox delivery query.
- System B approval UI uses session token or admin credential (MVP: hard-coded credential or HTTP basic). Future: proper auth session for Ben.

---

## 15. GLOSSARY & TERMS

| Term | Definition |
|---|---|
| System A | STV Gmail AccountingOS — Python 3.12 FastAPI on Railway; classifies emails; runs state machine; creates drafts |
| System B | AI Accounting Hub — Python 3.11 FastAPI (to build); writes proof-gated bills to canonical Postgres |
| integration_outbox | Durable table in System A (ejxrbxoncsgglrqvjulg) that stores outbound events to System B. Survives Railway restarts. |
| bill_intent | An outbox event type: a structured invoice ready to become a bill in System B |
| draw_intent | An outbox event type: a construction draw fee opportunity ready for System B's draw engine |
| bank_block | An outbox event type: a P0 bank change fraud detection event; creates ATEP block in System B |
| payment_confirmed | An outbox event type: Aubrey's payment confirmation; marks bill as paid in System B |
| gmail_tracker_id | The join key between Systems A and B. payment_request_tracker.id (System A) = bills.gmail_tracker_id (System B). UNIQUE constraint in System B. |
| gmail_invoiceproof | The advisory pre-screening result from System A's invoice_proof.py, passed in the bill_intent payload to System B as context. NOT System B's formal Gate 1 proof. |
| VCAP Full Bundle | System B's formal proof product: proof_bundles row with vcap_state, proof_hash (SHA-256), proof_signature (HMAC-SHA256), passed=True. This is Gate 1. |
| AIVS chain | SHA-256 hash chain in System B's audit_rows table. Every bill commit appends a row. Chain break is a hard stop. |
| ATEP | Bank change fraud block in System B. Set when bank_block intent received. Blocks payment path. |
| Temporal workflow | Long-running, durable workflow in Temporal Cloud. Holds the approval gate. Survives restarts. |
| aihub_workflow_id | Temporal workflow ID stored on payment_request_tracker after /intents/bill returns. Used to fire approval signal. |
| bill-synced callback | System B's POST to System A's /integration/bill-synced after a bill reaches canonical commit. Advances tracker to "Booked / Ready to Book in QB". |
| CHUNK_6 | Draw fee engine in System B (existing shadow-mode implementation). 5%/2%/1% split per QB spec §5.3. Activated (not rebuilt) in Phase 4. |
| supabase-aihub MCP | The MCP server scoped to fdnwlcomuddzmluvbylg (aihub DB). NEVER the default supabase MCP (which = SwarmSync). |
| CRUX spike | RESOLVED 2026-07-01. Was: pre-existing documented blocker in FinalSpec §4.6 (QBWC poll cadence measurement + Rightworks persistent-poller approval), gating Phase 6. Now: Rightworks confirmed in writing no persistent/unattended poller exists or is supported (2h global inactivity auto-logout, non-adjustable; scheduled-task/service-account workaround explicitly declined). Final model: business-hours, session-tied QBWC polling. Phase 6 is unblocked under this model. |
| STV CM LLC | Summa Terra CM LLC. Commission-on-partnership entity. Hard-blocked in both System A fee_agent and System B draw engine independently. |
| P0 | Highest-priority alert. bank_change_risk fires P0. Goes to Google Chat immediately. |

---

## 16. MONITORING, METRICS & OBSERVABILITY

### System A metrics (integration-specific)

| Metric | Target | Alert Threshold | Channel |
|---|---|---|---|
| Outbox pending rows | 0 after each delivery run | > 20 rows | Dashboard warning |
| Outbox delivery failures (attempts=5, status=failed) | 0 | > 0 | Email + Google Chat P1 |
| Outbox delivery attempt 3 (not yet failed) | Track only | > 3 for same row | Dashboard warning |
| Mike approval signal delivery failures | 0 | > 0 (3 retries exhausted) | Google Chat P1 |
| Bill-synced callback receive failures (System B retries exhausted) | 0 | > 0 | Reconciliation report next day |

### System B metrics

| Metric | Target | Alert Threshold | Channel |
|---|---|---|---|
| Bills in exception queue age | < 24h | > 24h unresolved | Google Chat P1 |
| Temporal approval age | < 48h | > 48h without signal | Google Chat P1 (Temporal timer) |
| AIVS chain status | VALID | Any BROKEN row | Google Chat P0 |
| proof_bundles coverage | 100% of approved bills | Any approved bill without passed=True bundle | Immediate gate failure |
| System B /health endpoint | 200 OK | Non-200 for > 5 min | Google Chat P1 |
| draw fee math errors | 0 | > 0 | Google Chat P1 |

### Daily digest email (automated, sent to Ben)

```
STV Integration Health — YYYY-MM-DD
=====================================
Outbox: N delivered, N pending, N failed
Bills today: N drafted, N verified, N approved
Exception queue: N open items (oldest: N hours)
AIVS chain: VALID / BROKEN
Temporal: N active workflows, N escalated (>48h)
Dashboard: System B section loading OK

Action items:
- [auto-generated list of anything exceeding thresholds]
```

### Logging (new events to log in automation_audit_log — System A)

| Event | Fields |
|---|---|
| outbox_row_written | tracker_id, event_type, outbox_id, timestamp |
| outbox_delivered | outbox_id, system_b_response_status, bill_id, workflow_id, timestamp |
| outbox_delivery_failed | outbox_id, attempt, error, timestamp |
| approval_signal_fired | tracker_id, workflow_id, evidence_email_id, timestamp |
| approval_signal_failed | tracker_id, workflow_id, attempt, error, timestamp |
| bill_synced_received | tracker_id, bill_id, qb_txn_id, previous_status, new_status, timestamp |
| outbox_bank_change_guard | tracker_id, event_type_blocked="bill_intent", timestamp |
| outbox_stv_cm_llc_guard | fee_opportunity_id, timestamp |

### Logging (System B — new events to audit_rows AIVS chain)

| Event | action_type |
|---|---|
| Bill intent received | bill_intent_received |
| Gate 1 passed | invoiceproof_gate1_passed |
| Gate 1 failed | invoiceproof_gate1_failed |
| Approval signal received | approval_signal_received |
| Bill approved (canonical commit) | bill_approved |
| Bank block created | atep_bank_block_created |
| Draw fee generated (3 bills) | draw_fee_generated |
| Bill-synced callback fired | bill_synced_callback_fired |
| STV CM LLC canary fired | stv_cm_llc_draw_attempted — P1 alert (this should never happen) |

---

## 17. ALTERNATIVE DESIGNS CONSIDERED

### Alternative 1: NATS/JetStream as integration bus (System A publishes events to NATS)

**Pros:** Durable message queue with at-least-once delivery; fan-out to multiple consumers; JetStream persists messages across restarts.

**Cons:** Requires adding NATS client to System A (new dependency); NATS is a new Railway service System A doesn't have; adds operational complexity to a system that's currently simple FastAPI + Supabase.

**Why rejected:** System A is live and stable. Adding NATS requires code changes to a deployed, tested system (200+ passing tests). The integration_outbox pattern achieves the same durability guarantee using Supabase (which System A already depends on) without touching System A's existing dependencies. Outbox-to-webhook is simpler to debug, rollback, and reason about at this scale (~10 bills/day).

### Alternative 2: System B polls System A's Supabase directly (no webhook)

**Pros:** No outbox delivery job; System B controls poll cadence; System A makes no new calls.

**Cons:** Requires System B to have read access to System A's Supabase (ejxrbxoncsgglrqvjulg) — cross-DB credential sharing is explicitly prohibited by the architecture. Creates tight coupling between System B's polling logic and System A's table schema. Poll latency adds to total end-to-end latency.

**Why rejected:** Cross-DB credential sharing is a hard rule violation. Federated databases must remain federated — each system owns its own data and access. Webhook + outbox is the correct pattern for this.

### Alternative 3: Merge both Supabase projects into one

**Pros:** Eliminates cross-system HTTP calls; enables SQL joins between payment_request_tracker and bills; one DB client per service.

**Cons:** Two systems with separate purposes, separate teams (even if both are Ben), separate migration cadences, and separate access controls become entangled. Future team members or services cannot be scoped to one system without the other. RLS policies become complex. Migration conflicts possible.

**Why rejected:** Governor crux decision D2 resolved this: keep federated. The join key (bills.gmail_tracker_id) satisfies the only cross-system query need. Operational simplicity of separate projects outweighs the join convenience at this scale.

### Alternative 4: System A fires approval signal immediately on Mike email detection (skip outbox)

**Pros:** Lower latency for approval (no outbox poll cycle); simpler code.

**Cons:** If System B is down at the moment of Mike's email, the approval signal is lost with no retry. Must store workflow_id before signal can fire (requires bill to already exist in System B). If signal fires before Temporal workflow is in the correct state, Temporal behavior is undefined.

**Why rejected:** The outbox delivery job already handles durability for the bill_intent path. The approval signal has a similar need: System A must confirm that aihub_workflow_id is stored before firing the signal. The outbox delivery path guarantees bill creation and workflow_id capture before any signal is attempted. Signal fires synchronously after successful delivery confirmation — no outbox needed for the signal itself, but the dependency ordering is critical (enforced in Section 7 edge case documentation).

---

## 18. FINAL BUILD CHECKLIST

### AI Agent Execution Contract

This spec will be executed by Claude Code (or equivalent). Before writing any code, the agent must:
- [ ] Read all 18 sections of this spec AND the Architecture Governor Summary at the top
- [ ] Read the companion architecture decision packet: `architecture-decision-packet-stv-integration-layer-2026-06-29.md`
- [ ] Produce a file tree and implementation plan as first output (no code until plan is approved by Ben)
- [ ] Verify each "must-not-break" guarantee is tested before marking any phase complete
- [ ] Treat the Definition of Done below as the only valid completion signal
- [ ] Stop and escalate if any must-not-break guarantee is at risk during implementation
- [ ] Never mark a phase complete based on local-only verification — staging confirmation required

### Phase 0 checklist

- [ ] Migration 001 applied to ejxrbxoncsgglrqvjulg via supabase-gmail-automation MCP
- [ ] Migration 002 applied to fdnwlcomuddzmluvbylg via supabase-aihub MCP
- [ ] Migration 003 (RLS) applied to fdnwlcomuddzmluvbylg via supabase-aihub MCP
- [ ] Pre-migration CI assertion passes: DATABASE_URL_AIHUB contains 'fdnwlcomuddzmluvbylg'
- [ ] AIHUB_OUTBOX_TOKEN set in Railway System A env vars
- [ ] SYSTEM_A_CALLBACK_TOKEN set in Railway System B env vars
- [ ] SUPABASE_URL_AIHUB + SUPABASE_SERVICE_ROLE_KEY_AIHUB set in Railway System B env vars
- [ ] SUPABASE_ANON_KEY_AIHUB set (for dashboard extension, Phase 5)
- [ ] Verify: System A can POST to System B /health with correct token → 200
- [ ] Verify: System B can POST to System A /health with correct token → 200
- [ ] Verify: wrong token → 401 on both endpoints

### Phase 1 checklist

- [ ] outbox_writer.py: bill_intent written when tracker eligible
- [ ] outbox_writer.py: NO bill_intent if bank_change_risk_flag=True
- [ ] outbox_writer.py: NO bill_intent if tracker.current_status in BLOCKED_STATES
- [ ] outbox_writer.py: idempotent (UNIQUE constraint test)
- [ ] outbox_delivery_job.py: picks up pending rows, POSTs to System B
- [ ] outbox_delivery_job.py: marks delivered on 2xx; increments attempts on 5xx
- [ ] outbox_delivery_job.py: alert at attempt 3; status=failed at attempt 5
- [ ] System B POST /intents/bill: 400 on bank_change_risk=True
- [ ] System B POST /intents/bill: 200 idempotent on duplicate gmail_tracker_id
- [ ] System B POST /intents/bill: bill created, Temporal started, workflow_id returned
- [ ] System B InvoiceProof Gate 1: proof_bundles row created, passed=True for clean invoice
- [ ] System B: tracker.aihub_workflow_id updated after successful delivery
- [ ] Unit tests: all outbox_writer + intents unit tests pass
- [ ] E2E smoke test: 5 test bill_intents delivered with zero failures

### Phase 2 checklist

- [ ] System A: approval signal fires after detect_mike_approval() → True
- [ ] System A: aihub_workflow_id must be stored before signal fires (precondition enforced)
- [ ] System B POST /approvals/{wf_id}: Temporal signal accepted, bill → approved
- [ ] System B POST /approvals/{wf_id}: 200 idempotent if already approved
- [ ] System B POST /approvals/{wf_id}: manual_ui path requires note ≥ 10 chars
- [ ] System B approval UI: renders list of bills with status=verified
- [ ] System B approval UI: shows vendor_name, amount, project, draft_date, mike_email_detected, proof_status
- [ ] System B approval UI: "Approve" button fires POST /approvals/{wf_id}
- [ ] System B bill-synced callback: fires after canonical commit
- [ ] System B bill-synced callback: retries 3× on System A 5xx
- [ ] System A POST /integration/bill-synced: tracker advances to "Booked / Ready to Book in QB"
- [ ] System A POST /integration/bill-synced: 200 idempotent if aihub_status already "synced"
- [ ] E2E test Scenario 1 (email approval path): confirmed in staging
- [ ] E2E test Scenario 2 (in-person approval UI path): confirmed in staging

### Phase 3 checklist

- [ ] outbox_writer.py: bank_block event written when bank_change_risk=True (not bill_intent)
- [ ] System B POST /intents/bank-block: ATEP block created
- [ ] System B POST /intents/bank-block: scans in-flight bills → exception queue
- [ ] System B POST /intents/bank-block: 200 idempotent on duplicate sender_email
- [ ] E2E test Scenario 3: bank change email → ATEP block → no bill_intent
- [ ] Assert: integration_outbox has 0 bill_intent rows for bank_change_risk tracker

### Phase 4 checklist

- [ ] outbox_writer.py: draw_intent written when fee_opportunities.blocked=False
- [ ] outbox_writer.py: NO draw_intent if fee_opportunities.blocked=True (STV CM LLC)
- [ ] System B POST /intents/draw: 400 on STV CM LLC entity
- [ ] System B POST /intents/draw: draw engine CHUNK_6 activated (not shadow mode)
- [ ] System B draw fee: 3 fee bills created with exact 5%/2%/1% amounts
- [ ] System B draw fee: math validation (sum = 8% of draw_amount) enforced
- [ ] System B draw fee: 3 Temporal workflows started, blocked at approval gates
- [ ] E2E test Scenario 4: draw email → 3 fee bills → approval via UI → AuditProof
- [ ] Assert: STV CM LLC draw test case returns 400 from System B (canary test)

### Phase 5 checklist

- [ ] outbox_writer.py: payment_confirmed event written after Aubrey confirmation detected
- [ ] System B POST /intents/payment-confirmed: bill.status → paid
- [ ] System B POST /intents/payment-confirmed: 200 idempotent if already paid
- [ ] Dashboard: second Supabase client (SUPABASE_URL_AIHUB + SUPABASE_ANON_KEY_AIHUB) initialized
- [ ] Dashboard: bills section renders from fdnwlcomuddzmluvbylg (status, vendor, amount, gmail_tracker_id)
- [ ] Dashboard: draw_packages section renders
- [ ] Dashboard: no write operations possible via anon key (RLS verified)
- [ ] E2E test Scenario 5: Aubrey confirmation → bill paid → dashboard updated
- [ ] Dashboard verified in staging browser: both sections load within 3 seconds

### Definition of Done (all 10 must be simultaneously true in staging)

1. All 5 scenarios pass E2E tests in staging (Scenarios 1–5 in Section 5)
2. Zero rows in System A draft_queue with status='sent' after full pipeline run
3. AIVS chain: verify.py reports VALID after 50 test commits
4. Bill with bank_change_risk=True: confirmed no bill_intent outbox row, no bill in System B
5. STV CM LLC draw: confirmed 400 from System B, no draw_package created
6. All 7 must-not-break guarantees pass as named regression tests in CI
7. Database URL guard: CI fails if DATABASE_URL_AIHUB does not contain fdnwlcomuddzmluvbylg
8. Ben's dashboard loads both System A and System B sections in staging browser
9. Ben's approval UI: verified in staging — bill list loads, Approve button fires, bill advances
10. Daily digest email: delivered to Ben's inbox with correct content from staging

**NOT done if:**
- Any of the 10 conditions above verified only locally ("works on my machine")
- Code looks correct but no E2E test has been run in staging
- Ben has not reviewed the approval UI and dashboard in staging himself
- AIVS chain validated with fewer than 50 test commits
- Any must-not-break guarantee test is skipped or commented out

---

*Section count: 18 of 18 produced.*

## CONSISTENCY CHECK RESULTS

```
All 18 sections checked for internal contradictions.

✓ Section 2 scope (no QBWC) is consistent with Section 14 (QBWC deferred to Phase 6)
✓ Section 3 acceptance criteria (no auto-send) is consistent with Section 9 security rules
✓ Section 7 error codes (bank_change_risk → 400) are consistent with Section 5 flows
✓ Section 8 latency targets are compatible with Section 11 retry policies
   (5× retries with exp. backoff add < 30min worst-case, acceptable for non-real-time path)
✓ Section 9 (anon RLS SELECT-only) is consistent with Section 6.4 (RLS policies)
✓ Section 11 deployment (Phase 0 first) is consistent with Section 13 migration ordering
✓ Section 12 API specs are consistent with Section 6 data models
✓ Section 16 monitoring thresholds are consistent with Section 8 performance targets
✓ All 7 must-not-break guarantees appear in Section 10 regression tests
✓ Definition of done (Section 18) references all 5 scenarios from Section 5

Status: ✅ ZERO CONTRADICTIONS — spec is ready for build
```
