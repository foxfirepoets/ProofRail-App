# CHUNK_1_INFRA: Stand up the canonical Postgres system-of-record with the initial multi-entity schema.

## Summary

Creates the foundational infrastructure: the **Supabase Postgres** canonical store (the system of record that replaces Google Sheets, project ref `fdnwlcomuddzmluvbylg`), the initial multi-entity accounting schema, and a docker-compose stack for **NATS + Temporal** (the event bus and workflow engine) used by later chunks. Postgres is the managed Supabase instance — not a local container. This is first because every other chunk reads or writes the canonical store. It hands off a migrated, queryable database and a running local NATS/Temporal stack to CHUNK_2_TRANSPORT.

## Acceptance Criteria

- [ ] `docker-compose up -d` brings up NATS (JetStream) and Temporal locally (Postgres is Supabase-managed, not containerized).
- [ ] App connects to the Supabase canonical store via `DATABASE_URL` (Supabase Postgres; password URL-encoded). Secrets come only from `.env` — never hard-coded.
- [ ] Supabase Postgres has `pgcrypto` and `pg_trgm` extensions enabled (via migration `CREATE EXTENSION IF NOT EXISTS`).
- [ ] Migration `20260626_1200_init_canonical` creates tables `companies`, `vendors`, `bills`, `proof_bundles`, `audit_rows` with all columns, FKs, CHECK constraints, and indexes from SPEC §6/§13 (including the `idx_vendors_name_trgm` GIN trigram index for unified search). Apply via Alembic against `DATABASE_URL`, or via the `supabase-aihub` MCP `apply_migration`.
- [ ] Migration has a working DOWN (Alembic `downgrade base`) that drops all tables cleanly.
- [ ] `amount >= 0` CHECK on `bills.amount` and other integrity constraints from SPEC §13 are enforced.
- [ ] A health-check script confirms a live connection to the Supabase canonical store.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No HTTP endpoints — infrastructure and schema layer only.

## Database Changes

- `companies`: one row per QB company file / legal entity (NEW)
- `vendors`: vendor master with `qb_list_id`, `qb_edit_sequence`, `bank_fingerprint`, `swarmscore`, `raw_extensions` JSONB (NEW)
- `bills`: AP bills with `qb_txn_id`, `qb_edit_sequence`, `amount DECIMAL(14,2)`, `status`, `invoiceproof_bundle_id` FK, `raw_extensions` JSONB (NEW)
- `proof_bundles`: VCAP/AIVS proof records — `kind`, `vcap_state`, `proof_hash`, `proof_signature`, `passed`, `payload` (NEW)
- `audit_rows`: AIVS hash-chain — `row_hash`, `prev_hash`, `action_type`, `actor`, `inputs_json`, `outputs_json` (NEW)
- Extensions: `pgcrypto` (gen_random_uuid), `pg_trgm` (unified search)

## Test Scenarios

- **Happy path**: migration UP runs clean against Supabase; all five tables exist with expected columns and indexes (assert via `information_schema`).
- **Edge case**: inserting a `bills` row with `amount = -1` is rejected by the CHECK constraint.
- **Failure case**: migration DOWN drops everything; re-running UP succeeds (idempotent rebuild); `CREATE EXTENSION IF NOT EXISTS` is safe to re-run.
- **Integration**: CHUNK_2_TRANSPORT can connect using the Supabase `DATABASE_URL` and insert a `companies` row.

## Dependencies

- **Requires**: None
- **Blocks**: CHUNK_2_TRANSPORT, CHUNK_3_CANONICAL, CHUNK_4_AUDIT (all read/write the canonical store)

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_1_INFRA</promise>
