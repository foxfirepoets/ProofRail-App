# Sandbox Seed Opening-Balance Journal Entry

Per `spec-qb-sandbox-environment-2026-07-01.md` §5 step 7 / §6: the sandbox file must NOT contain real historical
transaction data. This is a single, synthetic, balances-to-zero journal entry — entered manually in QuickBooks
(`Company > Make General Journal Entries`) — purely so the sandbox has *some* non-zero balances to exercise
reporting/reconciliation logic during Spec B's E2E testing. It is not a reconstruction of any real STV history.

**This step is manual QuickBooks GUI work.** No CSV/IIF import mechanism applies to journal entries in this
workflow — enter it directly in the sandbox file.

## Entry

| Line | Account | Class | Customer:Job | Debit | Credit | Memo |
|---|---|---|---|---|---|---|
| 1 | 10200 Construction Loan Funding | (none) | (none) | $10,000.00 | | Sandbox seed — synthetic opening balance, not real STV data |
| 2 | 15300 CIP — Hard Costs | 10 Site & Excavation | HL Hunter's Landing | | $10,000.00 | Sandbox seed — synthetic opening balance, not real STV data |

**Date:** Use the date the sandbox file is created (do not backdate to mimic a real period).

**Verification after entry:**
- [ ] Trial balance for the sandbox file shows the $10,000.00 as the only non-zero balances.
- [ ] `File > Utilities > Verify Data` completes with no integrity errors.
- [ ] This JE is clearly labeled in the memo field so it is never mistaken for a real transaction if the file is
      ever reviewed by someone unfamiliar with its purpose.

## Why this specific entry

- Exercises one CIP bucket (`15300 CIP — Hard Costs`) and one Class/Customer:Job combination, so Spec B's
  round-trip reconciliation test (Section 10, step 8) has at least one non-zero balance to diff against after a
  test `BillAdd` is posted.
- Deliberately small and obviously synthetic ($10,000.00, generic memo) so it can never be confused with a real
  STV draw amount.
