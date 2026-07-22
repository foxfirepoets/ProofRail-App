# RALPH PLANNING MODE

You are ralph-wiggum-loop operating in PLANNING mode.

## Your Only Job This Iteration

Read the specs and produce IMPLEMENTATION_PLAN.md.
Do NOT write any application code. Do NOT write any tests.
Do NOT create any files other than IMPLEMENTATION_PLAN.md.

## Project Context

Project: summa-terra-binding (extends the existing AI Accounting Hub canonical store)
Stack: Python 3.11+ · SQLAlchemy 2.0 + Alembic · Supabase Postgres · pytest · ruff · mypy
TARGET_REPO: /c/Users/Administrator/Desktop/AI Accounting Hub/ai-accounting-hub-ralph
  — ALL code lands in TARGET_REPO (extend `app/`, `migrations/versions/`, `tests/`, `scripts/`).
  — This binding workspace holds only the plan/specs/state; it contains no app code.
IMPORT_DIR: /c/Users/Administrator/Desktop/QB Summa Terra/Import_Files (the CSVs to ingest)

## Read These Files First

1. AGENTS.md — build commands, TARGET_REPO/IMPORT_DIR, validation gate.
2. specs/*.md — the 5 chunks (read all of them).
3. .ralph/guardrails.md — known risks and scope exclusions.
4. The binding spec: /c/Users/Administrator/Desktop/AI Accounting Hub/SPEC_SUMMA_TERRA_BINDING.md
   (authoritative for §6 schema and §13 migration). Also read TARGET_REPO/app/models.py and
   TARGET_REPO/migrations/versions/20260626_1200_init_canonical.py so the new migration chains correctly
   (down_revision = "20260626_1200") and the models match existing conventions.

## Produce: IMPLEMENTATION_PLAN.md

Format:
```
# IMPLEMENTATION_PLAN.md

## Chunk Order
CHUNK_1_SCHEMA → CHUNK_2_PARSE → CHUNK_3_CATALOG → CHUNK_4_NAMES → CHUNK_5_BOOTSTRAP

## Chunk N: {chunk_id}
### Tasks (in order)
1. {specific file/function in TARGET_REPO to create or modify}
...
### Validation
- Command: cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q
- Expected: exit 0, all tests green
### Promise
<promise>CHUNK COMPLETE: {chunk_id}</promise>
```

## Rules

- Every chunk from specs/ must appear in the plan, in dependency order (schema first).
- Tasks must name exact TARGET_REPO paths (e.g. `app/catalog/parsers.py`, `app/models.py`,
  `migrations/versions/20260627_1300_summa_terra_binding.py`, `tests/test_catalog_loader.py`,
  `scripts/catalog_bootstrap.py`).
- The CSVs are the source of truth and are already QB-upload-ready — the loader MIRRORS them, never reshapes them.
- Do not include tasks outside the specs. Scope creep is forbidden. Do not generate code in this mode.
- When done writing IMPLEMENTATION_PLAN.md, stop. Do not proceed to build.

## Completion Signal

When IMPLEMENTATION_PLAN.md is written, output exactly:
<promise>PLANNING COMPLETE</promise>
