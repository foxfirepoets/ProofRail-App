# Architecture Decision Packet
## System: STV Gmail AccountingOS × AI Accounting Hub — Integration Layer
## Date: 2026-06-29
## Verdict: READY_FOR_SPEC
## Confidence: HIGH — both systems fully read (code + schemas + specs); all 5 crux decisions resolved with concrete implementations; QBWC spikes are pre-documented System B internal blockers (FinalSpec.md §4.6), not integration-layer blockers

---

## 1. System Summary

This governance session covers the **integration layer** between two independently-live systems: STV Gmail AccountingOS (System A — live on Railway, fully tested) and AI Accounting Hub / QB Automation (System B — early design/build). System A detects accounting events from email (vendor invoices, Mike approvals, bank changes, draw packages, payment confirmations) and manages a human-communication lifecycle tracked in `payment_request_tracker`. System B receives structured accounting intents, runs a 4-gate SwarmSync proof spine, gates on human approval via Temporal, and writes to QuickBooks Desktop via the QBWC adapter. The integration layer is the **bridge** that connects these two systems: translating email events into accounting intents (A→B), carrying Mike approval signals across the boundary (A→B), activating bank-change blocks (A→B), routing construction-draw fee calculations (A→B), and closing the loop when a bill is synced to QB (B→A). Neither system is being redesigned — only a minimal integration surface is being added to each. Primary user: Ben Stone (stone@summaterraventures.com), accounting manager.

**[G7 CHECK: 1 CRITICAL risk found (QBWC spike — likelihood HIGH, impact HIGH). Mitigation IS defined in FinalSpec.md §4.6 (escape to scheduled batch-ETL). Verdict remains READY_FOR_SPEC for the integration layer. Write-back adapter code is separately gated behind the spike resolution.]**

---

## 2. Current-System Map

| Component | Type | Status | Location / Notes |
|---|---|---|---|
| Gmail FastAPI (System A) | API | LIVE | Railway: exemplary-tenderness-production.up.railway.app |
| GAS Poller | Job | LIVE | Google Apps Script, 1-min cadence, stone@ + adam@ |
| Supabase Gmail DB | Database | LIVE | ejxrbxoncsgglrqvjulr — 9 tables, anon RLS on 6 |
| Ben's Dashboard | UI | LIVE | dashboard/index.html — reads ejxrbxoncsgglrqvjulr anon RLS |
| SwarmSync client (System A) | SDK | LIVE | in-process + HTTP, circuit breaker, Supabase-first |
| AI Accounting Hub API (System B) | API | EARLY BUILD | Railway (not yet deployed) — aihub Supabase fdnwlcomuddzmluvbylg |
| NATS/JetStream (System B) | Event bus | PLANNED | Railway or embedded in Hub API |
| Temporal Cloud (System B) | Workflow engine | PLANNED | Free tier, 10k actions/month |
| Draw Engine CHUNK_6 (System B) | Module | SHADOW | app/draw_engine/ — shadow mode, no QBWC write-back yet |
| QBWC SOAP Endpoint (System B) | Adapter | NOT YET | Separate Railway service — requires stable URL before .qwc generation |
| QBWC v34 on Rightworks | Client | LIVE (idle) | Installed, "no application registered" — correct waiting state |
| **Integration Layer** | Bridge | **NOT YET** | New: webhooks + outbox + callback endpoints — subject of this packet |

---

## 3. Target Architecture

After this integration work is complete, the architecture adds a minimal integration surface to both systems without redesigning either one.

**Before:** Two independent systems with no connection. System A tracks email lifecycle. System B (when built) tracks accounting lifecycle. No event flows between them.

**After:**

```
System A (Gmail)                          Integration Layer              System B (Accounting Hub)
──────────────────                        ──────────────────             ──────────────────────────
GAS Poller → /classify                                                   
     │                                                                   
     ▼                                                                   
email_classifications                    A→B Webhooks                   
payment_request_tracker  ─── bill intent ──────────────→  POST /intents/bill
     │                   ─── draw intent ──────────────→  POST /intents/draw
     │                   ─── bank block  ──────────────→  POST /intents/bank-block
     │                   ─── mike approval ────────────→  POST /approvals/{workflow_id}
     │                                                              │
integration_outbox (new) ─── durable queue ──────────────────────►│
     │                                                              │
     │                   B→A Callback                              ▼
     │◄─── bill synced ──────────────────  POST /integration/bill-synced
     │                                              Temporal Workflow
payment_request_tracker                            → proof gates (1-4)
 .aihub_workflow_id (new)                          → human approval gate
 .aihub_bill_id (new)                              → canonical Postgres write
 .current_status updated                           → QBWC queue (gated on spike)
     │
     ▼
Ben's Dashboard (extended):
 Section A: email_messages / payment_request_tracker (existing)
 Section B: bills / draw_packages (new — reads aihub Supabase anon RLS)
```

**Schema additions (additive only — no breaking changes):**

System A additions:
- `payment_request_tracker`: add columns `aihub_workflow_id VARCHAR(128)`, `aihub_bill_id UUID`, `aihub_status VARCHAR(32)`
- `integration_outbox` (new table): `id UUID PK, tracker_id UUID, event_type VARCHAR(32), payload JSONB, status VARCHAR(16) DEFAULT 'pending', attempts INT DEFAULT 0, sent_at TIMESTAMPTZ, error_message TEXT, created_at TIMESTAMPTZ`
- New endpoint: `POST /integration/bill-synced` (Bearer auth, called by System B)

System B additions:
- `bills`: add column `gmail_tracker_id UUID` (link back to System A's payment_request_tracker.id)
- `draw_packages`: add column `gmail_fee_opportunity_id UUID`
- New endpoints: `POST /intents/bill`, `POST /intents/draw`, `POST /intents/bank-block` (System B already has `POST /approvals/{workflow_id}`)

---

## 4. Domain Entities

### Entity: email_messages (System A — SoT)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| gmail_message_id | VARCHAR | Gmail's message ID |
| sender / subject / body_preview | VARCHAR | Sanitized (injection guard) |
| has_attachments, attachment_types | BOOL / TEXT | Used to gate payment tracker creation |
| classification_status | VARCHAR | classified / rejected |

### Entity: email_classifications (System A — SoT)
| Field | Type | Notes |
|---|---|---|
| email_message_id | UUID FK | |
| workflow_type | VARCHAR | Porter Payment Request, Construction Draw, etc. |
| bank_change_risk | BOOL | P0 gate — if true, no bill intent ever created |
| confidence, urgency, labels | JSONB | |
| notes | TEXT | Mike approval language detected, etc. |

### Entity: payment_request_tracker (System A — SoT for email/communication lifecycle)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | Carries into System B as gmail_tracker_id |
| current_status | VARCHAR | 13-state machine (see §6) |
| vendor_name, amount, due_date | VARCHAR / DECIMAL | Passed to System B as bill intent fields |
| bank_change_risk_flag | BOOL | Hard block — if true, no intent ever created |
| aihub_workflow_id | VARCHAR(128) | [NEW] System B Temporal workflow ID |
| aihub_bill_id | UUID | [NEW] System B bills.id |
| aihub_status | VARCHAR(32) | [NEW] Mirror of System B bill.status for dashboard |

### Entity: fee_opportunities (System A — SoT for draw fee detection)
| Field | Type | Notes |
|---|---|---|
| email_id, project_canonical | VARCHAR | Source email + project name |
| draw_amount, estimated_fee | DECIMAL | 5% of draw |
| fee_payee, fee_payee_status | VARCHAR | CONFIRMED / UNCERTAIN / BLOCKED |
| blocked, blocked_reason | BOOL / TEXT | STV CM LLC always blocked=True |

### Entity: integration_outbox (System A — NEW)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tracker_id | UUID | FK → payment_request_tracker.id |
| event_type | VARCHAR(32) | bill_intent / draw_intent / bank_block / mike_approval |
| payload | JSONB | Full intent payload |
| status | VARCHAR(16) | pending / delivered / failed |
| attempts | INT | Circuit breaker: max 5 attempts |
| sent_at, error_message | TIMESTAMPTZ / TEXT | |

### Entity: bills (System B — SoT for accounting lifecycle)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| company_id, vendor_id | UUID FK | System B canonical entities |
| gmail_tracker_id | UUID | [NEW] Links back to System A tracker |
| amount, po_ref | DECIMAL / VARCHAR | |
| status | VARCHAR(24) | drafted → verified → approved → synced |
| invoiceproof_bundle_id | UUID FK | Gate 1 VCAP Full Bundle |

### Entity: proof_bundles (System B — SoT for accounting proof)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| kind | VARCHAR(24) | invoiceproof / auditproof / verifyapi |
| vcap_state, proof_hash, proof_signature | VARCHAR / TEXT | VCAP Full Bundle fields |
| passed | BOOL | Hard gate: bill cannot approve without passed=True |
| payload | JSONB | Includes gmail_prescreening from System A |

### Entity: draw_packages (System B — SoT for draw fee accounting)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | [PROPOSED] |
| gmail_fee_opportunity_id | UUID | [NEW] Links to System A fee_opportunities |
| project_canonical, draw_number | VARCHAR | |
| total_amount | DECIMAL | |
| status | VARCHAR | submitted → approved → fee-generated → funded → reconciled |
| dev_fee_bill_id, cm_fee_bill_id, pres_fee_bill_id | UUID FK | Three fee bill intents |

### Entity: vendors (System B — SoT for vendor identity + bank fingerprints)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR | Must be synced / mappable from System A vendor_name |
| bank_fingerprint | VARCHAR(256) | Hash of bank details — ATEP check |
| swarmscore | INT | Vendor trust tier |

---

## 5. Source-of-Truth Matrix

| Entity | SoT Location | Writers | Readers | Conflict Resolution | Risk |
|---|---|---|---|---|---|
| Email event (received, classified) | System A ejxrbxoncsgglrqvjulg | GAS Poller → /classify | Ben's dashboard, System B (via webhook) | System A is authoritative; System B never writes email records | LOW |
| Payment communication lifecycle (Received → Paid) | System A payment_request_tracker | /classify pipeline, /integration/bill-synced callback | Ben's dashboard | System A owns states up to "Synced to QB". System B's callback advances the state. System A never self-advances past Payment Confirmed without System B evidence. | MEDIUM — callback must be idempotent |
| Accounting lifecycle (drafted → synced) | System B bills | System B Temporal workflow | System B API, Ben's dashboard (new section) | System B is authoritative. System A stores a mirror field (aihub_status) for display only, never for decisions. | LOW |
| InvoiceProof Gate 1 result | System B proof_bundles | System B proof-core (in-process) | System B Temporal workflow | System B always runs its own Gate 1 VCAP Full Bundle. System A's proof_results is pre-screening input only — never the gate itself. | LOW — clearly separated |
| Vendor identity | System B vendors | System B (QB sync) | System B workflow, System A (read only for display) | System B is authoritative for QB vendor identity. System A's vendor_name is free-text and maps to System B vendors by fuzzy match + payment_tracker_id linkage. | MEDIUM — vendor_name may not match exactly |
| Bank change block | BOTH systems | System A: email_classifications.bank_change_risk. System B: ATEP gate on vendors.bank_fingerprint | Both | System A blocks intent creation (no bill intent for bank_change_risk=True). System B has independent ATEP gate. Both must block; neither depends on the other's block alone. | LOW — defense in depth |
| Draw fee calculation | System B draw_packages | System B draw engine (CHUNK_6) | System B proof gates, Ben's dashboard | System B is authoritative. System A's fee_opportunities.estimated_fee is an estimate (5% heuristic) for display only; System B recalculates exactly per QB spec §5.3. | LOW |
| STV CM LLC block | BOTH systems | System A: fee_agent.blocked=True. System B: draw engine hard-coded block | Both | System A never creates a fee_opportunities row with fee_payee=STV CM LLC without blocked=True. System B independently checks entity name before creating any fee bill. Both blocks are independent; neither depends on the other. | LOW — defense in depth |
| Mike approval state | System A (source) → System B (signal) | System A: email detection → transition. System B: Temporal signal received. | System B Temporal workflow | System A's email-detected approval is one input. System B also accepts manual UI approval (in-person override). System B's approval gate is the hard gate; System A's email detection is a signal source. | MEDIUM — signal must arrive; see §11 failure modes |
| QB write-back state | System B (qb_txn_id, qb_edit_sequence) | System B QBWC adapter | System B, System A (display mirror) | System B is authoritative. System A displays qb_txn_id for reference only, never writes to it. | LOW |

---

## 6. State Machines

### System A: payment_request_tracker.current_status

| State | Transitions To | Triggered By | Irreversible? | Notes |
|---|---|---|---|---|
| Received | Missing Information, Ready for Ben Review | /classify pipeline | No | Created on Porter email with attachment |
| Missing Information | Ready for Ben Review | Ben action | No | |
| Ready for Ben Review | Ready for Mike Approval, Approved by Mike | Ben action | No | **INTEGRATION TRIGGER HERE**: bill intent created, outbox written |
| Ready for Mike Approval | Sent to Mike for Approval | Ben action | No | |
| Sent to Mike for Approval | Approved by Mike | Mike email detected OR manual UI | No | |
| Approved by Mike | Sent to Aubrey for Payment Execution | Ben action | No | **INTEGRATION TRIGGER HERE**: mike_approval signal sent to System B |
| Sent to Aubrey for Payment Execution | Payment Confirmed | Aubrey email detected | No | |
| Payment Confirmed | Booked / Ready to Book in QB | [legacy — now replaced by System B callback] | No | System B callback drives this transition |
| Booked / Ready to Book in QB | Confirmation Sent to Requester | System B bill-synced callback | **YES** | aihub_status = "synced"; QB TxnID available |
| Confirmation Sent to Requester | Closed | Ben sends draft | No | |
| Closed | — | Final state | YES | |
| Bank Change Risk | Ready for Ben Review | Manual clearance ONLY | No | Requires both systems to clear |
| Duplicate Risk | Ready for Ben Review | Ben action | No | |
| Do Not Pay | — | Final state | YES | |

### System B: bills.status

| State | Transitions To | Triggered By | Irreversible? | Notes |
|---|---|---|---|---|
| drafted | verified | Temporal workflow: intent received + fields validated | No | gmail_tracker_id stored on creation |
| verified | approved | InvoiceProof Gate 1 passed (proof_bundles row, passed=True) | No | AuditProof Gate 2 appended |
| approved | synced | Human approval signal (Temporal.signal or POST /approvals/{id}) | **YES** | QB write queued after this |
| synced | — | QBWC adapter write-back + TxnID reconciled | YES | Callback to System A fires here |

### System B: draw_packages.status

| State | Transitions To | Triggered By | Irreversible? | Notes |
|---|---|---|---|---|
| submitted | approved | Draw intent received from System A fee_opportunities | No | |
| approved | fee-generated | Mike + CM approval (human gate) | YES | Three fee bill intents created |
| fee-generated | funded | All three fee bills reach "approved" | YES | |
| funded | reconciled | QBWC write-back confirmed | YES | |

---

## 7. Critical Workflows

### Workflow 1 — Standard Vendor Invoice (Porter → QB)
**Trigger:** Porter forwards invoice to stone@; GAS poller sends to /classify.

**Happy path:**
1. /classify: injection guard → classify as "Porter Payment Request" → create email_messages + email_classifications rows
2. bank_change_risk? NO → continue
3. Create payment_request_tracker (status=Received)
4. Run InvoiceProof (System A advisory, non-blocking) → proof_results row
5. Create Template 1 draft → draft_queue (pending_ben_review)
6. **[Integration trigger]** Write integration_outbox row (event_type=bill_intent, status=pending)
7. Background job delivers to System B POST /intents/bill; System B returns {bill_id, workflow_id}
8. Update payment_request_tracker: aihub_bill_id=X, aihub_workflow_id=Y
9. Outbox row marked delivered
10. System B: Temporal workflow → InvoiceProof Gate 1 (VCAP Full Bundle, uses System A prescreen as evidence) → human approval gate (blocked)
11. Mike approves (email or in-person):
    - Path A (email): System A detects → fires POST /approvals/{Y} → Temporal signal
    - Path B (in-person): Ben clicks "Approve" in System B UI → Temporal signal directly
12. System B: Gate 2 AuditProof (AIVS) → canonical Postgres bill commit → QBWC queue
13. QBWC drains → QB BillAdd → TxnID reconciled
14. **[Integration callback]** System B fires POST /integration/bill-synced to System A with {tracker_id, bill_id, qb_txn_id}
15. System A: advances payment_tracker to "Booked / Ready to Book in QB"; aihub_status="synced"
16. System A: Ben sends Template 2 draft (Payment Confirmed) to Porter

**Error path:** Bank change detected → stop at step 2; outbox written with event_type=bank_block instead.

---

### Workflow 2 — Mike In-Person Approval (No Email Trail)
**Trigger:** Mike approves verbally to Ben/Aubrey. No email is sent.

**Path:**
1. System B Temporal workflow is blocked at approval gate (bill in status=verified)
2. Ben navigates to System B approval UI: shows in-flight bills with vendor, amount, project, draft date
3. Ben clicks "Manually Approve" → POST /approvals/{workflow_id} from UI
4. System B Temporal signal received → bill advances to approved → commit path continues
5. Ben updates System A payment_tracker manually (or System B callback does it)

**No dependency on System A for this path. System B's UI is the override surface.**

---

### Workflow 3 — Bank Change Fraud Attempt
**Trigger:** Any email contains bank change keywords.

**Path (both systems must block independently):**
1. System A /classify: bank_change_risk=True detected PRE-LLM
2. P0 webhook fires immediately → Google Chat alert
3. email_classifications.bank_change_risk=True written
4. **Integration trigger:** outbox row written with event_type=bank_block
5. NO bill intent is created (hard gate in outbox writer: skip bill_intent if bank_change_risk=True)
6. System B receives POST /intents/bank-block → creates/updates vendor ATEP block
7. System B: any in-flight bill for that vendor → exception queue
8. Both systems: no payment path until Ben manually clears in both
9. Clear in System A: Ben sets bank_change_risk_flag=False on tracker (manual DB or UI action)
10. Clear in System B: Ben removes ATEP block via admin UI

---

### Workflow 4 — Construction Draw (Madison Park, Rock Creek)
**Trigger:** Lauren Farnsworth or Concord/Elite Construction sends draw package.

**Path:**
1. /classify: "Construction Draw" or "Lien Waiver / AIA G702/G703 / GC Pay App"
2. fee_agent: detect_fee_trigger → build_fee_opportunity → fee_opportunities row
3. Blocked check: STV CM LLC → blocked=True → NO intent created
4. Template 6 draft (Draw Package Acknowledgment) → draft_queue
5. **Integration trigger:** outbox row (event_type=draw_intent) with payload: {fee_opportunity_id, project, draw_amount, estimated_fee}
6. System B /intents/draw: receives draw intent → creates draw_packages row (status=submitted)
7. System B draw engine: computes exact 5%/2%/1% split per QB spec §5.3
8. Creates three fee bill intents (dev fee, CM fee, President fee)
9. Human approval gate (Mike + CM sign-off) → AuditProof → QBWC queue for 3 company files
10. Callback to System A: draws "Synced" status

---

### Workflow 5 — Aubrey Payment Confirmation
**Trigger:** aubrey@summaterraventures.com sends payment confirmation email.

**Path:**
1. /classify: "Aubrey Payment Execution" detected
2. payment_tracker state → "Payment Confirmed"
3. **Integration trigger:** outbox row (event_type=payment_confirmed)
4. System B /intents/payment-confirmed: updates bill.status to "paid"
5. System B queues reconciliation write to QB
6. Callback to System A when reconciled

---

## 8. Integration Boundaries

| Integration | Direction | Auth Method | What We Send | What We Receive | Failure Mode | Cost/Limit |
|---|---|---|---|---|---|---|
| System A → System B: bill intent | A→B | Bearer token (sa_* key, scoped) | {gmail_tracker_id, vendor_name, amount, po_ref, gmail_invoiceproof: {risk_level, final_decision, ...}, raw_extensions} | {bill_id, workflow_id, status} | System B down → outbox retries (max 5, backoff) | Free (Railway internal HTTP) |
| System A → System B: draw intent | A→B | Bearer token | {fee_opportunity_id, project_canonical, draw_amount, estimated_fee, fee_payee_status} | {draw_package_id} | Outbox retries | Free |
| System A → System B: bank block | A→B | Bearer token | {vendor_name, sender_email, tracker_id} | {block_id} | Outbox retries; P0 alert already fired | Free |
| System A → System B: mike approval | A→B | Bearer token | {workflow_id, approver="mike_email_detected", evidence_email_id} | {status} | Retry 3×; if failed → Ben sees "approval signal failed" in dashboard | Free |
| System B → System A: bill synced | B→A | Bearer token (System A issues, System B uses) | {tracker_id, bill_id, qb_txn_id, status="synced"} | {ok} | System A down → System B retries 3×; tracker stays at Payment Confirmed but bill is synced | Free |
| QBWC SOAP (System B internal) | B→QB | QBWC .qwc file + username/password | qbXML (BillAdd, etc.) | TxnID, EditSequence | Rightworks CRUX spike — see §15 | $0 (existing license) |
| SwarmSync proof-core (System B) | In-process | Self-issued sa_* key | evidenceInputs[] | {riskLevel, passed, proof_hash, proof_signature} | Gate fails closed | $0 (owner-operated) |
| SwarmSync proof (System A) | HTTP + in-process | SWARMSYNC_API_KEY | {tracker_id, vendor_name, risk_level, final_decision} | {proof_id} (advisory only) | Circuit breaker; non-blocking | $0 (owner-operated) |
| Gmail OAuth (System A) | Outbound | OAuth2 refresh token | MIME draft | draft_id | Non-blocking; draft_queue is source of truth | Free |
| GAS Poller → /classify | Inbound | Bearer token (CLASSIFIER_ENDPOINT) | EmailPayload | ClassificationResult | Retry on next poll cycle | Free |
| Supabase Gmail DB (System A) | Read/Write | SERVICE_ROLE_KEY (API) / ANON key (dashboard) | SQL via supabase-py | Row data | Dashboard degrades gracefully | Free tier or paid |
| Supabase aihub DB (System B) | Read/Write | SERVICE_ROLE_KEY / ANON key (dashboard) | Alembic SQL | Row data | Temporal retries; bill persisted | Free tier or paid |

---

## 9. Money / Auth / Proof Boundaries

### MONEY

| Location | Action | Trigger | Guard Condition | Idempotent? | Audit Log? |
|---|---|---|---|---|---|
| System B: POST /approvals/{workflow_id} | Commit bill to canonical Postgres | Human approval (email signal or UI click) | bill.status=verified + proof_bundles.passed=True + Temporal signal received | YES — workflow_id unique; double-signal returns existing status | YES — audit_rows AIVS hash-chain |
| System B: QBWC adapter | QB write-back (BillAdd) | bill.status=approved + QBWC poll | Gate 3 VerifyAPI must be VERIFIED | YES — idempotent qbXML; EditSequence conflict → re-base | YES — qb_txn_id reconciled back |
| System B: draw engine | Three fee journal entries | draw_packages.status=approved | Mike + CM approval, AuditProof chain validates | YES — draw_number + entity uniqueness prevents duplicate | YES — per fee bill audit_rows |
| System A: payment_tracker | State advance to Booked | System B callback with qb_txn_id | qb_txn_id must be non-null in callback payload | YES — idempotent if aihub_bill_id already set | YES — automation_audit_log |
| System A → System B | bill_intent delivery | payment_tracker Ready for Ben Review | bank_change_risk_flag=False AND tracker.status NOT in BLOCKED_STATES | YES — gmail_tracker_id unique in bills table; duplicate intent returns existing bill | YES — integration_outbox.delivered |

### AUTH

| Check Point | Token Type | Validates | Failure Behavior | Rate Limited? |
|---|---|---|---|---|
| System A /classify | Bearer token | GAS Poller identity | 401 → poller logs error, retries next cycle | No (internal only) |
| System A /verify/* | Bearer token | Ben or admin | 401 | No |
| System A /integration/bill-synced | Bearer token (System B uses System A-issued token) | System B identity only | 401 → System B retries 3×; logs | No |
| System B POST /intents/* | Bearer token (sa_* key, System A uses) | System A identity | 401 → outbox marks failed; alerts | No |
| System B POST /approvals/{id} | Bearer token (Ben or System A) | Approver identity | 401 → human sees error in UI | No |
| System B GET /bills/* | Bearer token | Ben only | 401 | No |
| Ben's Dashboard (System A) | Supabase anon key | RLS enforces SELECT-only on 6 tables | 403 on any write attempt (RLS) | No |
| Ben's Dashboard (System B section) | Supabase anon key (aihub) | RLS enforces SELECT-only on bills/draw_packages | 403 on write | No |

### PROOF

| Proof Type | Generated At | Storage Location | User-Visible? | Tamper-Proof? |
|---|---|---|---|---|
| InvoiceProof Gate 1 (System A, advisory) | /classify pipeline | System A proof_results table | No (internal) | No — advisory only, no VCAP Full Bundle |
| InvoiceProof Gate 1 (System B, hard gate) | System B Temporal workflow | System B proof_bundles (vcap_state, proof_hash, proof_signature) | Yes (via GET /bills/{id}/proof) | YES — VCAP Full Bundle, HMAC-SHA256 |
| AuditProof Gate 2 (System B) | Pre-GL commit | System B audit_rows (AIVS hash chain) | No (auditor access) | YES — SHA-256 hash chain, Ed25519 optional |
| VerifyAPI Gate 3 (System B) | Pre-autonomous execution | System B proof_bundles (kind=verifyapi) | No | YES — VCAP state machine |
| ATEP Gate 4 (System B) | Bank change block | System B vendors.bank_fingerprint + ATEP record | No | YES — fingerprint hash |
| Integration outbox delivery proof | Delivery confirmation | System A integration_outbox.sent_at | No (ops only) | No — operational log |

---

## 10. Data Flow

### Core flow: Porter invoice → QB write-back

```
Step 1  [System A]  GAS poller detects new email on stone@
Step 2  [System A]  POST /classify: injection guard → bank_change_risk check (FIRST)
Step 3  [System A]  classify_email() → workflow_type="Porter Payment Request"
Step 4  [System A]  DB writes: email_messages + email_classifications
Step 5  [System A]  bank_change_risk=False → continue (else: P0 alert, stop)
Step 6  [System A]  Create payment_request_tracker (status=Received)
Step 7  [System A]  Run InvoiceProof advisory → proof_results row (non-blocking)
Step 8  [System A]  Template 1 draft → draft_queue (pending_ben_review only)
Step 9  [System A]  Write integration_outbox (event_type=bill_intent, status=pending)
        [BOUNDARY]  ──────────────────────────────────────────────────────
Step 10 [Outbox]    Background job reads integration_outbox WHERE status=pending
Step 11 [Outbox]    POST /intents/bill to System B API (with proof prescreening payload)
Step 12 [System B]  Validate: bank_change_risk in payload? → 400 REJECT
Step 13 [System B]  vendor_name fuzzy-match → vendors table lookup / create
Step 14 [System B]  Create bills row (status=drafted, gmail_tracker_id=X)
Step 15 [System B]  Start Temporal workflow → returns {bill_id, workflow_id}
Step 16 [Outbox]    Mark integration_outbox delivered; update tracker: aihub_bill_id + workflow_id
        [BOUNDARY]  ──────────────────────────────────────────────────────
Step 17 [System B]  Temporal: build VCAP evidenceInputs (System A prescreen + DB lookups)
Step 18 [System B]  runProofProduct({product:'invoiceproof'}) → riskLevel + findings
Step 19 [System B]  riskLevel=CRITICAL? → exception queue. Else: bill → verified
Step 20 [System B]  AuditProof Gate 2: append AIVS audit_row; chain validates
Step 21 [System B]  Temporal BLOCKS: waiting for human approval signal
Step 22 [Signal A]  Mike email → System A detects → POST /approvals/{workflow_id}
        OR
Step 22 [Signal B]  Ben clicks "Approve" in System B UI → POST /approvals/{workflow_id}
Step 23 [System B]  Temporal signal received → bill → approved
Step 24 [System B]  Canonical Postgres commit; AuditProof row appended; chain validates
Step 25 [System B]  QBWC queue: enqueue BillAdd qbXML
Step 26 [QBWC]      QB Web Connector polls SOAP endpoint → sendRequestXML
Step 27 [System B]  receiveResponseXML: extract TxnID → bills.qb_txn_id updated; bill → synced
        [BOUNDARY]  ──────────────────────────────────────────────────────
Step 28 [System B]  POST /integration/bill-synced to System A API {tracker_id, qb_txn_id}
Step 29 [System A]  Advance payment_tracker → "Booked / Ready to Book in QB"; aihub_status="synced"
Step 30 [System A]  Ben sees bill synced in dashboard; sends Template 2 draft to Porter
```

**Failure path exits:**
- Step 2: bank_change_risk → STOP, P0 alert, no further processing
- Step 11: System B down → outbox increments attempt, retries with backoff (max 5)
- Step 18: InvoiceProof CRITICAL → bill → exception queue; no approval gate reached
- Step 21–22: Temporal times out → escalation timer fires → Ben notified; bill stays in verified
- Step 26: QBWC poll stalled → bill stays approved in canonical store; Temporal retains state; no data loss
- Step 28: System A down → System B retries 3×; tracker stays at Payment Confirmed (bill IS synced, just not reflected yet)

---

## 11. Failure Modes

| Scenario | Trigger | System State After | Detectable? | Recoverable? | Mitigation |
|---|---|---|---|---|---|
| System B down when outbox fires | Network / Railway restart | Outbox row status=pending, attempts+1 | YES — outbox.attempts > 0 | YES — retry on next job cycle | Exponential backoff, max 5 attempts, alert at attempt 3 |
| Mike approval signal fails (System B timeout) | POST /approvals/{id} returns 5xx | Temporal workflow still blocked; tracker at "Approved by Mike" | YES — System A logs error | YES — Ben uses System B UI to manually approve | Alert Ben dashboard; show "Approval signal pending" status |
| Duplicate bill intent delivered | Network retry sends same gmail_tracker_id twice | System B rejects second; returns existing bill_id | YES — idempotent guard | N/A — no damage | bills UNIQUE constraint on gmail_tracker_id; 200 on duplicate |
| Bank block arrives AFTER bill intent already delivered | Race condition: classify fires, outbox fires before bank_change_risk detected | System B has a bill in drafted state for a risky vendor | Partially — bank block intent arrives later | YES — bank block creates ATEP flag; in-flight bill routed to exception queue | System B /intents/bank-block must check for any in-flight bill for that vendor and flag it; System B never auto-approves |
| QBWC poll stalled / Rightworks session killed | Rightworks background-kill | Bill approved in canonical Postgres; QB not yet updated | YES — GET /sync/health shows sync lag | YES — Temporal retains state; QB write replays on next poll | Sync lag alert > threshold; poller approval ticket (pre-existing spike) |
| EditSequence conflict at QB write | QB record changed between approval and write-back | qbXML BillAdd fails with conflict | YES — receiveResponseXML error | YES — re-read QB record, re-base, retry once; else route to human | Standard QB optimistic-lock handling (FinalSpec.md §7) |
| AIVS hash chain broken | Tamper attempt or corrupted write | Bill commit rolls back; no QB write | YES — chain validation fails | Investigate source; re-run from last valid block | Hard rollback; alert paged immediately |
| InvoiceProof Gate fails closed (SwarmSync outage) | proof-core in-process fails | Temporal workflow aborts; bill stuck at drafted | YES — Temporal activity fails | YES — once proof-core restored, Temporal retries activity | Gates fail closed; never fail open. proof-core is in-process (no HTTP) — outage scenario is rare |
| System A callback endpoint down when System B fires bill-synced | System A Railway restart | Bill IS synced in QB; tracker shows "Payment Confirmed" not "Booked" | YES — System B retry log | YES — System B retries 3×; manual reconciliation if all fail | System B logs tracker_id + qb_txn_id; Ben can manually update tracker; or run reconciliation job |
| STV CM LLC draw intent delivered to System B | System A fee_agent blocked=True row somehow generates outbox row | System B draw engine detects entity=STV CM LLC → rejects | YES — 400 response | N/A | Defense in depth: System A outbox writer checks blocked=True; System B draw engine independently rejects STV CM LLC |
| auto-send triggered by integration | Integration layer calls send() | IMPOSSIBLE — draft_queue CHECK constraint prevents it | N/A | N/A | DB-level CHECK (status != 'sent'). Integration layer has no access to System A Gmail credentials. System B never calls Gmail API. |
| Wrong Supabase DB targeted | Developer uses supabase MCP instead of supabase-aihub MCP for System B work | Migrations hit wrong DB; data written to SwarmSync DB | YES — table not found errors immediately | YES — rollback if caught early | NEVER use supabase (default) MCP for System B. Only supabase-aihub MCP for fdnwlcomuddzmluvbylg. Enforced by CLAUDE.md. |

---

## 12. Duplicate / Sprawl Analysis

| Redundancy Found | Type | Risk Level | Recommendation |
|---|---|---|---|
| payment_request_tracker (System A) vs bills (System B) — both track a vendor payment | Data | MEDIUM | RESOLVED: clean phase split. Tracker owns email/communication lifecycle; bills owns accounting lifecycle. Join key: bills.gmail_tracker_id. Do NOT merge. |
| InvoiceProof run in System A (advisory, local checks) vs System B (hard gate, VCAP Full Bundle) | Code + Proof | LOW | RESOLVED: different purposes. System A = pre-screening triage (non-blocking advisory). System B = hard money gate (VCAP Full Bundle, blocks approval). System A's result is passed as evidence to System B. They are NOT duplicates. |
| fee_opportunities (System A) vs draw_packages (System B) — both represent a construction draw | Data | MEDIUM | RESOLVED: System A's fee_opportunities is email detection + fee estimate. System B's draw_packages is the accounting object with exact fee calculation. fee_opportunity_id is FK in draw_packages. System A = detection; System B = calculation + booking. |
| STV CM LLC block in System A (fee_agent) and System B (draw engine) | Code | LOW | KEEP BOTH (defense in depth). Each system independently blocks. Not a duplicate risk — redundant safety. |
| Bank change block in System A (P0 rule-based) and System B (ATEP gate) | Code | LOW | KEEP BOTH (defense in depth). Independent. System A blocks intent creation; System B blocks payment path. |
| Two SwarmSync proof clients (System A: HTTP client with circuit breaker; System B: in-process proof-core library) | Code | LOW | EXPECTED: different integration modes. System A uses HTTP because it predates the in-process library integration decision. System B uses in-process (recommended, zero-HTTP, zero-latency gates). No merge needed. |
| automation_audit_log (System A) vs audit_rows AIVS chain (System B) | Data | LOW | DIFFERENT PURPOSES: System A's audit log is an operational event log (non-tamper-evident, for debugging). System B's audit_rows is the AIVS hash-chain (tamper-evident, for financial proof). Do NOT merge. |

---

## 13. Build / Reuse / Delete Decisions

| Component | Decision | Rationale | Priority | Dependencies |
|---|---|---|---|---|
| integration_outbox table (System A) | BUILD NEW | Durable delivery guarantee for intents; prevents lost events when System B is down | P0 | Supabase migration on ejxrbxoncsgglrqvjulg |
| payment_request_tracker new columns (aihub_workflow_id, aihub_bill_id, aihub_status) | BUILD NEW (additive) | Link System A records to System B lifecycle | P0 | Supabase migration on ejxrbxoncsgglrqvjulg |
| POST /integration/bill-synced endpoint (System A) | BUILD NEW | Callback receiver from System B | P0 | Bearer token management |
| Outbox delivery background job (System A) | BUILD NEW | Polls integration_outbox, fires webhooks to System B, handles retries | P0 | Must run as part of Railway Service 1 (add to startup or cron) |
| POST /intents/bill endpoint (System B) | BUILD NEW | Idempotent bill intent receiver; starts Temporal workflow | P0 | System B API deployed, Temporal Cloud wired |
| POST /intents/draw endpoint (System B) | BUILD NEW | Draw intent receiver; creates draw_packages row, starts fee engine | P0 | Draw engine CHUNK_6 already in shadow mode |
| POST /intents/bank-block endpoint (System B) | BUILD NEW | ATEP block creation; scans in-flight bills for that vendor | P0 | System B vendors table + ATEP logic |
| bills.gmail_tracker_id column (System B) | BUILD NEW (additive) | Cross-system join key; idempotency guard | P0 | Alembic migration on fdnwlcomuddzmluvbylg |
| draw_packages.gmail_fee_opportunity_id column (System B) | BUILD NEW (additive) | Cross-system link for draw tracking | P1 | Alembic migration |
| System B approval UI (manual override) | REUSE WITH CHANGES | POST /approvals/{workflow_id} already spec'd; add bill list view with "Approve" button | P0 | System B deployed, Temporal Cloud wired |
| System B GET /bills list endpoint | BUILD NEW | Powers Ben's dashboard second section | P1 | System B deployed |
| Ben's Dashboard — System B section | BUILD NEW (additive) | Second Supabase client (aihub anon RLS) in existing dashboard/index.html | P1 | System B anon RLS policies applied to bills/draw_packages |
| System A proof_results table | REUSE AS-IS | Advisory proof log; passes its fields as gmail_invoiceproof in the intent payload | P1 | Add proof fields to bill intent payload schema |
| System A fee_opportunities table | REUSE AS-IS | Source of draw intent payload; no schema change needed | P1 | Outbox writer reads fee_opportunities.draw_amount etc. |
| SwarmSync proof-core (System B) | REUSE AS-IS | In-process Gate 1/2/3; already designed in FinalSpec.md §9 | P0 | No change needed |
| GAS poller (System A) | LEAVE ALONE | No change to poller; integration is downstream of /classify | — | — |
| System A draft_queue | LEAVE ALONE | No change; integration layer never writes here | — | — |
| System A Gmail OAuth | LEAVE ALONE | No change; integration layer never calls Gmail API | — | — |
| QBWC SOAP endpoint (System B) | BUILD NEW (separate Railway service) | Separate from Hub API; stable URL needed for .qwc file | P2 (after spike) | CRUX spike resolved first |

---

## 14. Non-Scope

- We are NOT merging the two Supabase projects (ejxrbxoncsgglrqvjulg + fdnwlcomuddzmluvbylg) because each has independent migrations, RLS policies, and owning teams; failure isolation is valuable; the additive integration surface (outbox + new columns) is sufficient.
- We are NOT adding NATS/JetStream to System A because System A is live and tested with direct Supabase writes; adding a message bus would require significant retesting with no benefit over the outbox+webhook pattern.
- We are NOT changing the 13-state payment_request_tracker machine in System A; we are only adding columns and a new terminal transition (Synced to QB via callback).
- We are NOT automating email sends from the integration layer; the draft_queue CHECK constraint is absolute; the integration layer never touches System A's Gmail credentials.
- We are NOT bypassing System B's human approval gate; System A's Mike-email detection sends a Temporal signal to the EXISTING approval gate, which still requires the gate to be in the correct state (bill=verified, proof=passed).
- We are NOT building live QBO/NetSuite/Xero adapters; those are Phase 4+ per FinalSpec.md §2.
- We are NOT changing System B's 4 proof gates; they remain hard fail-closed.
- We are NOT moving the QBWC spike deadline; write-back adapter code waits on spike resolution and Rightworks ticket.
- We are NOT building the QBWC SOAP endpoint or registering the .qwc file until after the integration spec is delivered and the spike is resolved.
- We are NOT touching System A's bank_change_risk P0 logic; the integration layer never reorders or delays this check.

---

## 15. Risk Register

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| **QBWC CRUX spike — RESOLVED 2026-07-01** (G9): Rightworks confirmed in writing there is no persistent/unattended poller; polling is business-hours, session-tied only (2h global inactivity auto-logout, non-adjustable; scheduled-task/service-account workaround explicitly declined by Rightworks) | LOW (was HIGH — now a known, accepted constraint) | MEDIUM — QB write-back only proceeds during active login sessions; off-hours items queue, not lost | Integration layer above QBWC is unaffected — bills commit to canonical Postgres regardless. Design accepts business-hours cadence as final; monitor queue age via daily digest rather than escalating to batch-ETL fallback. | Ben / integration engineer |
| Outbox job fails silently, intents pile up | MEDIUM | HIGH | Alert when outbox.attempts > 3. Add Railway health check that monitors outbox queue depth. Maximum 5 retries with exponential backoff. Dashboard shows "X intents pending delivery". | Integration engineer |
| Vendor name mismatch: System A vendor_name (free-text) doesn't match any System B vendors row | HIGH | MEDIUM | System B /intents/bill creates a draft vendor if no match (soft-create). Fuzzy match (pg_trgm) with confidence score. Ben reviews unmatched vendors in System B dashboard. Never auto-pay against an unmatched vendor. | System B backend |
| Mike approval signal race: System A fires /approvals/{id} before System B has created the Temporal workflow | MEDIUM | MEDIUM | /intents/bill is synchronous and returns workflow_id only after Temporal workflow is started. System A stores workflow_id before firing any approval signal. Signal has a short delay built in (fire only after bill_id is confirmed stored). | Integration engineer |
| System B bill-synced callback lost when System A is down; tracker never advances | LOW | MEDIUM | System B retries 3×. After failure, System B writes {tracker_id, qb_txn_id} to a reconciliation log. Daily reconciliation job: query System B for synced bills, update System A trackers where aihub_status != 'synced'. | Integration engineer |
| STV CM LLC leaks through draw engine (both blocks fail simultaneously) | LOW | HIGH | Independent double block: System A never creates outbox row when blocked=True; System B hard-rejects entity name "STV CM LLC". Both must fail for a leak — extremely unlikely. Add alert if System B ever rejects a STV CM LLC intent (it should never arrive). | Integration engineer + QA |
| DB identity confusion: developer runs migration against wrong Supabase project | MEDIUM | HIGH | CLAUDE.md hard rule: only supabase-aihub MCP for fdnwlcomuddzmluvbylg. Code comment in every migration file headers. CI step: assert correct project ref before running Alembic. | Engineer (enforced by CLAUDE.md) |

---

## 16. Definition of Done

1. `integration_outbox` table exists in System A Supabase (ejxrbxoncsgglrqvjulg), migration applied.
2. `payment_request_tracker.aihub_workflow_id`, `.aihub_bill_id`, `.aihub_status` columns exist.
3. `bills.gmail_tracker_id` column exists in System B Supabase (fdnwlcomuddzmluvbylg), unique constraint applied.
4. System A `POST /integration/bill-synced` endpoint: returns 200 and advances tracker state, returns 400 if tracker_id not found, returns 200 (idempotent) if already synced.
5. System B `POST /intents/bill`: returns 200 + {bill_id, workflow_id} on valid intent; returns 400 on bank_change_risk=True intent; returns 200 + existing bill_id on duplicate gmail_tracker_id.
6. System B `POST /intents/bank-block`: creates ATEP block; any in-flight bill for that vendor moves to exception queue; returns 200.
7. System B `POST /intents/draw`: creates draw_packages row; draw engine starts fee calculation; returns {draw_package_id}.
8. Outbox delivery job: delivers all pending intents within 2 minutes of creation when System B is healthy; retries with exponential backoff; alerts at attempt 3.
9. Mike email approval path: System A detects "this is approved" from mike@ → fires POST /approvals/{workflow_id} → Temporal signal received → bill.status advances to "approved". Verified end-to-end in integration test.
10. In-person approval path: Ben navigates to System B approval UI → clicks "Manually Approve" on a verified bill → bill.status advances to "approved". Verified in E2E test.
11. Bank block path: System A classifies bank-change email → outbox fires bank_block → System B creates ATEP block → any in-flight bill for that vendor lands in exception queue. Verified in integration test.
12. STV CM LLC: System A creates a fee_opportunities row with blocked=True for STV CM LLC → outbox writer does NOT create a draw_intent outbox row (assert no outbox row written). System B: POST /intents/draw with STV CM LLC entity returns 400.
13. Bill-synced callback: System B fires POST /integration/bill-synced → System A advances tracker to "Booked / Ready to Book in QB" with qb_txn_id stored.
14. Ben's dashboard shows System B section: bills table with status, amount, vendor, gmail_tracker_id — reads from aihub Supabase anon RLS. Verified: no write operations possible from dashboard.
15. No auto-send ever triggered: integration test confirms that no path through the integration layer ever calls Gmail send() or advances draft_queue.status to "sent". DB-level CHECK constraint verified present.

---

## 17. Handoff to Spec-Superstar

**Confirmed scope for master-integration-engineer (or spec-superstar) to specify in full:**

1. **Integration Outbox** (System A):
   - Table schema (exact SQL migration for ejxrbxoncsgglrqvjulg)
   - Outbox writer logic: when to write (what tracker states trigger each event_type)
   - Delivery job: poll cadence, retry logic, circuit breaker, alert thresholds
   - Auth: how System A acquires and stores the System B bearer token

2. **System A new endpoint `POST /integration/bill-synced`**:
   - Request schema: {tracker_id, bill_id, qb_txn_id, status}
   - State transition logic (which tracker state it advances to, evidence requirement)
   - Auth: how System B's token is issued and validated by System A

3. **System B `POST /intents/bill`**:
   - Request schema (full — including gmail_invoiceproof nested object)
   - Idempotency contract (gmail_tracker_id UNIQUE)
   - bank_change_risk guard (400 rejection)
   - Vendor fuzzy-match / soft-create logic
   - Response schema: {bill_id, workflow_id}
   - How Temporal workflow is started with intent payload

4. **System B `POST /intents/draw`**:
   - Request schema (fee_opportunity_id, project_canonical, draw_amount, estimated_fee)
   - Draw engine activation (how CHUNK_6 is invoked)
   - STV CM LLC hard block

5. **System B `POST /intents/bank-block`**:
   - Request schema
   - ATEP vendor block creation
   - In-flight bill scan and exception-queue logic

6. **Mike approval signal delivery**:
   - System A event: trigger condition (email classification + current tracker state)
   - POST /approvals/{workflow_id} request body
   - Error handling and retry

7. **System B approval UI** (manual override):
   - Bill list view: fields to display (vendor, amount, project, gmail_tracker_id, draft date, mike_email_detected flag)
   - "Approve" button → POST /approvals/{workflow_id}
   - Auth

8. **System B bill-synced callback to System A**:
   - When exactly it fires (after qb_txn_id reconciled back OR after canonical Postgres commit?)
   - System A endpoint URL management (configurable env var)
   - Retry policy

9. **Ben's dashboard System B section**:
   - Anon RLS policies for bills + draw_packages (mirror of System A pattern)
   - JS Supabase client config for aihub project
   - Display fields and refresh cadence

10. **Deployment map** (from infrastructure addendum — already resolved):
    - Railway Service 1 (existing): Gmail FastAPI + new outbox job
    - Railway Service 2 (new): AI Accounting Hub API
    - Railway Service 3 (new): QBWC SOAP endpoint (post-spike)
    - Railway Service 4 (optional): NATS/JetStream (or embedded in Service 2)
    - Temporal Cloud: connection from Service 2
    - .qwc file: generated after Service 3 URL is stable

**Constraints to preserve (non-negotiable in all specs):**
- NO auto-send. Integration layer cannot touch System A's Gmail API or draft_queue. ABSOLUTE.
- bank_change_risk=True in System A → NO bill_intent outbox row. EVER.
- System B gates fail closed. No proof = no commit. EVER.
- STV CM LLC blocked independently in both systems.
- supabase-aihub MCP only for fdnwlcomuddzmluvbylg. NEVER confuse the two projects.
- Alembic migrations for System B → aihub only.
- QB writes only after human approval + valid proof_bundles.passed=True.

---

## 18. Handoff to O2O

**Build order (sequential gates — cannot parallelize past each gate):**

**Gate 0 (prerequisite, both systems):**
- Apply System A schema migration (integration_outbox + new tracker columns)
- Apply System B schema migration (bills.gmail_tracker_id + draw_packages.gmail_fee_opportunity_id)
- Issue inter-service bearer tokens (System A issues one for System B to use on /integration/bill-synced; System B issues one for System A to use on /intents/*)

**Phase 1 — Core pathway (Scenario 1 end-to-end):**
1. Build System B: POST /intents/bill (idempotent, starts Temporal)
2. Build System A: outbox writer (bill_intent trigger condition)
3. Build System A: outbox delivery job
4. Integration test: System A creates tracker → outbox → System B bill created → verify bills.gmail_tracker_id set
5. Build System B: approval UI + manual override path
6. Integration test: manual approve → Temporal signal → bill.status=approved
7. Build System B: bill-synced callback POST /integration/bill-synced
8. Build System A: POST /integration/bill-synced endpoint
9. E2E test: full Scenario 1 (without QBWC — canonical Postgres commit is the endpoint)

**Phase 2 — Bank block + Mike email signal (Scenarios 2, 3):**
10. Build System B: POST /intents/bank-block + in-flight bill exception routing
11. Build System A: outbox writer for bank_block event_type
12. Build System A: mike approval signal delivery (POST /approvals/{workflow_id})
13. Integration test: Scenario 3 (bank block) + Scenario 2 (in-person approval already covered in Phase 1)

**Phase 3 — Draw fee workflow (Scenario 4):**
14. Build System B: POST /intents/draw + draw engine CHUNK_6 activation
15. Build System A: outbox writer for draw_intent; STV CM LLC block guard
16. Integration test: Scenario 4 (draw fee, three company files)

**Phase 4 — Close the loop + dashboard (Scenario 5 + UI):**
17. Build System A: Aubrey confirmation → payment_confirmed outbox event
18. Build System B: payment-confirmed intake
19. Apply System B anon RLS for bills/draw_packages
20. Extend Ben's dashboard with System B section (second Supabase client)
21. E2E test: all 5 scenarios end-to-end

**Phase 5 — QBWC write-back (CRUX spike RESOLVED 2026-07-01 — business-hours/session-tied polling confirmed):**
22. ~~Measure QBWC poll cadence + queue depth on Rightworks (CRUX spike)~~ DONE — cadence is business-hours/session-tied, no persistent poller supported
23. ~~File Rightworks persistent-poller support ticket~~ DONE — response received; no persistent poller, no scheduled-task/service-account workaround
24. Deploy QBWC SOAP endpoint (Railway Service 3), targeting the sandbox company file first
25. Generate .qwc file with SOAP URL
26. Register in QBWC on Rightworks VPS (Ben's manual action)
27. E2E test with actual QB Desktop write-back

**Circular dependency break:**
- System B /intents/bill needs Temporal Cloud connection → set up Temporal Cloud FIRST (before Service 2 is deployed), add connection config to Service 2 env vars. Bootstrap: deploy Service 2 with Temporal config as env vars; Service 2 starts workers on startup.

---

## 19. Handoff to QA / Audit

**Critical paths requiring integration tests:**

1. **No-auto-send invariant** — Assert: after running the full integration layer (System A → System B → callback), query System A draft_queue; assert NO row has status='sent'. Run as part of every CI cycle.

2. **bank_change_risk hard stop** — Test: classify a bank-change email. Assert: (a) outbox row event_type=bank_block exists, (b) NO outbox row with event_type=bill_intent exists for same tracker_id, (c) System B reports ATEP block active for vendor.

3. **STV CM LLC double block** — Test: send a draw email from a vendor mapped to STV CM LLC. Assert: (a) System A fee_opportunities.blocked=True, (b) NO outbox row with event_type=draw_intent, (c) Manual call to System B POST /intents/draw with entity=STV CM LLC returns 400.

4. **Proof gate fail-closed** — Test: mock SwarmSync proof-core to return riskLevel=CRITICAL. Assert: bill never advances past drafted, exception queue entry created, no Temporal approval signal ever fires.

5. **Idempotency under duplicate delivery** — Test: deliver same bill_intent twice (same gmail_tracker_id). Assert: System B returns existing bill_id on second call; bills table has exactly ONE row for that gmail_tracker_id; audit_rows has ONE creation event.

6. **In-person approval override** — Test: trigger Temporal workflow via bill intent; call POST /approvals/{workflow_id} directly (simulating Ben's UI click); assert bill.status=approved WITHOUT any System A mike email event.

7. **Bill-synced callback idempotency** — Test: System B fires /integration/bill-synced twice for same tracker_id. Assert: System A tracker advances state exactly once; aihub_status is "synced" after both calls.

8. **Wrong DB guard** — Test: run a Alembic migration command and assert it targets fdnwlcomuddzmluvbylg (check DATABASE_URL in env); assert NOT ejxrbxoncsgglrqvjulg. Fail CI if wrong project ref.

9. **AIVS chain tamper rejection** — Test: manually alter an audit_row.prev_hash; run chain validation. Assert: validation fails; no further writes accepted until chain is restored.

10. **Outbox failure / retry** — Test: mock System B as returning 503; run outbox delivery job; assert outbox.attempts increments and status remains pending. After 5 attempts, assert alert is triggered.

**Money/auth/proof flows requiring end-to-end verification:**
- Every bill that reaches "approved" state in System B must have a `proof_bundles` row with `passed=True` and a valid VCAP proof_hash. Assertion: `SELECT COUNT(*) FROM bills b LEFT JOIN proof_bundles p ON b.invoiceproof_bundle_id = p.id WHERE b.status='approved' AND (p.passed IS NULL OR p.passed=FALSE)` must return 0.
- Every approval action must produce an `audit_rows` entry linking it to the prior hash. Chain validation (`verify.py`) must return 0 failures.
- No QB write (BillAdd) without a valid `qb_edit_sequence` on the vendor record. Assertion in adapter pre-flight check.

---

## 20. Final Architecture Verdict

```
╔══════════════════════════════════════════════════════════╗
║  VERDICT: READY_FOR_SPEC                                 ║
║                                                          ║
║  All 5 crux decisions are RESOLVED (see §5, §10).       ║
║  All 8 hard gates are CONFIRMED.                         ║
║  20 sections complete.                                   ║
║  G7 CHECK: 1 CRITICAL risk (QBWC spike) has a defined   ║
║  mitigation (escape to batch-ETL per FinalSpec §4.6).    ║
║  Integration layer architecture does not depend on the   ║
║  QBWC spike resolution — bills commit to canonical       ║
║  Postgres regardless.                                    ║
╚══════════════════════════════════════════════════════════╝
```

**Resolved crux decisions (summary for spec-superstar):**

**D1 — PAYMENT LIFECYCLE OWNERSHIP:**
Clean phase split. System A owns: email detection → tracker states Received through Payment Confirmed. System B owns: accounting states drafted → synced. Handoff point: "Received" → bill intent created. Close loop: System B callback advances tracker to "Booked / Ready to Book in QB". The two state machines are complementary, not competing.

**D2 — DATABASE ARCHITECTURE:**
KEEP FEDERATED. Two Supabase projects remain separate. Ben's dashboard extended with a second Supabase client pointing to aihub. Cross-system reporting uses `bills.gmail_tracker_id` as the join key. No DB merge needed.

**D3 — PROOF DEDUPLICATION:**
System B runs its own Gate 1 (VCAP Full Bundle — required for proof_bundles schema). System A's proof_results data is passed as `gmail_invoiceproof` pre-screening evidence in the bill intent payload. Two separate proof objects serving different purposes: advisory triage (A) vs. hard financial gate (B).

**D4 — EVENT BUS COUPLING:**
WEBHOOK + OUTBOX PATTERN. System A POSTs to System B (no NATS in System A). System B POSTs callback to System A. System A `integration_outbox` table provides durability when System B is down. Railway HTTP (HTTPS public URLs) connects the two services.

**D5 — MIKE APPROVAL SIGNAL:**
Two-path solution. Path A (email): System A detects → fires POST /approvals/{workflow_id} → Temporal signal. Path B (in-person): Ben uses System B approval UI → same POST /approvals/{workflow_id} directly. System A stores workflow_id after /intents/bill response. System B's approval gate is the hard gate; System A's detection is one of two valid signal sources.

**Pre-existing blockers — RESOLVED 2026-07-01 (not integration blockers — System B internal):**
- ~~QBWC poll cadence measurement on Rightworks~~ RESOLVED: business-hours, session-tied polling only; no persistent poller exists or is supported (Rightworks written confirmation)
- ~~Rightworks persistent-poller support ticket~~ RESOLVED: response received — not supported; scheduled-task/service-account workaround explicitly declined
Both are documented in FinalSpec.md §4.6 and §14, and now resolved there. Write-back adapter code (Phase 6) is unblocked to proceed under the business-hours cadence model.

---

*Packet written by: System Architecture Governor v1.2.0*
*Session: STV Integration Layer Governance — 2026-06-29*
*Next step: Run master-integration-engineer skill with Section 17 as primary input.*
