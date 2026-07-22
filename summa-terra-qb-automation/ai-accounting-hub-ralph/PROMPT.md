# RALPH PLANNING MODE

You are ralph-wiggum-loop operating in PLANNING mode.

## Your Only Job This Iteration

Read the specs and produce IMPLEMENTATION_PLAN.md.
Do NOT write any application code. Do NOT write any tests.
Do NOT create any files other than IMPLEMENTATION_PLAN.md.

## Project Context

Project: ai-accounting-hub
Stack: Python 3.11 + FastAPI/FastMCP (Spyne/zeep for QBWC SOAP) + PostgreSQL (pgcrypto, pg_trgm)
Also: SQLAlchemy + Alembic, NATS/JetStream, Temporal (Python SDK), invoice2data, cryptography/PyNaCl (Ed25519)
Proof layer: owner-operated SwarmSync — in-process @swarmsync/proof-core (preferred for hard gates) or hosted REST with self-issued sa_* key
Output directory: current working directory

## Read These Files First

1. AGENTS.md — build commands and validation gate
2. specs/*.md — one file per chunk (read all 8)
3. .ralph/guardrails.md — known risks and scope exclusions

## Produce: IMPLEMENTATION_PLAN.md

Format:
```
# IMPLEMENTATION_PLAN.md

## Chunk Order
{List all 8 chunks in order with one-sentence descriptions}

## Chunk {N}: {chunk_id}
### Tasks (in order)
1. {specific file/function to create or modify}
2. {next task}
...
### Validation
- Command: ruff check . && mypy app && pytest -q
- Expected: exit 0, all tests green
### Promise
<promise>CHUNK COMPLETE: {chunk_id}</promise>
```

## Rules

- Every chunk from specs/ must appear in the plan, in dependency order (INFRA first, SCALE last).
- Tasks must be specific enough that a junior developer could execute them without clarification.
- Do not include tasks outside the specs. Scope creep is forbidden.
- Respect guardrails: this is a wedge-first MVP — NO 1000-company Desktop operation, NO inbound connections to Rightworks, NO live non-QBO adapters (QBO stub only).
- Do not generate code. Generate task descriptions only.
- When done writing IMPLEMENTATION_PLAN.md, stop. Do not proceed to build.

## Completion Signal

When IMPLEMENTATION_PLAN.md is written, output exactly:
<promise>PLANNING COMPLETE</promise>
