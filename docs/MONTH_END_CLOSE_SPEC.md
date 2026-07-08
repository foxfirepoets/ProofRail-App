# MONTH_END_CLOSE_SPEC — Co-work month-end close (test-build scope: sandbox rehearsal of the real cycle)

Prompt: `cowork_prompts/09_MONTH_END_CLOSE.md`. Output: a close packet per entity in
`12_Month_End_Close/{YYYY-MM}/`. Every checklist line is binary; anything not green becomes a
written exception. Nothing is "mostly done."

## Checklists

**1. Bank rec (per entity with a bank account)**
- [ ] statement on file (`{YYYYMM}_{ENTITY}_{BANK}_{last4}_stmt.pdf`) — chase via Missing-Docs if absent
- [ ] statement ending balance ties to QBO bank account balance (per Location)
- [ ] outstanding items listed with age; >30d items are exceptions
- [ ] no-feed banks (STDG MACU/Granite, STVE) — no bank import exists, so Co-work enters the txns
      itself from the statement PDF/CSV (pdf-mastery), then reconciles; it never invents a feed and
      never hand-waves a missing statement (chase via Missing-Docs). "No feed" ≠ "a human keys it."

**2. Credit card rec** — same pattern per card; unmatched charges need support (Missing-Docs chase).

**3. Loan rec (per lender per entity)**
- [ ] lender statement filed (entity Loans folder) · [ ] principal balance ties to loan liability account
- [ ] interest/fees booked to `CIP - Financing Costs` (or per CPA guidance) · [ ] draw activity ties to draw log
- [ ] retainage withheld ties to `GC Retainage Payable` per project

**4. Intercompany**
- [ ] `Due To Corp:X` (A) ↔ `Due From Projects:X` (B) mirror pairs NET TO 0.00 across realms, per entity
- [ ] `IC Clearing` (10000) reads 0.00 per class in both realms
- [ ] `Dev Fee Receivable` (B 12200) ties to the sum of A-side fee payables
- any non-zero mirror = exception with the pair's transaction lists attached

**5. Developer fee review**
- [ ] per entity: 5% × fee base per OAEA vs booked (A payable / B income) — penny-exact
- [ ] entities without a verified fee clause: NOTHING booked (list them)
- [ ] commissions: confirm ZERO commission postings anywhere in Realm A; Realm B accrual only if
      Ben has confirmed rates/recipients in writing (currently: he has not — must be zero)

**6. Vendor bills awaiting approval** — 05/07 queues empty or aging-explained; any 07 item
without a 09 receipt >24h = exception.

**7. Missing coding** — every posted transaction carries Location+Class+Customer+Item (report by
Location; "Not Specified" column must contain only pre-existing sample data — in production: nothing).

**8. Uncategorized transactions** — Uncategorized Asset/Income/Expense accounts read 0.00.

**9. AP/AR review** — AP aging ties; AR (B: fee invoices) aging reviewed; nothing >60d without a note.

**10. Close packet (per entity, PDF into `12_Month_End_Close/{YYYY-MM}/`)**
BS by Location + P&L by Location (+ BvA when budgets exist) · rec summaries 1–4 · fee review 5 ·
exception list with notes · audit-log extract for the month (JSONL slice) · optional AuditProof
seal: `POST /api/verify` `task:"audit_proof"` with the close summary; store `proof_id` +
`chain_hash` in the packet and audit log.

## Order of operations
statements in → recs 1–3 → intercompany 4 → fees 5 → queues 6 → coding sweeps 7–8 → AP/AR 9 →
packet 10 → Ben sign-off (recorded approval) → month tagged closed in the audit log.
