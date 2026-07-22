# CLAUDE.md — AI Accounting Hub

> ## ⚠️ THIS ENTIRE REPO IS DEPRECATED (2026-07-22)
> Merged in full into `foxfirepoets/ProofRail-App` (local: `Ben Projects\Co-Work QB Summa Terra`),
> under `summa-terra-qb-automation/` — 792 files, everything, nothing left behind. See
> `README.md` at this repo's root, and `summa-terra-qb-automation/README_MERGE.md` in the target
> repo. **Work in `Co-Work QB Summa Terra` from now on; treat this repo as read-only history.**
>
> The canonical STV memory file specifically moved to
> `Co-Work QB Summa Terra\MEMORY.md` — the `MEMORY.md` in this folder is now just a redirect stub
> (full pre-move history preserved at `MEMORY_ARCHIVED_2026-07-22.md` in this same folder).

The AI operating layer for legacy accounting systems. A canonical store fronts QuickBooks Enterprise Desktop (Rightworks-hosted, 10+ company files for a real-estate dev firm) via an async adapter, with a human-approval commit boundary and a SwarmSync proof spine as hard gates.

**Single source of truth:** `SPEC.md` (18-section design spec, the architecture). Domain binding to the real QuickBooks config (Summa Terra Ventures — cost codes 001–069, Draw-Package fee engine, 5/2/1 split, intercompany, dimensioned canonical model): `SPEC_SUMMA_TERRA_BINDING.md` (v2.0.0, Phase 2.5). QB-side authority lives in `C:\Users\Administrator\Desktop\QB Summa Terra\SPEC.md` (v2.2.0) — consume it, never redesign it. Architecture rationale: `ARCHITECTURE_DECISION.md`. Build is driven by the ralph workspace in `ai-accounting-hub-ralph/`.

## Architecture (do not violate)

- **Canonical Postgres (Supabase) is the system of record** — replaces Google Sheets. QuickBooks Desktop is an eventually-consistent **batch sink**, never the source of truth.
- **Transport is thin and swappable.** qbXML over QBWC outbound-poll is the only Rightworks-sanctioned channel. QB quirks (TxnID/EditSequence/ListID/CoA drift) live in a fat semantics layer + `raw_extensions` JSONB sidecar, behind a stable `AccountingAdapter` interface.
- **Async-by-design.** AI submits intents → Temporal holds them durably → human approves at the irreversible commit boundary → QBWC drains the queue on its poll cadence. **Poll cadence is business-hours and session-tied (RESOLVED 2026-07-01, see Guardrails) — not continuous/24-7.** Anything arriving off-hours queues in canonical Postgres until the next business-hours session.
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
- NO persistent/unattended poller — Rightworks confirmed (2026-07-01) there is no supported path to 24/7 QBWC polling. A global, non-adjustable 2-hour inactivity timeout fully logs out the RDP session (closing QuickBooks + Web Connector with it) regardless of disconnect-vs-signout, and Rightworks will not confirm/support a Windows Scheduled Task / service-account workaround. **QBWC polling is business-hours only, tied to a human's normal logged-in bookkeeping session** (their regular activity keeps the 2h idle timer from firing all day). Design the outbox/queue and any "stale intent" alerting around this — do not assume sub-hour or overnight delivery.
- NO 1000-company Desktop operation (physics wall — scale path is API adapters; QBO is a stub seam only).
- NO live non-QBO adapters, payroll, tax, bank feeds, vendor portals (future phases).
- Payments/proof logic (CHUNK_7) stays atomic — never merge into another chunk.
- Gates fail closed; never write to books/QB without a valid proof.
- NEVER commit `.env`, keys, or log raw bank fields / proof secrets. Store bank **fingerprints**, not raw details.
- Smallest correct change; do not add dependencies without updating `requirements.txt` + AGENTS.md.

## Open spikes (before adapter write code)

~~1. Measure real QBWC poll cadence + queue depth on one Rightworks file.~~
~~2. Get written Rightworks approval for a persistent poller (no inbound fallback exists).~~

**RESOLVED 2026-07-01 (Rightworks support ticket, written confirmation in thread):** No persistent/unattended poller exists or will be supported. QBWC + QuickBooks auto-open on hosted-session login (Rightworks will configure on request); the 2-hour global inactivity auto-logout is non-adjustable and ends the session (and QBWC with it) even across disconnect; Rightworks explicitly declined to confirm/support a scheduled-task/service-account workaround, redirecting that question to Intuit. **Final design: business-hours, session-tied QBWC polling** — coverage exists only while a human's normal bookkeeping session keeps the RDP session active; off-hours items queue in canonical Postgres until the next login. This is now the committed architecture, not an open question — see `architecture-decision-packet-stv-integration-layer-2026-06-29.md` §Risk R1/CRUX-spike and `integration-architecture-packet-stv-2026-06-29.md` for the updated Phase 6 gate status.

Separately confirmed: adding a sandbox QuickBooks company file (.QBW) to the existing hosted environment via Rightworks File Manager is free — no additional hosting charge. Cost/licensing questions for the extra file itself go to Intuit, not Rightworks.
