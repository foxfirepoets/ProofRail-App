# CHUNK_3_CANONICAL: Expose unified cross-company search and a read API over the canonical store.

## Summary

Builds the canonical service layer that turns the synced data into the firm's operational interface: unified cross-company search (the capability the firm has never had) and read endpoints powering a dashboard. This replaces Google Sheets as the operational view. It comes after TRANSPORT because it needs synced data, and hands a queryable read surface to the workflow and proof chunks.

## Acceptance Criteria

- [ ] `GET /search?q=` performs unified search across vendors/bills/transactions spanning ALL companies, p95 < 2s, using the `pg_trgm` GIN index.
- [ ] `GET /sync/health` returns per-company poll cadence, queue depth, and last-reconciled age.
- [ ] `GET /bills/{id}` and `GET /vendors/{id}` return canonical records including `raw_extensions`.
- [ ] Search results are namespaced by `company_id` (duplicate vendor names across entities are disambiguated).
- [ ] A minimal dashboard read endpoint aggregates synced vendors/bills for display.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

| Method | Path | Description |
|--------|------|-------------|
| GET | /search?q= | Unified cross-company search (vendors/bills/txns) |
| GET | /sync/health | Per-company poll cadence, queue depth, last-reconciled |
| GET | /bills/{id} | Canonical bill record incl. raw_extensions |
| GET | /vendors/{id} | Canonical vendor record incl. raw_extensions |

## Database Changes

No schema changes in this chunk (read-only over CHUNK_1_INFRA tables; may add read-optimized views).

## Test Scenarios

- **Happy path**: search for a vendor name returns matches from multiple companies within the latency budget.
- **Edge case**: same vendor name exists in two companies → both returned, each tagged with its `company_id`.
- **Failure case**: search with an empty/oversized query is rejected with a clear 400, not a 500.
- **Integration**: CHUNK_5_WORKFLOW reads canonical records via this layer when building intents.

## Dependencies

- **Requires**: CHUNK_1_INFRA, CHUNK_2_TRANSPORT
- **Blocks**: CHUNK_5_WORKFLOW

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_3_CANONICAL</promise>
