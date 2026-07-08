# DEV FEE MONITOR — paste per draw cycle or monthly

Follow `docs/DEV_FEE_QBO_WORKFLOW.md`:

1. Build the per-entity fee table: entity · OAEA fee base (VERIFIED bases only — cite the
   OAEA/registry source) · draws this period · 5% assessed fee · booked in Realm A (payable) ·
   booked in Realm B (income 40200 @ 15 STV CM) · variance.
2. Entities WITHOUT a verified fee clause (e.g., Carlo/EJH/Dominus/Camden/Rock Creek Acq until
   confirmed): list them as "NO OAEA ROW → NO FEE — refused" — never estimated.
3. Variances: any penny of difference between assessed and booked, or between the A and B legs,
   is a finding (Madison Draw 6 standard: billed 15,407.03 vs 5% = 15,307.03 → $100 flag).
4. Check `Dev Fee Receivable` (B 12200) ties to the sum of A-side fee payables; IC mirrors net 0.00.
5. Commission section (always, verbatim status): "Commissions are parent-side (Realm B) only.
   Rates confirmed by Ben 2026-07-06: Mike Watson 2% (21100/60200), Zach Coverston 2%
   (21300/60400), Porter Christensen 1% (21200/60300). Accounts exist; nothing booked
   automatically — each commission posting needs Ben's per-run approval. Class 90 Parent Overhead."
   Then confirm by inspection: ZERO commission postings in Realm A (accounts don't exist there),
   and in Realm B only commissions Ben explicitly approved this period.
6. Output: fee table + findings + (if Ben asks to true-up in sandbox) the exact
   `qbo_create_dev_fee_test.py` commands, DRY RUN shown. Log a `close_step` event with the table.
