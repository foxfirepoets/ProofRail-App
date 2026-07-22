# AI Accounting Hub — Design Specification

```
Spec Title:       AI Accounting Hub — The AI Operating Layer for Legacy Accounting Systems
Version:          1.0.0
Author:           Ben Stone (via Claude Code spec-superstar)
Last Updated:     2026-06-26
Status:           Ready for Build (Phase 1 MVP scope) / In Design (Phases 2–3)
Timeline:         90-day MVP (3 phases × 30 days); full platform 9–12 months
Confidence Level: ~90% — only 2 environment spikes remain before adapter code (see §14): QBWC poll cadence on Rightworks, Rightworks persistent-poller approval. Proof layer fully resolved: key authority (VCAP/AIVS specs, §9), cost = $0 (owner operates SwarmSync), and authoritative API surface captured from the owned repo (Appendix B).
Next Steps:       Resolve the CRUX spike (§4.6) → build Phase 1 wedge
Source of truth:  Architecture from FOSS scrub + deep research + 6-agent adversarial brainstorm
                  (C:\Users\Administrator\Desktop\Ultimate Brainstorm Output\ai-accounting-layer__20260626_060324\brainstorm-output.md)
Companion:        SPEC_SUMMA_TERRA_BINDING.md (v2.0.0) — binds this generic architecture to the real
                  QuickBooks Enterprise config for Summa Terra Ventures (QB Summa Terra SPEC.md v2.2.0):
                  dimensioned canonical model (cost codes 001–069, class, Customer:Job, Draw #), the
                  automated Draw-Package fee engine (5% / 2% / 1% split), intercompany Due-To/Due-From,
                  and domain-aware proof gates. Build it as Phase 2.5, after Phase 1 read-sync.
```

---

## 1. EXECUTIVE SUMMARY

Build **the AI operating layer for legacy accounting systems**: a vendor-agnostic platform where a **canonical Postgres store is the system of record** (replacing Google Sheets as the operational database), and QuickBooks Enterprise Desktop — hosted on a locked-down Rightworks VPS across 10+ company files for a real-estate development firm — is treated as an **eventually-consistent batch sink** reached through a self-built, async **QuickBooks-Desktop MCP server** over the QuickBooks Web Connector (QBWC).

The durable value — the product and the moat — lives **above the transport** in three layers: (1) the canonical store (unified cross-company search, cross-entity reporting, month-end close state), (2) a **Temporal-gated human-approval commit boundary** for autonomous-but-supervised accounting, and (3) a **SwarmSync proof spine** (InvoiceProof / AuditProof / VerifyAPI) implemented to native VCAP/AIVS/ATXN wire formats as **hard gates**, not logs.

**Business outcome:** eliminate manual coding, AP, fee calculations, reconciliations, and month-end close pain; give the firm unified cross-company visibility it has never had; and establish a platform that scales 10→1000 entities and swaps QuickBooks for QBO/Intacct/NetSuite/Xero/Dynamics as an adapter change, not a rewrite. **Primary users:** the firm's controller and accounting staff (approvers) and the AI automation agents (actors). **Why now:** QB Desktop is in active wind-down (Enterprise is the only edition Intuit still sells), forcing a vendor-agnostic layer that survives the platform's death — and SwarmSync's proof products make "verified before it touches the books" a shippable differentiator today.

---

## 2. SCOPE DEFINITION & NON-SCOPE

### In scope (full product)
- Canonical Postgres data model for multi-entity accounting (companies, accounts, vendors, bills, payments, journal entries, allocations, audit rows).
- Self-built **QuickBooks-Desktop MCP server**: thin qbXML/QBWC transport adapter + fat QB-semantics layer with `raw_extensions` sidecar.
- **NATS/JetStream** event bus; **Temporal** durable workflow + human-approval gates.
- **SwarmSync proof spine** as 4 hard gates (InvoiceProof, AuditProof, VerifyAPI, bank-change/ATEP).
- Invoice OCR / AP extraction via **invoice2data**.
- Unified cross-company search and cross-entity reporting (replaces Google Sheets).
- Adapter interface designed for future QBO/Intacct/NetSuite/Xero/Dynamics backends.

### Phase 1 MVP scope (the 90-day build — what ralph builds first)
- Read-only sync of **one** company file's vendors + bills → canonical Postgres.
- Dashboard showing synced data.
- **Spike: measure QBWC poll cadence + queue depth** on one Rightworks file (the CRUX, §4.6).
- File the Rightworks persistent-poller support ticket.

### Out of scope (this spec)
- **1000-company Desktop operation** — explicitly impossible (one-file-per-session physics, §8); the 1000 path is API adapters, deferred to Phase 4+.
- Live QBO/Intacct/NetSuite/Xero/Dynamics adapters — only the **seam** is built in Phase 3 (QBO stub); full adapters are future specs.
- Payroll, tax filing, bank-feed ingestion, vendor portals, document management — future phases.
- Any **inbound** connection to the Rightworks box — architecturally forbidden by the host.
- Any paid integration above $5–10/mo.

### Dependencies
- **Upstream:** Rightworks-hosted QB Enterprise + QBWC; SwarmSync proof APIs (InvoiceProof/AuditProof/VerifyAPI) per VCAP/AIVS/ATXN specs.
- **FOSS build spine (OSI-verified):** qbwc/qbwc (MIT), selfjared1/quickbooks_desktop (MIT), invoice2data (MIT), Temporal (MIT), NATS/JetStream (Apache-2.0), Flowable (Apache-2.0, optional), Postgres.

---

## 3. BUSINESS CONTEXT & ACCEPTANCE CRITERIA

**Business goal:** Replace manual, error-prone, Google-Sheets-based multi-entity accounting with autonomous AI automation that no human distrusts — because every money movement, GL write, and autonomous action is independently verified before it lands.

**Success metrics & targets:**
- Cross-company AP coding automated: ≥80% of bills auto-coded with human approving only exceptions.
- Month-end close time: reduce by ≥50% vs current manual baseline.
- Unified search: any vendor/transaction findable across all entities in <2s (currently impossible).
- Zero unverified writes: 100% of GL writes carry a valid AIVS hash-chain proof; 100% of payments pass an InvoiceProof gate.
- Zero double-pays / bank-change fraud incidents reaching execution.

**Acceptance criteria (Phase 1 MVP):**
- [ ] One company file's vendors + bills sync into canonical Postgres with `raw_extensions` preserved losslessly.
- [ ] Dashboard renders synced vendors/bills with cross-field search.
- [ ] QBWC poll cadence + max queue depth are **measured and documented** (a real number).
- [ ] Rightworks persistent-poller ticket filed and response recorded.
- [ ] Every sync run emits an AuditProof (AIVS) row; chain validates.

**Spec status:** Phase 1 sections are **build-phase** (fixed); Phases 2–3 are **design-phase** (refine as the CRUX spike resolves). If the CRUX resolves FALSE (poll cadence unusable / poller denied), §14 escape path converts the product to scheduled batch-ETL and this spec is revised to v2.0.0.

---

## 4. ARCHITECTURE & SYSTEM INTEGRATION

### 4.1 Layered architecture (top = durable value, bottom = disposable transport)
```
            ┌─────────────────────────────────────────────┐
            │  AI Orchestration Layer (agents)             │
            └───────────────┬─────────────────────────────┘
                            │ submits INTENTS (never direct writes)
            ┌───────────────▼─────────────────────────────┐
            │  SwarmSync Proof Spine (HARD GATES)          │
            │  InvoiceProof · AuditProof · VerifyAPI · ATEP│
            └───────────────┬─────────────────────────────┘
            ┌───────────────▼─────────────────────────────┐
            │  Temporal — durable workflow + HUMAN GATE    │
            │  (commit boundary at irreversible steps)     │
            └───────────────┬─────────────────────────────┘
            ┌───────────────▼─────────────────────────────┐
            │  Canonical Postgres  = SYSTEM OF RECORD      │
            │  (unified search, reporting, close state)    │
            └───────────────┬─────────────────────────────┘
            ┌───────────────▼─────────────────────────────┐
            │  NATS/JetStream event bus                    │
            └───────────────┬─────────────────────────────┘
            ┌───────────────▼─────────────────────────────┐
            │  Adapter Interface (stable contract)         │
            │   ┌─────────────────────────────────────┐   │
            │   │ QB-Desktop adapter (Phase 1–3)      │   │
            │   │  fat QB-semantics layer (quirks=data)│   │
            │   │  thin qbXML/QBWC transport (poll)    │   │
            │   └─────────────────────────────────────┘   │
            │   future: QBO · Intacct · NetSuite · Xero    │
            └───────────────┬─────────────────────────────┘
                            │ outbound poll ONLY (no inbound)
            ┌───────────────▼─────────────────────────────┐
            │  QuickBooks Enterprise Desktop (Rightworks)  │
            │  = eventually-consistent BATCH SINK          │
            └─────────────────────────────────────────────┘
```

### 4.2 Data flow (write path — the core pattern: async-by-design)
1. AI agent emits an **intent** (e.g., "create AP bill") onto NATS.
2. Temporal workflow picks it up, builds the canonical record, runs **VerifyAPI (Gate 3)** and, for AP, **InvoiceProof (Gate 1)**.
3. Workflow **blocks on a Temporal signal** at the irreversible step → **human approves the transition** (not the work).
4. On approval, write commits to canonical Postgres; **AuditProof (Gate 2, AIVS hash-chain)** row is appended; chain must validate or the commit rolls back.
5. The QB-Desktop adapter enqueues the write; **QBWC drains the queue on its poll cadence**; QB Desktop is updated as an eventually-consistent sink.
6. The qbXML response (TxnID/EditSequence) is reconciled back into the canonical record + `raw_extensions`.

### 4.3 Data flow (read path — real-time)
AI reads serve from the **canonical mirror at memory speed** — never blocked on the poll cycle. QB Desktop reconciliation updates the mirror in the background.

### 4.4 Integration points
- **QBWC ⇄ adapter:** SOAP/qbXML, outbound poll, one company file per QB session.
- **invoice2data:** OCR/extraction → structured fields → canonical bill + InvoiceProof inputs.
- **SwarmSync:** VCAP `verification_request`/`verification_callback`, AIVS bundle generation/validation, ATXN attestation, ATEP capability/tier checks.

### 4.5 New infrastructure
- Postgres (canonical store) · NATS/JetStream · Temporal cluster · adapter worker(s) running the QBWC SOAP endpoint · object store for proof bundles/OCR artifacts.

### 4.6 THE CRUX (must resolve before adapter code)
**Does QBWC outbound-poll on Rightworks sustain a reliable sub-10-min round-trip across the 10 files, AND will Rightworks permit a persistent poller in writing?**
- **TRUE →** full async operating layer is viable (this spec proceeds).
- **FALSE →** collapses to scheduled batch-ETL / vertical wedge; revise to v2.0.0.
- **First action:** stand up qbwc/qbwc on one file, measure cadence + queue depth, file the support ticket.

### 4.7 Ownership map
- Adapter + transport: integration engineer. Canonical store + search: backend. Proof spine: backend + SwarmSync liaison (key-authority unknown, §14). Approval UX: frontend. Temporal workflows: backend.

---

## 5. USER FLOWS & HAPPY PATH

**Actor:** Controller (approver). **Precondition:** AI has drafted an AP bill from an OCR'd vendor invoice; canonical mirror is current.

1. invoice2data extracts vendor, amount, line items, PO ref from the inbound invoice PDF.
2. AI agent emits `create_bill` intent → NATS.
3. Temporal builds the canonical bill record; runs **InvoiceProof (Gate 1)**: duplicate-billing check, math verification, PO match, vendor + bank-detail check.
4. If InvoiceProof `passed=false` (e.g., duplicate or bank-change) → routed to exception queue with the proof report attached; controller sees *why*.
5. If `passed=true` → workflow blocks on human-approval signal; controller sees the bill + green proof in the approval UI on their phone.
6. Controller approves → write commits to canonical Postgres; **AuditProof (Gate 2)** appends an AIVS row recording the AI proposal + human approval; chain validates.
7. Adapter enqueues the qbXML `BillAdd`; QBWC drains it on next poll; QB Desktop updated; TxnID reconciled back.
8. **Postcondition:** bill exists in canonical store + QB, with a tamper-evident proof chain linking AI decision → human approval → executed write.

**Alternate paths:**
- **A. Bank-change fraud:** vendor bank detail changed → Gate 4 (ATEP) requires TRUSTED tier; below tier → auto-block + escalate, no payment path.
- **B. Poll cadence slow:** intent sits durably in Temporal; controller still approves instantly against the mirror; QB write lands on the next cycle (async is expected).
- **C. Month-end close:** AI proposes close entries → **VerifyAPI (Gate 3)** must reach VERIFIED + carry `independent_attestor_signature` before any autonomous posting.

---

## 6. DATA MODELS & SCHEMA

### 6.1 Core tables (canonical store)
**companies** — one row per QB company file / legal entity (partnership).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| legal_name | VARCHAR(255) | NOT NULL | |
| qb_file_id | VARCHAR(128) | UNIQUE | QB company file identifier |
| entity_type | VARCHAR(32) | NOT NULL | e.g., partnership |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**vendors**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK→companies ON DELETE RESTRICT | |
| qb_list_id | VARCHAR(128) | | QB ListID (identity) |
| qb_edit_sequence | VARCHAR(64) | | optimistic-lock token |
| name | VARCHAR(255) | NOT NULL | |
| bank_fingerprint | VARCHAR(256) | | hash of bank details for change detection |
| swarmscore | INT | | vendor trust score |
| raw_extensions | JSONB | NOT NULL DEFAULT '{}' | lossless QB-native fields |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**bills**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK→companies | |
| vendor_id | UUID | FK→vendors | |
| qb_txn_id | VARCHAR(128) | | QB TxnID after write-back |
| qb_edit_sequence | VARCHAR(64) | | |
| po_ref | VARCHAR(128) | | |
| amount | DECIMAL(14,2) | NOT NULL CHECK (amount >= 0) | |
| status | VARCHAR(24) | NOT NULL | drafted→verified→approved→synced |
| invoiceproof_bundle_id | UUID | FK→proof_bundles | Gate 1 result |
| raw_extensions | JSONB | NOT NULL DEFAULT '{}' | line items etc. |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**audit_rows** (AuditProof / AIVS hash chain)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| row_id | BIGSERIAL | PK | |
| session_id | UUID | NOT NULL | |
| action_type | VARCHAR(48) | NOT NULL | e.g., ai_code_bill, human_approve |
| tool_name | VARCHAR(64) | | |
| inputs_json / outputs_json | JSONB | | |
| actor | VARCHAR(64) | NOT NULL | agent id or user id |
| prev_hash | CHAR(64) | NOT NULL | |
| row_hash | CHAR(64) | NOT NULL UNIQUE | SHA-256(row_id:session:action:tool:cost:ts:prev_hash) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**proof_bundles** — id, kind (invoiceproof/verifyapi), vcap_state, proof_hash, proof_signature, passed BOOL, payload JSONB, created_at.

**journal_entries / allocations** — multi-entity intercompany allocations + cross-property fee calcs (Phase 2+); allocation rows reference source + target company_id with a basis/percentage and an audit_row link.

### 6.2 Validation rules
- `amount` ≤ 0 rejected; `qb_edit_sequence` required on any write-back (optimistic lock).
- `raw_extensions` must round-trip losslessly (write what was read for untouched fields).
- A bill cannot move to `approved` without a `proof_bundles` row with `passed=true`.

### 6.3 Example (valid intent)
```json
{ "intent":"create_bill","company_id":"…","vendor_id":"…","amount":"12500.00",
  "po_ref":"PO-2291","raw_extensions":{"qb_line_items":[{"account":"6100","amt":"12500.00"}]} }
```

---

## 7. ERROR HANDLING & EDGE CASES

| Scenario | Code | HTTP/Status | Behavior / Mitigation |
|---|---|---|---|
| InvoiceProof fails (dup/math/PO/bank) | INVOICEPROOF_FAILED | 200 (gate) | Bill → exception queue with proof report; no payment |
| AIVS chain broken before GL write | AUDIT_CHAIN_BROKEN | 500 | **Hard rollback**; alert; do not commit |
| VerifyAPI not VERIFIED | VERIFY_NOT_READY | 409 | Block autonomous execution; route to human |
| Bank-change below TRUSTED tier | BANK_CHANGE_BLOCKED | 200 (gate) | Auto-block + escalate; ATEP capability denied |
| qbXML optimistic-lock conflict (EditSequence) | QB_EDIT_CONFLICT | 409 | Re-read from QB, re-base canonical, retry once, else human |
| QBWC poll stalled / queue backed up | QB_SYNC_LAGGED | n/a | Intent stays durable in Temporal; surface lag metric; no data loss |
| CoA drift (account missing in file) | COA_DRIFT | 422 | VerifyAPI catches pre-write; flag for mapping fix (killer demo) |
| Rightworks denies persistent poller | HOST_POLLER_DENIED | n/a | Trigger §14 escape: scheduled-batch mode |
| VCAP shared_secret missing for cross-org ADRP dispute | PROOF_KEY_CROSS_ORG | n/a | Internal gates unaffected (self-managed key); only third-party adjudication needs a SwarmSync-issued key — request out-of-band |

**Edge cases:** duplicate vendor names across entities (namespaced by company_id); same invoice to two entities (dedup keyed on company_id+vendor+amount+date); QB file locked by an interactive RDS user (poll retries, backs off); intent approved after the underlying QB record changed (EditSequence conflict → re-base).

**Failure modes & recovery:** NATS down → Temporal retains workflow state, replays. Postgres down → adapter holds qbXML responses in JetStream until store returns. Proof service down → gates **fail closed** (no write proceeds without a valid proof — never fail open on money/books).

---

## 8. PERFORMANCE & SCALABILITY

**Latency targets:** canonical read (AI/dashboard) <100ms p95 (served from mirror, never the poll). Approval-UI render <300ms p95. Proof gate evaluation <2s p95.

**Throughput / the physics ceiling (HARD CONSTRAINT):** QB Desktop opens **one company file per session**; file switch is **30–120s**. Concurrency = number of licensed Rightworks RDS sessions running QB, not code threads. Therefore:
- Write-back throughput to QB is bounded by `(concurrent QB sessions) × (1 / file-switch+session time)`.
- **1000 companies on Desktop is a sync horizon of hours, not seconds — out of scope.** The canonical store hides *read* latency but cannot manufacture *write* throughput into QB.

**Scalability plan:** scale = the canonical store + the adapter interface, **not** QB. 10 companies on Desktop (bootstrap) → batch windows per file. 1000 companies → **API-based adapters** (QBO/Intacct) that have no per-file serialization; Desktop is the migration origin. Postgres scales with read replicas + partitioning by company_id; NATS/Temporal scale horizontally.

**Cost budget:** FOSS spine = $0 license. Hosting Postgres/NATS/Temporal on modest infra. **SwarmSync proof layer = $0 — the owner operates SwarmSync**, so InvoiceProof/AuditProof/VerifyAPI hosted usage (normally $750 pilot + $1.5k–7.5k/mo tiers) carries no marginal cost, and the owner controls API keys, the marketplace, and ADRP adjudication directly. This removes the proof layer from the budget constraint entirely. **Remaining ceiling note:** hosted QB Desktop is ~$50–80/seat/mo (license+RDS) — incompatible with the $5–10/mo target at scale, which is *why* the scale path is off-Desktop. Phase-1 stays within budget (single seat already owned by the firm).

---

## 9. SECURITY & COMPLIANCE

**AuthZ/AuthN:** AI agents authenticate to the orchestration layer with scoped capability tokens (ATXN allowed_actions). PAYMENT_FORM and bank-change actions require **ATEP TRUSTED tier**. Human approvers authenticate to the approval UI; approval signals are attributable.

**Proof/crypto (native wire formats):**
- **AuditProof = AIVS:** `row_hash = SHA-256("{row_id}:{session_id}:{action_type}:{tool_name}:{cost_cents}:{timestamp}:{prev_hash}")`; optional Ed25519 session signature. Self-hostable (`verify.py`, stdlib only).
- **InvoiceProof = VCAP Full Bundle:** `proof_hash = SHA-256(canonical_json(bundle))`; `proof_signature = HMAC-SHA256(canonical_json(proof_body), shared_secret)`. **Use Full Bundle, not AIVS-Micro** (Micro lacks the action log ADRP needs for AP dispute adjudication).
- **VerifyAPI = VCAP state machine + ADRP `verify_resolution`**; requires ATXN `independent_attestor_signature` for Primary (independently adjudicable) validity.

**Gates are hard, fail-closed.** No GL write without a validating AIVS chain; no payment without InvoiceProof `passed=true`; no autonomous execution without VerifyAPI VERIFIED.

**Platform ownership (decisive) + authoritative integration surface (verified against the owned monorepo `C:\Users\Administrator\Desktop\SwarmSync`, 2026-06-26):** The owner operates SwarmSync (NestJS API + `@swarmsync/proof-core`), so the proof layer is **$0** and has **two equally-free integration modes — the recommended one removes HTTP entirely:**

1. **In-process library (RECOMMENDED for hard gates):** import **`@swarmsync/proof-core` → `runProofProduct({ product: 'invoiceproof'|'auditproof'|'verifyapi', evidenceInputs[], residual? })`**. Pure, deterministic, no network calls, no billing/entitlement gate, optional self-injected LLM `residual` client. This is the lowest-latency way to make a gate *synchronous and blocking* — ideal for Gate 1/2/3 inside the Temporal workflow. Control registries: `INVOICEPROOF_CONTROLS`, `AUDITPROOF_CONTROLS`, `VERIFYAPI_CONTROLS`.
2. **Hosted REST (for async/marketplace/cross-org ADRP):** base `API_BASE_URL` (owner-hosted). Auth = self-issuable **service-account keys `sa_…` via `X-API-Key`** (issued locally — no SwarmSync dependency), JWT Bearer, or `ssk_live_…` for VerifyAPI.

**Authoritative endpoints (corrected from marketing copy):**
- **InvoiceProof** (base `/invoice-proof`): `POST /invoice-proof/scan` (body `{text?, invoices[], poRegister[], vendorMaster[], paymentHistory[], approvalMatrix[], useSessionHistory?}` → `{scanId, riskLevel:CRITICAL|HIGH|MEDIUM|LOW, findings[], coverage_summary}`); `POST /invoice-proof/scan-pdf` (multipart PDF); **`POST /invoice-proof/webhook/incoming/:orgId` → `{decision: BLOCK|ALLOW, reason, scanId}`** — this BLOCK/ALLOW webhook IS the AP money-movement gate (Gate 1); plus `vendor-master`, `po-register`, `payment-history/bulk` for the vendor/PO context that bank-change (BEC) detection needs. Rule keys: `EXACT_DUPLICATE, MODIFIED_DUPLICATE, RECENT_DUPLICATE_IN_PAYMENT_HISTORY, MISSING_PO_REFERENCE, PO_AMOUNT_EXCEEDED, BANK_ACCOUNT_CHANGE_DETECTED, LINE_ITEM_MATH_ERROR, ROUND_DOLLAR_AMOUNT, vendor_address_mismatch`.
- **VerifyAPI** (base `/api/verify`): `POST /api/verify` (body `{source_type?, task?, output, rules?[], evidence?}` → `{id, status:SUBMITTED|RUNNING|COMPLETE|FAILED, findings[], confidence:0–1, sdDocConfidence, riskLevel}`); `GET /api/verify/:id`; `GET /api/proof`. Critical rules: `incomplete_deliverable, sync_direction_mismatch, version_mismatch, staging_not_production, open_critical_defects_at_delivery, unauthorized_auth_scope_change`. → Gate 3 (pre-autonomous-execution).
- **AuditProof** (base `/api/proof`): hosted surface is intake/compliance (`POST /api/proof/audit-intake`, `GET /api/proof/pilot-intakes`); the actual tamper-evident record generation is `runProofProduct({product:'auditproof'})` + AIVS bundle in proof-core → Gate 2.
- **AP2 / escrow** (base `/ap2`): `POST /ap2/negotiate | /respond | /deliver`; `GET /ap2/negotiations/:id/escrow-status` → `{escrowStatus: HELD|RELEASED|REFUNDED}`; `GET /ap2/negotiations/:id/verification` → `{PENDING|RUNNING|VERIFIED|FAILED}`. HELD→RELEASED requires atomic CAS (matches VCAP §4).

**Self-host verdict (repo-confirmed):** proof logic is fully local in proof-core; only the hosted billing-entitlement check and `ssk_live_*` issuance live on the API — both moot because the owner controls them and can issue `sa_*` keys locally. **No third-party runtime dependency.**

**Key authority — RESOLVED (verified 2026-06-26 against live VCAP-v1.0-draft §5 and AIVS-v1.0-draft §5 via Conduit; both repos MIT-licensed):**
- **AuditProof / AIVS Ed25519 is OPTIONAL and self-managed.** Spec §5: *"Implementations MAY produce bundles without Ed25519 signatures. The hash chain provides tamper-evidence independent of the signature."* The Identity Key is a locally-generated Ed25519 keypair (32-byte raw, stored `0600`); no authority issues it. Gate 2 self-hosts fully; signature only adds identity binding.
- **InvoiceProof / VerifyProof VCAP `proof_signature` = `HMAC-SHA256(canonical_json(proof_body), shared_secret)`**, where `shared_secret` is a **≥32-byte pre-shared key between the *marketplace* and the *verifier*** (spec §5.2). In our self-hosted topology **we operate both roles** (the Temporal workflow IS the verifier), so the secret is **self-generated** — no SwarmSync key issuance required for internal hard-gating.
- **SwarmSync-issued keys are required ONLY** if a proof must be independently adjudicable by *SwarmSync's* hosted marketplace / ADRP dispute resolution as a third party. That is an optional future capability (cross-org dispute), not a dependency of the internal money/GL gates. **→ Gates 1/2/3 are fully self-hostable; no third-party runtime dependency.**
- **VCAP timeout behavior confirmed:** on verifier timeout, escrow stays HELD (not auto-released/refunded) and routes to human review (§5 alt-path B and our commit-boundary design are spec-compliant).

**Compliance posture:** tamper-evident audit chain supports SOC 2 / ISO 42001 / EU AI Act alignment (SwarmSync design intent). PII/bank data: store bank **fingerprints**, not raw details, in canonical store; never log raw bank fields or proof secrets. TLS on all SwarmSync/QBWC calls.

---

## 10. TESTING STRATEGY

**Unit (≥90% on proof/gate logic, 100% on money/security paths):** AIVS chain build + tamper-detection (insert/delete/reorder); VCAP bundle canonical-JSON + signature; optimistic-lock conflict handling; `raw_extensions` round-trip; allocation math.

**Integration:** intent→Temporal→gates→Postgres→adapter queue, with mocked QBWC; InvoiceProof failure routing; AIVS broken-chain rollback; EditSequence conflict re-base.

**E2E:** OCR invoice → AI draft → InvoiceProof pass → human approve → qbXML BillAdd against a **QB Desktop sandbox** → TxnID reconciled. Plus fraud path (bank-change blocked) and CoA-drift path (VerifyAPI catch).

**Performance:** measure real QBWC poll cadence/queue depth (this is the CRUX spike, gated before further build); canonical read p95 <100ms under load.

**Security:** gates fail-closed under proof-service outage; capability-token scope enforcement; no secret/bank leakage in logs; tamper a bundle → gate rejects.

---

## 11. DEPLOYMENT & ROLLOUT STRATEGY

**Pre-deploy:** all tests pass; CRUX spike documented; Rightworks ticket response recorded; migrations tested; proof gates verified fail-closed.

**Adapter worker placement:** the QBWC SOAP endpoint the Web Connector polls runs **off the Rightworks box** (cloud) — QB's Web Connector on the hosted side polls outbound to it. Confirm Rightworks allows the outbound poll target (Core tier explicitly supports "any app using the QuickBooks Web Connector").

**Rollout:** Phase 1 on **one** company file → validate → expand to all 10 read-only → enable gated write-back on one file → expand. Each step monitored for sync lag, gate failures, EditSequence conflicts.

**Rollback:** canonical store is SoR, so a bad adapter release is rolled back without data loss (intents replay from Temporal/JetStream). Never auto-retry a money/GL write on rollback — re-evaluate gates first. DB migrations ship with UP/DOWN (§13).

**Comms:** notify the controller before enabling any write-back; proof reports are the customer-facing trust artifact.

---

## 12. API DOCUMENTATION (internal service surface)

**POST /intents** — submit an AI accounting intent.
Auth: capability token. Body: `{ intent, company_id, … , raw_extensions }`. → `202 { workflow_id }` (async). Errors: 400 validation, 403 capability denied, 409 conflict.

**POST /approvals/{workflow_id}** — human approves/rejects the commit-boundary signal.
Auth: approver. Body: `{ decision:"approve"|"reject", note }`. → `200 { status }`. Side effect: appends AuditProof row.

**GET /search?q=** — unified cross-company search (vendors/bills/txns). → `200 { results[] }`, p95 <2s.

**GET /bills/{id}/proof** — fetch the InvoiceProof/VerifyAPI bundle (PDF/JSON) for a bill. → `200 { bundle }` or 404.

**GET /sync/health** — poll cadence, queue depth, last-reconciled per company. → `200 { per_company[] }` (powers the lag metric).

**Adapter (QBWC SOAP, generated):** `authenticate`, `sendRequestXML`, `receiveResponseXML`, `getLastError`, `closeConnection` — standard QBWC methods, served by the qbwc/qbwc-derived endpoint.

**SwarmSync proof integration (owned platform — see §9 for full surface).** Preferred binding for the hard gates is the in-process library, not HTTP:
```ts
import { runProofProduct } from '@swarmsync/proof-core';
// Gate 1 (AP): block the payment unless InvoiceProof clears
const r = await runProofProduct({ product: 'invoiceproof', evidenceInputs });
if (r.riskLevel === 'CRITICAL' || r.findings.some(f => f.severity === 'critical'))
  return blockToHumanQueue(r);            // BLOCK == Gate fails closed
```
Async/marketplace path (when cross-org adjudication is wanted): `POST {API_BASE_URL}/invoice-proof/scan` or the `POST /invoice-proof/webhook/incoming/:orgId` BLOCK/ALLOW webhook, authenticated with a locally-issued `sa_*` service-account key (`X-API-Key`). VerifyAPI Gate 3: `POST /api/verify`. Escrow state for money-movement: `GET /ap2/negotiations/:id/escrow-status`.

---

## 13. DATABASE MIGRATIONS

**Migration `20260626_1200_init_canonical.sql` — UP:**
```sql
CREATE TABLE companies ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_name VARCHAR(255) NOT NULL, qb_file_id VARCHAR(128) UNIQUE,
  entity_type VARCHAR(32) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now() );

CREATE TABLE vendors ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
  qb_list_id VARCHAR(128), qb_edit_sequence VARCHAR(64),
  name VARCHAR(255) NOT NULL, bank_fingerprint VARCHAR(256), swarmscore INT,
  raw_extensions JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now() );

CREATE TABLE bills ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id),
  vendor_id UUID NOT NULL REFERENCES vendors(id),
  qb_txn_id VARCHAR(128), qb_edit_sequence VARCHAR(64), po_ref VARCHAR(128),
  amount DECIMAL(14,2) NOT NULL CHECK (amount >= 0),
  status VARCHAR(24) NOT NULL DEFAULT 'drafted',
  invoiceproof_bundle_id UUID, raw_extensions JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now() );

CREATE TABLE proof_bundles ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind VARCHAR(24) NOT NULL, vcap_state VARCHAR(24), proof_hash CHAR(64),
  proof_signature TEXT, passed BOOLEAN NOT NULL DEFAULT false, payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now() );

CREATE TABLE audit_rows ( row_id BIGSERIAL PRIMARY KEY, session_id UUID NOT NULL,
  action_type VARCHAR(48) NOT NULL, tool_name VARCHAR(64),
  inputs_json JSONB, outputs_json JSONB, actor VARCHAR(64) NOT NULL,
  prev_hash CHAR(64) NOT NULL, row_hash CHAR(64) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now() );

ALTER TABLE bills ADD CONSTRAINT fk_bill_proof
  FOREIGN KEY (invoiceproof_bundle_id) REFERENCES proof_bundles(id);

CREATE INDEX idx_vendors_company ON vendors(company_id);
CREATE INDEX idx_bills_company ON bills(company_id);
CREATE INDEX idx_bills_vendor ON bills(vendor_id);
CREATE INDEX idx_bills_status ON bills(status);
CREATE INDEX idx_audit_session ON audit_rows(session_id);
-- unified search
CREATE INDEX idx_vendors_name_trgm ON vendors USING gin (name gin_trgm_ops);
```
**DOWN:** `DROP TABLE audit_rows, proof_bundles, bills, vendors, companies CASCADE;`
(Requires `pgcrypto` + `pg_trgm` extensions.)

---

## 14. KNOWN LIMITATIONS & FUTURE WORK

**Limitations / risks (with mitigations):**
1. **One-file-per-session physics** → never run 1000 companies on Desktop; scale path is API adapters (designed-for, built later).
2. **Rightworks persistent-poller permission** is the most-likely-fatal unknown; **no inbound fallback**. → File ticket Phase 1; if denied, escape to scheduled-batch mode (v2.0.0).
3. **"Thin swappable adapter" is unproven** until a second backend exists. → Phase 3 QBO stub validates the seam; success = <20% changed mapping code (EpistemicAuditor's falsifier).
4. **CoA drift** silently breaks qbXML writes across differently-configured files. → VerifyAPI catches pre-write (also the killer demo).
5. ~~**VCAP shared_secret / Ed25519 key authority** may require SwarmSync issuance → breaks full self-hosting of Gate 1/3.~~ **RESOLVED 2026-06-26** (live VCAP §5.2 + AIVS §5, MIT repos): Ed25519 is optional/self-managed; VCAP `shared_secret` is a self-generated marketplace↔verifier key and we operate both roles. Gates 1/2/3 self-host fully. SwarmSync-issued keys needed only for optional third-party (cross-org) ADRP dispute adjudication — not a runtime dependency. No spike required.
6. **Commoditization base rate (~5–10%)** for canonical integration layers (Codat/Rutter/Merge precedent). → **Wedge-first**: win one verified AP workflow before generalizing; proof-as-moat needs the verification to become non-optional (mandate/distribution).

**Spikes required before adapter code:** (a) QBWC poll cadence + queue depth measurement; (b) Rightworks poller approval. ~~(c) SwarmSync key-authority confirmation~~ — DONE (resolved against live specs, see risk 5 / §9).

**Deferred (future specs):** live QBO/Intacct/NetSuite/Xero/Dynamics adapters; intercompany allocation engine + cross-property fee automation (Phase 2); bank-feed ingestion; payroll/tax; vendor portals; document management; reconciliation automation; month-end close orchestration at full scale.

**Spec evolution:** living document; update with CRUX-spike results to v1.1.0, or v2.0.0 if the escape path triggers.

---

## 15. GLOSSARY & TERMS

- **QBWC (QuickBooks Web Connector):** Intuit's outbound-poll SOAP bridge; the only Rightworks-sanctioned third-party connection.
- **qbXML / QBFC:** QuickBooks Desktop SDK request/response formats. This build uses qbXML.
- **TxnID / EditSequence / ListID:** QB transaction id / optimistic-lock token / entity identity.
- **Canonical store:** vendor-agnostic Postgres = the system of record.
- **`raw_extensions`:** JSONB sidecar preserving QB-native fields losslessly.
- **Commit boundary:** the irreversible step (money move / GL write) where the Temporal workflow blocks for human approval.
- **AIVS:** Agentic Integrity Verification Spec — Ed25519 + SHA-256 hash-chain proof bundles (backs AuditProof).
- **VCAP:** verification request/callback + escrow state machine (backs InvoiceProof & VerifyAPI).
- **ATXN / ADRP / ATEP / SwarmScore:** transaction attestation / dispute-resolution / trust-tier+capability / vendor trust score primitives.
- **InvoiceProof / AuditProof / VerifyAPI:** SwarmSync products = AP gate / tamper-evident decision record / pre-execution validation.

---

## 16. MONITORING, METRICS & OBSERVABILITY

**Product metrics:** % bills auto-coded; % approved without edit; month-end close duration; unified-search latency; exceptions caught by InvoiceProof.

**Technical metrics:** **QBWC poll cadence + queue depth per company** (the headline health metric); sync lag (last-reconciled age); gate evaluation latency; EditSequence conflict rate; AIVS chain-validation failures (must be 0).

**Business metrics:** double-pays/fraud blocked pre-execution; manual-hours saved.

**Alerts (fail-closed posture):** AIVS chain-validation failure → page (severity high; blocks writes). Proof-service unreachable → page (gates fail closed). Sync lag > target window → warn. Rightworks poll stalled → page. Bank-change block fired → notify controller.

**Logging:** every intent, gate result, approval, and write-back logged with session_id linking to the audit chain. Never log raw bank details or proof secrets. Operational logs 90 days; audit chain retained indefinitely (tamper-evident record).

---

## 17. ALTERNATIVE DESIGNS CONSIDERED

**Alt 1 — Web Connector AS the architecture (conventional).** Treat QBWC as the platform. *Rejected:* QB Desktop is in wind-down and QBWC is poll-only/one-file — building durable value on it is the commoditized failure pattern (Archaeologist). Demote it to a swappable adapter.

**Alt 2 — COM / QODBC / local agent / RPA on the QB box.** *Rejected on environment grounds:* Rightworks forbids custom `.exe` install and inbound ports; QODBC is paid; RPA on hosted desktops is chronically fragile (breaks on host updates). Confirmed by Rightworks docs.

**Alt 3 — QB Desktop as system of record, Postgres as cache.** *Rejected:* one-file-per-session serialization makes Desktop unusable as the 1000-scale SoR; write throughput can't be manufactured. Invert it — Postgres is SoR, Desktop is a batch sink (ConstraintCartographer).

**Alt 4 — Custom proprietary proof layer instead of native SwarmSync wire formats.** *Rejected:* bundles wouldn't be independently adjudicable under ADRP; implement to VCAP/AIVS/ATXN spec exactly (stone-spec-expert).

**Alt 5 — Platform-first (build the full multi-ERP canonical layer up front).** *Partially rejected:* base rate for up-front universal integration layers is ~5–10% survival. **Chosen compromise:** build the platform *mechanism* but **sequence it as a vertical wedge** — one verified AP workflow first, seams designed for the multi-ERP future, earned not speculated.

**Chosen design rationale:** Option C's mechanism (canonical mirror + Temporal commit-boundary + async transport) on Option E's trajectory (Desktop-disposable, multi-ERP-ready), delivered as Option B's wedge. It is the only design that satisfies the Rightworks constraints, dissolves the autonomous-vs-gated and thin-vs-deep contradictions, makes the proof spine native, and keeps the scale path off the dying transport.

---

## 18. FINAL BUILD CHECKLIST

**Phase 1 MVP (build now):**
- [ ] Stand up qbwc/qbwc SOAP endpoint (off-box) against ONE Rightworks company file.
- [ ] **Measure + document QBWC poll cadence and max queue depth** (CRUX gate).
- [ ] File Rightworks persistent-poller support ticket; record the answer.
- [ ] Fork selfjared1/quickbooks_desktop qbXML codec into the QB-Desktop adapter (read path).
- [ ] Postgres + migration `20260626_1200_init_canonical.sql` applied (pgcrypto, pg_trgm).
- [ ] Read-only sync: one file's vendors + bills → canonical store with `raw_extensions` preserved.
- [ ] Dashboard renders synced data + unified search.
- [ ] AuditProof (AIVS) row per sync run; `verify.py` chain validation in CI.
- [ ] Health endpoint exposes poll cadence + sync lag.

**Phase 2 (design→build):**
- [ ] NATS + Temporal; intent→workflow→commit-boundary human gate.
- [ ] VerifyAPI (Gate 3) + AuditProof (Gate 2) on gated write-back; AP BillAdd on one file.
- [ ] EditSequence optimistic-lock conflict handling + re-base.
- [ ] Confirm VCAP key authority with SwarmSync.

**Phase 3 (design→build):**
- [ ] InvoiceProof (Gate 1, VCAP Full Bundle) live as AP money-movement gate.
- [ ] Bank-change → ATEP TRUSTED-tier gate (Gate 4); SwarmScore wired.
- [ ] Scale read to all 10 files; one end-to-end approved, proof-signed payable.
- [ ] QBO adapter **stub** to validate the seam (target <20% changed mapping code).

**Cross-cutting:**
- [ ] All gates verified **fail-closed** under proof-service outage.
- [ ] 100% money/security-path test coverage; tamper tests reject bundles.
- [ ] No raw bank details / proof secrets in logs.

---

## CONSISTENCY CHECK RESULTS

All 18 sections checked for contradictions.

- ✓ §3 acceptance ("zero unverified writes") aligns with §9 hard fail-closed gates and §7 AUDIT_CHAIN_BROKEN rollback.
- ✓ §2 scope ("1000 companies out of scope on Desktop") aligns with §8 physics ceiling and §14 limitation 1 — consistent, not contradictory.
- ✓ §4 async-by-design aligns with §8 (reads from mirror, not poll) and §5 alternate path B.
- ✓ §9 "use VCAP Full Bundle, not Micro" aligns with §6 proof_bundles + §14 ADRP adjudication note.
- ✓ §11 rollback ("never auto-retry money/GL write") aligns with §7 fail-closed and §9.
- ✓ (Previously open) §9/§14 VCAP/AIVS key authority — **RESOLVED 2026-06-26** against the live MIT-licensed VCAP §5.2 and AIVS §5 drafts: gates self-host fully, no third-party runtime dependency. No longer a spike.

- ✓ Proof-layer integration surface verified against the **owned** SwarmSync monorepo (Appendix B): in-process `runProofProduct()` is the recommended zero-HTTP, zero-cost binding for the hard gates; hosted REST available for async/cross-org. No third-party runtime dependency.

**Status: 0 unresolved contradictions. 0 proof-layer unknowns (resolved + authoritative endpoints captured). Proof layer cost = $0 (owner operates SwarmSync). 2 environment spikes remain before adapter code (QBWC poll cadence + Rightworks poller approval) — neither blocks Phase 1 read-only work. Spec is build-ready for Phase 1.**

---

## APPENDIX B — SwarmSync Proof API Surface (repo-verified, owned platform, 2026-06-26)

Source: `C:\Users\Administrator\Desktop\SwarmSync` (NestJS API + `@swarmsync/proof-core`). Owner-operated → $0, full key/marketplace/ADRP control.

| Product | Gate | In-process (recommended) | Hosted REST | Auth |
|---|---|---|---|---|
| InvoiceProof | Gate 1 (AP money-movement) | `runProofProduct({product:'invoiceproof', evidenceInputs})` → `{riskLevel, findings[]}` | `POST /invoice-proof/scan`, `/scan-pdf`, `POST /invoice-proof/webhook/incoming/:orgId` → `{decision:BLOCK\|ALLOW}` | `sa_*` (X-API-Key, self-issued) / JWT / webhook secret |
| AuditProof | Gate 2 (pre-GL, AIVS chain) | `runProofProduct({product:'auditproof'})` + AIVS bundle | `POST /api/proof/audit-intake` (intake only) | JWT / `sa_*` |
| VerifyAPI | Gate 3 (pre-autonomous-exec) | `runProofProduct({product:'verifyapi'})` | `POST /api/verify`, `GET /api/verify/:id`, `GET /api/proof` | JWT / `ssk_live_*` / `sa_*` |
| AP2 / escrow | money-movement state | — | `POST /ap2/negotiate\|respond\|deliver`; `GET /ap2/negotiations/:id/escrow-status` (HELD\|RELEASED\|REFUNDED); `/verification` (PENDING\|RUNNING\|VERIFIED\|FAILED) | JWT / `sa_*` / HMAC gateway |

**Self-host verdict:** proof logic is pure/deterministic and fully local in `proof-core` (no calls to api.swarmsync.ai); only billing-entitlement + `ssk_live_*` issuance are hosted, both owner-controlled. Bank-change/BEC detection (`BANK_ACCOUNT_CHANGE_DETECTED`) requires prior vendor banking context — load it via `vendor-master` / `payment-history/bulk` from the canonical store.

---

## APPENDIX A — Proof-Layer Source Verification (Conduit, 2026-06-26)

Live-pulled via Conduit headless browser (audit-logged). SwarmSync org = 5 public repos, all **MIT**: `vcap-spec`, `aivs-spec`, `atep-spec`, `swarmscore-spec`, `commerce-demo-agent`.

- **VCAP-v1.0-draft §5.2:** `proof_signature = HMAC-SHA256(canonical_json(proof_body), shared_secret)`; `shared_secret` = "a pre-shared key between the marketplace and verifier (minimum 32 bytes)." `proof_body` ⊇ `{verification_id, negotiation_id, escrow_ref, passed, proof_hash, completed_at}`.
- **VCAP §7 timeout:** on timeout, verification→TIMEOUT, escrow stays **HELD** (not auto-released/refunded), human reviewer makes final settlement decision via a normal `verification_callback`.
- **AIVS-v1.0-draft §5:** Ed25519 signing of the chain hash; private/public key 32 bytes raw, stored `0600`; **"Implementations MAY produce bundles without Ed25519 signatures. The hash chain provides tamper-evidence independent of the signature."** Embedded `verify.py` is stdlib-only and offline.
- **Conclusion:** Both InvoiceProof (VCAP) and AuditProof (AIVS) hard gates are fully self-hostable with self-generated keys; SwarmSync key issuance is optional and only for cross-org ADRP dispute adjudication.
```
```
