# CHUNK_7_PAYMENTS: Implement the InvoiceProof AP money-movement gate (Gate 1) and bank-change/ATEP gate (Gate 4) with OCR intake.

## Summary

The atomic payments chunk. Implements InvoiceProof as the HARD AP money-movement gate (Gate 1): no payment proceeds unless InvoiceProof clears (duplicate billing, math, PO mismatch, bank-change). Adds the bank-change/BEC gate (Gate 4) via ATEP trust tiers, and invoice2data OCR intake feeding the verification. It comes after the write path (CHUNK_6) it protects and before scale. This is isolated as its own chunk because payment state must be atomic. It hands a proof-gated end-to-end payable to CHUNK_8_SCALE.

## Acceptance Criteria

- [ ] invoice2data extracts vendor/amount/line-items/PO from an invoice PDF into a canonical bill draft.
- [ ] InvoiceProof gate runs in-process `runProofProduct({product:'invoiceproof', evidenceInputs})` (or `POST /invoice-proof/scan`); `riskLevel=CRITICAL` or any critical finding ⇒ BLOCK to human queue (`INVOICEPROOF_FAILED`, fail-closed).
- [ ] Rule coverage: `EXACT_DUPLICATE`, `MODIFIED_DUPLICATE`, `RECENT_DUPLICATE_IN_PAYMENT_HISTORY`, `MISSING_PO_REFERENCE`, `PO_AMOUNT_EXCEEDED`, `LINE_ITEM_MATH_ERROR`, `ROUND_DOLLAR_AMOUNT`.
- [ ] Bank-change (`BANK_ACCOUNT_CHANGE_DETECTED`) routes through ATEP capability check: PAYMENT_FORM requires TRUSTED tier; below tier ⇒ auto-block + escalate (`BANK_CHANGE_BLOCKED`).
- [ ] Prior vendor banking/payment context is loaded from the canonical store (via `vendor-master` / `payment-history`) so BEC detection has context.
- [ ] Every payment decision emits a VCAP Full Bundle proof (not AIVS-Micro) and an AuditProof row; escrow/`proof_bundles` use atomic compare-and-swap (no double-release).
- [ ] No payment write occurs without `passed=true` and a valid proof (fail-closed); verified by test.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

| Method | Path | Description |
|--------|------|-------------|
| POST | /ap/intake | Submit an invoice (PDF/JSON) → OCR + InvoiceProof verdict |
| GET | /bills/{id}/proof | Fetch the InvoiceProof/VCAP proof bundle (PDF/JSON) |

Internal: InvoiceProof gate, ATEP tier check, bank-fingerprint comparison.

## Database Changes

No new tables (writes `proof_bundles`, sets `bills.invoiceproof_bundle_id`, updates `vendors.bank_fingerprint`/`swarmscore`). Single schema boundary.

## Test Scenarios

- **Happy path**: clean invoice → InvoiceProof LOW risk → human approves → payment write proceeds with VCAP proof attached.
- **Edge case**: same invoice submitted to two entities → duplicate detected and blocked, each scoped by `company_id`.
- **Failure case**: vendor bank detail changed + vendor below TRUSTED tier → auto-blocked, escalated, no wire.
- **Integration**: CHUNK_8_SCALE runs this gate across all 10 company files end-to-end.

## Dependencies

- **Requires**: CHUNK_4_AUDIT, CHUNK_5_WORKFLOW, CHUNK_6_VERIFY
- **Blocks**: CHUNK_8_SCALE

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_7_PAYMENTS</promise>
