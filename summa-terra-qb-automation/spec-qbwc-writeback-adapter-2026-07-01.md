# Spec: QBWC Write-Back Adapter (Phase 6) Under Business-Hours/Session-Tied Polling

## SPEC METADATA
```
Spec Title: QBWC Write-Back Adapter — Business-Hours/Session-Tied Polling
Version: 1.0.0
Author: AI Accounting Hub integration team
Last Updated: 2026-07-01
Status: Ready for Build
Timeline: 3–4 weeks (SOAP endpoint + adapter logic + sandbox E2E test plan execution)
Confidence Level: ~80% — qbXML BillAdd mechanics assumed standard; exact EditSequence/TxnID retry behavior must be validated empirically against the sandbox file (Section 14)
Next Steps: Ready to build once spec-qb-sandbox-environment-2026-07-01.md (Spec A) has completed its handoff (Section 18 of that spec)
```

## ARCHITECTURE GOVERNOR SUMMARY
```
Feature: QBWC Write-Back Adapter, Phase 6
Completed: 2026-07-01

Existing systems touched: 6 — canonical Postgres (bills, draw_packages, proof_bundles, audit_rows tables in ai-accounting-hub-ralph), Temporal workflow engine (app/workflow/), app/integration/intents_router.py (approval endpoints), app/integration/daily_digest.py (existing queue-depth monitoring — REUSE), the sandbox QuickBooks company file (Spec A), Rightworks-hosted QBWC runtime
NOT touched: app/scale/, app/transport/ existing stubs beyond what this spec defines, app/canonical/, app/ingestion/, System A (STV Gmail AccountingOS) — this spec is entirely System B / QB-write-back-side
Source of truth conflicts: 0 — canonical Postgres remains system of record per CLAUDE.md; QuickBooks remains an eventually-consistent batch sink; this spec does not change that invariant, it implements the sink's write path
Stateful objects mapped: 3 — outbox/queue item (queued → sent-to-qbwc → confirmed-txnid → reconciled | failed), QBWC session (idle → polling → session-active-writing → session-ended), bill row (already modeled in intents_router.py — approved → qb_synced added by this spec)
Money/auth/proof boundary crossings: 1 — this is the ONLY point in the entire system where an approved, proof-gated, human-approved financial intent becomes a real accounting-system transaction (BillAdd). This is the single highest-stakes boundary in the whole integration layer.
Reuse opportunities found (DO NOT rebuild): app/integration/daily_digest.py already aggregates queue-depth/staleness metrics — extend it, do not build a parallel monitoring system; existing AIVS audit_rows / append_audit_row (app/audit/service.py) — reuse for the QBWC write commit, do not invent a second audit mechanism; existing approval gate in intents_router.py (_resolve_bill_approval) — this spec only adds what happens AFTER approval, does not re-implement approval
Must-not-break guarantees: 5 — no bill is ever written to QB without a passed proof_bundles row (Gate 1) AND an 'approved' bill status (human gate); no double-post on retry (idempotency via TxnID/EditSequence tracking); no write ever targets a production file until the sandbox E2E plan (Section 5) fully passes; the 4 existing proof gates (CLAUDE.md) remain fail-closed; canonical Postgres remains queryable/correct even if QuickBooks is fully offline for days
Definition-of-done conditions: 8 (see Section 3)
Technical spikes required before spec is final: 2 — exact qbXML BillAdd EditSequence conflict-retry behavior (validate empirically against sandbox, Section 14); real observed poll interval reliability during a normal business-hours session (validate empirically, Section 14)

Status: ✅ CLEAR TO SPEC
```

---

## 1. Executive Summary

Build the QBWC (QuickBooks Web Connector) write-back adapter that drains approved, proof-gated bill intents from canonical Postgres and writes them into QuickBooks Desktop Enterprise as real `BillAdd` transactions — the final, previously-unbuilt link in the AI Accounting Hub pipeline. This spec is written against a now-confirmed architecture constraint (resolved 2026-07-01 via written Rightworks confirmation): there is no persistent/unattended poller available on the Rightworks hosted environment, so the adapter must be explicitly designed for **business-hours, session-tied polling** rather than continuous 24/7 sync. Business goal: close the loop so approved bills actually land in the books without manual re-entry, while being honest in the design about when that sync happens. Primary user: the integration engineer building this adapter, with STV's controller/Ben as the eventual runtime beneficiary (bills appear in QuickBooks without manual entry during their normal workday). This must be built and fully proven against the sandbox file (Spec A) before it ever touches a production company file.

## 2. Scope Definition & Non-Scope

**In scope:**
- A FastAPI-hosted SOAP/qbXML endpoint (`/qbwc`) that QuickBooks Web Connector polls, implementing the standard QBWC session handshake (`serverVersion`, `clientVersion`, `authenticate`, `sendRequestXML`, `receiveResponseXML`, `closeConnection`).
- Adapter logic that reads approved, `invoiceproof_bundle_id`-populated bills from canonical Postgres (via the existing `bills` table — no new schema needed for the read side) and emits `BillAdd` qbXML requests.
- Idempotency handling using QuickBooks' `TxnID`/`EditSequence` semantics, so a retried or resumed session never double-posts a bill.
- Explicit handling of the business-hours/session-tied polling model: what happens to intents queued during off-hours/weekend gaps, and reuse of the existing daily-digest queue-depth monitoring to surface stale queued bills.
- The 9-step sandbox end-to-end test plan (structural build → isolation proof → Gmail ingest → Gate 1 → Temporal durability → human approval → QBWC drain → round-trip reconciliation → negative/failure drills), executed against the sandbox file from Spec A.
- The cutover strategy from sandbox to production: new/low-history entities may be built fresh in the new structure; the 10+ year production files are overlaid with the new Class/cost-code structure, never rebuilt from scratch.

**Out of scope:**
- Building the sandbox company file itself (Spec A — this spec consumes it as a precondition).
- ItemAdd / draw-fee QB write-back beyond BillAdd — noted as future work once BillAdd is proven (Section 14).
- Any change to Gate 1 (InvoiceProof), Temporal, or the approval endpoints themselves — those are already built and audited (see `spec-compliance-audit-stv-integration-layer-2026-06-30.md`); this spec only adds what happens after a bill reaches `status='approved'`.
- Any attempt to bypass or work around the confirmed business-hours polling constraint (e.g., mouse-jigglers, unsupported scheduled-task workarounds) — Rightworks explicitly declined to support this; this spec designs around the constraint, not against it.
- Migrating production company files (deferred to a separate cutover effort, outline only in Section 14).

**Phase dependencies:**
- Depends on: `spec-qb-sandbox-environment-2026-07-01.md` (Spec A) — hard precondition, cannot begin sandbox E2E testing (Section 5, steps 3+) without it.
- Depends on: existing, already-built and audited approval/Gate-1/Temporal pipeline in `ai-accounting-hub-ralph/app/integration/intents_router.py` (read-only dependency — this spec does not modify it).
- Depended on by: any future production cutover work (out of scope here, referenced in Section 14).

## 3. Business Context & Acceptance Criteria

**Business goal:** Eliminate manual bill re-entry into QuickBooks for approved bills, while being architecturally honest that sync only happens during business hours (a real, accepted constraint, not a bug).

**Success metric:** % of approved bills that reach `qb_synced` status without manual intervention, measured against the sandbox file first, then a controlled production pilot.

**Target:** 100% of approved bills in the sandbox file sync correctly (right vendor, right cost-code Item, right Class, right Customer:Job, correct TxnID captured back) within one business-hours session of approval; 0% double-posts across repeated test runs.

**Acceptance criteria:**
- [ ] `/qbwc` SOAP endpoint deployed and responding to a real QuickBooks Web Connector handshake.
- [ ] Sandbox `.qwc` (from Spec A) successfully polls this endpoint and completes a full sync cycle with `Last result: Success`.
- [ ] An approved bill (Gate 1 passed, human-approved) in canonical Postgres is written to the sandbox QuickBooks file as a correct `BillAdd`, with the returned `TxnID` and `EditSequence` captured back into `bills.raw_extensions`.
- [ ] Re-running the same intent (simulating a retry after a session gap) does NOT create a duplicate bill in QuickBooks.
- [ ] A bill approved outside business hours (simulated: no active session) remains correctly queued in Postgres and syncs on the next business-hours session — verified end-to-end, not just asserted.
- [ ] All 9 sandbox E2E test plan steps (Section 5) pass with saved evidence.
- [ ] Zero writes ever occur against a production company file during this spec's build/test phase.
- [ ] Ben sign-off on sandbox E2E results before any production-file cutover planning begins.

**Spec Status:** Build-phase spec. The two technical spikes noted in the Governor Summary (EditSequence conflict-retry behavior, real poll-interval reliability) should be resolved empirically during Section 5's E2E execution and folded back into this spec as v1.1.0 if behavior differs from what's assumed here.

## 4. Architecture & System Integration

**Data flow:**
```
Canonical Postgres bills table (status='approved', invoiceproof_bundle_id populated)
  → QBWC Adapter Query Handler (on each Web Connector poll cycle, business-hours only)
  → qbXML BillAdd request queued for this session
  → QuickBooks Web Connector (running in the active Rightworks session)
  → QuickBooks Desktop (sandbox file first, production later)
  → qbXML response (TxnID, EditSequence)
  → Adapter writes back: bills.qb_txn_id, bills.qb_edit_sequence, bills.status='qb_synced'
  → AIVS audit_rows entry appended (Gate 2, reusing app/audit/service.py)
  → app/integration/daily_digest.py picks up sync status for the next digest (reuse, no new monitoring system)
```

**Integration points:**
- Inbound: QBWC's outbound poll to `/qbwc` (SOAP). No inbound trigger is ever initiated from QuickBooks' side beyond this poll — consistent with CLAUDE.md's "no inbound connection/listener" guardrail (the poll itself originates from QuickBooks, not from an external caller reaching in).
- Outbound (from this adapter's perspective, during a poll cycle): reads `bills` table, writes `bills.qb_txn_id`/`qb_edit_sequence`/`status`, calls `app.audit.append_audit_row`.
- Reuses: `app/integration/daily_digest.py` aggregation queries — extend with a "bills approved but not yet qb_synced, by age" metric rather than building a new monitor.

**New infrastructure required:**
- `/qbwc` SOAP endpoint (Spyne/zeep, per CLAUDE.md stack — already a listed dependency, not new).
- New columns on `bills`: `qb_txn_id`, `qb_edit_sequence`, `qb_synced_at` (see Section 13).
- A sandbox-then-production `.qwc` deployment pattern (Spec A produces the sandbox `.qwc`; this spec's Section 11 covers production `.qwc` generation as a later, gated step).

**External dependencies:** QuickBooks Web Connector runtime (Rightworks-hosted), qbXML/SOAP protocol (Spyne/zeep, already in the CLAUDE.md stack).

**Ownership map:** Integration engineer owns the adapter code and SOAP endpoint. Ben owns sign-off at the sandbox-E2E gate and the eventual production cutover decision.

## 5. User Flows & Happy Path

**Happy Path: A bill syncs to QuickBooks during a normal business-hours session**

Actor: The system (no human action required at this stage — approval already happened upstream).
Precondition: A bill exists in canonical Postgres with `status='approved'` and a passed `invoiceproof_bundle_id` (i.e., it has already cleared Gate 1 and the human approval gate, per the already-built/audited pipeline).

Steps:
1. STV's bookkeeper logs into the Rightworks hosted desktop for normal daily work; QuickBooks + Web Connector auto-open (per the Rightworks-configured session behavior).
2. Web Connector polls `/qbwc` on its configured interval (target: 15–30 min) for as long as the session stays active.
3. The adapter's query handler finds the approved bill, builds a `BillAdd` qbXML request (vendor, amount, cost-code Item line, Class, Customer:Job, Draw # custom field where applicable).
4. QuickBooks processes the request; returns `TxnID` and `EditSequence`.
5. Adapter writes `qb_txn_id`, `qb_edit_sequence`, `status='qb_synced'`, `qb_synced_at` back to the `bills` row.
6. Adapter appends an AIVS audit row (`action_type='qb_write_confirmed'`) via the existing `append_audit_row` service.
7. Session continues; next poll cycle picks up any newly-approved bills.
8. At end of day, the bookkeeper's session eventually goes idle past the 2-hour Rightworks inactivity window (or they log off) — polling stops until the next business-hours login.

Postcondition: Bill reflected correctly in QuickBooks with a durable TxnID reference; canonical Postgres and QuickBooks agree.

**Alternate path — bill approved outside business hours:** Bill sits in `status='approved'` with no `qb_txn_id` until the next business-hours session begins polling; this is expected, correct behavior, not a failure state. The daily digest (extended per Section 4) surfaces "N bills approved, awaiting QB sync" so this is visible, not silent.

**Alternate path — session interrupted mid-sync (2-hour inactivity logout fires mid-poll):** The in-flight qbXML request either completes (QuickBooks finishes processing) or is cut off. On the next session, the adapter must re-check: did this bill already get a `TxnID` in QuickBooks even though our write-back to Postgres didn't complete? (Section 7 — this is the core idempotency edge case.)

## 6. Data Models & Schema

**Extended `bills` table (new columns, migration in Section 13):**

| Column | Type | Notes |
|---|---|---|
| `qb_txn_id` | TEXT, nullable | QuickBooks' TxnID once BillAdd succeeds; NULL = not yet synced |
| `qb_edit_sequence` | TEXT, nullable | QuickBooks' EditSequence, needed for any future edit/void operations |
| `qb_synced_at` | TIMESTAMPTZ, nullable | When the write-back completed |
| `qb_sync_attempts` | INTEGER, default 0 | Incremented on each attempt; used for stale-queue alerting, not a hard retry cap (business-hours gaps are expected, not failures) |

**qbXML BillAdd request shape (illustrative, per QuickBooks SDK conventions):**
```xml
<BillAddRq requestID="{bill.id}">
  <BillAdd>
    <VendorRef><FullName>{vendor.qb_name}</FullName></VendorRef>
    <TxnDate>{bill.created_at date}</TxnDate>
    <RefNumber>{bill.po_ref}</RefNumber>
    <ExpenseLineAdd>
      <AccountRef><FullName>{cost_code.qb_account}</FullName></AccountRef>
      <Amount>{bill.amount}</Amount>
      <ClassRef><FullName>{phase.qb_class}</FullName></ClassRef>
      <CustomerRef><FullName>{customer_job.qb_name}</FullName></CustomerRef>
    </ExpenseLineAdd>
  </BillAdd>
</BillAddRq>
```
`requestID` is set to `bill.id` (the canonical Postgres UUID) specifically so the adapter can correlate a QBWC response back to the originating bill even across a session gap.

**qbXML response captured:**
```json
{"TxnID": "80000001-1234567890", "EditSequence": "1234567890", "requestID": "<bill.id>"}
```

## 7. Error Handling & Edge Cases

| Scenario | HTTP/qbXML status | Handling |
|---|---|---|
| Session ends mid-BillAdd (2h inactivity logout fires) | N/A — connection drop | On next poll cycle, before re-submitting, the adapter MUST query QuickBooks (`BillQuery` by `RefNumber`/vendor/amount match, or by `requestID` if QuickBooks echoed it) to check whether the bill already posted. **Never blindly resubmit** — this is the highest-risk double-post scenario and must be tested explicitly in Section 5/10. |
| `EditSequence` conflict (concurrent edit detected by QuickBooks) | qbXML error in response | Re-read the current record, apply the adapter's write again with the fresh `EditSequence`, retry once; if it fails twice, mark the bill `status='exception'` and alert via daily digest — do not loop indefinitely |
| Vendor/cost-code/Class/Customer:Job reference doesn't exist in the target QuickBooks file (list drift) | qbXML error, invalid reference | Fail closed: mark `status='exception'`, do NOT auto-create the missing list entry in QuickBooks (list changes are a human decision, not something this adapter should do silently) |
| QBWC session simply never happens (no one logs in for days — weekend, holiday) | N/A | Expected, not an error. Bills accumulate in `status='approved'`, `qb_txn_id IS NULL`. Daily digest surfaces the count/age. Only escalate if age exceeds a reasonable business threshold (e.g., >3 business days), not on every off-hours gap. |
| Duplicate `BillAdd` attempted for a bill that already has `qb_txn_id` populated | N/A — adapter-side check | The query handler's read from Postgres MUST filter `qb_txn_id IS NULL` — a bill with a `TxnID` already recorded is never re-submitted, full stop |
| QuickBooks file is in single-user mode or locked when the poll fires | qbXML error | Log, mark this poll cycle's attempt as failed for that item, retry next cycle within the same or next session — do not treat as a permanent failure |

## 8. Performance & Scalability Requirements

**Explicitly NOT continuous/24-7** — this is the central design constraint of this spec (resolved 2026-07-01, see CLAUDE.md).

- **Poll interval:** 15–30 minutes, configurable via the `.qwc` `RunEveryNMinutes` setting, active only while a business-hours session is open.
- **Coverage window:** Business hours only, tied to normal login activity — no SLA for overnight/weekend delivery. This must be communicated as an accepted design property, not hidden.
- **Throughput:** Given STV's real volume (per `integration-architecture-packet-stv-2026-06-29.md`: ~50–200 vendor bills/month per entity across 10 entities), even at the low end of the polling window this comfortably clears any realistic queue depth within a single business day.
- **Queue depth monitoring:** Reuse `app/integration/daily_digest.py` (already built, 27 tests passing per the recent fix pass) — extend its aggregation to report `bills WHERE status='approved' AND qb_txn_id IS NULL`, bucketed by age, so anyone watching the digest can see if something is stuck longer than a normal business-hours gap would explain.

## 9. Security & Compliance Requirements

**Authentication & authorization:** QBWC's own username/password handshake (per the `.qwc` file, Spec A) gates who can even connect to `/qbwc`. The endpoint itself validates the QBWC session ticket per the standard SOAP handshake; no additional bearer-token layer is needed here since QBWC's protocol already provides this.

**Data protection:** No new PII/bank-detail handling — this adapter only writes accounting entries (vendor name, amount, cost-code, Class, project) already present and approved in canonical Postgres. Per CLAUDE.md: never log raw bank fields; this adapter does not touch bank fields at all (that's ATEP/Gate 4's domain, upstream of this spec).

**Proof boundary (the most important security property in this spec):** This adapter is the ONLY code path in the entire system permitted to write BillAdd to QuickBooks. It MUST verify, at write time (not just trust the upstream `status='approved'` flag), that:
1. `bills.invoiceproof_bundle_id IS NOT NULL`, and
2. the referenced `proof_bundles.passed = True`, and
3. `bills.status = 'approved'`.

This is a defense-in-depth re-check, not a redundant gate — CLAUDE.md's "gates fail closed; never write to books/QB without a valid proof" is a hard guardrail, and this is the last line of defense before an irreversible external write.

**Compliance:** Sandbox-first, then production, is itself a compliance control — no untested code path is permitted to write to the real books.

## 10. Testing Strategy

**The 9-step sandbox end-to-end test plan (executed against Spec A's sandbox file — this IS the primary test strategy for this spec, not a separate afterthought):**

1. **Structural build proof** — confirm the sandbox file (from Spec A) matches the target cost-code/Class structure (already covered by Spec A's own sign-off; re-verified here as a precondition check).
2. **QBWC isolation proof** — confirm the sandbox `.qwc` cannot address any production file (re-verify Spec A's Section 9 result still holds).
3. **Gmail ingest → intent creation** — feed 5–10 representative test bills through the existing System A → `/intents/bill` pipeline (already built/audited); confirm intents land in Postgres with correct fields.
4. **Gate 1 InvoiceProof** — confirm valid bills get a passed proof bundle; confirm a deliberately malformed bill fails closed (already covered by the existing `tests/test_gate1_wiring.py`, re-run here as context, not rebuilt).
5. **Temporal durability** — confirm a pending-approval workflow survives a worker restart mid-flight.
6. **Human approval** — approve via the existing approval UI/API; confirm only approved intents proceed.
7. **QBWC drain (THIS SPEC'S new coverage)** — confirm the adapter picks up the approved bill on the next poll and successfully writes `BillAdd` to the sandbox file.
8. **Round-trip reconciliation (THIS SPEC'S new coverage)** — query the bill back from QuickBooks; diff against the canonical intent; confirm zero field drift; confirm idempotency by re-running the same intent and confirming NO double-post.
9. **Negative/failure drills (THIS SPEC'S new coverage)** — simulate: session-gap-mid-write (Section 7), EditSequence conflict, missing list reference, QBWC offline/queue-growth-then-drain. Each must fail safe and be observable via the daily digest.

**Unit/integration tests (in `ai-accounting-hub-ralph/tests/`, following existing conventions per the recent fix pass — `@pytest.mark.integration`, `RUN_INTEGRATION=1` gated where a real DB/QuickBooks session is needed):**
- `test_qbwc_adapter.py`: BillAdd request-building logic (mocked qbXML response) — vendor/cost-code/Class/Customer:Job mapping correctness.
- `test_qbwc_idempotency.py`: the query handler never selects a bill with `qb_txn_id IS NOT NULL`; simulated session-gap re-check logic (Section 7) does not double-post.
- `test_qbwc_proof_boundary.py`: adapter refuses to write a bill lacking a passed proof bundle or `status != 'approved'`, even if directly invoked (defense-in-depth test — Section 9).
- Extend `tests/test_daily_digest.py`: new assertions for the `qb_txn_id IS NULL` age-bucketed metric.

## 11. Deployment & Rollout Strategy

**Pre-deployment checklist:**
- [ ] Spec A's sandbox file complete and signed off.
- [ ] All 9 E2E steps (Section 10) pass against the sandbox file.
- [ ] `ruff check . && mypy app && pytest -q` green, including the new adapter tests.
- [ ] Ben sign-off specifically on the sandbox E2E results (separate from Spec A's structural sign-off).

**Rollout plan — explicitly staged, sandbox before any production file:**
1. **Stage 1 (this spec's scope):** Deploy `/qbwc` endpoint; register only the sandbox `.qwc`; run all 9 E2E steps repeatedly until stable.
2. **Stage 2 (future, gated on Stage 1 success + Ben approval, NOT automatically part of this spec):** Generate a production `.qwc` for ONE low-volume production entity; run a 2–4 week controlled pilot with production files otherwise closed during testing; reconcile monthly.
3. **Stage 3 (future):** Widen to remaining production entities one at a time.

**Cutover strategy for existing production files (per the research already completed and referenced in the updated architecture docs):**
- **New/low-history entities:** may be built fresh in the new structure directly — cheap, clean.
- **The 10+ year production files:** **overlay** the new Class/cost-code structure onto them via IIF (additive list changes), never rebuild via bulk transaction reimport — IIF/CSV transaction import does not preserve invoice↔payment links or reconciliation status, which would break AR/AP aging and bank reconciliation. This is a hard constraint carried forward from the prior QB Rightworks VPS research, not a new decision made in this spec.

**Rollback plan:** If Stage 1 testing reveals a fundamental problem (e.g., EditSequence handling proves unreliable), no production file is ever touched, so rollback is simply: stop, fix, re-test against the sandbox. If Stage 2's pilot reveals a problem, the pilot entity's file can be restored from a pre-pilot backup (standard QuickBooks backup discipline — **always back up the target file immediately before enabling write-back against it**).

**Communication:** Ben is notified at the Stage 1→2 gate (this spec's actual completion point) and must explicitly approve before Stage 2 begins — this spec's Definition of Done stops at Stage 1.

## 12. API Documentation

**Endpoint: `POST /qbwc` (SOAP, not REST — qbXML/QBWC protocol)**

This does not follow REST conventions; it implements the standard QBWC SOAP contract (`serverVersion`, `clientVersion`, `authenticate`, `sendRequestXML`, `receiveResponseXML`, `connectionError`, `getLastError`, `closeConnection`) via Spyne/zeep, per the CLAUDE.md stack. Full method-by-method qbXML request/response contracts should be documented in the adapter's own module docstring at build time, following the existing pattern in `app/integration/intents_router.py`'s docstrings (spec section references, guardrail letter-codes G1-G9 style).

**No new REST/JSON endpoints are introduced by this spec** — the existing `/intents/*` and `/approvals/*` endpoints (already built) are untouched; this spec only adds the QBWC-facing SOAP surface and its internal read/write logic against `bills`.

## 13. Database Migrations

**Migration: add QBWC write-back tracking columns to `bills`**

```sql
ALTER TABLE bills
  ADD COLUMN qb_txn_id TEXT,
  ADD COLUMN qb_edit_sequence TEXT,
  ADD COLUMN qb_synced_at TIMESTAMPTZ,
  ADD COLUMN qb_sync_attempts INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_bills_pending_qb_sync
  ON bills (status)
  WHERE status = 'approved' AND qb_txn_id IS NULL;
```

**Rollback:**
```sql
DROP INDEX IF EXISTS idx_bills_pending_qb_sync;
ALTER TABLE bills
  DROP COLUMN qb_txn_id,
  DROP COLUMN qb_edit_sequence,
  DROP COLUMN qb_synced_at,
  DROP COLUMN qb_sync_attempts;
```

Follow the same Alembic migration file convention established in the recent fix pass (`ai-accounting-hub-ralph/migrations/versions/`), and apply via `supabase-aihub` MCP or Alembic per CLAUDE.md's Database/MCP section — never via the default `supabase` MCP (that's SwarmSync's).

## 14. Known Limitations & Future Work

**Limitations:**
1. **No SLA for off-hours delivery, by design.** This must be stated plainly to Ben and any stakeholder — bills approved Friday evening will not reach QuickBooks until the next business-hours login, per the confirmed Rightworks constraint. This is not a bug to fix later; it's the accepted architecture.
2. **EditSequence conflict-retry behavior is a technical spike, not yet empirically validated.** Resolve during Section 10's E2E execution; if real behavior differs from Section 7's assumed handling, update this spec to v1.1.0 with the observed behavior.
3. **Real poll-interval reliability during a live business-hours session is also a technical spike.** The 15–30 min target is a starting assumption; measure actual cadence during E2E testing and adjust `.qwc` `RunEveryNMinutes` accordingly.

**Deferred / future work:**
- ItemAdd / draw-fee QB write-back (currently only bill-level BillAdd is in scope; draw-package fee entries per `SPEC_SUMMA_TERRA_BINDING.md` §5.3 are a natural Phase 7 extension once BillAdd is proven stable).
- Production cutover execution itself (Stage 2/3 in Section 11) — this spec covers Stage 1 only; Stage 2/3 should get their own spec once Stage 1 is signed off, since the risk profile (real production financial data) warrants fresh Architecture Governor analysis at that time.
- Automated overnight batch-ETL fallback, previously proposed as an escape path in the architecture-decision-packet's original Risk R1 — no longer the primary mitigation now that business-hours polling is confirmed workable, but worth revisiting only if real usage shows business-hours coverage is insufficient.

## 15. Glossary & Terms

- **QBWC:** QuickBooks Web Connector — the only Rightworks-sanctioned transport for QuickBooks Desktop integration; outbound-poll only.
- **BillAdd:** The qbXML request type that creates a new bill/vendor-expense transaction in QuickBooks.
- **TxnID / EditSequence:** QuickBooks' transaction identifier and optimistic-concurrency version stamp; both are required for any future edit and for idempotency detection in this spec.
- **Business-hours, session-tied polling:** The confirmed final architecture (2026-07-01) — QBWC only syncs while a human's normal Rightworks login session is active; no persistent/unattended polling exists or is supported.
- **Sandbox file:** See Spec A's glossary — the isolated test company file this spec's E2E plan runs against.
- **CIP bucket / cost-code Item / Class / Customer:Job / Draw #:** See `SPEC_SUMMA_TERRA_BINDING.md` and Spec A's glossary — the dimensional model this adapter must correctly populate on every BillAdd.

## 16. Monitoring, Metrics & Observability

**Extend `app/integration/daily_digest.py` (reuse, do not rebuild):**
- New metric: count and max-age of `bills WHERE status='approved' AND qb_txn_id IS NULL`, i.e., approved-but-not-yet-synced-to-QB.
- New metric: `qb_sync_attempts` distribution — surfaces bills that have seen repeated failed attempts (potential list-reference drift or EditSequence conflict pattern).
- New metric: last successful QBWC poll timestamp (from `/qbwc`'s own session handling) — if this is stale for longer than a normal business-hours gap would explain (e.g., >3 business days), that's worth a human look.

**Logging:** Every `BillAdd` request and response logged with `requestID` (=bill UUID) correlation, at the same audit-trail rigor as the existing AIVS `append_audit_row` calls elsewhere in the codebase — this is a proof boundary (Section 9), and its evidence trail matters as much as the write itself.

## 17. Alternative Designs Considered

**Alternative 1: Continuous/24-7 polling via a persistent background service**
Pros: no off-hours delivery gap.
Cons: **not available** — Rightworks confirmed in writing (2026-07-01) there is no supported path to this; the global 2-hour inactivity auto-logout is non-adjustable and explicitly not exempted for scheduled tasks/service accounts.
Why rejected: not a design choice, a hard external constraint. Documented here for completeness per the spec methodology, but this was never actually a live option once Rightworks responded.

**Alternative 2: Scheduled batch-ETL export (originally proposed as the escape path in the architecture-decision-packet's Risk R1)**
Pros: doesn't depend on session timing at all; could run as a true background job.
Cons: QuickBooks Desktop has no API to receive a batch import unattended either (same underlying constraint — writing to QB Desktop requires QBWC, which requires an active session, or manual IIF import, which requires a human). Batch-ETL doesn't actually solve the unattended-write problem; it just moves where the manual step happens.
Why rejected as primary: business-hours/session-tied QBWC polling already achieves near-equivalent coverage (bills sync during the same day they're approved, in nearly all real cases) with far less engineering complexity than building a parallel batch pipeline. Kept as a documented fallback only if real usage proves session-tied coverage insufficient (Section 14).

**Chosen design rationale:** Business-hours, session-tied QBWC polling directly matches the confirmed, supported Rightworks environment, reuses the already-built approval/proof/audit pipeline without any changes to it, and is honest about its one real limitation (off-hours delivery gap) rather than hiding it behind false continuous-sync promises.

## 18. Final Build Checklist

**Code Implementation Checklist:**
- [ ] `/qbwc` SOAP endpoint implemented (Spyne/zeep) with full QBWC handshake methods
- [ ] Query handler: selects `bills WHERE status='approved' AND qb_txn_id IS NULL`, re-verifies proof boundary (Section 9) at write time
- [ ] BillAdd qbXML request builder: vendor, amount, cost-code Item, Class, Customer:Job, Draw # mapping
- [ ] Response handler: writes `qb_txn_id`, `qb_edit_sequence`, `qb_synced_at`, `status='qb_synced'`; appends AIVS audit row
- [ ] Session-gap re-check logic (Section 7): before resubmitting, query QuickBooks to confirm the bill didn't already post
- [ ] EditSequence conflict handling: re-read → retry once → mark `exception` on second failure
- [ ] Database migration: `qb_txn_id`, `qb_edit_sequence`, `qb_synced_at`, `qb_sync_attempts` columns + index (Section 13)
- [ ] `app/integration/daily_digest.py` extended with pending-sync age/count metrics (Section 16)

**Testing Checklist:**
- [ ] Unit tests: BillAdd request-building, idempotency filter, proof-boundary refusal (Section 10)
- [ ] All 9 sandbox E2E steps executed and passed with saved evidence (Section 10)
- [ ] Negative drills: session-gap-mid-write, EditSequence conflict, missing list reference, QBWC-offline-then-drain — each verified to fail safe
- [ ] `ruff check . && mypy app && pytest -q` exits 0 clean

**Deployment Checklist:**
- [ ] Spec A sandbox handoff received and its sign-off confirmed
- [ ] Sandbox `.qwc` successfully completes a full poll cycle against the deployed `/qbwc` endpoint
- [ ] Production `.qwc` generation explicitly deferred until Stage 2 (Section 11) — not part of this spec's completion

**Post-Build Checklist:**
- [ ] Ben sign-off on all 9 E2E results
- [ ] Technical spikes (Section 14: EditSequence retry behavior, real poll cadence) resolved and folded back into a v1.1.0 update of this spec if observed behavior differed from assumptions
- [ ] Explicit written confirmation that Stage 2 (any production file) has NOT been started, pending separate go-ahead

**AI Agent Execution Contract:**
- [ ] Read this spec's Architecture Governor Summary and all 18 sections, AND Spec A in full, before writing any code
- [ ] Treat Section 9's proof-boundary re-check as non-negotiable — never remove or weaken it, even if it seems redundant with upstream checks
- [ ] Never generate or register a `.qwc` file targeting a production company file as part of this spec's work
- [ ] Stop and escalate to Ben if any of the 9 E2E steps reveals a double-post, a proof-boundary bypass, or any write to a file other than the sandbox
