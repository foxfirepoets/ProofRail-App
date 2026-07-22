# Integration Architecture Packet
## STV Gmail AccountingOS × AI Accounting Hub — Full Integration
### Produced by: master-integration-engineer v1.2.0
### Date: 2026-06-29
### Governed by: system-architecture-governor (READY_FOR_SPEC verdict, 2026-06-29)
### Companion: architecture-decision-packet-stv-integration-layer-2026-06-29.md

---

## INTAKE CONFIRMATION

All 10 diagnostic questions answered from provided context. Zero assumptions required for blocking questions Q1–Q4.

| Q | Question | Answer Source | Status |
|---|---|---|---|
| Q1 | Systems | FinalSpec.md + CLAUDE.md + code | CONFIRMED |
| Q2 | Source of truth | Governor packet §5 | CONFIRMED |
| Q3 | Data types | main.py + payment_tracker.py + spec | CONFIRMED |
| Q4 | Triggers | rules.py + main.py + outbox design | CONFIRMED |
| Q5 | Stakes | CURRENT_ACCOUNTING_FIRE_LIST.md + spec | CONFIRMED |
| Q6 | Approval gates | payment_tracker.py HUMAN_REQUIRED_STATES + FinalSpec §5 | CONFIRMED |
| Q7 | Volume | FinalSpec §8 (~10 bills/day), Temporal free tier | CONFIRMED |
| Q8 | Current process | Stage 1 deliverables + MEMORY.md §4 | CONFIRMED |
| Q9 | Constraints | CLAUDE.md hard rules + FinalSpec §2 | CONFIRMED |
| Q10 | Proof requirement | FinalSpec §9 VCAP/AIVS + SwarmSync proof-core | CONFIRMED |

---

## 1. Integration Goal

This integration eliminates the manual handoff between the STV Gmail AccountingOS (which detects and classifies accounting events from email) and the AI Accounting Hub (which writes verified, proof-gated entries to QuickBooks Enterprise Desktop). Without this integration, email-detected invoices, draw packages, Mike approvals, and payment confirmations require Ben Stone to manually translate information between two systems — a process that creates the same category of entry errors and missed developer fees that both systems were built to eliminate.

With this integration in place, a Porter payment request email automatically becomes a canonical bill in Postgres (with a VCAP-signed InvoiceProof gate), a Mike approval email automatically signals the Temporal workflow that was waiting for it, a construction draw email automatically triggers the 5%/2%/1% fee split calculation across three company files, and a bank-change email automatically blocks the payment path in both systems simultaneously — all without Ben having to manually bridge the two systems. The business outcome is a fully auditable, proof-gated AP and draw-fee workflow where the only manual steps are the ones that must legally remain human (Ben reviews drafts, Mike approves, Aubrey wires).

---

## 2. Systems Connected

| System | Version / Tier | Hosting | API Available | API Type | Rate Limits |
|---|---|---|---|---|---|
| STV Gmail AccountingOS (System A) | Python 3.12 / FastAPI, Stage 5 | Railway (exemplary-tenderness-production.up.railway.app) | YES | REST (FastAPI) + Supabase | None enforced (internal) |
| AI Accounting Hub (System B) | Python 3.11 / FastAPI, early build | Railway (planned, new service) | YES (planned) | REST (FastAPI) + Temporal Cloud | None enforced (internal) |
| Supabase Gmail DB | Postgres, managed | Supabase cloud (ejxrbxoncsgglrqvjulg) | YES | supabase-py + REST | Free tier limits (500MB, 2 connections) |
| Supabase aihub DB | Postgres, managed | Supabase cloud (fdnwlcomuddzmluvbylg) | YES | supabase-py + Alembic | Free tier limits |
| SwarmSync proof-core | In-process library + hosted REST | Owner-operated (Ben owns SwarmSync) | YES | In-process (zero HTTP) + REST | $0 (owner-operated) |
| Temporal Cloud | Free tier | Temporal cloud | YES | Temporal SDK (Python) | 10k workflow actions/month |
| NATS/JetStream | v2.x | Railway Service 4 (or embedded in Service 2) | YES | NATS client | None at this volume |
| QuickBooks Enterprise Desktop | v24.0 | Rightworks VPS (cloud-hosted Windows RDS) | QBWC ONLY | SOAP/qbXML outbound poll | One company file per session; poll cadence RESOLVED 2026-07-01: business-hours, session-tied only (no persistent poller — see below) |
| Gmail (stone@ + adam@) | Gmail API v1 | Google cloud | YES (drafts only) | REST (OAuth2) | 250 quota units/second |
| Google Apps Script (GAS Poller) | GAS runtime | Google cloud | YES | GAS runtime triggers | 6 min execution limit; 90 executions/day |

**QuickBooks Desktop / Rightworks constraints:**
- QB Desktop is NOT a web service. No REST API. Cannot receive webhooks. All writes are polling-based via QBWC.
- Rightworks forbids inbound connections and persistent daemons without a support ticket.
- One company file open per session. Multiple company files require sequential session switches (30–120s each).
- QBWC must be registered with a .qwc file. The .qwc file requires a stable, deployed SOAP endpoint URL — this is a LATE BUILD ARTIFACT.
- **CRUX SPIKE — RESOLVED 2026-07-01 (Rightworks support ticket, written confirmation):** no persistent/unattended poller exists or will be supported. QuickBooks + QBWC auto-open on hosted-session login (Rightworks will configure). Rightworks enforces a global, non-adjustable 2-hour inactivity timeout that fully logs out the session (ending QuickBooks + QBWC with it) regardless of disconnect-vs-signout. Rightworks explicitly declined to confirm/support a Windows Scheduled Task / service-account workaround, redirecting to Intuit. **Final design: business-hours, session-tied polling** — QBWC polls on its configured interval only while a human's normal login session is active; off-hours items queue in canonical Postgres. Write-back adapter code is UNBLOCKED — proceed with this cadence model, not an open spike.

---

## 3. Source of Truth

| Data Type | Source-of-Truth System | Justification |
|---|---|---|
| Email event (received, classified) | System A — email_messages, email_classifications | Gmail is the origin; System A's rule classifier is the authoritative detection layer. System B never classifies emails. |
| Payment communication lifecycle (Received → Payment Confirmed) | System A — payment_request_tracker | This tracks communication state (drafts sent, Mike notified, Aubrey confirmed). System B has no visibility into email thread state. |
| Vendor invoice accounting (bill drafted → synced) | System B — bills | System B owns the accounting lifecycle and runs the hard proof gates. System A stores a display mirror only (aihub_status). |
| Vendor identity | System B — vendors (synced from QB via QBWC read path) | QB Desktop is the legal AP vendor master. System B vendors mirrors QB, normalizes it, and adds bank_fingerprint + swarmscore. System A's vendor_name is free-text intake only — never master. |
| Bank change block / ATEP status | BOTH (defense in depth) | System A blocks intent creation (no bill_intent if bank_change_risk_flag=True). System B blocks payment path (ATEP gate on vendors). Both blocks are independent; neither trusts the other alone. |
| Draw fee calculation (5%/2%/1%) | System B — draw_packages + draw engine CHUNK_6 | System B recalculates exactly per QB spec §5.3. System A's estimated_fee (5% heuristic in fee_opportunities) is display-only triage; never the accounting calculation. |
| Proof bundles (Gate 1/2/3) | System B — proof_bundles | System A's proof_results is an advisory pre-screening log (non-VCAP, no proof_hash). System B's proof_bundles are the formal VCAP Full Bundles that gate approval. |
| QB write-back state (TxnID, EditSequence) | QB Desktop (via System B reconciliation) | QB is the eventually-consistent sink. System B stores TxnID/EditSequence after write-back. System A stores qb_txn_id for display only. |
| STV CM LLC block status | System A (fee_agent.blocked=True) + System B (draw engine hard block) | Both systems independently block. Not a SoT conflict — redundant safety on a critical fraud/error prevention rule. |
| Audit chain (tamper-evident) | System B — audit_rows (AIVS SHA-256 hash chain) | System A's automation_audit_log is an operational event log (non-cryptographic). System B's AIVS chain is the financial proof spine. |
| Draft queue | System A — draft_queue | System B has zero access to this table. Integration layer never writes here. CHECK constraint (status != 'sent') is absolute. |
| Cost codes / Chart of Accounts | QB Desktop (authoritative) → System B catalogs (canonical mirror) | QB spec §6.1–6.7 defines the COA; cost codes 001–069 are imported into System B as the seed catalog. System A has no cost code awareness. |

**Multi-data-type SoT verification:** 3-question framework applied to every row above. No "both" answers exist except the intentional defense-in-depth blocks (bank change, STV CM LLC), which are documented as redundant safety — not SoT conflicts.

---

## 4. Current Process (Before Integration)

```
PORTER PAYMENT REQUEST FLOW (current):
Step 1:  Porter emails invoice PDF to stone@summaterraventures.com
Step 2:  System A classifies email, creates payment_request_tracker, drafts Template 1
Step 3:  Ben reads Template 1 draft, manually reviews invoice PDF
Step 4:  Ben manually emails/texts Mike for approval
Step 5:  Mike replies "This is approved" (System A detects this, updates tracker)
Step 6:  Ben manually creates Template 2 draft for Aubrey, reviews, sends
Step 7:  Aubrey executes wire/ACH manually from bank
Step 8:  Aubrey confirms by email (System A detects, updates tracker)
Step 9:  Ben manually logs into QuickBooks on Rightworks VPS
Step 10: Ben manually creates Bill in QB (vendor, amount, account code, class, job)
Step 11: Ben manually marks as paid in QB
Step 12: Ben updates Google Sheets reconciliation tracker

PAIN POINTS:
- Steps 9-12 are entirely manual and must be repeated for each vendor payment
- No proof that QB entry matches the original invoice amount/vendor
- No automated link between System A tracker and QB transaction
- No duplicate prevention on the QB write
- Developer fee opportunity tracking is manual (fee_opportunities in System A is detection only)

DRAW PACKAGE FLOW (current):
Step 1:  Lauren Farnsworth emails draw package PDF
Step 2:  System A classifies, creates fee_opportunities row (5% estimate), Template 6 draft
Step 3:  Ben manually reviews draw package
Step 4:  Ben manually calculates 5% developer fee, 2% CM fee, 1% President fee
Step 5:  Ben manually creates journal entries in QB for each of three company files
Step 6:  No automated verification that fee entries match draw total
Step 7:  No audit trail linking draw email to QB journal entries

PAIN POINTS:
- Steps 4-6 require manual calculation and triple QB entry (three company files)
- Fee calculation errors possible; no systematic duplicate detection
- No proof chain from draw email to QB JEs
```

---

## 5. Target Process (After Integration)

```
PORTER PAYMENT REQUEST FLOW (future):
Step 1:  Porter emails invoice PDF to stone@                              [UNCHANGED]
Step 2:  System A classifies, creates tracker, Template 1 draft          [UNCHANGED]
Step 3:  System A outbox: bill_intent written (bank_change_risk=False)   [NEW - automated]
Step 4:  Outbox delivery job: POST /intents/bill to System B             [NEW - automated]
Step 5:  System B: creates bill (gmail_tracker_id linked), starts Temporal [NEW - automated]
Step 6:  System B: InvoiceProof Gate 1 (VCAP Full Bundle)               [NEW - automated]
Step 7:  Temporal blocks — awaiting approval signal                      [NEW - automated]
Step 8a: Mike replies "This is approved" → System A detects              [UNCHANGED detection]
Step 8b: System A fires POST /approvals/{workflow_id} → Temporal signal  [NEW - automated]
        OR:
Step 8b: Ben clicks "Approve" in System B UI (in-person path)           [NEW - manual override]
Step 9:  System B: bill → approved, AuditProof (AIVS), canonical commit  [NEW - automated]
Step 10: QBWC adapter queues BillAdd; QB Desktop updated on next poll    [NEW - automated]
Step 11: System B: bill → synced; fires POST /integration/bill-synced   [NEW - automated]
Step 12: System A: tracker → "Booked / Ready to Book in QB"             [NEW - automated]
Step 13: Ben sends Template 2 draft to Porter (manual send)              [UNCHANGED - Ben sends]

ELIMINATED: Steps 9-12 of current process (manual QB entry, manual Sheets update).
REMAINING MANUAL: Ben reviews/sends drafts (guardrail — never auto-send).
                  Mike's approval (human gate — never automated).
                  Aubrey's wire execution (human gate — never automated).

DRAW PACKAGE FLOW (future):
Step 1:  Lauren emails draw package                                       [UNCHANGED]
Step 2:  System A classifies, creates fee_opportunities, Template 6      [UNCHANGED]
Step 3:  System A outbox: draw_intent (not STV CM LLC, fee_payee_status check) [NEW]
Step 4:  Outbox delivery: POST /intents/draw to System B                 [NEW - automated]
Step 5:  System B draw engine CHUNK_6: exact 5%/2%/1% calculation       [NEW - automated]
Step 6:  Three fee bill intents created (one per company file)           [NEW - automated]
Step 7:  Human approval gate (Mike + CM sign-off) per fee bill           [UNCHANGED - required]
Step 8:  AuditProof (AIVS hash chain) → QBWC queued for 3 files        [NEW - automated]
Step 9:  System B callback: draw → funded status; System A updated       [NEW - automated]

ELIMINATED: Manual fee calculation (Step 4 current), manual triple-QB-entry (Step 5 current).
```

---

## 6. Object Mapping

| Source System | Source Object | Destination System | Destination Object | Notes |
|---|---|---|---|---|
| System A | payment_request_tracker row | System B | bills row | Via integration_outbox bill_intent → POST /intents/bill. gmail_tracker_id is the join key. |
| System A | fee_opportunities row | System B | draw_packages row | Via integration_outbox draw_intent → POST /intents/draw. gmail_fee_opportunity_id is the join key. |
| System A | email_classifications (bank_change_risk=True) | System B | vendors ATEP block | Via integration_outbox bank_block → POST /intents/bank-block. Vendor identified by sender_email + vendor_name. |
| System A | email_classifications (Mike approval detected) | System B | Temporal workflow signal | Via POST /approvals/{workflow_id}. workflow_id stored on payment_request_tracker.aihub_workflow_id. |
| System A | payment_request_tracker (Aubrey confirmed) | System B | bills.status="paid" | Via integration_outbox payment_confirmed → POST /intents/payment-confirmed. |
| System A | proof_results row (advisory) | System B | proof_bundles.payload.gmail_invoiceproof | Carried as nested object in bill intent payload. Pre-screening evidence only — not the gate itself. |
| System B | bills.status="synced" + qb_txn_id | System A | payment_request_tracker.current_status + aihub_status | Via POST /integration/bill-synced callback. |
| System B | draw_packages.status="funded" | System A | fee_opportunities (display update) | Via callback — informational only. |
| System B | bills (all) | Ben's dashboard | bills display section | Via Supabase anon RLS on aihub DB — read-only. |
| System B | draw_packages (all) | Ben's dashboard | draw fee display section | Via Supabase anon RLS on aihub DB — read-only. |
| QB Desktop | Vendor list (ListID, Name, EditSequence) | System B | vendors table | Via QBWC read path (Phase 1 read-only sync, already designed in FinalSpec §5). |
| QB Desktop | Bills (TxnID) | System B | bills.qb_txn_id | Written back after BillAdd via QBWC. Reconciled into canonical record. |

---

## 7. Field Mapping

### Bill Intent: payment_request_tracker → POST /intents/bill payload

| Source Field | Source System | Source Format | Destination Field | Destination System | Transform Required | Nullable |
|---|---|---|---|---|---|---|
| id | payment_request_tracker | UUID | gmail_tracker_id | bills | None (carry as-is) | NO — dedup key |
| vendor_name | payment_request_tracker | Free-text VARCHAR(100) | vendor_name | bills intent payload | Trim + normalize whitespace; fuzzy-match to vendors table | NO |
| amount | payment_request_tracker | DECIMAL(14,2) — may be NULL if not detected | amount | bills | Validate > 0; NULL → route to human review queue, do not create bill | YES (if NULL, hold) |
| invoice_number | payment_request_tracker | VARCHAR extracted from subject | po_ref | bills | Map invoice_number → po_ref; trim | YES |
| due_date | payment_request_tracker | ISO date string or NULL | due_date | bills raw_extensions | Date validation (within fiscal year ± 1 year); NULL allowed | YES |
| project_id | payment_request_tracker | Label string (e.g. "Madison Park") | raw_extensions.project_label | bills | Carry as-is in raw_extensions; System B maps to Customer:Job | YES |
| risk_level | proof_results | VARCHAR("low"/"medium"/"high"/"critical") | gmail_invoiceproof.risk_level | bills intent payload | Carry as-is | NO |
| final_decision | proof_results | VARCHAR("approved"/"flagged"/"blocked") | gmail_invoiceproof.final_decision | bills intent payload | If "blocked" → System B rejects bill intent with 422 | NO |
| checks_passed | proof_results | INT (0-7) | gmail_invoiceproof.checks_passed | bills intent payload | Carry as-is | NO |
| bank_change_risk | proof_results | BOOL | gmail_invoiceproof.bank_change_risk | bills intent payload | If True → System B rejects with 400; outbox should never send this | NO |
| duplicate_detected | proof_results | BOOL | gmail_invoiceproof.duplicate_detected | bills intent payload | If True → System B flags bill for human review | NO |
| vendor_confidence | proof_results | FLOAT (0.0–1.0) | gmail_invoiceproof.vendor_confidence | bills intent payload | Carry as-is | NO |
| source_thread_id | payment_request_tracker | Gmail thread ID | raw_extensions.gmail_thread_id | bills | Carry for audit trail | YES |
| source_email_id | payment_request_tracker | Gmail message ID | raw_extensions.gmail_message_id | bills | Carry for audit trail | YES |
| requested_by_email | payment_request_tracker | Email address | raw_extensions.requested_by_email | bills | Carry as-is | YES |

**Full bill intent JSON schema:**
```json
{
  "gmail_tracker_id": "uuid",
  "vendor_name": "string (normalized)",
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
    "checks_passed": 0,
    "bank_change_risk": false,
    "duplicate_detected": false,
    "vendor_confidence": 0.0
  }
}
```

### Draw Intent: fee_opportunities → POST /intents/draw payload

| Source Field | Source System | Source Format | Destination Field | Destination System | Transform | Nullable |
|---|---|---|---|---|---|---|
| email_id | fee_opportunities | Gmail message ID | gmail_fee_opportunity_id (via row id) | draw_packages | Carry fee_opportunities.id as foreign key | NO |
| project_canonical | fee_opportunities | VARCHAR | project_canonical | draw_packages | Trim + normalize | NO |
| draw_amount | fee_opportunities | DECIMAL or NULL | draw_amount | draw_packages | If NULL → reject draw intent; require human to set amount | YES (hold if NULL) |
| estimated_fee | fee_opportunities | DECIMAL (5% heuristic) | estimated_fee_hint | draw_packages | Advisory only; System B recalculates exact amount | YES |
| fee_payee | fee_opportunities | VARCHAR | fee_payee_hint | draw_packages | Advisory; System B validates against entity map | YES |
| fee_payee_status | fee_opportunities | "CONFIRMED"/"UNCERTAIN"/"BLOCKED" | fee_payee_status | draw_packages | BLOCKED → reject; UNCERTAIN → route to human before fee entry | NO |
| blocked | fee_opportunities | BOOL | [guard] | [outbox writer] | If True → DO NOT write draw_intent outbox row. Hard stop. | NO |
| thread_id | fee_opportunities | Gmail thread ID | raw_extensions.gmail_thread_id | draw_packages | Carry for audit | YES |

**Critical QB-specific field notes:**
- System B maps project_canonical → Customer:Job (QB field) using the canonical lookup table
- System B maps cost codes to QB expense account ListIDs using the cost-code catalog (001–069 seed data)
- System B's draw engine calculates exact fee amounts per QB spec §5.3; estimated_fee from System A is a triage hint only
- STV CM LLC check: if fee_payee resolves to "STV CM LLC" in System B entity map → hard reject 400

### Approval Signal: System A → System B

| Data | Type | Notes |
|---|---|---|
| workflow_id | VARCHAR(128) | Stored on payment_request_tracker.aihub_workflow_id after /intents/bill response |
| decision | "approve" or "reject" | Always "approve" for email-detected Mike approval |
| source | "email_detected" or "manual_ui" | Distinguishes email path (A) from manual path (B UI) |
| evidence_email_id | VARCHAR | Gmail message ID of Mike's approval email (Path A) or null (Path B) |
| note | VARCHAR | "Mike approval language detected: 'this is approved'" (Path A) or Ben's note (Path B) |

### Bill-Synced Callback: System B → System A

| Data | Type | Notes |
|---|---|---|
| tracker_id | UUID | payment_request_tracker.id (= bills.gmail_tracker_id) |
| bill_id | UUID | bills.id |
| qb_txn_id | VARCHAR(128) | QB TxnID from BillAdd response |
| status | "synced" or "paid" | "synced" = QB write-back complete; "paid" = payment reconciled |

**QB company file migration risk:** qb_txn_id is stored as a secondary reference only. The primary integration dedup key is gmail_tracker_id (bills.gmail_tracker_id UNIQUE). If the QB company file is ever migrated, qb_txn_id will change — that is a QB-side concern; the canonical bill.id and gmail_tracker_id remain stable.

---

## 8. Trigger Design

| Trigger | System | Type | Frequency | Reliability | Latency SLA |
|---|---|---|---|---|---|
| New Porter payment request email | System A (GAS Poller → /classify) | Scheduled poll | 1-min cadence (GAS trigger) | 99%+ (GAS) | < 2 min email → tracker created |
| Mike approval email detected | System A (/classify → payment tracker transition) | Event-driven (on email poll) | Per email | 99%+ | < 2 min email → approval signal fired |
| Bank change email detected | System A (/classify → bank_change_risk=True) | Event-driven | Per email | 99%+ | < 2 min (P0, highest priority) |
| Draw package email detected | System A (/classify → fee_opportunities) | Event-driven | Per email | 99%+ | < 2 min email → draw_intent queued |
| Aubrey confirmation email | System A (/classify → tracker transition) | Event-driven | Per email | 99%+ | < 2 min email → payment_confirmed queued |
| Outbox delivery job | System A (background job) | Scheduled | Every 1 min (same as poller) | 99% (Railway) | < 1 min outbox → System B delivery |
| System B bill_synced callback | System B (after QBWC write-back) | Event-driven | Per bill synced | 99% (Railway HTTP) | < 1 min System B → System A callback |
| QBWC poll (System B SOAP endpoint) | QB Web Connector on Rightworks | Scheduled outbound poll | TBD (CRUX spike — target 30 min) | 95% (Rightworks session risk) | < 30 min bill approved → QB updated |
| Temporal workflow timeout/escalation | System B | Timer (Temporal) | Per workflow | 99.9% (Temporal Cloud) | 48h SLA for approval before escalation |

**Trigger risk assessment:**
- GAS poller: 1-min cadence is aggressive; 6-min execution limit per run is not an issue for single-email classify calls. Risk: GAS quota (90 executions/day = sufficient for business hours). Mitigation: monitor quota usage.
- QBWC poll: greatest scheduling uncertainty — depends on CRUX spike. Rightworks session idle timeout is the primary risk. Mitigation: Rightworks support ticket for QB + QBWC auto-start.
- Outbox delivery job: runs in Railway Service 1 process; Railway container restarts reset in-memory state — outbox is DB-backed, so restarts are safe.

**QB Desktop scheduling constraint:** QBWC poll is the ONLY write mechanism. 5–30 minute minimum practical interval on Rightworks. Real-time QB updates are architecturally impossible. Bills commit to canonical Postgres immediately (synchronous); QB Desktop is eventually-consistent.

---

## 9. Sync Direction

| Data Type | Direction | Conflict Resolution | Re-sync Policy |
|---|---|---|---|
| Bill intent (invoice) | A → B (one-way push via webhook) | System B is authoritative on accounting; System A display mirrors aihub_status | If delivery fails: outbox retries max 5×. If all fail: alert; manual re-submit via System B UI |
| Draw fee intent | A → B (one-way push) | System B is authoritative on fee calculation | Same retry policy |
| Bank change block | A → B (one-way push) | Both systems block independently; System B ATEP is authoritative for payment path | System A does not re-sync; each classification event fires once |
| Mike approval signal | A → B (one-way push) | System B Temporal gate is authoritative; System A fires a signal, not a command | If signal delivery fails: retry 3×; Ben uses manual UI as fallback |
| Bill-synced callback | B → A (one-way callback) | System A mirrors aihub_status for display; never overrides System B | If callback fails: System B retries 3×; daily reconciliation job as backstop |
| QB vendor list | QB → B (read-only sync, QBWC) | QB is master vendor list; System B mirrors + enriches | Full refresh on each QBWC read cycle |
| QB write-back (bills, JEs) | B → QB (QBWC adapter) | QB wins on EditSequence conflict (re-base and retry once) | Temporal retains state; replays on next poll cycle |
| Ben's dashboard data (System B) | B → dashboard (read-only Supabase anon RLS) | System B is always authoritative; dashboard reads only | Auto-refresh every 60s (same pattern as System A dashboard) |

---

## 10. Auth and Credentials

| System | Auth Method | Credential Storage | Rotation Policy | Who Manages |
|---|---|---|---|---|
| System A FastAPI (/classify, /integration/*) | Bearer token (CLASSIFIER_BEARER_TOKEN) | Railway env vars | On compromise | Ben / Railway admin |
| System B FastAPI (/intents/*, /approvals/*) | Bearer token (AIHUB_API_KEY, sa_* self-issued) | Railway env vars + .env | On compromise | Ben / Railway admin |
| System A → System B (outbox delivery) | Bearer token: System A holds AIHUB_OUTBOX_TOKEN | Railway env var (System A) | On compromise | Ben |
| System B → System A (bill-synced callback) | Bearer token: System B holds SYSTEM_A_CALLBACK_TOKEN | Railway env var (System B) | On compromise | Ben |
| Supabase Gmail DB (ejxrbxoncsgglrqvjulg) | SUPABASE_SERVICE_ROLE_KEY (API) + ANON key (dashboard) | Railway env vars | Annual or on compromise | Ben |
| Supabase aihub DB (fdnwlcomuddzmluvbylg) | SUPABASE_SERVICE_ROLE_KEY (aihub) + ANON key (dashboard section) | Railway env vars (Service 2) | Annual or on compromise | Ben |
| SwarmSync proof-core (System B, in-process) | Self-issued sa_* key (X-API-Key header) | .env + Railway env var | On compromise | Ben (owner-operated SwarmSync) |
| Temporal Cloud | TEMPORAL_NAMESPACE, TEMPORAL_API_KEY | Railway env var (Service 2) | Per Temporal Cloud rotation | Ben |
| NATS/JetStream | Username/password or token | Railway env var | Annual | Ben |
| Gmail OAuth2 (System A) | OAuth2 refresh token (GOOGLE_REFRESH_TOKEN) | Railway env var | Annual (Google forces reauth) | Ben |
| GAS Poller → /classify | CLASSIFIER_BEARER_TOKEN in GAS script properties | GAS Script Properties (encrypted) | On compromise | Ben |
| QBWC registration | Username/password in .qwc file | .qwc file (stored on Rightworks VPS) | On app re-registration | Ben |

**Security rules enforced:**
- No credentials stored in code, Git, or Google Sheets.
- Two separate Supabase service role keys — one for each project. Never swap them.
- supabase-aihub MCP only connects to fdnwlcomuddzmluvbylg. The supabase (default) MCP connects to SwarmSync — never use it for System B work.
- System B's dashboard section uses the aihub ANON key (publishable, RLS-protected) — not the service role key.
- QBWC credential (username/password in .qwc) is per-application, per-company-file. Generate fresh GUIDs for OwnerID and FileID.

---

## 11. Validation Rules

### Outbox Writer (System A — enforced before writing any outbox row)

| Rule | Check | On Failure |
|---|---|---|
| Bank change guard | payment_request_tracker.bank_change_risk_flag MUST be False | DO NOT write bill_intent row. Write bank_block row instead. |
| Blocked state guard | tracker.current_status NOT IN BLOCKED_STATES | DO NOT write any intent row. Log to audit. |
| STV CM LLC guard (draw) | fee_opportunities.blocked MUST be False | DO NOT write draw_intent row. Log to audit. |
| Amount present (bill) | tracker.amount IS NOT NULL AND > 0 | Write outbox row with flag: amount_missing=True. System B holds bill in manual review. |
| No duplicate outbox | integration_outbox: no existing pending/delivered row for same tracker_id + event_type | Skip (idempotent). Log deduplicated event. |
| Tracker status precondition | For bill_intent: tracker.current_status IN ('Received', 'Ready for Ben Review') | Only create intent when tracker is in a forward-moving state |

### System B Intake (POST /intents/bill — enforced before creating any bill)

| Rule | Check | On Failure |
|---|---|---|
| Bank change hard reject | gmail_invoiceproof.bank_change_risk = True | Return 400: "Bank change risk — intent rejected" |
| Proof blocked hard reject | gmail_invoiceproof.final_decision = "blocked" | Return 422: "InvoiceProof blocked — intent rejected" |
| Idempotency | bills.gmail_tracker_id already exists | Return 200 with existing {bill_id, workflow_id}. No new bill. |
| Amount validation | amount > 0 AND is numeric | If NULL or ≤ 0: create bill with status=drafted, flag amount_review=True, notify Ben |
| Vendor fuzzy match | pg_trgm similarity(vendor_name, vendors.name) ≥ 0.75 | If no match above threshold: create soft-draft vendor (unconfirmed=True), hold for Ben |
| Company lookup | Derive company_id from project_label or default entity | If can't determine: hold in manual_review queue |
| Due date range | due_date within (today - 365) to (today + 365) | Out-of-range: flag for human review; do not reject |

### System B Intake (POST /intents/draw)

| Rule | Check | On Failure |
|---|---|---|
| STV CM LLC block | fee_payee matches "stv cm llc" (case-insensitive) | Return 400: "STV CM LLC blocked" |
| Fee payee status | fee_payee_status != "BLOCKED" | Return 400 |
| Draw amount | draw_amount > 0 | Return 422 if null or ≤ 0 |
| Idempotency | draw_packages.gmail_fee_opportunity_id already exists | Return 200 with existing draw_package_id |
| Fee split math | 5% + 2% + 1% = 8% of draw_amount = three fee bills; sum must equal calculated total | Fail closed: do not create fee bills if math fails; alert Ben |

---

## 12. Approval Gates

| Gate | What Requires Approval | Approver | Channel | SLA | Escalation |
|---|---|---|---|---|---|
| Bill commit (every bill) | Any bill advancing from verified → approved | Mike Watson (email detected) OR Ben (manual UI override) | Email (System A detects) OR System B approval UI | 48 hours | Ben escalates after 48h stale; Temporal escalation timer fires P1 alert |
| Draw fee (all three fee bills) | Each of three fee bill intents from draw engine | Mike + CM sign-off (per QB spec — owner-confirmed) | System B approval UI (one gate per company file) | 48 hours | Same escalation as above |
| In-person approval override | When Mike approves verbally (no email) | Ben Stone (clicks "Manually Approve" in System B UI) | System B approval UI (bills list with amount, vendor, project, draft date) | Immediate when Ben opens UI | N/A — Ben is the override actor |
| Vendor amount = NULL | Bill intent with no amount detected | Ben Stone (manual review in System B UI) | System B approval UI (amount_review queue) | 24 hours | Alert after 24h |
| Vendor unmatched | vendor_name fuzzy match fails | Ben Stone (vendor confirmation in System B UI) | System B vendor review queue | 24 hours | Alert after 24h |
| Bank change clearance | After bank_change_risk P0 fires | Ben Stone (manual clearance in BOTH systems) | System A: manual DB/UI. System B: admin UI to remove ATEP block. | No SLA — manual by design | None — no payment path exists until cleared |
| STV CM LLC (draw) | If STV CM LLC somehow appears in draw intent | Auto-reject — no human gate needed | System B returns 400; outbox writer never creates this | N/A | Audit alert if STV CM LLC ever appears in draw_intent outbox |

**Hard rule:** No payment gate is automated. Mike Watson's email detection in System A fires a Temporal signal — it does not bypass the gate. The Temporal workflow must be in the correct state (bill=verified) before the signal is accepted. If a signal arrives for a workflow that is not at the approval gate, it is queued until the gate is reached.

---

## 13. Idempotency and Duplicate Prevention

| Entity | Dedup Key | Storage | Check-Before-Create | On Duplicate |
|---|---|---|---|---|
| integration_outbox row | tracker_id + event_type (UNIQUE constraint) | System A Supabase | Yes — INSERT ... ON CONFLICT DO NOTHING | Log dedup event; return existing row |
| bills (System B) | gmail_tracker_id (UNIQUE constraint on bills table) | System B Supabase | Yes — /intents/bill checks bills.gmail_tracker_id | Return 200 + existing {bill_id, workflow_id} |
| draw_packages (System B) | gmail_fee_opportunity_id (UNIQUE constraint) | System B Supabase | Yes — /intents/draw checks draw_packages.gmail_fee_opportunity_id | Return 200 + existing draw_package_id |
| proof_bundles (System B) | bill_id + kind (UNIQUE) | System B Supabase | Temporal activity checks before creating | Return existing bundle; do not re-run Gate 1 |
| audit_rows (System B AIVS chain) | row_hash (UNIQUE) | System B Supabase | SHA-256 is deterministic; collision = tamper | Hard error — AIVS chain broken; rollback |
| bill-synced callback | tracker_id + status="synced" (idempotent endpoint) | System A tracker aihub_status | System A: if aihub_status already = "synced", return 200 no-op | Return 200; no state change |
| QBWC BillAdd | qb_txn_id (reconciled back after first write) | System B bills.qb_txn_id | Adapter checks if qb_txn_id is already set before queuing BillAdd | Skip write; log duplicate-detected |

**QB company file migration risk:** If QB company file is migrated, qb_txn_id changes. bills.gmail_tracker_id (not qb_txn_id) is the canonical dedup key. System B must check gmail_tracker_id first; qb_txn_id is a secondary reference that may be stale after migration.

**Webhook idempotency (outbox delivery):**
1. Outbox writer: INSERT ... ON CONFLICT (tracker_id, event_type) DO NOTHING
2. Outbox delivery job: marks row sent_at + status=delivered after 2xx from System B
3. System B /intents/bill: if gmail_tracker_id exists in bills → return 200 with existing bill_id (do not create duplicate)
4. System A /integration/bill-synced: if aihub_status already "synced" for same tracker_id → return 200 no-op

---

## 14. Failure Handling

| Failure Scenario | Detection | Immediate Action | Recovery | Notify Who |
|---|---|---|---|---|
| System B down when outbox fires | HTTP 5xx or connection refused | Mark outbox row: attempts+1, status=pending | Retry with exponential backoff (1→2→4→8→16 min, max 5 attempts) | Alert Ben's dashboard at attempt 3; email alert at attempt 5 |
| Mike approval signal: System B 5xx | HTTP 5xx from POST /approvals/{workflow_id} | Retry 3× with 30s delay | After 3 failures: log "approval_signal_failed" on tracker; show warning in Ben's dashboard | Ben (visual dashboard warning) |
| Temporal workflow stuck: no approval in 48h | Temporal escalation timer fires | Temporal sends P1 alert to Google Chat | Ben reviews System B approval UI; manually approves or rejects | Ben (P1 Google Chat alert) |
| Bank block arrives after bill intent was already delivered | Outbox processes bank_block after bill_intent | System B /intents/bank-block scans for in-flight bill with same vendor_name; flags it | System B moves flagged bill to exception queue; P0 alert | Ben (P0 alert) |
| QBWC poll stalled (Rightworks session killed) | GET /sync/health shows sync_lag > threshold | Temporal retains approved bills in queue; no data loss | Rightworks session restart; QBWC auto-polls on reconnect | Ben (sync lag alert); IT |
| QB EditSequence conflict at write | QBWC BillAdd returns conflict error | Re-read QB vendor ListID + EditSequence; retry BillAdd once | If still fails after retry: route to human exception queue | Ben (exception queue) |
| AIVS hash chain broken | chain validation fails before GL commit | Hard rollback; no bill commit proceeds | Investigate source of tamper/corruption; re-run from last valid block | Ben + audit log review |
| InvoiceProof Gate 1 blocks bill | proof_bundles.passed=False, riskLevel=CRITICAL | Bill → exception queue; no approval gate reached | Ben reviews exception queue in System B; decides action | Ben (System B exception queue) |
| System A down when bill-synced callback fires | HTTP connection refused from System B | System B retries 3× with 30s delay | After 3 failures: System B logs {tracker_id, qb_txn_id} in reconciliation log; daily job picks it up | Ben (reconciliation report shows gap) |
| Outbox delivery: all 5 retries exhausted | outbox.attempts = 5, status=failed | Alert fires | Ben manually re-submits via System B UI (direct POST /intents/bill) | Ben (email alert) |
| STV CM LLC in draw intent (double guard fails) | System B /intents/draw returns 400 | Log alert: "STV CM LLC draw intent received — both guards should have caught this" | Investigate outbox writer code path | Ben + developer (audit alert — this should never happen) |
| amount=NULL in bill intent | System B receives null amount | Bill created with status=drafted, amount_review=True | Ben reviews in System B amount_review queue | Ben (UI queue) |
| Wrong Supabase project targeted | Table-not-found errors immediately | Operation fails with clear error | Developer corrects MCP/env var; run correct migration | Developer (immediate error — no silent failure) |

---

## 15. Reconciliation

| Reconciliation Type | Frequency | Source of Truth | What Is Compared | Alert Threshold | Who Reviews |
|---|---|---|---|---|---|
| Outbox delivery | Continuous (after each delivery job run) | integration_outbox table | Delivered rows vs System B bills.gmail_tracker_id existence | Any outbox row with attempts > 3 | Ben (dashboard) |
| Bill lifecycle coverage | Daily | System B bills | Every bill with status ≠ 'synced' that is > 7 days old | Any bill > 7 days in non-terminal state | Ben (System B dashboard) |
| AIVS chain validation | Every commit (in-process) + daily CI job | System B audit_rows | SHA-256 hash chain from row 1 to current; prev_hash chain validates | Any chain break → immediate page | Ben + developer |
| QB write-back coverage | Daily | System B bills | Bills with status='approved' AND qb_txn_id IS NULL AND > 24h | Any mismatch | Ben (sync health dashboard) |
| Bill-synced callback coverage | Daily | System B reconciliation log | Bills with status='synced' in System B where System A tracker.aihub_status != 'synced' | Any mismatch → run reconciliation job | Ben (automated job) |
| Draw fee math | Per draw_package | System B draw engine | (5% + 2% + 1%) fee bills sum = 8% of draw_amount | Any math mismatch → reject fee generation | Ben (System B draw UI) |
| proof_bundles coverage | Per bill approval | System B | bills WHERE status='approved' AND invoiceproof_bundle_id IS NULL | Any bill without proof bundle | Immediate block (gate fails closed) |

**Reconciliation report format (bill lifecycle):**
```
Date: YYYY-MM-DD
Period: [start] to [end]
Bills created by integration: N
Bills with status=synced (QB confirmed): N
Bills in approved (awaiting QB): N
Bills in exception queue: N
AIVS chain: VALID / BROKEN (N broken rows)
Outbox: N delivered, N pending, N failed
Action required: [None / Review exception queue / Investigate AIVS chain]
```

---

## 16. Audit Logging

### System A audit trail (existing + new)

| Event | Log Fields | Storage | Retention |
|---|---|---|---|
| Email classified | email_id, workflow_type, urgency, bank_change_risk, agent, timestamp | automation_audit_log | 2 years |
| Bill intent created | tracker_id, event_type, payload_hash, outbox_id, timestamp | automation_audit_log | 7 years |
| Bill intent delivered | outbox_id, system_b_response, bill_id, workflow_id, timestamp | integration_outbox.sent_at | 7 years |
| Outbox delivery failure | outbox_id, attempt, error_message, timestamp | integration_outbox.error_message | 2 years |
| Mike approval signal fired | tracker_id, workflow_id, evidence_email_id, timestamp | automation_audit_log | 7 years |
| Bill-synced callback received | tracker_id, bill_id, qb_txn_id, new_status, timestamp | automation_audit_log | 7 years |

### System B audit trail (existing per FinalSpec §6 + new)

| Event | Log Fields | Storage | Retention |
|---|---|---|---|
| Bill intent received | gmail_tracker_id, bill_id, vendor_name, amount, intake_timestamp | audit_rows (AIVS) | Indefinite (tamper-evident) |
| InvoiceProof Gate 1 result | bill_id, proof_bundle_id, passed, risk_level, timestamp | audit_rows (AIVS) + proof_bundles | 7 years |
| Human approval signal received | workflow_id, bill_id, approver_source, evidence_email_id, timestamp | audit_rows (AIVS) | 7 years |
| Bill committed to canonical Postgres | bill_id, amount, vendor_id, company_id, approver, timestamp | audit_rows (AIVS) | 7 years |
| QBWC BillAdd queued | bill_id, qbxml_request_hash, queue_timestamp | audit_rows (AIVS) | 7 years |
| QBWC TxnID reconciled | bill_id, qb_txn_id, qb_edit_sequence, timestamp | audit_rows (AIVS) + bills | 7 years |
| Bill-synced callback fired | bill_id, tracker_id, qb_txn_id, callback_status, timestamp | audit_rows (AIVS) | 7 years |
| Draw fee generated | draw_package_id, three_fee_bill_ids, math_verified, timestamp | audit_rows (AIVS) | 7 years |
| ATEP bank block created | vendor_name, sender_email, tracker_id, timestamp | audit_rows (AIVS) | 7 years |

**AIVS hard rules (System B):**
- audit_rows is append-only. No DELETE or UPDATE ever.
- Every commit to bills, proof_bundles, draw_packages, or journal_entries generates an audit_rows entry.
- row_hash = SHA-256("{row_id}:{session_id}:{action_type}:{tool_name}:{cost_cents}:{timestamp}:{prev_hash}")
- chain validation (verify.py, stdlib-only) runs in CI on every push and daily on production.
- Chain break → immediate page; no further writes accepted until chain is restored.

---

## 17. Security and Permissions

| Access Level | Who | Systems | What They Can Do |
|---|---|---|---|
| Admin | Ben Stone (owner) + developer | All services, all Supabase projects | Full access, credential management, QBWC registration |
| Approver | Ben Stone (UI) | System B approval UI | View in-flight bills, click "Approve" or "Reject", view proof reports |
| System A service | System A FastAPI process | System B /intents/*, /approvals/* | POST intents (scoped sa_* token) — no GET of all bills |
| System B service | System B FastAPI process | System A /integration/bill-synced | POST callback (scoped callback token) — no other System A access |
| Dashboard (read-only) | Ben (browser) | Both Supabase DBs (anon RLS) | SELECT only on 6 System A tables + bills/draw_packages in System B |
| Temporal worker | System B Railway Service 2 | Temporal Cloud + aihub Supabase | Execute workflow activities; write to bills, proof_bundles, audit_rows |
| QBWC adapter | System B Railway Service 3 | QB Desktop (outbound only) | Read QB data + write approved intents via qbXML |
| No access | All others | All | None |

**Least privilege rules:**
- System A's AIHUB_OUTBOX_TOKEN is scoped to POST /intents/* only — cannot read System B bills or proof data.
- System B's SYSTEM_A_CALLBACK_TOKEN is scoped to POST /integration/bill-synced only — cannot read System A email data.
- Dashboard anon keys have RLS SELECT-only. Any write attempt returns 403 at the DB level (RLS policy).
- SwarmSync sa_* key is self-issued by Ben (owner-operated). Scoped to proof products only.
- supabase-aihub MCP: exclusively for fdnwlcomuddzmluvbylg. Never used against ejxrbxoncsgglrqvjulg. This is enforced by CLAUDE.md and must be enforced in code via separate env vars (SUPABASE_URL_AIHUB vs SUPABASE_URL).

---

## 18. Manual Override

| Scenario | Override Action | Who Can Override | Audit Trail |
|---|---|---|---|
| System B down, urgent bill needed | Ben creates bill directly in System B UI; or Ben enters directly in QB Desktop (manual QB entry) | Ben Stone | automation_audit_log: "manual_override"; QB audit trail |
| Approval signal failed, bill stuck | Ben opens System B approval UI → clicks "Manually Approve" | Ben Stone | audit_rows AIVS: action_type="manual_approval", actor="ben_stone_ui" |
| Outbox delivery exhausted (5 attempts failed) | Ben manually calls System B via Postman or System B UI "Re-submit intent" | Ben Stone / developer | automation_audit_log: "manual_resubmit" + new outbox row |
| Bank block clearance (both systems) | System A: Ben sets bank_change_risk_flag=False on tracker + email_classifications (Supabase admin). System B: Ben removes ATEP block via System B admin UI. | Ben Stone | automation_audit_log (System A) + audit_rows (System B AIVS) |
| Bill in exception queue (Gate 1 blocked) | Ben reviews exception queue in System B; can reject (close workflow) or override with documented reason | Ben Stone | audit_rows AIVS: action_type="exception_override", actor="ben_stone_ui", reason |
| Draw fee calculation disputed | Ben rejects draw_package in System B approval UI; restarts with corrected amount | Ben Stone | audit_rows AIVS |
| QBWC stuck, QB entry urgent | Ben manually enters in QB Desktop; then marks bill qb_txn_id manually in System B admin | Ben Stone | audit_rows AIVS: action_type="manual_qb_entry" |
| Integration paused for maintenance | Set INTEGRATION_ENABLED=False env var on Railway Service 1 (disables outbox delivery job) | Developer | automation_audit_log: "integration_paused" |

**Override rule:** Every override is logged with: who, what changed, why, and when. No silent overrides. System B exception override requires a free-text reason field (minimum 10 characters).

---

## 19. Monitoring and Alerting

| Metric | Normal Range | Alert Threshold | Alert Channel | On-Call |
|---|---|---|---|---|
| Outbox queue depth (pending rows) | 0–5 | > 20 rows | Ben's dashboard warning | Ben |
| Outbox failed deliveries (attempts = 5, status=failed) | 0 | > 0 | Email to Ben + Google Chat P1 | Ben |
| System B health (/health endpoint) | 200 OK | Non-200 or no response for > 5 min | Google Chat P1 | Developer |
| Temporal workflow approval age | < 48h | > 48h without approval signal | Google Chat P1 (Temporal escalation timer) | Ben |
| AIVS chain validation | VALID (0 broken rows) | Any broken row | Email + Google Chat P0 | Ben + developer |
| QBWC sync lag (last-reconciled age) | < 60 min (target post-spike) | > 2× normal cadence | Google Chat P1 | Ben |
| Bills in exception queue age | < 24h | > 24h unresolved | Google Chat P1 | Ben |
| Bank change block active (ATEP) | 0 (no active blocks) | Any active block | Google Chat P0 (already fires on classify) | Ben |
| GAS poller health | 1-min cadence | No run in > 5 min | Google Chat P1 | Ben |
| Supabase DB connectivity (both projects) | Connected | Error on test query | Email alert | Developer |
| Railway service restarts (Service 1, 2, 3) | 0 per day | > 2 restarts/day | Email | Developer |
| proof_bundles coverage | 100% of approved bills | Any approved bill without passed=True proof bundle | Immediate gate block (no commit possible) | Ben (gate failure surface) |

**Daily digest email to Ben:**
```
STV Integration Health — YYYY-MM-DD
Outbox: N delivered, N pending, N failed
Bills today: N drafted, N verified, N approved, N synced
Exception queue: N open items
AIVS chain: VALID / BROKEN
QBWC last sync: [timestamp]
Action items: [auto-generated list of anything > threshold]
```

---

## 20. Test and Proof Plan

| Test | Type | Pass Criteria | Environment |
|---|---|---|---|
| Scenario 1 happy path (Porter → QB) | End-to-end | Bill created in System B with correct vendor, amount, gmail_tracker_id; Mike email triggers Temporal signal; bill reaches approved; QBWC write-back confirmed (post-spike) or canonical commit confirmed (pre-spike) | System B staging + System A staging |
| Scenario 2 in-person approval | End-to-end | Bill in verified state; Ben clicks "Approve" in System B UI; bill advances to approved; no System A email event required | System B staging |
| Scenario 3 bank change block | End-to-end | Bank change email → P0 fires → outbox has bank_block (no bill_intent) → System B creates ATEP block → in-flight bill moves to exception queue | System A staging + System B staging |
| Scenario 4 draw fee | End-to-end | Draw email → fee_opportunities created (blocked=False, non-STV CM LLC) → draw_intent outbox → System B creates draw_package → draw engine creates 3 fee bills → approval gate → AuditProof | Both staging |
| Scenario 5 Aubrey confirmation | End-to-end | Aubrey email → payment_confirmed outbox → System B bill.status=paid → reconciliation write queued | Both staging |
| Duplicate outbox guard | Idempotency | Same email classified twice → exactly ONE outbox row per (tracker_id, event_type) | System A staging |
| Duplicate bill intent guard | Idempotency | POST /intents/bill called twice with same gmail_tracker_id → System B returns existing bill_id both times; ONE bill in DB | System B staging |
| bank_change_risk hard reject (System B) | Validation | POST /intents/bill with gmail_invoiceproof.bank_change_risk=True → 400 response; no bill created | System B staging |
| STV CM LLC draw reject (System B) | Validation | POST /intents/draw with fee_payee resolving to "STV CM LLC" → 400; no draw_package created | System B staging |
| Outbox retry to System B down | Resilience | Mock System B as 503; outbox attempts increment; at attempt 3, alert fires; System B restored → attempt 4 succeeds | Local / staging |
| AIVS chain tamper rejection | Security | Manually alter audit_rows.prev_hash for row N; run chain validation → BROKEN detected; no further commits accepted | System B staging |
| Bill-synced callback idempotency | Idempotency | System B fires /integration/bill-synced twice for same tracker_id → System A advances status once; second call returns 200 no-op | Both staging |
| In-person approval UI render | UI | System B approval UI lists all verified bills with vendor, amount, project, draft date, mike_email_detected flag | System B staging + browser |
| No-auto-send invariant | Security | Run full integration pipeline; query System A draft_queue; assert zero rows with status='sent' | System A staging |
| Wrong DB protection | Security | Attempt to run Alembic migration against ejxrbxoncsgglrqvjulg using aihub DATABASE_URL → CI pre-check catches wrong project ref and fails | CI |
| proof_bundles coverage | Integrity | After approving a bill: verify bills.invoiceproof_bundle_id IS NOT NULL AND proof_bundles.passed=True | System B staging |
| Rollback Phase 1 | Rollback | Disable INTEGRATION_ENABLED → all pending outbox rows stop delivery; System B receives no new intents; System A continues classifying emails | System A staging |

---

## 21. Implementation Phases

| Phase | Scope | Gate Before Next Phase |
|---|---|---|
| Phase 0: Schema & Auth | System A migration (integration_outbox + tracker columns). System B migration (bills.gmail_tracker_id, draw_packages.gmail_fee_opportunity_id). Inter-service bearer token issuance. System B anon RLS for dashboard. | Both migrations applied. Auth tokens set in Railway env vars. Test: each service can make authenticated calls to the other. |
| Phase 1: Bill Intent (Scenario 1, no QBWC) | Build outbox writer (bill_intent trigger). Build outbox delivery job. Build System B POST /intents/bill. Verify bill created with gmail_tracker_id. Temporal workflow started. InvoiceProof Gate 1 runs. Temporal blocks at approval gate. | Integration test: Porter email → bill created in System B with correct fields. Gate 1 passed. Temporal running. No duplicates after 5 test runs. Ben sign-off. |
| Phase 2: Approval Signals (Scenarios 1 + 2) | Build System A mike approval signal (POST /approvals/{workflow_id}). Build System B approval UI (bill list + "Approve" button). Build bill-synced callback (System B POST → System A). Build System A POST /integration/bill-synced endpoint. | E2E test: both approval paths (email and manual UI). Callback received. Tracker advances. Ben sign-off. |
| Phase 3: Bank Block + Exception Queue (Scenario 3) | Build System A bank_block outbox event. Build System B POST /intents/bank-block. Build System B in-flight bill exception routing. | Integration test: bank change email → ATEP block → in-flight bill in exception queue. Verify no bill_intent created alongside bank_block. Ben sign-off. |
| Phase 4: Draw Fee Workflow (Scenario 4) | Build System A draw_intent outbox event (with STV CM LLC guard). Build System B POST /intents/draw + draw engine CHUNK_6 activation (promote from shadow to active with approval gates). | Integration test: draw email → draw_package → 3 fee bills → approval gate. STV CM LLC test case passes (400 returned). AuditProof chain validates. Ben sign-off. |
| Phase 5: Payment Confirmed (Scenario 5) + Dashboard | Build System A payment_confirmed outbox event. Build System B POST /intents/payment-confirmed. Extend Ben's dashboard with System B section (anon RLS reads on bills/draw_packages). | E2E test: all 5 scenarios. Dashboard renders System B data. Reconciliation report running and clean. Ben sign-off. |
| Phase 6: QBWC Write-Back (CRUX spike RESOLVED — business-hours/session-tied polling confirmed 2026-07-01) | Deploy QBWC SOAP endpoint (Railway Service 3). Generate .qwc file. Ben registers in QBWC on Rightworks VPS, targeting the sandbox company file first (see Rightworks File Manager upload — free, no additional hosting charge). Test BillAdd against QB Desktop sandbox/staging file. Enable write-back for approved bills once sandbox E2E passes. | Sandbox E2E test with actual QB write-back during a live business-hours session. TxnID reconciled. Off-hours queuing behavior verified (intent submitted after hours lands correctly on next login). Ben sign-off. |

**Rollback plan:**

| Phase | Rollback Action | Time | Who |
|---|---|---|---|
| Phase 0 | Drop integration_outbox; revert tracker column migration (DOWN migration); revoke tokens | < 30 min | Developer |
| Phase 1 | Set INTEGRATION_ENABLED=False env var → outbox job stops; System B receives no new intents; no data written to QB | < 5 min | Developer |
| Phase 2 | Disable approval signal delivery in outbox job config; Ben uses System B UI as sole approval path | < 5 min | Developer |
| Phase 3 | Disable bank_block outbox event type (config flag); P0 alert still fires but no ATEP block written to System B | < 5 min | Developer |
| Phase 4 | Re-set draw engine CHUNK_6 to shadow mode (config flag); draw_intents queue but don't activate draw engine | < 5 min | Developer |
| Phase 5 | Disable dashboard System B section (comment out second Supabase client in HTML); bills still sync | < 5 min | Developer |
| Phase 6 | Deregister .qwc from QBWC (Ben removes via "Remove Application" in QBWC UI); bills stay approved in canonical Postgres; no QB writes | < 15 min | Ben + developer |

---

## 22. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | QBWC CRUX spike — RESOLVED 2026-07-01: Rightworks confirmed no persistent poller; polling is business-hours/session-tied only | LOW (was HIGH, now a known/accepted constraint) | MEDIUM — QB write-back only occurs during active login sessions; off-hours items queue, not lost | Accepted design: canonical Postgres remains the system of record regardless; bills committed and provable without QB even during off-hours queuing windows. Batch-ETL fallback no longer needed as primary mitigation — business-hours cadence is the confirmed supported path. Monitor queue depth/age via daily digest (`app/integration/daily_digest.py`) to catch any bill stuck queued longer than expected. |
| R2 | Outbox delivery job fails silently (no alert at attempt 3) | MEDIUM | HIGH — intents lost, bills never created in System B | Alert at attempt 3 (Google Chat P1). Alert at attempt 5 (email). Dashboard shows queue depth. Daily reconciliation catches any gap. |
| R3 | Vendor name fuzzy match produces wrong vendor match in System B | HIGH | MEDIUM — bill created for wrong vendor; may approve wrong payment | Threshold: ≥ 0.75 similarity required. Below threshold: hold in vendor_review queue, never auto-match to wrong vendor. Ben confirms in System B UI. Two-factor: gmail_tracker_id AND vendor_name must agree. |
| R4 | Mike approval signal arrives at System B before bill is created (race condition) | MEDIUM | MEDIUM — signal lost; Temporal never unblocks | /intents/bill is synchronous (System A waits for workflow_id before storing aihub_workflow_id). Signal only fires after workflow_id confirmed stored. Add 5s delay in signal delivery after bill_id confirmed. |
| R5 | Bank block event arrives in System B after bill_intent was already processed | LOW | HIGH — ATEP block too late; bill in verified state for blocked vendor | /intents/bank-block scans for in-flight bills on same vendor; routes them to exception queue immediately on block creation. Neither gate trusts the other; defense in depth. |
| R6 | STV CM LLC leaks through both guards simultaneously | LOW | HIGH — fee entry for blocked entity | Two independent guards (System A outbox writer + System B draw engine). Both must fail simultaneously. Add audit alert: "STV CM LLC draw_intent received" is a canary — if ever seen, investigate immediately. |
| R7 | AIVS hash chain break from concurrent write collision | LOW | HIGH — all bill commits blocked until chain restored | Sequential AIVS row writes (no concurrent inserts to audit_rows). Use DB transaction with row lock. Validate chain before every commit. Alert immediately on break. |
| R8 | Railway Service restart during outbox delivery loses in-flight HTTP call | MEDIUM | LOW | Outbox row stays pending (DB-backed). Next delivery job run retries. Idempotency on System B ensures no duplicate bill. |
| R9 | Wrong Supabase project targeted (developer uses supabase MCP instead of supabase-aihub MCP) | MEDIUM | HIGH — migrations or data written to SwarmSync DB (wrong project) | CLAUDE.md hard rule. CI pre-check asserts DATABASE_URL project ref = fdnwlcomuddzmluvbylg. Separate env var names (SUPABASE_URL for System A, SUPABASE_URL_AIHUB for System B). Error is immediate (table not found) — not silent. |
| R10 | Temporal Cloud free tier exceeded (10k actions/month) | LOW | MEDIUM — workflow creation fails; bills not processed | ~10 bills/day × 10 Temporal actions/bill = 3,000 actions/month. Well within limit. Monitor: alert at 7k/month. Paid tier available if volume grows. |

**Risk Register completeness check (cross-reference from Sections 7, 11, 13, 14):**
- Section 7 field mapping risks: vendor name mismatch (R3 ✓), QB TxnID migration (covered in §13 design) ✓
- Section 11 failure scenarios: outbox failures (R2 ✓), AIVS break (R7 ✓), QBWC failure (R1 ✓)
- Section 13 idempotency edge cases: duplicate bill_intent (covered by UNIQUE constraint design) ✓
- Section 14 unresolved failure scenarios: all have documented recovery paths ✓

---

## 23. Final Verdict

### Hard Rules Verification

| Rule | Status | Section Reference |
|---|---|---|
| Rule 1: Never sync money-impacting data without an audit log | SATISFIED — §16 covers all financial events in both System A (audit_log) and System B (AIVS chain) | §16 |
| Rule 2: Never trust email alone for payment changes | SATISFIED — System A's Mike email detection fires a Temporal SIGNAL; the Temporal gate must be in correct state (verified) to accept it. Email alone cannot approve; System B gate is the hard block. | §12, §5 |
| Rule 3: Never allow external vendor bank account changes without out-of-band verification | SATISFIED — bank_change_risk=True stops ALL downstream processing; ATEP block in System B; manual clearance required in both systems | §3, §8, §11 |
| Rule 4: Never allow duplicate invoices or payments without dedup check | SATISFIED — bills.gmail_tracker_id UNIQUE; integration_outbox (tracker_id, event_type) UNIQUE; proof_bundles (bill_id, kind) UNIQUE | §13 |
| Rule 5: Never let Google Sheets become hidden source of truth | SATISFIED — Ben's dashboard is read-only (Supabase anon RLS SELECT only). Integration touches Sheets nowhere. | §3, §17 |
| Rule 6: Never assume QB Desktop behaves like a web API | SATISFIED — QBWC poll model designed throughout; no webhook-based QB design anywhere | §2, §8, §21 Phase 6 |
| Rule 7: Never ignore Rightworks/VPS scheduling and session constraints | SATISFIED — CRUX spike documented as Phase 6 gate; all phases 0–5 work without QBWC | §2, §21 |
| Rule 8: Never use one-way sync without a reconciliation report | SATISFIED — §15 defines 6 reconciliation checks; daily reconciliation job designed | §15 |
| Rule 9: Never create an automation that bypasses a required approval gate | SATISFIED — Temporal approval gate is mandatory for every bill; mike email detection is a SIGNAL to the gate, not a bypass; in-person override still goes through the gate | §12 |
| Rule 10: Never treat "API is available" as "integration is solved" | SATISFIED — dedup (§13), approval gates (§12), failure handling (§14) all explicitly designed | Throughout |
| Rule 11: Never skip idempotency for webhooks, payments, invoices, or vendor records | SATISFIED — every entity has dedup key and idempotency contract | §13 |
| Rule 12: Never mark integration complete without proof of round-trip | SATISFIED — §20 requires bill-synced callback verified, AIVS chain validation in CI, reconciliation report clean for Phase 6 sign-off | §20, §21 |

**All 12 Hard Rules: SATISFIED.**

### Verdict

```
╔══════════════════════════════════════════════════════════════════╗
║  VERDICT: READY_TO_SPEC                                          ║
║                                                                  ║
║  Justification:                                                  ║
║  - All 5 integration crux decisions resolved (governor §5)       ║
║  - All 12 hard rules verified against all data types             ║
║  - Source-of-truth defined for every data type (§3)              ║
║  - Approval gates documented for every money-moving action (§12) ║
║  - Dedup keys specified for every created entity (§13)           ║
║  - Audit log model covers all write operations (§16)             ║
║  - 0 Q5-Q10 assumptions — no ASSUMPTION-DEPENDENT modifier       ║
║  - Mixed readiness: Phases 0-5 READY_TO_SPEC.                   ║
║    Phase 6 (QBWC write-back) = LEGACY_CONSTRAINTS_BLOCKING       ║
║    pending CRUX spike (FinalSpec §4.6).                          ║
║                                                                  ║
║  Most restrictive overall verdict: READY_TO_SPEC                 ║
║  (QBWC constraint is a known, gated, pre-existing spike          ║
║  with a defined escape path — does not block speccing            ║
║  Phases 0-5 of the integration layer.)                           ║
╚══════════════════════════════════════════════════════════════════╝
```

**Per-data-type readiness:**

| Data Type / Phase | Readiness | Blocking Issue (if any) |
|---|---|---|
| Bill intent (A→B) | READY_TO_SPEC | None |
| Draw fee intent (A→B) | READY_TO_SPEC | None |
| Bank block (A→B) | READY_TO_SPEC | None |
| Mike approval signal (A→B) | READY_TO_SPEC | None |
| Payment confirmed (A→B) | READY_TO_SPEC | None |
| Bill-synced callback (B→A) | READY_TO_SPEC | None |
| QB write-back (QBWC) | READY_TO_SPEC | CRUX spike RESOLVED 2026-07-01 — business-hours/session-tied polling confirmed by Rightworks in writing; no longer blocking |
| In-person approval UI | READY_TO_SPEC | None |
| Ben's dashboard System B section | READY_TO_SPEC | None |

---

## 24. Handoff to O2O

```
INTEGRATION HANDOFF PACKAGE
==============================
Skill: master-integration-engineer
Packet: integration-architecture-packet-stv-2026-06-29.md
Governor Packet: architecture-decision-packet-stv-integration-layer-2026-06-29.md
Verdict: READY_TO_SPEC (Phases 0–5 immediately; Phase 6 gated on CRUX spike)
Next skill: spec-superstar (use §17 of governor packet + §7 field mappings as input)

Implementation phases ready for agents:
- Phase 0: Schema migrations (System A + System B), inter-service auth token issuance,
            System B anon RLS for dashboard section
- Phase 1: Outbox writer (bill_intent) + outbox delivery job + System B POST /intents/bill
            + Temporal workflow start
- Phase 2: Mike approval signal delivery + System B approval UI + bill-synced callback
            + System A POST /integration/bill-synced
- Phase 3: Bank block outbox + System B POST /intents/bank-block + exception queue routing
- Phase 4: Draw fee outbox + System B POST /intents/draw + draw engine CHUNK_6 activation
- Phase 5: Payment confirmed outbox + System B POST /intents/payment-confirmed
            + Ben's dashboard System B section
- Phase 6: QBWC SOAP endpoint (Railway Service 3) + .qwc file + write-back adapter
            [GATED ON CRUX SPIKE]

Recommended agent assignments:
- atlas-db: System A integration_outbox migration + tracker column migration
             System B bills.gmail_tracker_id migration + draw_packages.gmail_fee_opportunity_id migration
             System B anon RLS policies for bills + draw_packages
- backend engineer (Ben/System B): POST /intents/bill, /intents/draw, /intents/bank-block,
                                    /intents/payment-confirmed; approval UI; Temporal workflow wiring
- backend engineer (System A): outbox writer logic + delivery job + POST /integration/bill-synced
- frontend engineer: extend dashboard/index.html with second Supabase client (aihub anon key)
                     + bills/draw display sections
- devops: Railway Service 2 deployment + env var management + health checks + monitoring setup

Constraints agents MUST preserve:
- NO writes to draft_queue from any integration code path. EVER.
- NO Gmail API calls from integration code (only System A's existing pipeline calls Gmail).
- bank_change_risk_flag=True on tracker → NO bill_intent outbox row. Hard stop in outbox writer.
- System B /intents/bill MUST check and reject gmail_invoiceproof.bank_change_risk=True (400).
- STV CM LLC: outbox writer checks fee_opportunities.blocked=True → no draw_intent.
              System B /intents/draw independently checks entity name (400 if STV CM LLC).
- Both supabase projects MUST be treated as completely separate. NEVER mix credentials.
- supabase-aihub MCP only for fdnwlcomuddzmluvbylg (aihub). Enforced in CLAUDE.md.
- All Alembic migrations → aihub Supabase (fdnwlcomuddzmluvbylg) ONLY.
- Temporal approval gate is MANDATORY. Mike email detection = signal to gate, not bypass.
- Gates fail closed: proof-core unavailable → bill stays in drafted, not auto-approved.
- QBWC write-back: wait for CRUX spike resolution. Do not deploy Railway Service 3 or
  generate .qwc until spike is complete.
```

---

## 25. Handoff to Brutal Truth Audit

```
PRE-LAUNCH CHECKLIST FOR brutal-truth-launch-audit
====================================================
Integration: STV Gmail AccountingOS × AI Accounting Hub
Environment to audit: staging (both Railway services + both Supabase projects)

Before auditing, verify:
[ ] integration_outbox: (tracker_id, event_type) UNIQUE constraint confirmed (§13)
[ ] bills.gmail_tracker_id UNIQUE constraint confirmed (§13)
[ ] All 5 approval gate scenarios documented and live-tested (§12, §20)
[ ] AIVS chain validation running in CI (verify.py) + daily production job (§16)
[ ] Daily reconciliation report running and clean for 7 consecutive days (§15)
[ ] Both Railway service health checks active (/health endpoints responding) (§19)
[ ] Both Supabase anon RLS verified: no write operations possible from dashboard (§17)
[ ] No draft_queue rows with status='sent' in System A after full integration run (§20)
[ ] Bank block path: verified bank_change_risk=True email → ATEP block → no bill_intent (§20)
[ ] STV CM LLC: verified draw email → blocked=True fee_opportunity → NO draw_intent (§20)
[ ] proof_bundles: ALL approved bills have invoiceproof_bundle_id with passed=True (§20)
[ ] Inter-service tokens set in Railway env vars (NOT in code or Git) (§10)
[ ] supabase-aihub MCP usage: CI step confirms DATABASE_URL_AIHUB points to fdnwlcomuddzmluvbylg (§10)
[ ] Rollback Phase 5 tested: INTEGRATION_ENABLED=False stops outbox job; System B receives no new intents (§21)
[ ] Ben sign-off on Phase 5 gate (all 5 scenarios working, dashboard showing correct data) (§21)

Phase 6 additional checks (QBWC write-back — CRUX SPIKE RESOLVED 2026-07-01):
[x] QBWC poll cadence RESOLVED: business-hours, session-tied only (no persistent poller supported — Rightworks written confirmation)
[x] Rightworks persistent-poller question filed AND response received — answer: not supported; scheduled-task/service-account workaround explicitly declined by Rightworks
[ ] .qwc file generated with correct OwnerID + FileID (unique GUIDs) + SOAP endpoint URL, targeting the sandbox company file first
[ ] QB Desktop sandbox file tested: BillAdd writes correctly, TxnID returned
[ ] EditSequence conflict handling tested: conflict detected → re-read → retry → succeeds
[x] Rightworks VPS: QB + QBWC confirmed to auto-start on session login (support ticket response, 2026-07-01) — auto-open is a supported request, persistence across the 2h inactivity timeout is NOT
[ ] Off-hours queuing verified: intent submitted outside business hours lands correctly on next login (new check, added per resolved cadence model)

Run /brutal-truth-launch-audit after Phase 5 staging proof is complete.
Run again after Phase 6 QBWC write-back is live in staging.
```

---

## READINESS VERDICT

```
OVERALL: READY_TO_SPEC — Phases 0–5 (integration layer, all 5 scenarios)

BLOCKERS FOR WRITE-BACK ONLY (Phase 6):
  1. QBWC poll cadence measurement on one Rightworks company file
     → Action: Ben stands up qbwc/qbwc against one file, measures cadence + queue depth
     → Output: documented number (e.g., "8 min round-trip, max 50 queue depth")
  2. Rightworks persistent-poller support ticket
     → Action: Ben files ticket requesting QB + QBWC auto-start at login
     → Output: written response from Rightworks support (YES or NO)
     → If NO: escape to scheduled batch-ETL per FinalSpec §4.6 (v2.0.0 revision)

THESE BLOCKERS DO NOT BLOCK PHASES 0–5.
The integration layer (outbox, webhooks, callbacks, approval UI, dashboard) can be
fully specified and built NOW. Bills will commit to canonical Postgres and be provably
correct without QB Desktop. QB is the eventually-consistent sink — the canonical store
is the value.
```

---

*Packet: 25 of 25 sections produced.*
*Skill: master-integration-engineer v1.2.0*
*Governed by: system-architecture-governor v1.2.0 (READY_FOR_SPEC, 2026-06-29)*
*Session: STV Gmail × QB Automation Integration Architecture — 2026-06-29*
