# Spec: QuickBooks Sandbox Company File & Test Environment

## SPEC METADATA
```
Spec Title: QB Sandbox Company File & Test Environment
Version: 1.0.0
Author: AI Accounting Hub integration team
Last Updated: 2026-07-01
Status: Ready for Build
Timeline: 1–2 weeks (mostly manual QB Desktop work + one Rightworks ticket)
Confidence Level: ~85% — assumes New Company from Existing Company File carries the assumed lists; must be verified against the actual source file at build time (Section 14)
Next Steps: Ready to build — begin with Task 1 (Rightworks File Manager upload confirmation)
```

## ARCHITECTURE GOVERNOR SUMMARY
```
Feature: QB Sandbox Company File & Test Environment
Completed: 2026-07-01

Existing systems touched: 3 — Rightworks-hosted QuickBooks Desktop Enterprise (10 production company files), Rightworks File Manager, QBWC (QuickBooks Web Connector)
NOT touched: canonical Postgres (Supabase, fdnwlcomuddzmluvbylg), Temporal, ai-accounting-hub-ralph app code (this spec is QB-side setup only)
Source of truth conflicts: 0 — QuickBooks Desktop remains the eventually-consistent batch sink (per CLAUDE.md); Postgres remains system of record; the sandbox file is a NEW, independent artifact with no claim to be a source of truth for anything
Stateful objects mapped: 1 — the sandbox company file itself (does not yet exist → exists-empty → structured → validated → ready-for-integration-testing)
Money/auth/proof boundary crossings: 0 — sandbox file contains no real transactions, no real vendor payments, no proof-gate interaction (Spec B owns that boundary)
Reuse opportunities found (DO NOT rebuild): File > New Company from Existing Company File (native QB feature — do not hand-build a chart of accounts from scratch); Rightworks File Manager upload (native, free — do not request a new hosting mechanism)
Must-not-break guarantees: 3 — production company files unmodified; existing QBWC .qwc registrations for production untouched; no accidental restore-over of a production filename
Definition-of-done conditions: 6 (see Section 3)
Technical spikes required before spec is final: 1 — confirm at build time which source company file's list structure is closest to SPEC_SUMMA_TERRA_BINDING.md before running New Company from Existing Company File (Section 14)

Status: ✅ CLEAR TO SPEC
```

---

## 1. Executive Summary

Build a standalone, structurally-isolated QuickBooks Desktop Enterprise sandbox company file, hosted in the existing Rightworks environment alongside the 10 real Summa Terra Ventures (STV) production files, so the QBWC write-back integration (Spec B) can be built and proven end-to-end against real QuickBooks mechanics before any automation ever touches production data. This closes the last open item from the QBWC integration architecture (CLAUDE.md "Open spikes," now resolved) by giving the write-back adapter a safe target. Primary user: the integration engineer building/testing Spec B, and Ben (STV owner) for structural sign-off. This is foundational, one-time setup work — not a recurring process — estimated at 1–2 weeks, gated only by a short Rightworks confirmation and manual QuickBooks list-building.

## 2. Scope Definition & Non-Scope

**In scope:**
- Creating one new, empty-of-transactions QuickBooks company file inside the existing Rightworks hosted environment, via `File > New Company from Existing Company File...`.
- Structuring that file's Chart of Accounts, Classes, Items (cost codes 001–069), Customer:Jobs, and custom fields to match `SPEC_SUMMA_TERRA_BINDING.md` v2.0.0, using CSV import where supported and IIF import where CSV cannot reach (Classes, custom fields).
- Seeding minimal opening balances via a single synthetic journal entry (not a historical reconstruction).
- Registering a sandbox-only `.QWC` Web Connector application with its own unique `FileID`/`OwnerID` GUIDs, targeting only the sandbox file.
- Structural sign-off checklist and validation before the sandbox file is handed to Spec B for integration testing.

**Out of scope:**
- Any code changes to `ai-accounting-hub-ralph/` (that is Spec B).
- The QBWC write-back adapter itself, BillAdd logic, poll-interval configuration (Spec B).
- Migrating or touching any of the 10 real production company files (explicitly future work — see Spec B §14 cutover strategy).
- Payroll, tax, bank feeds, or any live third-party integration inside the sandbox file (CLAUDE.md guardrail: no live non-QBO adapters in this phase).
- Building a fully complete replica of every STV entity — the sandbox only needs enough structure to prove the integration pipe works, not every real cost code/vendor in production.

**Phase dependencies:**
- Depends on: `SPEC_SUMMA_TERRA_BINDING.md` v2.0.0 (canonical cost-code/Class/Customer:Job/5-2-1 design authority — never redesign, only consume).
- Depended on by: `spec-qbwc-writeback-adapter-2026-07-01.md` (Spec B) — the sandbox file produced here is Spec B's primary and required test target.

## 3. Business Context & Acceptance Criteria

**Business goal:** De-risk the QBWC write-back go-live by proving the full write path against a real QuickBooks file with zero exposure to the 10 production company files containing 10+ years of live financial data for a real-estate development firm.

**Success metric:** Zero production-file incidents during Spec B's development and testing; sandbox file structurally matches the binding spec closely enough that Spec B's tests are representative of production behavior.

**Target:** 100% of Spec B's QBWC write-back testing (BillAdd, TxnID/EditSequence handling) occurs against the sandbox file before any write-back code path is enabled against a production file.

**Acceptance criteria:**
- [ ] Sandbox `.QBW` file exists in the Rightworks hosted environment, uploaded/confirmed via File Manager, at $0 additional hosting cost (per Rightworks written confirmation, 2026-07-01).
- [ ] Chart of Accounts, Class list (phase/dimension per binding spec), cost-code Items (001–069, each mapped to one of the four CIP buckets per `SPEC_SUMMA_TERRA_BINDING.md` §6.4/`Cost_Codes_and_Items.md`), and at least one Customer:Job exist in the sandbox file.
- [ ] A dedicated `.qwc` file with a unique `FileID` GUID is registered in Web Connector, provably bound only to the sandbox file (Section 9 test).
- [ ] Zero write access from the sandbox `.qwc` app to any production company file (Section 9 test — this is the single most important proof in this spec).
- [ ] Ben (or delegated STV reviewer) has signed off that the sandbox structure is close enough to real use to be a valid test target.
- [ ] All 10 production company files are unmodified (verified via a before/after account-count and last-modified check).

**Spec Status:** Build-phase spec — this is manual QuickBooks configuration work plus one registration script; low ambiguity, low likelihood of requiring a rewrite once started.

## 4. Architecture & System Integration

**Data flow (setup, not runtime):**
```
Existing STV production file (source of COA/Class/Item shape)
  → File > New Company from Existing Company File (QuickBooks native)
  → New sandbox .QBW file (zero transactions)
  → CSV import (COA, Customers:Jobs, Items) + IIF import (Classes, custom fields)
  → Seed journal entry (minimal opening balances)
  → Rightworks File Manager upload/confirmation (hosted environment)
  → Sandbox .qwc registration in Web Connector (own FileID GUID)
  → [Handoff to Spec B for integration testing]
```

**Integration points:**
- Rightworks File Manager (manual upload/confirm — no API; UI-driven per Rightworks support).
- QuickBooks Web Connector (`.qwc` registration only in this spec; the SOAP endpoint it polls is Spec B's).
- `SPEC_SUMMA_TERRA_BINDING.md` as the structural source of truth for what the sandbox must contain.

**New infrastructure required:** None in the AI Accounting Hub codebase. This spec produces artifacts entirely inside the Rightworks-hosted QuickBooks Desktop environment plus one `.qwc` config file (which Spec B's adapter will also reference).

**External dependencies:** Rightworks hosting (File Manager, Web Connector runtime), QuickBooks Desktop Enterprise's native import tooling (Excel/CSV wizard, IIF import via `File > Utilities > Import`).

**Ownership map:** Ben/STV owner — structural sign-off and access to the hosted desktop. Integration engineer — builds the CSV/IIF import files and registers the sandbox `.qwc`.

## 5. User Flows & Happy Path

**Happy Path: Building the sandbox file**

Actor: Integration engineer, with STV owner sign-off gate at the end.
Precondition: Access to the Rightworks hosted desktop; `SPEC_SUMMA_TERRA_BINDING.md` v2.0.0 available for reference.

Steps:
1. Engineer opens the Rightworks hosted QuickBooks Desktop Enterprise session.
2. Engineer selects the existing STV company file whose list structure is closest to the binding spec's target (technical spike — see Section 14).
3. `File > New Company from Existing Company File...` → names the new file clearly, e.g. `Summa Terra SANDBOX - DO NOT USE FOR REAL WORK.QBW`.
4. QuickBooks creates the new file with cloned Chart of Accounts / preferences / lists, zero transactions.
5. Engineer builds the CSV import file for Items (cost codes 001–069, mapped to CIP buckets) and Customer:Jobs, and runs `File > Utilities > Import > Excel Files`.
6. Engineer builds the IIF file for the Class list (phase/dimension) and any custom fields not covered by CSV, and runs `File > Utilities > Import > IIF Files`.
7. Engineer enters one seed journal entry establishing minimal, synthetic opening balances (not historical data).
8. Engineer confirms the file is visible/hosted correctly via Rightworks File Manager (per Rightworks: free, no ticket required for this step).
9. Engineer generates a sandbox-only `.qwc` file with a unique `FileID`/`OwnerID` and registers it in Web Connector, pointed only at the sandbox `.QBW`.
10. Engineer runs the isolation proof test (Section 9) — confirms the sandbox `.qwc` app cannot read/write any production file.
11. Ben reviews the sandbox structure against the binding spec and signs off.

Postcondition: Sandbox file exists, structurally validated, isolated, and ready to be Spec B's test target.

**Alternate path — structure mismatch found during Ben's review (step 11):** Engineer amends the CSV/IIF import files and re-imports the specific list (Classes, Items, etc.) rather than rebuilding the whole file; QuickBooks list imports are additive/updatable, not destructive to the whole file.

## 6. Data Models & Schema

This spec has no Postgres/application schema — its "schema" is the QuickBooks list structure itself.

**QuickBooks list structure (target, per `SPEC_SUMMA_TERRA_BINDING.md`):**

| List | Source path in | Import method | Cardinality (sandbox minimum) |
|---|---|---|---|
| Chart of Accounts | Cloned via New Company from Existing | Native clone (no import needed) | As cloned from source file |
| Items (cost codes) | `Cost_Codes_and_Items.md` | CSV via `File > Utilities > Import > Excel Files` | 001–069, each mapped to 1 of 4 CIP buckets, 0 orphans |
| Customer:Jobs | Binding spec §6 | CSV via Import wizard | ≥1 test project |
| Class list (phase/dimension) | Binding spec §6, §5.2 | IIF import (CSV wizard does not cover Classes) | ≥1 phase per test project |
| Custom fields | Binding spec (Draw # dimension, etc.) | IIF import or manual list-record entry | Draw # field present and usable |
| Opening balances | N/A — synthetic seed only | Manual journal entry | One JE, non-zero but arbitrary/small |

**`.qwc` registration artifact (XML, generated at build time):**
```xml
<QBWCXML>
  <AppName>STV Sandbox Integration</AppName>
  <AppID></AppID>
  <AppURL>[Spec B's SOAP endpoint URL — placeholder until Spec B deploys]</AppURL>
  <AppDescription>Sandbox-only QBWC app — targets Summa Terra SANDBOX file exclusively</AppDescription>
  <AppSupport>[internal support contact]</AppSupport>
  <UserName>[sandbox-specific service username]</UserName>
  <OwnerID>{NEW-UNIQUE-GUID}</OwnerID>
  <FileID>{NEW-UNIQUE-GUID}</FileID>
  <QBType>QBFS</QBType>
  <Scheduler><RunEveryNMinutes>15</RunEveryNMinutes></Scheduler>
</QBWCXML>
```
Both GUIDs must be freshly generated and MUST NOT match any of the 10 production `.qwc` files' `FileID`/`OwnerID` values.

## 7. Error Handling & Edge Cases

| Scenario | Handling |
|---|---|
| `New Company from Existing Company File` also clones users/passwords from the source file | Review cloned user list immediately after creation; remove/reset any inherited credentials before the sandbox is used by anyone other than the engineer |
| IIF import partially fails (bad row) | IIF imports are transactional per list-type in QuickBooks; a bad row typically halts that list's import — re-run after fixing the offending row; **back up the sandbox file before each IIF import** (low risk since no real transactions exist yet, but keep the habit) |
| Engineer accidentally restores/imports over the WRONG (production) filename | Hard stop — **always verify the destination filename explicitly before any restore/import step**; sandbox filenames must contain a clear marker (`SANDBOX`) to make this mistake visually obvious |
| Sandbox `.qwc` FileID collides with a production FileID (typo/copy-paste error) | QBWC would then be able to address a production file through the sandbox app — treat as a CRITICAL error; Section 9's isolation test must catch this before Spec B ever runs against it |
| Rightworks File Manager upload fails or file doesn't appear | Escalate to Rightworks support (hosting/file-transfer bucket, not a QuickBooks data issue) |
| Source company file's list structure is far from the binding spec (cost codes don't exist yet, no Class-per-phase convention) | Acceptable — the sandbox doesn't need to start close; CSV/IIF import corrects it. Do not block on finding a "perfect" source file (see Section 14 spike) |

## 8. Performance & Scalability Requirements

Not applicable in the traditional sense — this is a one-time manual setup task, not a running service. The only "performance" concern is Rightworks session mechanics already documented in CLAUDE.md (business-hours/session-tied usage). No throughput, latency, or scaling targets apply to this spec.

## 9. Security & Compliance Requirements

**Authentication & authorization:** Sandbox file access uses the same Rightworks-hosted-desktop access control as production (no new auth mechanism introduced). The sandbox `.qwc` app should use a distinct QBWC username from any production `.qwc` app, so its activity is separately auditable in Web Connector logs.

**Data protection:** No real vendor bank details, no real payment data, no real PII beyond what's needed for a synthetic test Customer:Job. Do not copy real vendor/customer records with real contact/banking details into the sandbox — use clearly-fake test data.

**Isolation proof (the core security requirement of this spec):**
1. Register the sandbox `.qwc` and run one no-op qbXML `HostQuery`/`CompanyQuery` through it. **Confirm the response identifies the sandbox company, never a production company.**
2. Attempt to run the sandbox `.qwc` app while a production file is the active/open file in QuickBooks. **Confirm Web Connector refuses or errors** (QBWC binds one app to one FileID; this is a structural guarantee, not a policy — verify it empirically here rather than trusting the theory).
3. Document both results with screenshots/logs as the sign-off evidence for Section 3's acceptance criteria.

**Compliance:** No GDPR/PII/payment-compliance surface introduced — this file processes no real transactions.

## 10. Testing Strategy

**Manual verification tests (no automated test suite — this is QuickBooks configuration, not application code):**
- [ ] Isolation proof (Section 9, steps 1–2) — the single mandatory test.
- [ ] Cost-code Item count = 69, each mapped to exactly one of the four CIP buckets, 0 orphans (mirrors the binding spec's own DoD language in `SPEC_SUMMA_TERRA_BINDING.md` line 137).
- [ ] Class list contains at least one phase per test Customer:Job.
- [ ] Seed journal entry balances to $0 (debits = credits) and does not trip any QuickBooks integrity warning.
- [ ] `Verify Data` (QuickBooks native integrity check, `File > Utilities > Verify Data`) run once on the finished sandbox file — confirms no corruption from the import process.
- [ ] Production file account counts and "last modified" timestamps captured before and after this entire spec's work, confirmed unchanged.

## 11. Deployment & Rollout Strategy

**"Deployment" here means the file existing and being handed off.**

1. Complete Section 5's happy path steps 1–9.
2. Run Section 9 isolation proof; do not proceed if it fails.
3. Ben structural sign-off (Section 3 acceptance criteria).
4. Hand off the sandbox `.QBW` filename/location and the sandbox `.qwc` file to Spec B's implementation.

**Rollback plan:** If the sandbox file becomes corrupted or misconfigured beyond easy repair, delete it and redo Section 5 — it contains no real data, so there is no data-loss risk in starting over. This is explicitly why the file is built fresh rather than migrated from history.

**Communication:** Notify Ben when the sandbox is ready for review (step 11), and again when Spec B begins consuming it, so he knows any future QuickBooks activity in that file is test traffic, not real bookkeeping.

## 12. API Documentation

Not applicable — this spec produces no application API. The only "interface" is the `.qwc` XML file (Section 6) that Web Connector consumes, and that file's `AppURL` is owned by Spec B, not this spec.

## 13. Database Migrations

Not applicable — no Postgres schema changes in this spec. (Spec B may reference `companies`/sandbox-identifying rows in canonical Postgres; that migration, if any, belongs to Spec B.)

## 14. Known Limitations & Future Work

**Limitations:**
1. **Source file selection is a judgment call, not a formula.** Which of the 10 production files most closely resembles the target structure is not determined by this spec — flag as a technical spike: before Task 1 execution, the engineer must pick a source file and briefly justify the choice (e.g., "closest existing Class usage" or "smallest/simplest file to clone quickly"). Any file works as a starting point since CSV/IIF import corrects the structure afterward.
2. **The sandbox does not represent production data volume.** Testing here proves correctness, not performance/scale of a file with 10+ years of transactions — that risk is explicitly deferred to a controlled production pilot in Spec B §14.
3. **No automated way to verify the sandbox stays isolated over time.** If someone manually reassigns the sandbox `.qwc`'s FileID later, isolation could silently break — recommend a periodic manual spot-check, not just a one-time proof.

**Deferred / future work:**
- Building a second sandbox file per entity type (if one sandbox proves insufficient for testing intercompany Due-To/Due-From pairing across two files) — only pursue if Spec B's testing reveals single-file coverage is insufficient.
- Automating sandbox rebuild via script — not worth building for a one-time setup task.

**Spec evolution:** This spec is effectively "done" once the sandbox exists and passes sign-off; it does not need ongoing updates unless the binding spec's structure changes materially.

## 15. Glossary & Terms

- **Sandbox company file:** A new, empty-of-transactions `.QBW` file built to test the QBWC integration, structurally isolated from production.
- **CIP bucket:** Construction-in-progress capitalization bucket that each cost-code Item maps to (per `SPEC_SUMMA_TERRA_BINDING.md`).
- **Class (in this context):** The QuickBooks dimension representing phase, per the binding spec's Class/phase convention — not "Class = property" (corrected terminology; see binding spec §6).
- **Customer:Job:** QuickBooks' project dimension — one Customer:Job per STV project.
- **`.qwc` / `FileID` / `OwnerID`:** Web Connector's registration artifact and the GUIDs that bind a QBWC app to exactly one company file.
- **File Manager:** Rightworks' hosted file-upload tool, confirmed free for adding company files to the existing hosted environment.

## 16. Monitoring, Metrics & Observability

Not applicable as a running system — this is one-time setup. The only "observability" artifact is the isolation-proof evidence (Section 9), which should be saved (screenshots/log excerpts) as a durable record, since it's the safety proof the rest of the integration work relies on.

## 17. Alternative Designs Considered

**Alternative 1: Full duplicate via Create Copy / Back Up Company, restored under a new name**
Pros: includes real transaction history/volume for more realistic testing.
Cons: carries 10+ years of real, sensitive financial data into a test file; conflicts with the "build fresh, don't migrate history" decision already made for the production cutover strategy (Spec B §14); unnecessary risk for what this spec needs.
Why rejected as the primary path: the goal is to test the *pipe*, not reconstruct history. Kept as a documented fallback only if Spec B later needs to test against realistic data volume — see Spec B §14.

**Alternative 2: Build the sandbox file completely from a blank QuickBooks company file (no cloning) plus full CSV/IIF import of everything, including Chart of Accounts**
Pros: cleanest possible starting point, zero inherited cruft.
Cons: significantly more manual import work (COA import via CSV is supported but still requires careful account-type mapping); no meaningful benefit over cloning-then-correcting since New Company from Existing already gives a valid COA/preferences baseline for free.
Why rejected: more work for no real safety or correctness benefit.

**Chosen design rationale:** `New Company from Existing Company File` + targeted CSV/IIF correction is the fastest path to a *valid, empty* QuickBooks file that still needs the least manual rebuilding, matching the earlier QB Rightworks research findings on CSV/IIF import boundaries.

## 18. Final Build Checklist

**Setup Checklist:**
- [ ] Source company file selected and justified (Section 14 spike)
- [ ] `New Company from Existing Company File` executed; sandbox file named with clear `SANDBOX` marker
- [ ] Cloned user list reviewed; no inherited real credentials left active
- [ ] Items CSV import complete: 001–069 cost codes, CIP-bucket-mapped, 0 orphans
- [ ] Customer:Jobs CSV import complete: ≥1 test project
- [ ] Class list IIF import complete: ≥1 phase per test project
- [ ] Custom fields present (Draw # dimension usable)
- [ ] Seed journal entry entered, balances to $0
- [ ] `Verify Data` run clean on sandbox file
- [ ] Rightworks File Manager upload/confirmation complete (no ticket needed per 2026-07-01 confirmation)
- [ ] Sandbox `.qwc` generated with fresh, unique `FileID`/`OwnerID` (confirmed distinct from all 10 production files)
- [ ] Isolation proof test executed and evidence saved (Section 9)
- [ ] Production file account counts / last-modified timestamps confirmed unchanged (before/after check)
- [ ] Ben structural sign-off obtained
- [ ] Sandbox filename, location, and `.qwc` file handed off to Spec B implementation

**AI Agent Execution Contract:**
- [ ] Read this spec's Architecture Governor Summary and all 18 sections before beginning any work
- [ ] Treat Section 9's isolation proof as the single non-negotiable gate — do not proceed to Spec B handoff without it passing with saved evidence
- [ ] Never restore/import into a filename that is not clearly marked `SANDBOX`
- [ ] Stop and escalate to Ben if the source-file selection spike (Section 14) cannot be resolved confidently
