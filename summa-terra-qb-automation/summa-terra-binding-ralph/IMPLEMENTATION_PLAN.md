# IMPLEMENTATION_PLAN.md

Project: summa-terra-binding — migration + plug-and-play IIF/CSV catalog loader.
TARGET_REPO: /c/Users/Administrator/Desktop/AI Accounting Hub/ai-accounting-hub-ralph (ALL code lands here).
IMPORT_DIR:  /c/Users/Administrator/Desktop/QB Summa Terra/Import_Files
Source spec: ../SPEC_SUMMA_TERRA_BINDING.md (§6 schema, §13 migration). Authoritative for all field names.
Conventions (observed in TARGET_REPO, MUST match):
- Models: `Base(DeclarativeBase)` + `TimestampMixin`, `UUID(as_uuid=False)` w/ `server_default=text("gen_random_uuid()")`,
  `Numeric(14,2)`, `String(n)`, `CheckConstraint`, `Index`; `from __future__ import annotations`.
- Migrations: `op.execute(""" <verbatim SQL> """)`, idempotent extensions, `DROP ... CASCADE` down-path,
  `revision`/`down_revision` string constants.
- Validation gate after EVERY task: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q` (must exit 0).
- Loader uses **stdlib `csv`** + existing SQLAlchemy — NO new dependencies expected.

## Chunk Order
CHUNK_1_SCHEMA → CHUNK_2_PARSE → CHUNK_3_CATALOG → CHUNK_4_NAMES → CHUNK_5_BOOTSTRAP

---

## Chunk 1: CHUNK_1_SCHEMA
Add the dimensioned models + the Alembic migration. One schema boundary; everything else depends on it.

### Tasks (in order)
1. `app/models.py` — append new ORM models (do NOT alter existing 5; same style/imports). Add:
   - `Account` (`accounts`): `id` UUID PK; `company_id` FK→companies; `number` String(8); `name` String(128);
     `acct_type` String(32); `statement` CHAR(2); `is_cip_bucket` Boolean default false; `parent_only` Boolean
     default false; `UniqueConstraint(company_id, number)`; `Index("idx_accounts_company","company_id")`.
   - `Class` (`classes`): `id`; `company_id` FK; `code` String(8); `name` String(64); `UniqueConstraint(company_id, code)`.
   - `CostCode` (`cost_codes`): `id`; `company_id` FK; `code` String(8); `name` String(64);
     `maps_to_account` String(8) NOT NULL; `default_class_code` String(8) nullable; `kind` String(16) NOT NULL;
     `fee_role` String(16) nullable; `UniqueConstraint(company_id, code)`; `Index("idx_costcodes_company","company_id")`.
   - `CustomerJob` (`customer_jobs`): `id`; `company_id` FK; `path` String(128); `parent_path` String(128) nullable;
     `UniqueConstraint(company_id, path)`.
   - `DrawPackage` (`draw_packages`): `id`; `company_id` FK; `draw_number` String(32); `customer_job` String(128);
     `package_total` Numeric(14,2) NOT NULL; `status` String(16) NOT NULL default 'submitted'; `approved_by`
     String(64) nullable; `approved_at` DateTime(tz) nullable; `CheckConstraint("package_total >= 0",
     name="ck_draw_pkg_total_nonneg")`; `UniqueConstraint(company_id, draw_number)`; `Index("idx_drawpkg_company","company_id")`.
   - `BillLine` (`bill_lines`): `id`; `bill_id` FK→bills ondelete CASCADE; `cost_code_id` FK→cost_codes;
     `account_number` String(8) NOT NULL; `class_code` String(8) NOT NULL; `customer_job` String(128) NOT NULL;
     `amount` Numeric(14,2) NOT NULL; `is_retainage` Boolean default false; `Index("idx_billlines_bill","bill_id")`.
   - `FeeEntry` (`fee_entries`): `id`; `draw_package_id` FK→draw_packages; `book_company_id` FK→companies;
     `fee_role` String(16) NOT NULL; `percent` Numeric(5,4) NOT NULL; `amount` Numeric(14,2) NOT NULL;
     `dr_account` String(8) NOT NULL; `cr_account` String(8) NOT NULL; `intercompany_link_id` FK→intercompany_links
     nullable; `proof_bundle_id` FK→proof_bundles nullable; `qb_txn_id` String(128) nullable; `status` String(16)
     NOT NULL default 'drafted'; `UniqueConstraint(draw_package_id, fee_role)`; `Index("idx_feeentries_draw","draw_package_id")`.
   - `IntercompanyLink` (`intercompany_links`): `id`; `partnership_company_id` FK→companies; `parent_company_id`
     FK→companies; `partnership_account` String(8) NOT NULL; `parent_account` String(8) NOT NULL; `amount`
     Numeric(14,2) NOT NULL; `source_ref` String(64) nullable.
   - Extend `Company`: add `role` String(16) nullable (NOT a hard NOT NULL in the ORM — DB backfills then enforces);
     `qb_entity_code` String(16) nullable; `expense_dev_fee` Boolean NOT NULL default false.
   - Extend `Bill`: add `draw_package_id` String(UUID) FK→draw_packages nullable; `net_amount_due` Numeric(14,2)
     nullable; `approval_id` String(64) nullable.
2. `migrations/versions/20260627_1300_summa_terra_binding.py` — new migration, `revision="20260627_1300"`,
   `down_revision="20260626_1200"`. `upgrade()` via `op.execute(""" … """)` blocks, in FK-safe order:
   a. `ALTER TABLE companies ADD COLUMN role VARCHAR(16)` (nullable, NO default), `ADD COLUMN qb_entity_code
      VARCHAR(16)`, `ADD COLUMN expense_dev_fee BOOLEAN NOT NULL DEFAULT false`.
   b. `CREATE TABLE accounts/classes/customer_jobs` (no cross-deps), then `cost_codes`, `draw_packages`,
      `intercompany_links`, then `fee_entries` (refs draw_packages + intercompany_links + proof_bundles),
      then `bill_lines` (refs bills + cost_codes). Use the exact columns/UNIQUE/CHECK from task 1.
   c. `ALTER TABLE bills ADD COLUMN draw_package_id UUID REFERENCES draw_packages(id), ADD COLUMN net_amount_due
      DECIMAL(14,2), ADD COLUMN approval_id VARCHAR(64)`.
   d. Indexes: `idx_accounts_company, idx_costcodes_company, idx_drawpkg_company, idx_billlines_bill,
      idx_feeentries_draw`.
   e. `CREATE VIEW v_intercompany_net AS` — per `(partnership_company_id, parent_company_id)` sum of
      `intercompany_links.amount` exposed as `net` (the close gate reads it; target $0).
   f. Backfill comment block + executable backfill: leave `role` to be set by the loader/bootstrap, but the
      migration MUST end the column nullable (the bootstrap sets role on the company rows it creates). Document
      in the migration docstring that a blanket DEFAULT was deliberately avoided.
   `downgrade()`: `DROP VIEW IF EXISTS v_intercompany_net;` then `DROP TABLE IF EXISTS fee_entries, bill_lines,
   intercompany_links, draw_packages, cost_codes, customer_jobs, classes, accounts CASCADE;` then
   `ALTER TABLE bills DROP COLUMN ...; ALTER TABLE companies DROP COLUMN ...;`.
3. `tests/test_binding_schema.py` — assert: migration is importable; all 8 model classes import; UNIQUE/CHECK
   present; (integration, gated on `RUN_INTEGRATION=1`) `alembic upgrade head` then `downgrade -1` round-trips and
   the `companies.role` column is nullable post-upgrade. Mark live-DB cases `@pytest.mark.integration`.

### Validation
- Command: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`
- Expected: exit 0, all tests green.
### Promise
<promise>CHUNK COMPLETE: CHUNK_1_SCHEMA</promise>

---

## Chunk 2: CHUNK_2_PARSE
Pure CSV/IIF parsers — no DB, no env, no network. The brittle "match the document" logic, unit-tested.

### Tasks (in order)
1. `app/catalog/__init__.py` — empty package marker.
2. `app/catalog/rows.py` — frozen dataclasses: `AccountRow(number,name,acct_type,statement,is_cip_bucket)`,
   `ClassRow(code,name)`, `CostCodeRow(code,name,account_name,default_class_name,kind,fee_role)`,
   `VendorRow(name)`, `CustomerJobRow(path,parent_path)`.
3. `app/catalog/parsers.py` — stdlib `csv.DictReader`; functions:
   - `parse_accounts(path) -> list[AccountRow]` (cols `Number, Account Name, Type, Description`); set
     `is_cip_bucket` for number in {15100,15200,15300,15400,15500}; map QB Type→`acct_type`/`statement`
     (BANK/AR/AP/OCASSET/OCLIAB/LTLIAB/EQUITY/INC/COGS/EXP/etc.; BS vs PL).
   - `parse_classes(path) -> list[ClassRow]` (`Class Name`): split leading `^(\S+)\s+(.*)$` → code, name.
   - `parse_cost_codes(path) -> list[CostCodeRow]` (`Item Name, Type, Description, Account, Default Class`):
     keep `account_name` verbatim (resolution is CHUNK_3); derive `kind` (`^0\d\d`→draw; in
     {100,101,110,120,121,122,200,201}→lifecycle; startswith `FEE-`→fee; `RETAINAGE-HELD`→retainage) and
     `fee_role` (FEE-DEV→dev_5_partnership, FEE-DEV-INC→dev_inc_5_parent, FEE-CEO→ceo_2_parent,
     FEE-PRES→pres_1_parent, else None).
   - `parse_vendors(path) -> list[VendorRow]` (`Vendor Name`).
   - `parse_customer_jobs(path) -> list[CustomerJobRow]` (`Customer:Job`): `parent_path` = text before the last `:`.
   - `parse_iif(path) -> set[str]` (optional parity): extract account/item names; used by CHUNK_5 as a non-fatal
     warning if CSV-derived names diverge from the .iif.
   - Each parser raises `FileNotFoundError(<explicit file>)` if the CSV is absent (no silent empty list).
4. `tests/test_catalog_parsers.py` — run against the real IMPORT_DIR: assert counts (partnership COA 36 /
   parent 22 / classes 10 / partnership items 68 / parent items 3 / partnership vendors 44 / parent vendors 2 /
   jobs 5) and spot-check derivations (`003 Concrete`→draw, `068 Construction Profit`→draw + fee_role None,
   `FEE-DEV`→fee/dev_5_partnership, `100 Land Acquisition`→lifecycle, `HL Hunter's Landing:Sitework`→parent
   `HL Hunter's Landing`). Pure — no DB fixtures.

### Validation
- Command: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`
- Expected: exit 0, all tests green.
### Promise
<promise>CHUNK COMPLETE: CHUNK_2_PARSE</promise>

---

## Chunk 3: CHUNK_3_CATALOG
Idempotent upsert of the template lists (COA, Classes, Cost Codes), resolving account name→number.

### Tasks (in order)
1. `app/catalog/loader.py` — `LoadResult(inserted:int, updated:int, unchanged:int)` and a private
   `_upsert(session, model, key_cols, values) -> str` ('inserted'|'updated'|'unchanged') used by all loaders.
2. `load_accounts(session, company_id, rows) -> LoadResult` — upsert on (company_id, number); set `parent_only`
   from the caller (parent-file rows whose number ∈ the verified parent-only set
   {12200,21100,21200,40200,40300,40400,60200,60300,70100,70200}); set `is_cip_bucket` from the row.
3. `load_classes(session, company_id, rows) -> LoadResult` — upsert on (company_id, code).
4. `load_cost_codes(session, company_id, rows) -> LoadResult` — resolve each `account_name` → an existing
   `accounts.number` for this company (build a name→number map once); raise `CatalogError` naming the item +
   unresolved account if not found (0 orphans). Resolve `default_class_name`→`classes.code`. Enforce bucket
   invariant: `kind=='draw'` ⇒ resolved number ∈ {15200,15300}, else raise. Upsert on (company_id, code).
5. `tests/test_catalog_loader.py` (integration, gated): load parent then partnership into two `companies` rows;
   assert counts, 0 orphans, FEE-DEV→15500, bucket invariant holds; **re-run = LoadResult(0,0,N)** (idempotent);
   mutate one CSV value in a fixture copy → exactly 1 updated. Use a transaction rolled back per test.

### Validation
- Command: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`
- Expected: exit 0, all tests green.
### Promise
<promise>CHUNK COMPLETE: CHUNK_3_CATALOG</promise>

---

## Chunk 4: CHUNK_4_NAMES
Idempotent upsert of the name lists (Vendors into the existing table, Customer:Jobs into the new catalog).

### Tasks (in order)
1. `app/catalog/loader.py` — add `load_vendors(session, company_id, rows, *, company_role) -> LoadResult`:
   upsert on (company_id, name) into the EXISTING `vendors` table/model; if `company_role=='partnership'` and a
   row name startswith `EXEC —`/`EXEC -`, raise `CatalogError` (defense-in-depth on the file split).
2. `load_customer_jobs(session, company_id, rows) -> LoadResult` — upsert on (company_id, path) into
   `customer_jobs`; preserve `parent_path`.
3. `tests/test_catalog_names.py` (integration, gated): partnership vendors 44 (incl. `IC — Summa Terra Ventures`)
   + jobs 5; parent vendors 2 (`EXEC —` present only in parent); re-run idempotent; loading `EXEC —` into a
   partnership raises.

### Validation
- Command: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`
- Expected: exit 0, all tests green.
### Promise
<promise>CHUNK COMPLETE: CHUNK_4_NAMES</promise>

---

## Chunk 5: CHUNK_5_BOOTSTRAP
The plug-and-play payoff: one command loads + verifies + reports, re-runnably.

### Tasks (in order)
1. `app/catalog/assertions.py` — `assert_split_at_file_level(session, partnership_company_id)` (no parent_only
   accounts; no cost code with fee_role ∈ {dev_inc_5_parent,ceo_2_parent,pres_1_parent}); `assert_bucket_invariant`
   (all draw cost codes → 15200/15300); `assert_no_orphans` (every maps_to_account resolves; every
   default_class_code resolves). Each raises `AssertionFailure` listing offending rows.
2. `app/catalog/bootstrap.py` — `argparse` CLI `python -m app.catalog.bootstrap --parent <ref> --partnership
   <ref> --imports <dir> [--dry-run]`:
   a. open a session (reuse `app/db.py` `get_session`); ensure alembic at head OR print a clear instruction.
   b. get-or-create the two `companies` rows; set `role='parent'`/`'partnership'` and `legal_name`/`entity_type`.
   c. parent: `load_accounts(parent_only flagged)` → classes → cost_codes → vendors → customer_jobs.
   d. partnership: same order; `load_*` calls with `company_role='partnership'`.
   e. run the three assertions; on `--dry-run`, do all of the above inside a transaction and ROLLBACK.
   f. print a per-company summary table (counts + GREEN/RED) and the aggregate LoadResult; `sys.exit(0)` on
      GREEN, `sys.exit(1)` on any AssertionFailure/CatalogError (with the offending rows printed).
3. `scripts/catalog_bootstrap.py` — thin wrapper invoking `app.catalog.bootstrap.main()` (parity with existing
   `scripts/` style) so it can run as a script.
4. `tests/test_catalog_bootstrap.py` (integration, gated): end-to-end against a clean schema — one run loads
   both companies, all assertions pass, exit 0, counts match (parent 22/3, partnership 36/68, vendors 2/44,
   classes 10, jobs 5); second run idempotent (0/0); `--dry-run` commits nothing; a seeded parent_only row in the
   partnership makes split-at-file-level fail with exit 1.
5. Update `TARGET_REPO/README` or `AGENTS.md` only if a command changed — otherwise no doc churn.

### Validation
- Command: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`
- Expected: exit 0, all tests green.
### Promise
<promise>CHUNK COMPLETE: CHUNK_5_BOOTSTRAP</promise>

---

## Notes for build mode
- Integration tests touching the live Supabase DB must be `@pytest.mark.integration` and skipped unless
  `RUN_INTEGRATION=1` (match the prior build's convention) so the default `pytest -q` gate stays green offline.
- No new pip dependencies are anticipated (stdlib `csv` + existing SQLAlchemy/Alembic). If one becomes
  unavoidable, add it to `requirements.txt` AND `.ralph/guardrails.md` before importing it.
- Never reshape the CSVs; never create `cip_account_number`; never give `companies.role` a blanket default;
  never load parent-only accounts / parent fee_roles / `EXEC —` vendors into a partnership.
