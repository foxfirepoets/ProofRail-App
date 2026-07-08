# HOURLY INBOX RUN — paste each working hour (or when Ben says "inbox run")

Process new mail per `docs/GMAIL_AUTOMATION_SPEC.md`:

1. Search: `in:inbox newer_than:2d -label:ProofRail/Processed -label:ProofRail/DoNotPost`.
2. For each thread: classify (INVOICE/DRAW_SHEET/LIEN_WAIVER/INSPECTION/LENDER_DOC/BANK_NOTICE/
   VENDOR_INQUIRY/LENDER_CORRESPONDENCE/APPROVAL/OTHER) and apply the matching ProofRail label.
3. Attachments: run `python scripts/classify_attachment.py --file "<name>" --subject "<subj>"
   --from "<sender>"` — follow its routing verbatim. `do_not_post:true` = HARD STOP → label
   `ProofRail/DoNotPost`, file to `14_Do_Not_Post`, log, done with that item.
4. Save attachments to Drive per the folder spec (label ↔ folder 1:1, filename law). Dedupe
   by message-id + sha256.
5. INVOICE items: extract vendor/invoice-no/amount/due-date/coding candidates, then build the
   packet: `python scripts/build_invoiceproof_packet.py --vendor "<exact>" --invoice-no <no>
   --amount <amt> [--line-items-total <n>] [--po <po>] --project "<cust:job>" --location
   "<loc>" --class "<cls>" --item "<code>" --source "gmail:<msgid>" [--send]`
   PASS → approval packet in `05_Pending_Approval` · FLAG → same, marked NEEDS OVERRIDE REASON ·
   FAIL → `ProofRail/Quarantined` + `10_Exceptions`.
6. DRAW_SHEET items: run the draw workflow (`03_DRAW_REVIEW.md` steps) or queue it and say so.
7. BANK_NOTICE: label `ProofRail/Risk-BankChange`, open an exception REQUIRING out-of-band
   phone verification to the number on file. Never update anything from the email. Never reply.
8. APPROVAL replies (Mike/Zach): match to the pending item; record via append_audit_log
   (`--approval approved --approver <email> --source gmail:<msgid>`); move packet to
   `06_Approved_For_QBO`.
9. Drafts (never send): missing-doc requests, acknowledgments, aging follow-ups.
10. Apply `ProofRail/Processed` ONLY where save + filing + logging ALL succeeded.
11. Report: table of items processed (class, source, action, verdict), drafts created,
    exceptions opened. Log one `intake_classified` event per item and a run summary.
