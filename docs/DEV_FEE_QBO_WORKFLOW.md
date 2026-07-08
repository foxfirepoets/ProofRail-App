# DEV_FEE_QBO_WORKFLOW — the 5% developer fee, two realms, exact sandbox tests

## The rule (from the OAEAs via the frozen spec — DOCUMENTS = LAW)

- The partnership owes **only** the 5% developer/CM fee to STV CM, LLC (universal payee per the
  7-2-26 OAEA refresh). Fee base varies per OAEA (12SB excludes land). **No EntityRegistry/OAEA
  row → no fee — refused, never estimated.**
- **Realm A (partnership)** books the fee PAYABLE side only. **NEVER any commission expense or
  payable in Realm A — for Watson, Coverston, Christensen, or anyone. The accounts don't even
  exist there, by design (the verify script asserts their absence).**
- **Realm B (parent)** books the fee INCOME side: `Developer Fee Income` (40200), Location
  `15 STV CM`.
- Commissions are parent-side only. Rates/recipients **RESOLVED by Ben 2026-07-06** (this
  supersedes the earlier "Zach 3%" worksheet reading — Zach is 2%, not 3%):
  - Mike Watson **2%** → `Comm Payable - Watson (2%)` 21100 / `CEO Commission Expense (2%)` 60200
  - Zach Coverston **2%** → `Comm Payable - Coverston (2%)` 21300 / `Commission Expense - Coverston (2%)` 60400 (added 2026-07-06 via `qbo_add_commission_coverston.py`)
  - Porter Christensen **1%** → `Comm Payable - Christensen (1%)` 21200 / `Pres Commission Expense (1%)` 60300
  The three account pairs now EXIST in Realm B, but **no commission is booked automatically**.
  Each commission posting is a separate owner-approved action (Ben approves + `--execute-sandbox`),
  class `90 Parent Overhead`. `qbo_create_dev_fee_test.py` still has NO commission code path — the
  dev-fee flow never books a commission. OPEN FOLLOW-UP: if commissions are paid via Bills to a
  member-vendor, Realm B currently has vendors only for Watson and Christensen (EXEC vendors) — a
  vendor for Zach Coverston would need to be added before a Bill-based commission payment.

## Realm A mechanics (fee payable)

Bill · Vendor `IC - STV CM` · Item `FEE-DEV` (→ `CIP - Dev Fee Capitalized` 15500) ·
Location = entity · Class = phase · Customer = project:phase · amount = round(base × 0.05, 2).
COA law: **capitalized dev fee NEVER for 12SB / Summa Elite** (script refuses those entities);
expensed treatment (60100 Developer Fee Expense) is a CPA judgment — present options, never decide.

## Realm B mechanics (fee income)

Invoice · Location `15 STV CM` · Class `90 Parent Overhead` · line item mapped to
`Developer Fee Income` (40200) · same amount, same DocNumber → the pair must tie to the penny.
(Realm B has no seeded customers/items, so the test script idempotently creates clearly-marked
fixtures: customer `SBX TEST - {entity} (IC)`, item `SBX TEST Dev Fee Income`.)
Cross-realm law: `Dev Fee Receivable` (B 12200) mirrors the A-side payable; IC mirrors must net
0.00 — checked at month-end.

## Exact sandbox test cases

```bash
# T1 — happy path (Madison, base $306,140.60 -> fee $15,307.03, the Draw 6 canonical number)
python scripts/qbo_create_dev_fee_test.py --entity Madison --base 306140.60 \
  --location-a "04 Madison Park" --class-a "40 Vertical" --customer-a "Madison West" \
  --docnumber DEVFEE-TEST-MADISON-D6 --execute-sandbox
# PASS = Realm A Bill 15307.03 + Realm B Invoice 15307.03, tie check PASS, commissions_booked=false

# T2 — pair-tie audit: rerun T1 (same docnumber) -> deterministic RequestId, no double-post
# T3 — forbidden entity: --entity 12SB ... -> REFUSED before any API call
# T4 — no-registry entity: --entity Carlo (no verified fee clause) -> operator must NOT run it;
#      Co-work refuses to prepare the packet (no OAEA row -> no fee)
# T5 — commission guard: grep the audit log after T1: commissions_booked must be false
#      (the dev-fee flow books NO commission — rates are confirmed, but accrual is a separate
#      owner-approved posting, never part of this flow).
# T6 — partnership-commission canary: qbo_verify_setup_counts.py asserts 'Comm Payable - Watson (2%)'
#      (and Coverston/Christensen) exist ONLY in Realm B (cross-realm bleed check)
# T7 — partial-pair drill (PR-020): if Realm B leg ever fails, script prints/logs the
#      compensating action (void the Realm A bill manually in the UI) — verify the message
```

Verification after T1: `python scripts/qbo_read_report_by_location.py --realm A` shows
15,307.03 under `04 Madison Park`; `--realm B` shows 15,307.03 under `15 STV CM`.
