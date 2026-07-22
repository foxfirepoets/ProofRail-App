# Proposed Chart of Accounts — Summa Terra Ventures (Deliverable 2)

Companion to `SPEC.md` §6.1. This COA ships **inside the locked template** and is **identical in every
partnership file** (parent has a few extra overhead/income accounts, flagged below). Numbering is enabled.

**Design rules (do not violate):**
- **No GL account per project.** Project detail comes from Customer:Job; cost-code detail from Items.
- CIP/development costs are a **balance-sheet asset** with *group-level* subaccounts only (four buckets:
  Land, Soft, Hard, Financing + a fifth, Developer-Fee-Capitalized). All draw-line detail (concrete vs.
  steel vs. supervision) lives in the **Item**, never in a new account (`Cost_Codes_and_Items.md`).
- Keep the list lean — every account below earns its place. **This COA is intentionally NOT expanded for the
  draw schedule;** the draw's 001–069 lines are Items that roll into these broad CIP buckets.

**Fee split (corrected — load-bearing):** A partnership books **only the 5% developer fee** (`15500`/`60100`
Dr, `21000` Due-To Summa Terra Cr). The **2% CEO + 1% President commissions are PARENT-ONLY** (`60200`/`60300`
Dr, `21100`/`21200` Cr) — Summa Terra pays them *after* it earns the fee. Commission accounts must **never**
exist in a partnership file. See `SPEC.md` §12.4.

**Legend — File:** P = Parent only · T = Partnership (template) · B = Both.
**Stmt:** BS = Balance Sheet · PL = Profit & Loss.
**Job?** = project/Customer:Job coding required. **Fee?** = affects 5% developer-fee base.

| # | Account | Type | File | Stmt | Job? | Fee? | Purpose / Example |
|---|---------|------|------|------|------|------|-------------------|
| **10000** | **Cash & Bank** | | | | | | |
| 10100 | Operating Bank | Bank | B | BS | – | – | Day-to-day operating cash |
| 10200 | Construction Loan Funding Account | Bank | T | BS | – | – | Draw proceeds land here |
| 10300 | Reserve / Interest Reserve | Bank | T | BS | – | – | Lender-required reserves |
| 10400 | Escrow | Bank | T | BS | – | – | Closing/escrow holds |
| 10500 | Credit Card Clearing | Credit Card | B | BS | – | – | Card activity |
| **12000** | **Receivables** | | | | | | |
| 12100 | Accounts Receivable | A/R | B | BS | yes | – | Customer/draw billings |
| 12200 | Developer Fee Receivable / Due-From Partnership | Other Current Asset | P | BS | – | yes | **Parent** records the 5% owed by the partnership |
| 12500 | Due From — <Counterparty> | Other Current Asset | B | BS | – | – | Intercompany asset leg (one per counterparty) |
| **15000** | **Construction in Progress / Development Costs** | | | | | | |
| 15100 | CIP — Land & Acquisition | Other Current Asset | T | BS | yes | * | Land + acquisition (Items carry detail) |
| 15200 | CIP — Soft Costs | Other Current Asset | T | BS | yes | * | A&E, entitlements, legal, etc. |
| 15300 | CIP — Hard Costs | Other Current Asset | T | BS | yes | yes | Site, concrete, framing, MEP, etc. |
| 15400 | CIP — Financing Costs | Other Current Asset | T | BS | yes | * | Interest, loan fees, carry |
| 15500 | CIP — Developer Fee Capitalized | Other Current Asset | T | BS | yes | – | Partnership books the **5%** here (capitalize if CPA confirms; else expense to 60100) |
| **17000** | **Fixed / Other Assets** | | | | | | |
| 17100 | Completed Real Estate (placed in service) | Fixed Asset | T | BS | yes | – | When CIP is completed |
| 17900 | Accumulated Depreciation | Fixed Asset (contra) | T | BS | – | – | If held for rental |
| **20000** | **Liabilities** | | | | | | |
| 20100 | Accounts Payable | A/P | B | BS | yes | – | Vendor bills |
| 20200 | GC Retainage Payable (holdback) | Other Current Liability | T | BS | yes | – | If contracts use retainage |
| 20300 | Accrued Expenses | Other Current Liability | B | BS | – | – | Period-end accruals |
| 21000 | Developer Fee Payable / Due-To Summa Terra | Other Current Liability | T | BS | – | yes | Partnership owes parent the **5% only** (the partnership's whole fee obligation) |
| 21100 | Commission Payable — Mike Watson (CEO 2%) | Other Current Liability | **P only** | BS | – | yes | Parent owes CEO **after** it earns the fee — never on a partnership file |
| 21200 | Commission Payable — Porter Christensen (Pres 1%) | Other Current Liability | **P only** | BS | – | yes | Parent owes President — never on a partnership file |
| 22000 | Construction Loan Payable | Long Term Liability | T | BS | – | – | Lender principal |
| 22500 | Due To — <Counterparty> | Other Current Liability | B | BS | – | – | Intercompany liability leg (one per counterparty) |
| 23000 | Draw Liability / Unearned Draw | Other Current Liability | T | BS | – | – | Draws received not yet costed (if applicable) |
| **30000** | **Equity** | | | | | | |
| 30100 | Partner Capital — <Partner> | Equity | T | BS | – | – | One per partner (capital accounts) |
| 30200 | Investor Contributions | Equity | T | BS | – | – | Capital in |
| 30300 | Distributions | Equity | T | BS | – | – | Capital out to partners |
| 30900 | Retained Earnings | Equity | B | BS | – | – | Accumulated |
| **40000** | **Income** | | | | | | |
| 40100 | Sale Proceeds | Income | T | PL | yes | – | Lot/unit/property sales |
| 40200 | Developer Fee Income | Income | P | PL | – | yes | Parent recognizes 5% |
| 40300 | Management Fee Income | Income | P | PL | – | – | Other mgmt-co income |
| 40400 | Reimbursement Income | Income | P | PL | – | – | Cost reimbursements |
| 40900 | Other / Rental Income | Income | T | PL | yes | – | Interim rental |
| **50000** | **Cost of Sales** | | | | | | |
| 50100 | Cost of Real Estate Sold | COGS | T | PL | yes | – | CIP relieved at sale |
| 50200 | Closing Costs / Commissions on Sale | COGS | T | PL | yes | – | Selling costs |
| **60000** | **Project-Related Operating (parent recognizes commissions here)** | | | | | | |
| 60100 | Developer Fee Expense (partnership) | Expense | T | PL | yes | – | Only if the 5% is expensed instead of capitalized to 15500 |
| 60200 | CEO Commission Expense (2%) | Expense | **P only** | PL | – | yes | Parent expenses CEO comp (paid from the fee it earns) |
| 60300 | President Commission Expense (1%) | Expense | **P only** | PL | – | yes | Parent expenses President comp |
| **70000** | **Parent Overhead / Operating Expenses** | | | | | | |
| 70100 | Salaries & Wages | Expense | P | PL | – | – | Mgmt-co payroll (allocated by Class) |
| 70200 | Office / Software / Rightworks | Expense | P | PL | – | – | G&A |
| 70300 | Professional Fees (CPA/Legal) | Expense | B | PL | – | – | Outside services |
| 70400 | Insurance | Expense | B | PL | yes | * | Allocate to projects where direct |
| 70500 | Property Taxes | Expense | T | PL | yes | * | Carry cost |
| 70600 | Interest Expense | Expense | T | PL | yes | * | Loan interest (if expensed) |
| 70700 | Marketing | Expense | B | PL | yes | – | Project + corporate |
| **80000** | **Other** | | | | | | |
| 80100 | Other Income / Expense | Other | B | PL | – | – | Non-operating |

`*` The **fee base is the approved Draw Package total** (confirmed), so the 5% is computed on the whole
package, not per cost line — the per-account `Fee?` flag is informational only. Non-draw costs (insurance,
taxes, interest) are outside the draw and therefore outside the fee base. See `Cost_Codes_and_Items.md` §4.

**Subaccount discipline:** CIP subaccounts stop at the *group* level (Land/Soft/Hard/Financing). All finer
detail (concrete vs. framing vs. permits) lives in the **Item** dimension, never in new accounts.
