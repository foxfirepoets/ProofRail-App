# CHUNK_3_CATALOG: Idempotent upsert of COA + Classes + Cost Codes into the canonical catalogs

## Summary

Build `app/catalog/loader.py` upsert functions that take CHUNK_2's parsed rows and write the **template lists**
(chart of accounts, classes, cost codes) into the canonical store, scoped per `company_id`. Resolves each cost
code's **account NAME → account number** against the COA just loaded, and sets `accounts.parent_only` from which
file the account came in (the `*_Parent.csv` set minus the `*_Partnership.csv` set). Fully idempotent so the
plug-and-play bootstrap (CHUNK_5) can re-run safely.

## Acceptance Criteria

- [ ] `load_accounts(session, company, rows)` upserts on `UNIQUE(company_id, number)`; sets `is_cip_bucket` for
      `15100/15200/15300/15400/15500`; sets `parent_only=true` for accounts present only in the parent file set
      (verified set: `12200, 21100, 21200, 40200, 40300, 40400, 60200, 60300, 70100, 70200`).
- [ ] `load_classes(session, company, rows)` upserts on `UNIQUE(company_id, code)`.
- [ ] `load_cost_codes(session, company, rows)` upserts on `UNIQUE(company_id, code)`; resolves
      `maps_to_account` from the row's account NAME to an existing `accounts.number` in the same company —
      **0 orphans** (every cost code resolves) or the load fails loudly naming the unresolved item.
- [ ] `default_class_code` is resolved from the item's "Default Class" name to a loaded `classes.code`.
- [ ] **Idempotent**: a second identical load makes 0 changes (assert via a row-diff count) and never duplicates.
- [ ] **Bucket invariant** enforced at load: every `kind='draw'` cost code's `maps_to_account ∈ {15200,15300}`;
      reject otherwise.
- [ ] Load order respects FKs: accounts → classes → cost_codes (cost codes reference both).
- [ ] `ruff check . && mypy app` clean.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No HTTP endpoints — internal loader service layer.

## Database Changes

No schema changes (uses CHUNK_1 tables `accounts`, `classes`, `cost_codes`).

## Test Scenarios

- **Happy path**: load parent COA(22)+classes(10)+items(3) into a `role='parent'` company and partnership
  COA(36)+classes(10)+items(68) into a `role='partnership'` company; every cost code's `maps_to_account`
  resolves; `15500` FEE-DEV resolves; counts match.
- **Edge case**: re-running the load is a no-op (0 inserts/updates); changing one CSV value then re-loading
  updates exactly that row.
- **Failure case**: an item whose "Account" name is not in the COA raises a clear error naming the item and the
  unresolved account name (no silent NULL `maps_to_account`).
- **Integration**: the loaded catalogs are what CHUNK_5's split-at-file-level + bucket assertions verify.

## Dependencies

- **Requires**: CHUNK_1_SCHEMA, CHUNK_2_PARSE.
- **Blocks**: CHUNK_5_BOOTSTRAP.

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_3_CATALOG</promise>
