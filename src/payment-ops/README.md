# STV Payment Operations

This module is the Phase 3 in-memory vertical slice for the simplified payment-control register. It is deliberately human-execution-only: it creates records and evidence links, but has no bank, QBO, Gmail-send, or money-movement adapter. The repository is process-local Phase 1 persistence only; idempotency does not survive restart or coordinate multiple instances. Replace it with a durable adapter before production execution.

All POST routes require `Authorization: Bearer <PAYMENT_OPS_API_KEY>`. The key must be configured; missing configuration or credentials returns 401. GET list routes remain readable.

## Invariants

- An obligation is fail-closed: evidence-backed account identity with a stable pay-from ID, payee, amount, amount basis, due date, pay-to reference, approval, and Ben capability are required before scheduling.
- The only legal bill path is `DISCOVERED → VERIFIED → APPROVAL_NEEDED/APPROVED → READY_FOR_EXECUTION → SCHEDULED → PAID_PENDING_CLEARING → CLEARED → RECONCILED`.
- Autopay skips transaction approval but can only become `CLEARED` with `BANK_FEED` or `STATEMENT` clearing evidence.
- Aubrey is never selected silently. `mark-unavailable` is pre-execution only and requires an explicit reason plus a fallback draft/task reference.
- Non-bill outflows are separate records and have no bill-state transition method.
- Every mutation returns the current record, an audit ID, and missing gates; invalid transitions return HTTP 409, malformed non-bill records return 422, and unknown IDs return 404.

## Integration

`PaymentOpsModule` is registered by the API root module. Replace `InMemoryPaymentOpsRepository` with a persistent adapter during ProofRail migration; retain the service guards and state machine as the authoritative mutation boundary.
