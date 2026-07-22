# STV Variance Booking Sheet — Cover Note

**Summa Terra Ventures — QuickBooks Journal-Entry Booking Sheet**
**Bank-Reconciliation Variance Fixes**

**Date:** 2026-06-24

> **PREPARED FOR HUMAN REVIEW — nothing has been posted to QuickBooks.**

## Purpose

This packet documents the journal entries required to correct four verified
bank-reconciliation variances across the Summa Terra Ventures (STV) project
entities. Each entry is staged on the accompanying CSV
(`STV_Variance_Booking_Sheet.csv`) ready for a reviewer to post to QuickBooks.
The total ready-to-post amount (excluding the JE9 HOLD item) is **$3,840.31**.

## Assumptions

- All amounts have been **independently verified** against the 2026 Bank
  Reconciliation workbook **and** the bank-transaction dataset.
- **Root cause:** these are fees that **cleared the bank but were never posted
  in QuickBooks** (the QB register was frozen).
- Each fix **debits an expense account and credits the project's bank account**.
- **JE7 is a refund reversal:** debit bank, credit the original expense account.

## Variance Subtotals

| Entity | Subtotal |
| --- | --- |
| Freeman Ranch | $535.81 |
| Ventura Landing | $1,522.50 |
| RM Texas Partners (net: 1,000 − 18) | $982.00 |
| Rock Creek | $800.00 |
| **Total ready-to-post (excludes JE9 HOLD)** | **$3,840.31** |

## Items Needing a Source Document / Confirmation

- **JE4 — Check 262 clear date** (Ventura Landing): confirm the actual bank-clear
  date before posting.
- **JE5 — Ventura Capitol Services true 2026 date:** workbook cell shows
  **9/12/2025** (likely a copy error; true period is 2026). Fix the date before
  posting.
- **JE7 — exact original expense account** for the $18 refund (Development Costs –
  Recording Fees): confirm the original expense account credited.
- **JE9 — Rock Creek second $800 check image** (fitid 2daa1928…): **possible
  duplicate**. Pull the check image and **verify it is not a duplicate** before
  posting. If it is a duplicate CPA payment, initiate stop-payment/recovery.

## Separate PENDING Item (NOT on This Sheet)

- **HLN Arixa "Ask My Accountant" $317,137.06 plug** — awaits the Arixa
  **10/18/2024 settlement statement**. **Do NOT clear to expense.** This is a
  balance-sheet reclass to be handled per CPA guidance.
