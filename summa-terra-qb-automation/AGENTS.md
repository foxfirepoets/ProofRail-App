# AGENTS.md — AI Accounting Hub

The AI operating layer for legacy accounting systems. A canonical store fronts QuickBooks Enterprise Desktop (Rightworks-hosted, 10+ company files for a real-estate dev firm) via an async adapter, with a human-approval commit boundary and a SwarmSync proof spine as hard gates.

**Single source of truth:** `SPEC.md` (18-section design spec, the architecture). Domain binding to the real QuickBooks config (Summa Terra Ventures — cost codes 001–069, Draw-Package fee engine, 5/2/1 split, intercompany, dimensioned canonical model): `SPEC_SUMMA_TERRA_BINDING.md` (v2.0.0, Phase 2.5). QB-side authority lives in `C:\Users\Administrator\Desktop\QB Summa Terra\SPEC.md` (v2.2.0) — consume it, never redesign it. Architecture rationale: `ARCHITECTURE_DECISION.md`. Build is driven by the ralph workspace in `ai-accounting-hub-ralph/`.

## Architecture (do not violate)

- **Canonical Postgres (Supabase) is the system of record** — replaces Google Sheets. QuickBooks Desktop is an eventually-consistent **batch sink**, never the source of truth.
- **Transport is thin and swappable.** qbXML over QBWC outbound-poll is the only Rightworks-sanctioned channel. QB quirks (TxnID/EditSequence/ListID/CoA drift) live in a fat semantics layer + `raw_extensions` JSONB sidecar, behind a stable `AccountingAdapter` interface.
- **Async-by-design.** AI submits intents → Temporal holds them durably → human approves at the irreversible commit boundary → QBWC drains the queue on its poll cadence.
- **SwarmSync proof spine = hard gates, not logs.** Gate 1 InvoiceProof (AP money-movement), Gate 2 AuditProof/AIVS hash-chain (pre-GL), Gate 3 VerifyAPI (pre-autonomous-exec), Gate 4 ATEP bank-change. **All gates fail closed.**

## Stack

Python 3.11 · FastAPI/FastMCP (+ Spyne/zeep for QBWC SOAP) · **Supabase Postgres** (pgcrypto, pg_trgm) · SQLAlchemy + Alembic · NATS/JetStream · Temporal · invoice2data · cryptography/PyNaCl (Ed25519). Proof layer is owner-operated SwarmSync ($0): in-process `@swarmsync/proof-core` preferred, hosted REST with self-issued `sa_*` key as fallback.

## Database / MCP

- Canonical store = Supabase project `fdnwlcomuddzmluvbylg`. Connect via `DATABASE_URL` (in `.env`).
- **Use the `supabase-aihub` MCP for this project** (scoped to that project ref). The `supabase` MCP is SwarmSync's — do not point it here.
- Migrations: Alembic against `DATABASE_URL`, or `supabase-aihub` `apply_migration`. Enable extensions with `CREATE EXTENSION IF NOT EXISTS`.

## Build commands

See `ai-accounting-hub-ralph/AGENTS.md`. Validation gate (must exit 0 before any commit): `ruff check . && mypy app && pytest -q`. `docker-compose up -d` runs NATS + Temporal only — Postgres is Supabase-managed.

## ralph workflow

Build runs in `ai-accounting-hub-ralph/` (8 chunks, INFRA→…→SCALE). Starts in planning mode (`PROMPT.md == PROMPT_plan.md`); after `<promise>PLANNING COMPLETE</promise>`, `cp PROMPT_build.md PROMPT.md` and loop. Read `.ralph/guardrails.md` before any action.

## Guardrails (hard limits)

- NO inbound connection/listener on the Rightworks box — outbound QBWC poll only.
- NO 1000-company Desktop operation (physics wall — scale path is API adapters; QBO is a stub seam only).
- NO live non-QBO adapters, payroll, tax, bank feeds, vendor portals (future phases).
- Payments/proof logic (CHUNK_7) stays atomic — never merge into another chunk.
- Gates fail closed; never write to books/QB without a valid proof.
- NEVER commit `.env`, keys, or log raw bank fields / proof secrets. Store bank **fingerprints**, not raw details.
- Smallest correct change; do not add dependencies without updating `requirements.txt` + AGENTS.md.

## Open spikes (before adapter write code)

1. Measure real QBWC poll cadence + queue depth on one Rightworks file.
2. Get written Rightworks approval for a persistent poller (no inbound fallback exists).
