# CHUNK_4_AUDIT: Implement the AIVS hash-chain audit layer (AuditProof / Gate 2) as a hard pre-write gate.

## Summary

Implements AuditProof: a tamper-evident AIVS hash chain over every AI/human action, enforced as a HARD GATE before any GL write (a broken chain causes a hard rollback, never a warning). Maps to SwarmSync AIVS (Ed25519 + SHA-256), self-hosted via `runProofProduct({product:'auditproof'})` or local signing. It comes here so the proof substrate exists before any write-back chunk. It hands a validating audit chain and proof-bundle plumbing to the workflow, verify, and payments chunks.

## Acceptance Criteria

- [ ] Each action appends an `audit_rows` row with `row_hash = SHA-256("{row_id}:{session_id}:{action_type}:{tool_name}:{cost_cents}:{timestamp}:{prev_hash}")`.
- [ ] A `verify.py`-style validator confirms the full chain offline using only stdlib (insert/delete/reorder detection).
- [ ] Optional Ed25519 signing of the chain hash; key is locally generated, stored `0600`; signing is optional (hash chain alone is tamper-evident per AIVS §5).
- [ ] Sensitive input keys are redacted to `"[REDACTED]"` before hashing (no raw bank fields / secrets).
- [ ] A broken or out-of-order chain causes `AUDIT_CHAIN_BROKEN` and blocks the write (fail-closed); verified by test.
- [ ] `proof_bundles` rows are written for AuditProof results.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No public HTTP endpoints — internal proof/audit service layer (`append_audit_row`, `validate_chain`, `build_aivs_bundle`). Consumed by later chunks.

## Database Changes

No schema changes in this chunk (writes `audit_rows` and `proof_bundles` created by CHUNK_1_INFRA).

## Test Scenarios

- **Happy path**: a sequence of actions produces a chain that `validate_chain` accepts; `verify.py` exits 0.
- **Edge case**: redaction replaces values for keys matching sensitive substrings before hashing.
- **Failure case**: tampering with one row's `inputs_json` breaks the chain → validator exits 1 and the write is blocked.
- **Integration**: CHUNK_5_WORKFLOW appends an AuditProof row on every approval; CHUNK_7_PAYMENTS references the chain.

## Dependencies

- **Requires**: CHUNK_1_INFRA
- **Blocks**: CHUNK_5_WORKFLOW, CHUNK_6_VERIFY, CHUNK_7_PAYMENTS

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_4_AUDIT</promise>
