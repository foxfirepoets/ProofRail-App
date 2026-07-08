# VENDOR_BILL_AUTOMATION_SPEC — the normal invoice workflow (email → proof → approval → sandbox bill)

## 1. Extract (from the invoice PDF/email; every field cites its source)

vendor (must match a Realm A vendor DisplayName exactly — fuzzy match proposes, human
confirms) · invoice number · amount (+ line-items total if itemized) · due date · project
(Customer:Job) · **Location** (legal entity) · **Class** (cost phase) · **Product/Service item**
(cost code 001–…/FEE-*) · PO if referenced · bank details ONLY as last-4 (never store raw).

Coding sources, in order: (1) explicit statement on the invoice; (2) GC cost-code crosswalk;
(3) vendor's coding history; (4) UNKNOWN → exception (PR-043: never guess).

## 2. Prove (before any approval — see INVOICEPROOF_ROUTING_SPEC.md)

`build_invoiceproof_packet.py` runs duplicate detection (exact + modified), amount math,
bank-change warning (any bank/remit change → out-of-band verification, the email is never
enough), missing W-9/support/coding checks, then (with `--send`) the SwarmSync scan.
Verdict: PASS / FLAG / FAIL — stricter of local and SwarmSync wins.

## 3. Approval packet (`05_Pending_Approval`)

One page per bill: extracted fields · proposed QBO coding (all four dimensions) ·
InvoiceProof verdict + findings + scanId · duplicate/bank-change status · source citations
(gmail msgid, Drive path) · the exact posting command (pre-filled, DRY RUN by default).
FLAG needs Ben's written override reason; FAIL never reaches this folder.

## 4. QBO sandbox bill creation packet

```
python scripts/qbo_create_sandbox_bill.py \
  --vendor "GC - Concord Homes Utah" --item "003 Concrete" --amount 42180.55 \
  --location "04 Madison Park" --class "40 Vertical" --customer "Madison West:Vertical" \
  --docnumber INV-20441 --txndate 2026-07-05 --execute-sandbox
```
The script re-verifies every ref exists (refuses otherwise), refuses duplicate
DocNumber+Vendor, posts with a deterministic RequestId, and audit-logs attempt/result.
Realm A only. Payment execution: **never** — bills are recorded, paying them stays human.

## 5. Audit trail (per bill, in order)

`intake_classified` → `attachment_saved` → `invoice_extracted` → `invoiceproof_packet`
(verdict) → `approval` (approver, channel, ts, override reason if FLAG) → `create_attempt` /
`create_ok` (RequestId, QBO Bill Id) → `posting_verified` (report read). Any gap = the bill is
not done, whatever any label says.
