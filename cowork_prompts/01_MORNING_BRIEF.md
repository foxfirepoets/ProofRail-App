# MORNING BRIEF — paste first thing each day (after 00_MASTER_OPERATOR_PROMPT if new session)

Run the Morning Brief:

1. Gmail sweep (read-only): count new mail since yesterday's summary by class
   (INVOICE/DRAW_SHEET/BANK_NOTICE/APPROVAL/…), list anything in `ProofRail/Quarantined`,
   `ProofRail/Risk-BankChange` (verbatim subjects), and `ProofRail/Action` older than 3 days.
2. Queues: list `05_Pending_Approval` items (age, amount, verdict), `07_QBO_Sandbox_Handoff`
   items not yet posted, and any 07 item without a `09_QBO_Results` receipt in >24h (exception!).
3. Exceptions: every folder in `10_Exceptions` with age and one-line status.
4. Yesterday: read the last `daily_summary` event in `logs/cowork_audit_*.jsonl` and report
   postings made (QBO IDs), proof pass rate, anything carried over.
5. Intake heartbeat: if no mail was processed on the last business day, say so LOUDLY.
6. Money watch: any bank-change requests pending out-of-band verification (these never wait silently).
7. End with: "Today I recommend: [1–3 items, each citing its source]" — then wait for Ben.

Log the brief: `python scripts/append_audit_log.py --actor cowork --event-type daily_summary
--source "local:morning-brief" --summary "<one-line stats>"`.
