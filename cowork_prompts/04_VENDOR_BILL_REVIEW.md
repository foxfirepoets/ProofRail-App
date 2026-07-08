# VENDOR BILL REVIEW — paste to review the invoice queue (or one invoice)

Scope: **[Ben: "the queue" or paste gmail:<msgid> / drive:<path>]**
Follow `docs/VENDOR_BILL_AUTOMATION_SPEC.md`:

1. For each invoice in scope, show the extraction: vendor (exact QBO DisplayName — if fuzzy,
   show the candidate and ASK, never assume) · invoice no · amount (+ line total) · due date ·
   proposed coding: project (Customer:Job) / Location / Class / Item — with the evidence for
   each coding choice (invoice text, GC crosswalk, vendor history). Unknown coding → exception,
   not a guess (PR-043).
2. Ensure the InvoiceProof packet exists (build it if missing — see 02_HOURLY_INBOX_RUN step 5).
   Show verdict + findings + scanId.
3. Duplicate + bank-change status explicitly (even when clean, say "checked: clean").
4. W-9 / insurance status for the vendor (W9-Insurance tracking).
5. Verdict routing: PASS → ready for approval · FLAG → present findings + ask Ben for a written
   override reason (record it verbatim) · FAIL → quarantined, list what would clear it.
6. For approvable items, output the exact posting command (DRY RUN form) into the packet:
   `python scripts/qbo_create_sandbox_bill.py --vendor "<exact>" --item "<code>" --amount <amt>
   --location "<loc>" --class "<cls>" --customer "<cust:job>" --docnumber <invoice-no>`
7. Log every review (`invoice_extracted`, `invoiceproof_packet` refs). Nothing posts from this
   prompt — posting happens in the approval session (06).
