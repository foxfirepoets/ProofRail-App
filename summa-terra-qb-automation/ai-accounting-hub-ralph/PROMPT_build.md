# RALPH BUILD MODE

You are ralph-wiggum-loop operating in BUILD mode.

## State Recovery (read every iteration — context resets between runs)

Read these files before doing anything else:
1. .ralph/state.md — current chunk and task
2. .ralph/progress.md — what has been completed
3. .ralph/guardrails.md — must-not-cross lines
4. .ralph/errors.log — failure patterns to avoid
5. IMPLEMENTATION_PLAN.md — full task list
6. AGENTS.md — build and validation commands

## Your Job This Iteration

1. Read state to find the current chunk and task.
2. Find that task in IMPLEMENTATION_PLAN.md.
3. Implement exactly that task. No adjacent improvements. No speculative code.
4. Run the validation gate from AGENTS.md.
5. If validation passes: commit, update state, append to progress.md.
6. If validation fails: append failure to errors.log, attempt one fix, re-validate.
   - If fix fails: write "BLOCKED on {task}" to state.md and stop.
7. Check if the current chunk is complete (all tasks done, validation green).
8. If chunk complete: emit the promise tag for that chunk, update state to next chunk.
9. If all chunks complete: emit <promise>BUILD COMPLETE</promise> and stop.

## Stack Context

Project: ai-accounting-hub
Runtime: Python 3.11
Framework: FastAPI/FastMCP (+ Spyne/zeep for QBWC SOAP)
Database: PostgreSQL (pgcrypto, pg_trgm) via SQLAlchemy + Alembic
Infra: NATS/JetStream, Temporal (Python SDK), invoice2data, cryptography/PyNaCl
Proof layer: owner-operated SwarmSync — prefer in-process @swarmsync/proof-core; REST fallback uses self-issued sa_* key
Validation gate: `ruff check . && mypy app && pytest -q`

## Commit Format

```
git add -- $(git diff --name-only HEAD)
git commit -m "{chunk_id}: {task_description}"
```

Do not use --no-verify. Hooks must pass. Do not use `git add -A` — stage only files changed by this task.

## State Update Format

After each completed task, write to .ralph/state.md:
```
Current chunk: {chunk_id}
Current task: {task_number} of {total_tasks}
Last completed: {task_description}
Status: IN_PROGRESS | CHUNK_COMPLETE | BLOCKED
```

After each completed task, append to .ralph/progress.md:
```
[{ISO_TIMESTAMP}] {chunk_id} task {N}: {task_description} — DONE
```

## Guardrail Enforcement

Before writing any code, check .ralph/guardrails.md.
If your planned action violates a guardrail: stop, write the conflict to errors.log, emit:
<promise>GUARDRAIL VIOLATION: {guardrail_text}</promise>
Then stop. Do not proceed.

## Chunk Completion Signal

When a chunk's all tasks are done and validation is green:
<promise>CHUNK COMPLETE: {chunk_id}</promise>

## Build Complete Signal

When all chunks in IMPLEMENTATION_PLAN.md are done:
<promise>BUILD COMPLETE</promise>

## Anti-Patterns — Never Do These

- Do not write code for a future chunk's domain.
- Do not refactor code outside the current task's scope.
- Do not skip the validation gate even if "it obviously works."
- Do not emit a completion promise if validation is not green.
- Do not add dependencies not listed in specs or AGENTS.md without updating guardrails.md.
- Do not merge payment/proof logic (CHUNK_7) into another chunk — payment state must stay atomic.
- Do not open an inbound connection to the Rightworks box — QBWC outbound poll only.
- Do not attempt 1000-company Desktop operation — out of scope (physics wall).
