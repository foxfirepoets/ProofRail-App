# QBO_ADVANCED_SETUP_SPEC — Two-Realm Sandbox Setup (source of truth: `qbo Source Files/0_SETUP_RUNBOOK.md`)

QBO **Advanced** is mandatory (Plus caps classes+locations at 40 combined; Realm A alone carries
18 Locations + 5 Classes + growth). Sandbox targets:

| Realm | Company | Realm ID | Role |
|---|---|---|---|
| A | Partnerships Summa Terra Ventures Sandbox (renamed 2026-07-06; was "Advanced Sandbox Company US 0e8d") | 9341457403104290 | Partnership / Projects ("STV Projects Combined" design) |
| B | Parent- Summa Terra Ventures Sandbox (renamed 2026-07-06; was "Advanced Sandbox Company US ee68") | 9341457403104051 | Parent / Corporate ("Summa Terra Ventures - Corporate" design) |

## 1. Required company settings (each realm, BEFORE any import — QBO UI, manual)

Gear → Account and settings → Advanced:
1. Categories → **Track classes ON** · "Warn me when a transaction isn't assigned" ·
   assignment = **One to each row in transaction**
2. Categories → **Track locations ON**, Location label = **"Location"**
3. Chart of accounts → **Enable account numbers**
4. **Projects ON** (Realm A)
5. Intuit-AI policy (spec §9.15): suggestions ON; **Project Management Agent auto-create OFF**;
   no auto-post rules beyond payroll/BillPay matches. Intuit-AI output = hints, never truth.

## 2. Exact seed order (dependencies are real — do not reorder)

| # | What | Realm | Source file | Count | Why this order |
|---|---|---|---|---|---|
| 1 | Accounts (COA) | A | `1_COA_Partnership_REALM_A.csv` | 139 | everything references accounts |
| 2 | Accounts (COA) | B | `2_COA_Parent_REALM_B.csv` | 109 (+1 auto-parent, see note) | — |
| 3 | Products/Services | A | `3_Products_Services_REALM_A.csv` | 69 | items resolve Expense Account against COA |
| 4 | Vendors | A | `4_Vendors_REALM_A.csv` | 53 | needed before bill tests |
| 5 | Vendors | B | `5_Vendors_REALM_B.csv` | 3 | — |
| 6 | Locations (API: Department) | A | `6_Locations_REALM_A_API_SEED.csv` | 18 | legal entities |
| 7 | Locations (API: Department) | B | `7_Locations_REALM_B_API_SEED.csv` | 17 | corporate family incl. 15 STV CM, 16 HLE |
| 8 | Classes | A | `8_Classes_REALM_A_API_SEED.csv` | 5 | cost phases |
| 9 | Classes | B | `9_Classes_REALM_B_API_SEED.csv` | 1 | 90 Parent Overhead |
| 10 | Customers/Projects | A | `10_Customers_Projects_REALM_A_API_SEED.csv` | 64 | colon = parent:child hierarchy |

One command runs all ten in order: `python scripts/qbo_seed_all.py` (dry run) →
`python scripts/qbo_seed_all.py --execute-sandbox` (writes + auto-verification).

Rules encoded in the seeders:
- QBO cannot import IIF — the CSVs are the design translation; the API is the vehicle for
  steps 6–10 (no QBO UI bulk import exists for Locations/Classes/Customers).
- Colon account names create sub-accounts; parents are created before children.
- **Known exception:** Realm B row `Land Held for Sale:HLE` (13900) has no parent row; the
  seeder auto-creates parent `Land Held for Sale` (same type, no acct number) and logs it.
  Realm B live count is therefore 109 + 1 auto-parent = 110 seeded accounts.
- A/R, A/P, Retained Earnings are intentionally absent — QBO creates its own singletons;
  never hand-create duplicates.
- Idempotent: existing names are skipped ("exists"), nothing is updated, nothing is deleted.
- Intuit sandboxes ship WITH sample data (Craig-style records). Verification therefore checks
  "every expected name present," not raw totals; extras are reported, reviewed, never deleted.

## 3. Acceptance counts (the counts ARE the acceptance test)

- **Realm A:** 139 imported accounts (+QBO-created singletons) · 18 Locations · 5 Classes ·
  69 Items · 53 Vendors · 64 Customers/Projects
- **Realm B:** 109 accounts (+1 auto-parent) · 17 Locations · 1 Class · 3 Vendors

## 4. Verification steps

1. `python scripts/qbo_verify_setup_counts.py` — per-entity expected/found/missing/extras,
   account-number spot check, cross-realm bleed canaries, and the birth certificate:
   **Balance Sheet with columns by Location renders one column per entity** in each realm.
2. `python scripts/qbo_read_report_by_location.py --realm A` (and `--realm B`) to eyeball it.

## 5. Manual QBO UI checks (10 minutes, after seeding)

- [ ] Settings show Class + Location tracking ON with the right options (both realms)
- [ ] Chart of Accounts shows account numbers and the sub-account tree (spot: `Operating Cash:12SB`, `Due To Corp:Union`)
- [ ] Realm B: review auto-created parent `Land Held for Sale` (add acct number if Ricks prefers)
- [ ] Products & Services shows 69 Service items with correct purchase accounts (spot: `FEE-DEV` → CIP - Dev Fee Capitalized)
- [ ] All Lists → Locations: 18 (A) / 17 (B); Classes: 5 (A) / 1 (B)
- [ ] Customers (A): 64 with project:phase hierarchy (spot: `12SB Hunters Landing:Acquisition`)
- [ ] Detail types: QBO-mandatory metadata translated from the IIF design (BANK→Checking,
      EQUITY→Partner's Equity, INC→Service/Fee Income, etc.) — refine later if Ricks prefers;
      they do not affect the gates
- [ ] Sample-data extras exist (sandbox ships pre-seeded) — leave them; do not delete
- [ ] Opening balances: NONE (not part of this test; they arrive only via obgen F5 with tie-out proof)

## 6. Out of scope for this test build

Rightworks / QB Desktop Enterprise / Web Connector / IIF import · production realms ·
opening balances · payments of any kind.
