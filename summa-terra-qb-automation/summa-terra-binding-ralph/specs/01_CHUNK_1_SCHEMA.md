# CHUNK_1_SCHEMA: Add the dimensioned canonical model + Alembic migration for the Summa Terra binding

## Summary

Extend the canonical store with the QuickBooks dimensions the binding needs: a chart of accounts, classes,
cost codes, customer:jobs, draw packages, bill lines, fee entries, and intercompany links — plus new columns
on `bills` and `companies` and a reconciliation view. This is the single schema boundary for the whole binding;
every later chunk reads these tables. It hands off ORM models that CHUNK_2–5 import.

Source of truth: `../AI Accounting Hub/SPEC_SUMMA_TERRA_BINDING.md` §6 and §13 (migration
`20260627_1300_summa_terra_binding`, `down_revision = "20260626_1200"`).

## Acceptance Criteria

- [ ] SQLAlchemy models added to `app/models.py` for: `Account`, `Class`, `CostCode`, `CustomerJob`,
      `DrawPackage`, `BillLine`, `FeeEntry`, `IntercompanyLink`; plus new columns on `Company`
      (`role`, `qb_entity_code`, `expense_dev_fee`) and `Bill` (`draw_package_id`, `net_amount_due`, `approval_id`).
- [ ] Migration `migrations/versions/20260627_1300_summa_terra_binding.py` with `down_revision="20260626_1200"`;
      UP creates 8 tables + 6 columns + view `v_intercompany_net`; DOWN reverses all of it cleanly.
- [ ] `companies.role` is added **nullable with no blanket default**, then backfilled, then `SET NOT NULL`
      (a `DEFAULT 'partnership'` would mis-tag the parent row — see §13 of the binding spec).
- [ ] `cost_codes.maps_to_account` (NOT `cip_account_number`) is the posting-account column.
- [ ] Uniqueness: `accounts(company_id,number)`, `classes(company_id,code)`, `cost_codes(company_id,code)`,
      `customer_jobs(company_id,path)`, `draw_packages(company_id,draw_number)`, `fee_entries(draw_package_id,fee_role)`.
- [ ] `alembic upgrade head` applies against the live Supabase `DATABASE_URL`; `alembic downgrade -1` reverts.
- [ ] `v_intercompany_net` returns net per counterparty pair (the close gate reads it; net must be $0).
- [ ] `ruff check . && mypy app` clean.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No HTTP endpoints — schema + ORM models only.

## Database Changes

- `accounts` (NEW): `id, company_id FK→companies, number, name, acct_type, statement CHAR(2), is_cip_bucket,
  parent_only, UNIQUE(company_id,number)`.
- `classes` (NEW): `id, company_id, code, name, UNIQUE(company_id,code)`.
- `cost_codes` (NEW): `id, company_id, code, name, maps_to_account, default_class_code, kind, fee_role,
  UNIQUE(company_id,code)`.
- `customer_jobs` (NEW): `id, company_id, path, parent_path NULL, UNIQUE(company_id,path)`.
- `draw_packages` (NEW): `id, company_id, draw_number, customer_job, package_total CHECK(>=0), status,
  approved_by, approved_at, UNIQUE(company_id,draw_number)`.
- `bill_lines` (NEW): `id, bill_id FK→bills ON DELETE CASCADE, cost_code_id FK→cost_codes, account_number,
  class_code, customer_job, amount, is_retainage`.
- `fee_entries` (NEW): `id, draw_package_id FK, book_company_id FK→companies, fee_role, percent NUMERIC(5,4),
  amount, dr_account, cr_account, intercompany_link_id FK NULL, proof_bundle_id FK NULL, qb_txn_id, status,
  UNIQUE(draw_package_id,fee_role)`.
- `intercompany_links` (NEW): `id, partnership_company_id FK, parent_company_id FK, partnership_account,
  parent_account, amount, source_ref`.
- `companies` (ALTER): add `role VARCHAR(16)` (backfill→NOT NULL), `qb_entity_code VARCHAR(16)`,
  `expense_dev_fee BOOLEAN NOT NULL DEFAULT false`.
- `bills` (ALTER): add `draw_package_id UUID FK→draw_packages`, `net_amount_due DECIMAL(14,2)`,
  `approval_id VARCHAR(64)`.
- `v_intercompany_net` (NEW VIEW): per `(partnership_company_id, parent_company_id)`, sum legs; expose `net`.

## Test Scenarios

- **Happy path**: `alembic upgrade head` creates all 8 tables, 6 columns, and the view; models import and a row
  inserts/round-trips for each table.
- **Edge case**: running `alembic upgrade head` twice is a no-op (already at head); CHECK rejects negative
  `package_total`.
- **Failure case**: `alembic downgrade -1` drops everything the migration added and restores the prior schema
  exactly (init `20260626_1200` intact).
- **Integration**: the ORM models are importable by CHUNK_3's loader without modification.

## Dependencies

- **Requires**: existing migration `20260626_1200_init_canonical` (the canonical store).
- **Blocks**: CHUNK_2, CHUNK_3, CHUNK_4, CHUNK_5.

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_1_SCHEMA</promise>
