# CHUNK_4_NAMES: Idempotent upsert of Vendors and Customer:Jobs from the QB name lists

## Summary

Extend `app/catalog/loader.py` with upserts for the **names lists**: vendors (into the existing `vendors` table
from CHUNK_1 of the prior build) and customer:jobs (into the `customer_jobs` catalog from CHUNK_1 of this
binding). Vendors are scoped per company; the parent `EXEC —` vendors load only into the parent file. This
completes the catalog so dimensioned bills (future fee engine) can reference real vendors and jobs.

## Acceptance Criteria

- [ ] `load_vendors(session, company, rows)` upserts vendors on `(company_id, name)`; partnership file loads its
      44 vendors, parent file loads its 2 (`EXEC — Mike Watson`, `EXEC — Porter Christensen`). Reuses the
      existing `vendors` table/model (do not create a second vendor table).
- [ ] `load_customer_jobs(session, company, rows)` upserts on `UNIQUE(company_id, path)`; preserves the
      `parent_path` hierarchy (e.g. `HL Hunter's Landing:Sitework` → parent `HL Hunter's Landing`). 5 rows.
- [ ] **Idempotent**: a second load makes 0 changes; no duplicate vendors or jobs.
- [ ] `EXEC —` vendors never load into a `role='partnership'` company (defense-in-depth on the file split).
- [ ] `IC — Summa Terra Ventures` vendor is present in the partnership file (it is the intercompany fee payee).
- [ ] `ruff check . && mypy app` clean.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No HTTP endpoints — internal loader service layer.

## Database Changes

No schema changes (uses existing `vendors` + CHUNK_1 `customer_jobs`).

## Test Scenarios

- **Happy path**: load partnership vendors(44)+jobs(5) and parent vendors(2); counts match; `IC — Summa Terra
  Ventures` present in partnership; `EXEC —` vendors present only in parent.
- **Edge case**: a vendor name already present (e.g. from the prior read-sync) updates in place, no duplicate.
- **Failure case**: attempting to load `EXEC —` vendors into a partnership company is rejected with a clear error.
- **Integration**: vendors + jobs join cleanly to `bill_lines.customer_job` and future `fee_entries` payees.

## Dependencies

- **Requires**: CHUNK_1_SCHEMA, CHUNK_2_PARSE.
- **Blocks**: CHUNK_5_BOOTSTRAP.

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_4_NAMES</promise>
