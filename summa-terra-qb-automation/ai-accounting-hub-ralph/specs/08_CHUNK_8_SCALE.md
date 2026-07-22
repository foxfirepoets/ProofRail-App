# CHUNK_8_SCALE: Scale read sync to all 10 company files and prove the adapter seam with a QBO stub.

## Summary

Completes the 90-day MVP: scales read sync from one to all 10 company files, runs one end-to-end approved + proof-signed payable across the firm, and builds a QBO adapter STUB against the same `AccountingAdapter` interface to prove the "swappable adapter" thesis (target: <20% changed mapping code). This is last because it depends on every gate working. It hands off a validated wedge and a demonstrated multi-ERP seam — explicitly NOT 1000-company Desktop operation, which is out of scope.

## Acceptance Criteria

- [ ] Read sync runs across all 10 company files into the canonical store; unified search spans all entities.
- [ ] One end-to-end payable is approved and proof-signed (InvoiceProof + AuditProof + VerifyAPI) across the full pipeline.
- [ ] A `QBOAdapter` stub implements the `AccountingAdapter` interface; swapping it in requires no changes to canonical/workflow/proof callers.
- [ ] Per-file sync lag and poll cadence are reported via `/sync/health` for all 10 files.
- [ ] All gates verified fail-closed under a simulated proof-service outage.
- [ ] Guardrail respected: NO attempt to run 1000-company Desktop operation (out of scope).
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No new public endpoints — extends `/sync/health` to all companies and adds the `QBOAdapter` implementation behind the existing interface.

## Database Changes

No schema changes (multi-company data already modeled by `company_id` in CHUNK_1_INFRA).

## Test Scenarios

- **Happy path**: all 10 files sync; a cross-company search returns results from every entity.
- **Edge case**: the QBO stub adapter is swapped in for one operation and callers are unaffected (<20% mapping delta).
- **Failure case**: proof service unreachable → all gates fail closed; no write proceeds.
- **Integration**: full pipeline (OCR → InvoiceProof → human gate → AuditProof → VerifyAPI → qbXML write-back) runs green end-to-end.

## Dependencies

- **Requires**: CHUNK_7_PAYMENTS
- **Blocks**: None (final MVP chunk)

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_8_SCALE</promise>
