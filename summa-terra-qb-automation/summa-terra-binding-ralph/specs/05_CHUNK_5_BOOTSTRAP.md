# CHUNK_5_BOOTSTRAP: One-command plug-and-play catalog bootstrap with split-at-file-level + bucket assertions

## Summary

Deliver the payoff: a single command that takes a parent company and a partnership company and **populates every
canonical catalog from the QB CSVs, verifies it, and reports — re-runnably**. This is the "just upload and it
auto-populates everything" experience, mirrored on the canonical side. Combines CHUNK_3 + CHUNK_4 loaders behind
`app/catalog/bootstrap.py` (a `python -m app.catalog.bootstrap` CLI) plus a thin `scripts/catalog_bootstrap.py`
wrapper, and runs the binding spec's hard assertions before declaring GREEN.

## Acceptance Criteria

- [ ] `python -m app.catalog.bootstrap --parent <ref> --partnership <ref> --imports <dir>` does, in order:
      (1) ensure `alembic` is at head (or instruct to run it), (2) upsert parent CSVs into the parent company,
      (3) upsert partnership CSVs into the partnership company, (4) run assertions, (5) print a summary table,
      (6) exit 0 on GREEN / non-zero on any failed assertion.
- [ ] Creates the two `companies` rows if absent (`role` set correctly: parent vs partnership) and is safe if
      they already exist.
- [ ] **Assertion — split-at-file-level**: the partnership company has **zero** accounts with `parent_only=true`
      and **zero** cost codes with `fee_role ∈ {dev_inc_5_parent, ceo_2_parent, pres_1_parent}`. (It DOES have
      `FEE-DEV` / `dev_5_partnership` — that is allowed.)
- [ ] **Assertion — bucket invariant**: every `kind='draw'` cost code maps to `15200` or `15300`.
- [ ] **Assertion — no orphans**: every `cost_codes.maps_to_account` resolves to an `accounts.number` in the
      same company; every `default_class_code` resolves to a `classes.code`.
- [ ] **Assertion — idempotency**: a second full bootstrap run reports `0 inserted, 0 updated` across all catalogs.
- [ ] Summary report prints per-company counts (accounts/classes/cost_codes/vendors/customer_jobs) and the
      assertion verdicts; e.g. `parent: 22 acct / 3 items … GREEN`, `partnership: 36 acct / 68 items … GREEN`.
- [ ] `ruff check . && mypy app` clean.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

CLI: `python -m app.catalog.bootstrap [--parent] [--partnership] [--imports] [--dry-run]`.
`--dry-run` parses + would-load + asserts in a rolled-back transaction and prints the report without committing.

## Database Changes

No schema changes (orchestrates CHUNK_1 tables; may INSERT the two `companies` rows).

## Test Scenarios

- **Happy path**: against a clean DB, one bootstrap call loads both companies, all assertions pass, exit 0,
  report shows the expected counts (parent 22/3, partnership 36/68, vendors 2/44, classes 10, jobs 5).
- **Edge case**: a second run is fully idempotent (0/0 changes) and still GREEN; `--dry-run` commits nothing.
- **Failure case**: if a `parent_only` account is somehow present in the partnership, the split-at-file-level
  assertion fails, the offending rows are printed, and the process exits non-zero.
- **Integration**: after bootstrap, the canonical catalogs are complete enough that the future Draw-Package fee
  engine (binding spec §5.3) can resolve every account/class/cost-code it needs.

## Dependencies

- **Requires**: CHUNK_1_SCHEMA, CHUNK_2_PARSE, CHUNK_3_CATALOG, CHUNK_4_NAMES.
- **Blocks**: None (final chunk).

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_5_BOOTSTRAP</promise>
