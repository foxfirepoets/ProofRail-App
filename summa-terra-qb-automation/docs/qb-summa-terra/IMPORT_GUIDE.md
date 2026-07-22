# QuickBooks Enterprise — Import Guide (Summa Terra new layout)

These files load the **new layout** (Chart of Accounts, Classes, the draw-schedule Items 001–069 with the
corrected fee split, Draw #29 Vendors, and the Hunter's Landing Customer:Job) into QuickBooks Enterprise
**Desktop**. Companion to `SPEC.md` §19. Generated from the spec + the real *Hunters Landing Draw #29*.

## Which file to use

| Format | File | Loads | Best for |
|--------|------|-------|----------|
| **IIF** (recommended — one upload, no column mapping) | **`QB_Import_Partnership_Template.iif`** | Accounts + Classes + Items + Vendors + Customer:Jobs for a **partnership** file | Building the **locked template** / each entity |
| **IIF** | **`QB_Import_Parent_SummaTerra.iif`** | Parent-only accounts (fee income, commissions), Classes, parent fee Items, EXEC vendors | The **Summa Terra parent** file |
| **CSV** (Excel-openable; for review or the Excel import wizard) | `CSV_*.csv` | Same data, one list per file | Reviewing in Excel, or importing Items/Vendors/Customers via the wizard |

> **IIF is the format that "auto-updates everything" in one shot.** QuickBooks Desktop has no native CSV
> importer for the Chart of Accounts or Classes — only Items/Vendors/Customers go through the CSV/Excel
> wizard. So use the **IIF** files to load the full layout; the CSVs are for review and for the lists the
> wizard supports.

## Before you import (required)

1. **BACK UP the company file** (File → Back Up Company). IIF import cannot be undone except by restore.
2. Turn on the two preferences the layout depends on, **before** importing:
   - Edit → Preferences → **Accounting** → Company Preferences → **Use account numbers** ✅ (so the 5-digit
     numbers in the `ACCNUM` column land).
   - Edit → Preferences → **Accounting** → **Use class tracking** ✅ (and "Prompt to assign classes").
3. Do this on a **fresh / template** file first, validate, then clone it per entity.

## Import procedure (IIF)

1. **File → Utilities → Import → IIF Files.**
2. Choose `QB_Import_Partnership_Template.iif` (or the Parent file). Confirm.
3. QuickBooks reads the sections **in order — Accounts first, then Classes, then Items** — so every Item's
   account already exists when the Item loads (referential integrity verified: 0 orphan references).
4. Review the import results dialog. Then spot-check Lists → Chart of Accounts / Item List / Class List.

The two `.iif` files each contain all five lists in one file, so it is **two uploads total** (one per file
type), not ten.

## What imports automatically vs. what you set up by hand

**✅ Auto-imported by the IIF:**
- Chart of Accounts (numbered, typed, with descriptions) — 36 accounts (partnership) / 22 (parent).
- Class list (10 development phases).
- Items 001–069 + lifecycle items + the fee/retainage Items, each mapped to one CIP bucket — 68 (partnership)
  / 3 (parent).
- Vendors (44 Draw #29 payees + GC/Lender/IC on the partnership; EXEC on the parent).
- Customer:Job (Hunter's Landing + phase jobs).

**✋ Must be set up manually in QuickBooks (IIF cannot carry these):**
1. **Custom fields** — define `Draw #`, `Approval ID`, `Fee Eligibility` (Lists → templates / "Define Fields"
   on Names & Items). These power the Draw Package (`SPEC.md` §6.7) and the Draw vs. Fee Reconciliation.
2. **Fee percentages** — open the fee Items and set the rate: `FEE-DEV` = **5%**, `FEE-DEV-INC` = **5%**,
   `FEE-CEO` = **2%**, `FEE-PRES` = **1%** (IIF imports them at 0; the % is entered in QB).
3. **Memorized transactions** (the anti-leakage engine — `SPEC.md` §12.4): build once, then memorize:
   - Partnership: a **Bill** from `IC - Summa Terra Ventures`, line = `FEE-DEV` (5% of draw total).
   - Parent: **"Developer Fee Income"** entry (Dr Due-From / Cr Developer Fee Income) and **"Executive
     Commissions"** (Dr `FEE-CEO`/`FEE-PRES` expense / Cr the two Commission Payables).
4. **Opening balances** — enter per the validated trial balance (`SPEC.md` §13 step 10); not in these files.
5. **Memorized report pack** — build the §16.1 reports once and memorize them.

## CSV / Excel wizard (alternative for Items, Vendors, Customers)

File → Utilities → Import → **Excel Files** → choose the list type → map columns to the matching
`CSV_*.csv` headers. Use this only if you prefer the wizard for those three lists; **Accounts and Classes
still come from the IIF.**

## Cloning per entity

The partnership IIF is written for **Hunter's Landing** as the pilot. For each additional entity, after import:
rename `Due From - Summa Terra Ventures` / `Due To - Summa Terra Ventures` if you track per-counterparty, set
the entity's Customer:Job, and set opening balances. Everything else (COA, Classes, Items) is identical by
design — that is what makes onboarding ≤ 2 hours (`SPEC.md` §11.5).

## Validation performed (offline)

These files were run through a validator that encodes QuickBooks' **documented list-import rules** — the
closest proxy to a live import without QuickBooks installed. Both files **PASS, 0 issues**:

| Check | Result |
|-------|--------|
| Tab-delimited; every row's column count matches its `!` header | ✅ |
| Valid account-type keywords (BANK/OCASSET/AP/INC/EXP/…) | ✅ |
| Valid item-type keywords (NONINV/SERV/OTHC) | ✅ |
| **List-name length ≤ 31 chars** (QB's hard limit; > 31 is rejected/truncated) | ✅ (19 names were abbreviated to comply) |
| Vendor/Customer names ≤ 41; job parent exists | ✅ |
| Referential integrity — every Item's account exists (0 orphans) | ✅ |
| No duplicate names within a list | ✅ |
| ASCII-only (no smart quotes/em-dashes that corrupt IIF) | ✅ |

**Name abbreviations (to meet the 31-char limit):** a few accounts/items are shortened in the import files
vs. the prose in `Chart_of_Accounts.md` / `Cost_Codes_and_Items.md` — the **number still carries identity**.
Examples: `Construction Loan Funding` (10200), `Dev Fee Payable - Summa Terra` (21000), `Comm Payable -
Watson (2%)` (21100), `Dev Fee Receivable (Due-From)` (12200), `068 Construction Profit (GC)` (the
"GC builder profit — not the dev fee" clarifier moved to the item Description). Rename to taste in QB **after**
import if you prefer longer labels (they're no longer constrained by the IIF importer once loaded).

**What this validation does NOT prove** (only a live import can): that your specific QB **version/edition**
accepts every type mapping; behavior if a list **name already exists** in the target file (IIF updates vs.
duplicates); and that **account-numbering/class preferences** were enabled first. Always do the first import
on a **backup or the QB sample company** and read the import-results log.

## Verification after import (quick)

- Chart of Accounts shows the four CIP buckets (15200/15300/15400/15500) + 15100 Land.
- Item `068 Construction Profit` maps to **CIP - Soft Costs** (it is the GC's profit, **not** the 5% fee).
- **Partnership file:** no `Commission` accounts except sales (50200); no Watson/Christensen. Exec commissions
  are parent-only (verified in the generated files).
- Item count: 68 (partnership) / 3 (parent). Class count: 10.
