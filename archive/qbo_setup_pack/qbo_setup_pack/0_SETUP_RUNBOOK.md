# QBO Advanced Setup Runbook — from design (v5) to two live realms
One sitting per realm, in this exact order. Design source: COA v5 IIFs (never imported —
QBO cannot read IIF; this pack is their translation). Spec law: §9.1 + dimensional law §9.

## 0. Prerequisites
Two QBO Advanced companies (Realm A = "STV Projects Combined", Realm B = "Summa Terra
Ventures - Corporate"). Advanced is mandatory: Plus caps classes+locations at 40 combined;
Realm A alone carries 18 Locations + 5 Classes + growth.

## 1. Company settings (each realm, before any import)
Gear → Account and settings → Advanced:
- Categories → **Track classes ON**, warn me when a transaction isn't assigned, **One to
  each row in transaction**
- Categories → **Track locations ON**, Location label = **"Location"**
- Enable account numbers (Chart of accounts → Enable)
- Projects ON (Realm A)
- Intuit-AI policy per spec §9.15: suggestions ON, Project Management Agent auto-create OFF

## 2. CSV imports (Gear → Import data)
| Order | File | Realm | Notes |
|---|---|---|---|
| 1 | `1_COA_Partnership_REALM_A.csv` | A | 139 accounts; colon names create sub-accounts. A/R, A/P, Retained Earnings intentionally absent — QBO creates its own singletons; do NOT hand-create duplicates |
| 2 | `2_COA_Parent_REALM_B.csv` | B | 109 accounts; same rules |
| 3 | `3_Products_Services_REALM_A.csv` | A | 69 items (cost codes). Import AFTER COA so Expense Account matches resolve. All type=Service; map "I purchase this" to the listed account |
| 4 | `4_Vendors_REALM_A.csv` | A | 53 vendors incl. IC - STV CM + lenders |
| 5 | `5_Vendors_REALM_B.csv` | B | 3 (EXEC Watson, EXEC Christensen, Ricks & Co) |

## 3. API/manual seeding (no QBO UI bulk import exists for these)
Fastest path: Intuit QBO MCP in Claude Code against the sandbox (spec §12 policy —
DISABLE_DELETE=true), or ten minutes of manual entry:
| File | Realm | QBO object | Count |
|---|---|---|---|
| `6_Locations_REALM_A_API_SEED.csv` | A | **Department** (UI label "Location") | 18 — the legal entities |
| `7_Locations_REALM_B_API_SEED.csv` | B | Department | 17 — corporate family incl. 15 STV CM, 16 HLE |
| `8_Classes_REALM_A_API_SEED.csv` | A | Class | 5 cost phases |
| `9_Classes_REALM_B_API_SEED.csv` | B | Class | 1 (90 Parent Overhead) |
| `10_Customers_Projects_REALM_A_API_SEED.csv` | A | Customer + sub-customer (colon = parent:child) | 64 projects/phases |

## 4. Verify (the counts ARE the acceptance test)
Realm A: 139 imported accounts (+3 QBO-created singletons) · 18 Locations · 5 Classes ·
69 items · 53 vendors · 64 customers. Realm B: 109 accounts · 17 Locations · 1 Class ·
3 vendors. Then run: Balance Sheet with columns by Location — must render one column per
entity, all zeros. That empty-but-correctly-shaped report is the birth certificate.

## 5. What comes next (not this pack)
Opening balances arrive ONLY via obgen F5 (extract → map → emit via API → G5 tie-out →
proof). Never key opening balances by hand into these realms — the migration must be
provable to the penny or it didn't happen.

## Known translation choices (from IIF → QBO taxonomy)
BANK→Bank/Checking · OCASSET→Other Current Assets · LTLIAB→Long Term Liabilities/Notes
Payable · EQUITY→Partner's Equity (Distributions→Partner Distributions; Accum Dep→its own
detail type) · INC→Service/Fee Income · EXINC→Other Income. Detail types are QBO-mandatory
metadata with no Desktop equivalent — refine per account later if Ricks prefers; they do
not affect the gates.
