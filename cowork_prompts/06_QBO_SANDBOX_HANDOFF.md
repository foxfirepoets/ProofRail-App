# QBO SANDBOX HANDOFF (APPROVAL SESSION) — Ben initiates; postings happen ONLY here

Run the approval session per `docs/COWORK_OPERATOR_RUNBOOK.md` §5:

1. List every item in `06_Approved_For_QBO` and `05_Pending_Approval`, numbered, each with:
   what it is · amount · realm · proposed coding · InvoiceProof verdict · approval evidence on
   file (msgid) or MISSING · the exact command that would post it.
2. Wait for Ben's explicit line, e.g. `approved: 1, 3` (FLAG items additionally need his
   override reason in the same message — refuse without it, PR-002).
3. For each approved item, in order:
   a. Record the approval FIRST:
      `python scripts/append_audit_log.py --actor ben --event-type approval --approval approved
      --approver ben --source "<packet path>" --summary "<item> approved for sandbox posting"`
   b. Run the item's command DRY RUN, show the output.
   c. Run it again with `--execute-sandbox`. Report the QBO Id verbatim. If it errors, report
      the error verbatim and stop that item (never improvise a workaround mid-session).
   d. Write the receipt (QBO Id, RequestId, TotalAmt, audit-log ts) to `09_QBO_Results` and
      move the packet from 07 → done.
4. Verify: `python scripts/qbo_read_report_by_location.py --realm A` (and B if touched) —
   confirm the postings appear under the right Location columns.
5. Close the session with a table: item · approved by · QBO Id · tie/verify status. Log a
   session summary event. Anything not approved stays exactly where it was.

Reminders that override everything: sandbox only · no payments · no commissions anywhere
without Ben's written rate/recipient confirmation · partnership realm never books commissions.
