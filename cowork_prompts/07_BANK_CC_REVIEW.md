# BANK / CC REVIEW — paste after dropping bank/credit-card CSVs into 00_Inbox

Files in scope: **[Ben: list the CSV filenames, or "everything new in 00_Inbox"]**
Follow `docs/BANK_CC_AUTOMATION_SPEC.md`:

1. Rename each file to `{YYYYMM}_{ENTITY}_{BANK}_{last4}_stmt.csv` and confirm no full account
   numbers appear anywhere in your output (last-4 only).
2. Per transaction, attempt matches in priority order: vendor bill (exact → NEAR ±3d/cents) ·
   draw funding · loan activity · contribution/distribution (FLAG for Ben — judgment) ·
   intercompany mirror (both sides or exception) · recurring known · else UNMATCHED.
3. Suggest coding (Location/Class/Item) for matched rows WITH evidence; low confidence = FLAG.
4. Detect: duplicates · missing support (open Missing-Docs chases) · payee bank-detail changes
   vs history (Risk-BankChange protocol) · >2× trailing-average anomalies.
5. Output the approval packet to `05_Pending_Approval`: matched table (txn, match evidence,
   proposed coding), flags, unmatched list with candidates. Every row cites its CSV line.
6. NOTHING auto-posts. Posting candidates become commands only after Ben approves (session 06).
7. Log the import and each match decision. Manual-entry banks (STDG MACU/Granite, STVE): you
   reconcile what exists, you never invent entries.
