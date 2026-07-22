# RALPH BUILD MODE

You are ralph-wiggum-loop operating in BUILD mode.

## State Recovery (read every iteration — context resets between runs)

1. .ralph/state.md — current chunk and task
2. .ralph/progress.md — what has been completed
3. .ralph/guardrails.md — must-not-cross lines
4. .ralph/errors.log — failure patterns to avoid
5. IMPLEMENTATION_PLAN.md — full task list
6. AGENTS.md — build/validation commands, TARGET_REPO, IMPORT_DIR

## Your Job This Iteration

1. Read state to find the current chunk and task.
2. Find that task in IMPLEMENTATION_PLAN.md.
3. Implement exactly that task **in TARGET_REPO** (not this workspace). No adjacent improvements.
4. Run the validation gate: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`.
5. If validation passes: commit (in TARGET_REPO), update state, append to progress.md.
6. If validation fails: append failure to errors.log, attempt one fix, re-validate.
   - If fix fails: write "BLOCKED on {task}" to state.md and stop.
7. If the current chunk's tasks are all done and the gate is green: emit the chunk promise, advance state.
8. If all chunks complete: emit <promise>BUILD COMPLETE</promise> and stop.

## Stack Context

Project: summa-terra-binding
TARGET_REPO: /c/Users/Administrator/Desktop/AI Accounting Hub/ai-accounting-hub-ralph
IMPORT_DIR:  /c/Users/Administrator/Desktop/QB Summa Terra/Import_Files
Runtime: Python 3.11+ · SQLAlchemy 2.0 + Alembic · Supabase Postgres · pytest · ruff · mypy
Validation gate: `cd "$TARGET_REPO" && ruff check . && mypy app && pytest -q`

## Commit Format (run inside TARGET_REPO)

```
cd "$TARGET_REPO"
git add -- $(git diff --name-only HEAD)
git commit -m "{chunk_id}: {task_description}"
```
Do not use --no-verify. Do not use `git add -A` — stage only files this task changed.

## State Update Format

.ralph/state.md:
```
Current chunk: {chunk_id}
Current task: {task_number} of {total_tasks}
Last completed: {task_description}
Status: IN_PROGRESS | CHUNK_COMPLETE | BLOCKED
```
.ralph/progress.md (append):
```
[{ISO_TIMESTAMP}] {chunk_id} task {N}: {task_description} — DONE
```

## Guardrail Enforcement

Before writing code, check .ralph/guardrails.md. If an action violates a guardrail: stop, write the conflict to
errors.log, emit `<promise>GUARDRAIL VIOLATION: {guardrail_text}</promise>`, then stop.

## Chunk / Build Completion Signals

`<promise>CHUNK COMPLETE: {chunk_id}</promise>` when a chunk's tasks pass the gate.
`<promise>BUILD COMPLETE</promise>` when every chunk in IMPLEMENTATION_PLAN.md is done.

## Anti-Patterns — Never Do These

- Do not write code into this binding workspace — all code goes in TARGET_REPO.
- Do not reshape the QB CSVs — the loader mirrors them exactly (they are QB-upload-ready).
- Do not create a `cip_account_number` column — it is `maps_to_account`.
- Do not give `companies.role` a blanket DEFAULT — backfill then SET NOT NULL.
- Do not load `parent_only` accounts, parent `fee_role` items, or `EXEC —` vendors into a partnership company.
- Do not skip the validation gate or commit on a red gate.
- Do not add dependencies without updating TARGET_REPO/requirements.txt + guardrails.md.
- Do not touch the prior build's chunks (transport/audit/canonical/workflow/verify/payments/scale) except to
  reuse the existing `vendors`/`Company`/models — extend, never rewrite.
