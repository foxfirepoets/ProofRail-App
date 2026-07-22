# CHUNK_5_WORKFLOW: Wire the NATS event bus and Temporal commit-boundary with human approval gates.

## Summary

Builds the async-by-design execution core: AI agents submit intents onto NATS, a Temporal workflow holds them durably and blocks on a human-approval signal at the irreversible commit boundary. This is the mechanism that makes "autonomous accounting with human approval gates" real — full autonomy on reversible compute, hard gate only at irreversibility. It comes after the canonical and audit layers exist, and hands a gated intent pipeline to the verify and payments chunks.

## Acceptance Criteria

- [ ] `POST /intents` accepts an AI intent (`{intent, company_id, ..., raw_extensions}`), returns `202 {workflow_id}`, and publishes to NATS/JetStream.
- [ ] A Temporal workflow consumes the intent, builds the canonical record, and BLOCKS on a human-approval signal at the irreversible step.
- [ ] `POST /approvals/{workflow_id}` resolves the signal (`approve`/`reject`) and appends an AuditProof (CHUNK_4) row on every decision.
- [ ] Capability tokens scope which actions an agent may submit (ATXN `allowed_actions`); unauthorized intents return 403.
- [ ] On approval, the canonical write commits only after the AIVS chain validates (fail-closed).
- [ ] Intents survive a worker restart (durable Temporal state; no lost or double-applied intents).
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

| Method | Path | Description |
|--------|------|-------------|
| POST | /intents | Submit an AI accounting intent (async) → 202 {workflow_id} |
| POST | /approvals/{workflow_id} | Human approve/reject the commit-boundary signal |

## Database Changes

No new tables (uses `bills`, `audit_rows`; may add an intents/workflow-tracking table if needed — single schema boundary only).

## Test Scenarios

- **Happy path**: intent → workflow blocks → human approves → canonical write commits + AuditProof row appended.
- **Edge case**: approval arrives after the underlying record changed → optimistic-lock re-base (handed to CHUNK_6) or clean rejection.
- **Failure case**: agent submits an action outside its capability scope → 403, no workflow started.
- **Integration**: CHUNK_6_VERIFY inserts a VerifyAPI gate into this workflow before autonomous execution.

## Dependencies

- **Requires**: CHUNK_3_CANONICAL, CHUNK_4_AUDIT
- **Blocks**: CHUNK_6_VERIFY, CHUNK_7_PAYMENTS

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_5_WORKFLOW</promise>
