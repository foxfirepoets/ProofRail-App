# CHUNK_6_VERIFY: Add the VerifyAPI pre-execution gate (Gate 3) and gated qbXML write-back with optimistic locking.

## Summary

Adds VerifyAPI as the pre-execution validation gate (Gate 3): no autonomous workflow executes unless VerifyAPI reaches VERIFIED and carries an `independent_attestor_signature`. It then extends the transport adapter to perform gated qbXML write-back (e.g., `BillAdd`) to ONE company file, handling QB's `EditSequence` optimistic-lock conflicts. It comes after the workflow exists and before payments, and hands a proven write path to CHUNK_7_PAYMENTS.

## Acceptance Criteria

- [ ] VerifyAPI gate calls `runProofProduct({product:'verifyapi'})` (in-process) or `POST {API_BASE_URL}/api/verify` with a self-issued `sa_*` key; advance only on VERIFIED/COMPLETE + low risk.
- [ ] Gate is HARD: a non-VERIFIED result returns `VERIFY_NOT_READY` (409) and routes to the human queue (fail-closed).
- [ ] qbXML write-back emits `BillAdd` for an approved bill to one company file and reconciles the returned `qb_txn_id`/`qb_edit_sequence`.
- [ ] `EditSequence` conflict → `QB_EDIT_CONFLICT` (409): re-read from QB, re-base the canonical record, retry once, else route to human.
- [ ] CoA drift (account missing in file) is caught pre-write as `COA_DRIFT` (422), not a silent failure.
- [ ] Write-back is enqueued and drained on the QBWC poll cadence (async); no write proceeds without VerifyAPI + AIVS validation.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

Extends CHUNK_5 workflow with an internal VerifyAPI gate step and extends the `AccountingAdapter` with a write method (`add_bill`). No new public endpoints (write is driven by approved intents).

## Database Changes

No schema changes (updates `bills.status`, `qb_txn_id`, `qb_edit_sequence`; writes `proof_bundles` for VerifyAPI results).

## Test Scenarios

- **Happy path**: approved intent passes VerifyAPI → `BillAdd` succeeds → `qb_txn_id` reconciled into canonical store.
- **Edge case**: stale `EditSequence` → re-read + re-base + single retry succeeds.
- **Failure case**: VerifyAPI returns non-VERIFIED → write blocked, routed to human; CoA drift caught pre-write.
- **Integration**: CHUNK_7_PAYMENTS adds the InvoiceProof money-movement gate ahead of this write path.

## Dependencies

- **Requires**: CHUNK_2_TRANSPORT, CHUNK_4_AUDIT, CHUNK_5_WORKFLOW
- **Blocks**: CHUNK_7_PAYMENTS

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_6_VERIFY</promise>
