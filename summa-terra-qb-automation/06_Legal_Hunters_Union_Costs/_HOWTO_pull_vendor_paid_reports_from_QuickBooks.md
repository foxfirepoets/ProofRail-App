# How to pull "actual cash paid" to Makers Line & Rich Development from QuickBooks

Goal: get the **confirmed amount paid** (checks actually cut) to each contractor, per entity — to replace the "billed" first-pass estimate.

## Step 1 — Open the right company file
Payments live in whichever entity cut the checks. Check these files, in order:
1. **12SB, LLC = "Hunter's Landing"** (the plain one) — this is THE Makers Line / Rich Development project. The legal evidence folder is literally "12SB – Hunter's Landing (Makers Line + Rich Development)." Lender = Canyon View CU. **Pull here first.**
2. **Union Walk / Union Station** — same entity, two names; the QB file may be named "Union Station." For Union's Makers Line / Rich Development payments.
3. **Hunters Landing North (HLN) = "Hunter's Landing North, LLC"** — a SEPARATE Utah entity (lender = Arixa), NOT the same as 12SB. Check only to confirm whether any Makers Line / Rich Development work touched it; it may be a different scope entirely.
4. **STV Development Group (STDG)** — only if the vendors aren't in the project files

> ⚠️ **Entity naming (confirmed against Adam's `GS-2026_Monthly Financial Process_Project Entities` sheet, 2026-06-26):** 12SB ("Hunter's Landing") and HLN ("Hunter's Landing North") are TWO different legal partnerships with different lenders — do not merge them. Union Walk and Union Station are ONE entity.

Switch files: **File → Open or Restore Company → Open a company file** (or **File → Open Previous Company**).
Confirm: **Vendors → Vendor Center** → look for "Makers Line" and "Rich Development" in the list.

## Step 2 — Run the report (per vendor, per file)
1. **Reports → Vendors & Payables → Transaction List by Vendor**
2. **Dates = All**
3. **Customize Report → Filters**
4. Filter **Name = Makers Line** (run again later for **Rich Development**)
5. Filter **Transaction Type → Multiple → check Bill Payment + Check** (+ Credit Card Charge if used). This leaves only money actually paid out.
6. **OK** → the **bottom total = cash actually paid**.

(To compare billed vs paid, add **Bill** to the transaction types: Bills = invoiced, Bill Payments/Checks = paid.)

Fast alternative: **Vendor Center → click vendor → Show: All Transactions, Date: All → QuickReport**.

## Step 3 — Save & send
No Excel on the VPS, so: **Print → Save as PDF**. Save into:
`I:\My Drive\ACCOUNTING - PC FILES\QB-MISC\Q2_2026_Catchup_Intake`
Name clearly: `MakersLine_PAID_HLN.pdf`, `RichDev_PAID_HLN.pdf`, `MakersLine_PAID_UnionWalk.pdf`, etc.

Then tell Claude — they'll total them and produce confirmed cash-paid figures by entity.

_Note: this is the authoritative "paid" source even while the QB monthly catch-up is in progress, because vendor payments (checks) are recorded when entered regardless of reconciliation status. Still confirm the file is reasonably current for the period in question._
