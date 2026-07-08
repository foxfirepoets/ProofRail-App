# MONTH-END CLOSE — paste at month end (multi-session; keep a running checklist)

Close month: **[Ben: YYYY-MM]**. Follow `docs/MONTH_END_CLOSE_SPEC.md` in order; every line is
binary; anything not green becomes a written exception in `10_Exceptions`.

1. Statements: confirm every entity's bank/CC/loan statement is filed (chase via Missing-Docs).
2. Bank recs per entity (per Location) → statement balance ties to QBO. Manual banks: verify
   Ben's entries, don't invent.
3. Credit card recs. 4. Loan recs (principal ties, interest booked, retainage ties).
5. Intercompany: Due To Corp:X ↔ Due From Projects:X nets 0.00 per entity across realms;
   IC Clearing reads 0.00 per class; Dev Fee Receivable ties to A-side payables.
6. Developer fee review (run 08_DEV_FEE_MONITOR if not done this cycle).
7. Approval queues: 05/07 empty or aging-explained; 07-without-09-receipt >24h = exception.
8. Coding sweep: BS + P&L by Location (`qbo_read_report_by_location.py`) — "Not Specified"
   must hold only pre-existing sandbox sample data; uncategorized accounts read 0.00.
9. AP/AR aging review.
10. Close packet per entity into `12_Month_End_Close/{YYYY-MM}/`: BS + P&L by Location,
    rec summaries, fee review, exception list with notes, audit-log extract. Optional: seal the
    close summary via SwarmSync (`task:"audit_proof"`) and record proof_id + chain_hash.
11. Present the packet to Ben; on his recorded sign-off, log `close_step: month closed`.

Report progress as a checklist table after each session so the close can resume cleanly.
