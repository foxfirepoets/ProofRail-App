# SPEC - QuickBooks Enterprise QBB to QBO Advanced Migration Pipeline

Spec Title: Summa Terra QuickBooks Desktop Enterprise `.QBB` to QBO Advanced Sandbox Migration
Version: 1.1.0
Author: Codex using qb-master, qbo-expert, and spec-superstar (v1.1.0 grounding pass: Claude, spec-superstar + architecture-cartographer)
Last Updated: 2026-07-08
Status: Ready for Build - Phase 1 Pilot
Timeline: 2-3 weeks for one-file pilot; 4-8 weeks for full 20+ file rollout after pilot sign-off
Confidence Level: ~90% (up from ~85% in v1.0.0) - every reuse claim in §4 is now independently verified against real repo files with matching evidence (see §0.1); remaining uncertainty is entirely the 5 technical spikes in §14, all of which require checking the live Rightworks/work-machine environment, not this repo
Next Steps: Build discovery report and control workbooks before any QBO write; resolve the 5 §14 technical spikes (environment checks, not code) before Phase 1 restore/extract begins

## Architecture Governor Summary

Feature: QBB-to-QBO migration pipeline
Completed: 2026-07-08 (v1.0.0); grounded 2026-07-08 (v1.1.0)

Existing systems touched: 9 - local QBB folder, Rightworks/QuickBooks Desktop Enterprise, restored QBW files, QODBC/Desktop SDK/exported reports, local migration workspace, mapping workbooks, existing `obgen`, existing QBO sandbox API scripts, two QBO Advanced sandbox realms
Source of truth conflicts: 0 blocking - source-of-truth is explicit per phase: QBB/QBW for historical source data, mapping workbook for target mapping, QBO sandbox only after approved import
Stateful objects mapped: 6 - source file, restore job, extraction job, mapping decision, import batch, reconciliation run
Money/auth/proof boundary crossings: 3 - QBO sandbox writes, QBO OAuth/realm selection, CPA/accounting treatment decisions
Reuse opportunities found: existing `obgen/vps_extract`, `obgen/run.py`, `scripts/qbo_common.py`, QBO seed scripts, existing QBO sandbox audit log rules - **all independently verified 2026-07-08, see §0.1**
Must-not-break guarantees: 9
Definition-of-done conditions: 14
Technical spikes required before spec is final: 5 (unchanged by this grounding pass - all 5 require live-environment verification, not repo verification)

Status: CLEAR TO SPEC

## 0.1 Reuse Verification (architecture-cartographer, 2026-07-08)

Every "existing systems to reuse" claim in §4 was independently checked against the actual repo files (not assumed from this spec's own text). Result: **zero mismatches, zero missing files.**

| Claim | Verified | Evidence |
|---|---|---|
| `obgen/vps_extract/Extract-QBEnterprise.ps1` | Exists, matches claim | File present at exact path |
| `obgen/run.py` for opening-balance/tie-out gates | Exists, with a scope caveat | Confirms QODBC->IIF extraction with gates G1-G7, but its output target is legacy IIF format for the old 10-to-2 desktop consolidation, not the QBO API directly. Reuse this for the **gate pattern** (G1-G4 style validation), not as a direct QBO-API loader - `qbo_api_loader` (§4 step 9) is new code, not a port of `run.py`. |
| `scripts/qbo_common.py` for sandbox guard/audit/throttling | Exists, matches claim exactly | Real sandbox-only guard (hard-fails off `sandbox-quickbooks.api.intuit.com`), audit logging, no-delete contract, deterministic RequestId, retry/backoff - every property this spec's §4 integration constraints assume is actually present |
| Existing QBO setup scripts (Accounts/Departments/Classes/Customers/Vendors/Items) | Exists, matches claim | `scripts/qbo_seed_accounts.py`, `qbo_seed_locations_departments.py`, `qbo_seed_classes.py`, `qbo_seed_customers_projects.py`, `qbo_seed_vendors.py`, `qbo_seed_items.py` all present and functional |

**One new finding, already resolved:** `qbo_setup_pack/qbo_setup_pack/` was a byte-identical duplicate of `qbo Source Files/` with zero script references anywhere - archived to `archive/qbo_setup_pack/` on 2026-07-08 (see `archive/README.md`). **If this migration pipeline needs seed CSVs, read from `qbo Source Files/` — the duplicate no longer exists at its old path.**

## 1. Executive Summary

Build a safe, repeatable migration pipeline that takes QuickBooks Desktop Enterprise backup files (`.QBB`), restores or supervises restoration to `.QBW`, extracts structured accounting data, maps that data into two QBO Advanced sandbox companies, generates dry-run import payloads/files, and proves the migration with reconciliation reports before any sandbox write. Phase 1 proves the full path using one selected `.QBB` file. Phase 2 applies the same pipeline to the 20+ entity backup set from `L:\My Drive\2 Areas\QuickBooks & VPS Operations\Enterprise QBB files`.

Business outcome: move Summa Terra from legacy Desktop/Rightworks files toward two QBO Advanced sandboxes without losing source traceability, entity reporting, AP/AR integrity, or CPA support. Success means each imported balance or transaction can be traced back to the original QuickBooks file, transaction, report, and migration batch.

Primary users: Ben/operator, CPA/controller reviewer, and the implementation agent running the migration. This is Desktop-to-QBO migration work, not normal ongoing ProofRail invoice automation.

## 2. Scope Definition and Non-Scope

In scope:
- Inventory one pilot `.QBB`, then all selected `.QBB` files.
- Detect duplicate/newer backups and recommend the selected source per entity.
- Create `SummaTerra-QB-Migration/` folder structure.
- Create `migration_control.xlsx` and `mapping_workbook.xlsx`.
- Restore or guide supervised restore from `.QBB` to `.QBW`.
- Extract lists, reports, and transaction detail from restored Desktop files.
- Normalize into staging tables with source traceability.
- Map source entity/project/accounts/vendors/customers/items to the two QBO Advanced sandbox companies.
- Generate QBO-ready CSV/import files and/or dry-run QBO API payloads.
- Load only to QBO Advanced sandboxes after explicit approval.
- Reconcile Enterprise source reports to staging and then to QBO.
- Generate CPA support package per entity/project.

Non-scope:
- No production QBO writes.
- No bank transfers, BillPayments, payments, ACH, checks, or money movement.
- No live cutover until sandbox reconciliation is accepted.
- No one-click direct `.QBB` to two-QBO conversion. QBB must be restored or supervised first.
- No silent accounting treatment choices. Capitalization, depreciation, sale gain/loss, partner allocations, developer-fee recognition, and opening-balance policy require CPA/controller sign-off.
- No deletion of QBO sandbox data by code. A poisoned sandbox is reset manually through Intuit Developer Portal.

Phase boundary:
- Phase 1 is a one-file pilot.
- Phase 2 extends to the full backup inventory.
- Phase 3 adds approved sandbox loading and reconciliation at volume.

## 3. Business Context and Acceptance Criteria

Why now:
- The existing Rightworks/Desktop files are the books of record during bridge operations.
- The future-state system uses two QBO Advanced sandboxes: Parent/management and Partnership/project.
- A direct 20+ file to 2 file conversion is structurally unsafe without mapping and reconciliation.

Success metrics:
- 100% of selected `.QBB` files inventoried.
- 100% of selected files either restored or marked blocked with reason.
- 100% of imported rows carry source file, source entity, source transaction/report reference, source date, and migration batch ID.
- 0 QBO sandbox writes before dry-run preview and approval.
- Trial Balance, Balance Sheet, P&L by month, open AP/AR, bank balances, loans, owner capital, developer fees, and intercompany balances tie or have documented variances.
- No unmapped account/vendor/customer/item/class/location reaches import output without exception status.

Acceptance criteria for Phase 1 pilot:
- One selected `.QBB` is inventoried, restored or blocked, and extracted.
- Discovery report identifies source entity, dates, company metadata, available reports, and extraction method.
- Control workbook and mapping workbook are created.
- Staging data validates with row counts and control totals.
- Dry-run QBO import package is generated.
- No live QBO or production realm is touched.

Acceptance criteria for full rollout:
- All selected `.QBB` files from the source folder are processed through the same gates.
- Duplicate backups are resolved by newest-by-default unless control workbook overrides.
- Final migration report is produced with one section per source entity.

## 4. Architecture and System Integration

System flow:

1. `01_source_qbb`: selected `.QBB` backups are copied or referenced from the source folder.
2. `inventory_qbb_files`: scans source files, parses entity/timestamp, and produces `00_control/source_file_inventory.csv`.
3. `restore_or_restore_assistant`: restores `.QBB` to `.QBW` where automation is available, otherwise generates a supervised checklist for QuickBooks Desktop Enterprise/Accountant.
4. `desktop_extractor`: reads restored `.QBW` using the safest available structured method: QODBC first if available, Desktop SDK second, Transaction Pro/exported CSV third.
5. `report_exporter`: exports required reports from every file in consistent naming format.
6. `normalizer`: converts raw exports to common staging schemas.
7. `mapper`: applies `mapping_workbook.xlsx` and writes normalized target-ready rows.
8. `qbo_import_generator`: emits CSVs and/or JSON payload previews.
9. `qbo_api_loader`: dry-run by default; sandbox writes only after explicit approval and existing sandbox guard.
10. `reconciler`: compares source reports vs staging vs QBO sandbox reports.
11. `cpa_support_package`: packages source reports, support schedules, exceptions, and reconciliation summaries.

Existing systems to reuse:
- `obgen/vps_extract/Extract-QBEnterprise.ps1` for read-only Desktop/QODBC extraction patterns.
- `obgen/run.py` for opening-balance generation and tie-out gates where applicable.
- `scripts/qbo_common.py` for sandbox guard, company sanity checks, token refresh, audit logs, throttling, and no-production enforcement.
- Existing QBO setup scripts for Accounts, Departments/Locations, Classes, Customers/Projects, Vendors, and Items.

Integration constraints:
- QuickBooks Desktop restore happens inside a Desktop-capable environment, likely Rightworks or a local Enterprise/Accountant install.
- In Rightworks, exported files land inside hosted storage and must be downloaded or synced to the local workspace.
- QBO Advanced API writes require realm-specific OAuth tokens and explicit sandbox realm selection.
- Intuit API details must be checked against current Intuit Developer docs before implementation; minorversion should be pinned deliberately and current docs indicate minorversion 75 is the active baseline as of the referenced Intuit minor-version page.

## 5. User Flows and Happy Path

Pilot happy path:
1. Operator selects one `.QBB` from the source folder.
2. `inventory_qbb_files` records file path, size, modified time, parsed entity, candidate backup timestamp, and duplicate group.
3. Operator confirms selected source in `migration_control.xlsx`.
4. Restore assistant produces either an automated restore command or a human restore checklist.
5. Restored `.QBW` lands in `02_restored_qbw/{entity}/`.
6. Extractor reads company metadata, lists, required reports, and transaction detail.
7. Normalizer writes staging tables to `04_staging/{entity}/`.
8. Mapper applies target QBO company/class/location/customer/project/account mappings.
9. Import generator writes dry-run outputs to `06_qbo_import_files/{batch_id}/`.
10. Reconciler proves source totals equal staging totals.
11. Operator reviews preview, exceptions, and reconciliation package.
12. Only after approval, sandbox loader writes to the selected QBO sandbox realm.
13. Reconciler pulls QBO reports and compares source vs QBO.

Full rollout happy path:
- Same as pilot, repeated per selected source entity, with duplicate-source selection governed by `mapping_workbook.xlsx`.

Human-in-loop restore path:
- If restore cannot be automated, the system writes a checklist containing exact source `.QBB`, expected output `.QBW`, destination folder, QuickBooks menu path, and confirmation fields for the operator to complete.

## 6. Data Models and Schema

Core staging tables may be CSV, SQLite, DuckDB, or Postgres. Phase 1 should use local files plus a manifest; Phase 2 may promote to SQLite/DuckDB for joins and repeatability.

`source_files`
```text
source_file_id
source_path
file_name
file_size_bytes
file_modified_at
parsed_entity_name
parsed_backup_date
duplicate_group_key
recommended_for_entity boolean
selection_status enum: RECOMMENDED | SELECTED | SUPERSEDED | BLOCKED
selection_reason
sha256
```

`restore_jobs`
```text
restore_job_id
source_file_id
entity_name
restore_method enum: AUTOMATED | SUPERVISED | BLOCKED
qbw_path
started_at
completed_at
status enum: PENDING | RESTORED | BLOCKED | FAILED
blocker_reason
operator_notes
```

`company_profile`
```text
entity_name
company_name
legal_entity_name
ein_masked
fiscal_year_start
report_basis
closing_date
last_transaction_date
last_reconciled_statement_date
source_qbw_path
extracted_at
```

`normalized_transactions`
```text
migration_batch_id
source_file_id
source_entity
source_txn_id
source_txn_type
source_doc_number
source_date
source_account
source_name
source_customer_job
source_class
source_item
memo
debit
credit
amount
target_qbo_company enum: PARENT | PARTNERSHIP
target_account
target_vendor_customer
target_customer_project
target_class
target_location
target_item
mapping_status enum: MAPPED | UNMAPPED | EXCLUDED | NEEDS_REVIEW
exception_code
```

`import_batches`
```text
migration_batch_id
entity_name
target_qbo_company
mode enum: DRY_RUN | SANDBOX_EXECUTE
created_at
approved_by
approved_at
source_control_total
staging_control_total
qbo_control_total
status enum: PREVIEW_READY | APPROVED | LOADED | RECONCILED | FAILED
```

`exceptions`
```text
exception_id
migration_batch_id
severity enum: BLOCKER | WARNING | INFO
category enum: SOURCE_FILE | RESTORE | EXTRACTION | MAPPING | IMPORT | RECONCILIATION | CPA_DECISION
entity_name
source_reference
description
recommended_action
owner
status enum: OPEN | RESOLVED | DEFERRED
```

Required mapping workbook tabs:
1. Source Files
2. Source Entity to Target QBO Company
3. Source Entity to QBO Class
4. Source Entity to QBO Location
5. Source Entity to QBO Customer/Project
6. Account Mapping
7. Vendor Deduping
8. Customer/Project Deduping
9. Item/Product-Service Mapping
10. Intercompany Mapping
11. Developer Fee Mapping
12. Opening Balance Rules
13. Historical Summary Rules
14. Import Batch Log
15. Exceptions

## 7. Error Handling and Edge Cases

Error codes:
- `MIG-001`: No `.QBB` files found in configured folder.
- `MIG-002`: Duplicate source backups require selection.
- `MIG-003`: QBB cannot be restored automatically; supervised restore required.
- `MIG-004`: Restored QBW company name does not match expected source entity.
- `MIG-005`: Extraction method unavailable or failed.
- `MIG-006`: Required report missing or export failed.
- `MIG-007`: Staging rows fail validation.
- `MIG-008`: Account/vendor/customer/item mapping missing.
- `MIG-009`: Transaction would post to wrong QBO company.
- `MIG-010`: Dry-run approval missing; write refused.
- `MIG-011`: QBO sandbox guard failed.
- `MIG-012`: QBO duplicate/collision detected.
- `MIG-013`: Reconciliation variance exceeds tolerance.
- `MIG-014`: CPA decision required before mapping/import.

Edge cases:
- Multiple `.QBB` files for one entity: default to newest by backup timestamp or file modified date, but mark older files as superseded and preserve them.
- Entity name cannot be parsed from filename: inventory still records file; mapping status becomes `NEEDS_REVIEW`.
- `.QBB` restore requires admin password or single-user mode: mark supervised, never request credentials in this system.
- Desktop file has a closing date or password: extract metadata only if available; flag limitation.
- QODBC unavailable in local environment: use Rightworks-hosted extraction or exported reports.
- Source file has Desktop classes/jobs/items that do not align with QBO dimensions: flag, do not coerce silently.
- Historical closed years have transaction detail but strategy says summary JEs: preserve detail in support package, import monthly trial-balance summary only.
- Current/open years have open AP/AR: use native Bills/Invoices where possible, not journal entries, so subledgers tie.
- Sold properties require sale support: mark as CPA-sensitive and generate dedicated sale package.
- Intercompany balances across source files do not net to zero: blocker until explained or accepted by CPA/controller.

## 8. Performance and Scalability

Targets:
- Inventory 100 files under 2 minutes on local disk.
- Generate discovery report for 20+ files under 10 minutes, excluding restore time.
- Extraction runtime target: under 30 minutes per restored QBW for standard reports and lists; transaction detail may exceed this and should stream to files.
- Normalization and mapping: under 5 minutes per entity for exported CSV-sized datasets.
- QBO API writes: throttle conservatively per realm and honor retry-after headers; use dry-run payload generation before any write.

Scalability decisions:
- File-based staging is acceptable for pilot.
- Promote to SQLite/DuckDB if transaction detail exceeds practical CSV join limits.
- Import batches are per entity and per target realm to keep rollback/reconciliation scoped.

## 9. Security and Compliance

Data classification:
- QBB/QBW files contain full accounting data and may include EINs, vendor tax data, bank account names, payroll-adjacent data, and partner capital information.
- Treat migration workspace as sensitive accounting data.

Rules:
- Do not commit `.QBB`, `.QBW`, raw exports, staging data, QBO tokens, `.env`, or CPA support packages to git.
- Mask EIN/TIN and bank account details in logs and reports unless the report is explicitly CPA-restricted.
- Never ask for or store QuickBooks admin passwords in code.
- QBO writes are sandbox-only until a separate production cutover spec is approved.
- All write logs must include realm, entity, operation, source ID, QBO ID, timestamp, and outcome.
- Every import output must preserve source traceability.

Accounting compliance:
- CPA/controller must approve opening-balance date, closed-year summary strategy, capitalization policy, depreciation support handling, sale gain/loss treatment, partner capital allocation, developer-fee recognition, and intercompany cleanup.

## 10. Testing Strategy

Unit tests:
- Filename parser detects entity names and timestamps.
- Duplicate detector groups backups by entity.
- Workbook schema generator creates all required tabs and columns.
- Normalizer validates dates, numeric amounts, debit/credit balance, and required source traceability.
- Mapper refuses unmapped accounts/vendors/customers/items.
- Import generator refuses rows with missing target company/class/location/account.

Integration tests:
- One fixture `.QBB` or exported fixture folder runs through inventory -> staging -> mapping -> dry-run import.
- QBO sandbox API dry-run prints payloads and writes no records.
- Sandbox guard fails if `QB_ENV` is not `sandbox` or realm/company name does not match.
- Reconciler identifies a planted variance.

Manual tests:
- Supervised restore checklist completed for one pilot source.
- Operator confirms restored QBW company name and last transaction date.
- CPA/controller reviews pilot mapping and opening-balance policy.

Regression tests:
- Existing QBO sandbox setup verification still passes.
- Existing no-production guard remains intact.
- Existing ProofRail MCP/QBO scripts are not given production write surfaces.

## 11. Deployment and Rollout Strategy

Phase 0 - Discovery only:
- Create folder structure.
- Inventory source files.
- Produce discovery report.
- No restore and no QBO write.

Phase 1 - One-file pilot:
- Select one representative `.QBB`, preferably an active project with AP/AR and a manageable transaction count.
- Restore/extract/normalize/map.
- Generate dry-run import package.
- Reconcile source to staging.
- Stop for review.

Phase 2 - Multi-file dry run:
- Process all selected files through inventory, restore/extract, staging, mapping, and dry-run packages.
- Produce consolidated exception dashboard.
- Resolve mapping blockers.

Phase 3 - Sandbox load:
- After explicit approval, load approved batches into the two QBO Advanced sandboxes.
- Run QBO reports and reconciliation.
- Produce final migration report.

Phase 4 - Production planning:
- Separate spec only. Requires CPA sign-off, production realm confirmation, export/backup plan, and rollback protocol.

Rollback:
- Before sandbox load, no rollback is needed because no QBO mutation occurs.
- After sandbox load, the default rollback is sandbox reset/reseed or manual void/inactivation. Code must not bulk-delete.

## 12. API and CLI Documentation

Proposed command surface:

```powershell
python -m migration.inventory_qbb_files `
  --source "L:\My Drive\2 Areas\QuickBooks & VPS Operations\Enterprise QBB files" `
  --workspace ".\SummaTerra-QB-Migration"
```

```powershell
python -m migration.init_workspace `
  --workspace ".\SummaTerra-QB-Migration"
```

```powershell
python -m migration.restore_or_restore_assistant `
  --workspace ".\SummaTerra-QB-Migration" `
  --entity "Madison Park"
```

```powershell
python -m migration.desktop_extractor `
  --workspace ".\SummaTerra-QB-Migration" `
  --entity "Madison Park" `
  --method auto
```

```powershell
python -m migration.normalize `
  --workspace ".\SummaTerra-QB-Migration" `
  --entity "Madison Park"
```

```powershell
python -m migration.map `
  --workspace ".\SummaTerra-QB-Migration" `
  --entity "Madison Park" `
  --mapping ".\SummaTerra-QB-Migration\00_control\mapping_workbook.xlsx"
```

```powershell
python -m migration.generate_qbo_import `
  --workspace ".\SummaTerra-QB-Migration" `
  --batch "BATCH_ID" `
  --dry-run
```

```powershell
python -m migration.load_qbo_sandbox `
  --workspace ".\SummaTerra-QB-Migration" `
  --batch "BATCH_ID" `
  --execute-sandbox
```

```powershell
python -m migration.reconcile `
  --workspace ".\SummaTerra-QB-Migration" `
  --batch "BATCH_ID"
```

QBO API entities likely involved:
- Account
- Department/Location
- Class
- Customer/Project
- Vendor
- Item/Product-Service
- Bill
- Invoice
- Purchase/Expense where appropriate
- JournalEntry for approved summaries/opening balances only
- Reports for Balance Sheet, Profit and Loss, Trial Balance where supported

Implementation must verify exact current QBO API details against Intuit Developer documentation before coding.

## 13. Database Migrations and File System Layout

Required folder structure:

```text
SummaTerra-QB-Migration/
  00_control/
    migration_control.xlsx
    mapping_workbook.xlsx
    source_file_inventory.csv
    discovery_report.md
  01_source_qbb/
  02_restored_qbw/
  03_raw_exports/
  04_staging/
  05_normalized/
  06_qbo_import_files/
  07_qbo_api_logs/
  08_reconciliation/
  09_exceptions/
  10_cpa_support_package/
```

No production database migration is required for Phase 1. If local relational staging is used, create a SQLite/DuckDB file under `04_staging/migration_staging.db` with the schemas in Section 6.

Git ignore requirements:
- Ignore `SummaTerra-QB-Migration/`
- Ignore `*.qbb`, `*.qbw`, `*.qbm`, `*.qbx`, `*.qba`, `*.qby`
- Ignore raw exports, staging DBs, and QBO API logs unless sanitized sample fixtures are intentionally created.

## 14. Known Limitations and Future Work

Technical spikes:
1. Confirm whether local machine has QuickBooks Desktop Enterprise/Accountant capable of restoring source `.QBB`; otherwise Rightworks restore remains supervised.
2. Confirm QODBC availability, bitness, and access permissions in the environment where `.QBW` files open.
3. Confirm whether Desktop SDK or Transaction Pro is available/allowed if QODBC is not.
4. Confirm current Intuit QBO API limits, minorversion behavior, and entity support before implementing API loader.
5. Confirm QBO Advanced class/location/project limits against current plan details before finalizing full entity mapping.

Future work:
- Production cutover spec.
- Automated restore using QuickBooks UI automation if officially safe and reliable.
- Full ProofRail integration for proof records on every QBO write.
- Web dashboard for exception review.
- CPA portal export package.

## 15. Glossary and Terms

`.QBB`: QuickBooks Desktop backup file. Must be restored before normal access.

`.QBW`: QuickBooks Desktop working company file.

QODBC: Driver that lets tools query QuickBooks Desktop data in structured form when the company file is open and authorized.

Realm: QBO company identifier used by the Accounting API.

Department: QBO API object that corresponds to QBO UI "Location".

Class: QBO tracking dimension. In the existing ProofRail design, Realm A uses Location/Department as legal entity and Class as phase.

Customer/Project: QBO project/job cost tracking structure.

Dry run: A run that generates payloads and reports but performs no QBO write.

Source traceability: The ability to prove exactly which source file/report/transaction produced each imported row.

## 16. Monitoring, Metrics, and Observability

Required logs:
- `00_control/discovery_report.md`
- `09_exceptions/exceptions.csv`
- `07_qbo_api_logs/qbo_migration_YYYYMMDD.jsonl`
- `08_reconciliation/{batch_id}_variance_report.xlsx`
- `10_cpa_support_package/{entity}/migration_summary.md`

Metrics:
- File inventory count.
- Duplicate groups count.
- Restore success/blocked/failed count.
- Extraction completeness by required report.
- Unmapped account/vendor/customer/item count.
- Dry-run row count by QBO entity type.
- Sandbox write success/failure count.
- Reconciliation variance by report and entity.
- Open blocker count by owner.

Alerts/blockers:
- Any production QBO host or production realm attempt.
- Any missing source traceability field.
- Any out-of-balance JE.
- Any unmapped row in import output.
- Any reconciliation variance above tolerance.
- Any CPA decision category still open before load.

## 17. Alternative Designs Considered

Alternative 1: Direct Intuit Desktop-to-QBO conversion per company.
- Rejected for this project because it is 20+ Desktop files into two QBO companies, not one source file to one target company.

Alternative 2: Import all historical transaction detail into QBO.
- Rejected as default because it can flood QBO and make reconciliation harder. Closed years should use monthly trial-balance summary entries unless detail is needed.

Alternative 3: Journal entries for all migrated data.
- Rejected because JEs bypass AP/AR subledgers and weaken bill/invoice aging. Use native Bills/Invoices for open AP/AR and current-year transaction detail where practical.

Alternative 4: Manual spreadsheet-only migration.
- Rejected because it cannot guarantee repeatability, source traceability, or dry-run gating.

Alternative 5: Production-first migration.
- Rejected. Sandbox-only until reconciliation and CPA/controller sign-off.

## 18. Final Build Checklist

Discovery:
- [ ] Source folder configured.
- [ ] Workspace folder structure created.
- [ ] `migration_control.xlsx` created.
- [ ] `mapping_workbook.xlsx` created with all 15 tabs.
- [ ] All source `.QBB` files inventoried.
- [ ] Duplicate backups grouped and newest recommended.
- [ ] Suspicious/missing files listed.
- [ ] Pilot source file selected.

Restore/extract:
- [ ] Pilot `.QBB` restored to `.QBW` or blocked with reason.
- [ ] Company metadata extracted.
- [ ] Required lists extracted.
- [ ] Required reports exported.
- [ ] 2025 and 2026 transaction detail extracted where available.
- [ ] Sold-property support extracted if applicable.

Normalize/map:
- [ ] Staging schemas generated.
- [ ] Dates, names, transaction types, accounts, classes, jobs, items, debit/credit values normalized.
- [ ] Every source row has source traceability.
- [ ] Target QBO company assigned.
- [ ] Target class/location/customer/project/account/item assigned or exception logged.
- [ ] CPA decision exceptions separated from technical exceptions.

Dry-run/import:
- [ ] QBO import files/payload previews generated.
- [ ] No unmapped rows included in import output.
- [ ] No QBO write before approval.
- [ ] Sandbox guard tested.
- [ ] QBO realm/company read-only sanity check passes.
- [ ] `--execute-sandbox` required for any write.

Reconcile:
- [ ] Source Trial Balance ties to staging.
- [ ] Source Balance Sheet ties to staging.
- [ ] Source P&L by month ties to staging.
- [ ] Open AP/AR ties or variance explained.
- [ ] Bank/loan/owner capital/intercompany/developer fee balances tie or variance explained.
- [ ] QBO reports tie after sandbox load.
- [ ] Final migration report generated.
- [ ] CPA support package generated.

Consistency Check Results:
- All sections checked for contradictions.
- Scope excludes production writes and Section 11 keeps production cutover as separate spec.
- Section 4 API integration reuses existing sandbox guards and Section 9 security forbids credentials/log secrets.
- Section 12 includes QBO API operations but requires current Intuit docs verification before build.
- No unresolved contradiction found.
- **v1.1.0 grounding pass (2026-07-08):** re-checked Section 4's reuse claims against actual repo
  files (see §0.1) - all verified, no contradictions introduced. Section 4/13 references to seed
  CSVs should point at `qbo Source Files/` only; the `qbo_setup_pack/` duplicate referenced nowhere
  in this spec's original text has been archived, so no update to this spec's own content was
  needed beyond the §0.1 note.
