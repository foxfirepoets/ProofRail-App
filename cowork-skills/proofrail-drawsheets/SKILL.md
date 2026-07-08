---
name: proofrail-drawsheets
description: Parse and reconcile STV general-contractor pay applications and draw sheets — identify the format (AIA G702/G703 xlsx from Concord Homes, Procore Prime Contract Invoice PDF from Elite Construction USA, legacy Rich Development invoice stacks), extract canonical lines, map GC cost codes to QB items via the GcCodeMap crosswalk, verify retainage rates and CM-fee math, track dual draw numbering, check change orders against the approved register, and feed reconcile_draw_sheet. Triggers - "draw sheet", "pay app", "pay application", "G702", "G703", "prime contract invoice", "reconcile this draw", "Arixa draw", any DRAW_SHEET classification in an Inbox Run.
---

# proofrail-drawsheets — the three GC grammars, decoded from live packages

A draw sheet is a claim about money. Your job: translate the GC's grammar into canonical
lines, then let physics (`reconcile_draw_sheet`) test the claim. Never reconcile what you
haven't correctly parsed; never guess a cost-code mapping (GcCodeMap or flag).

## 0. FORMAT DETECTION (always first)
| Signal | Format | GC / Projects |
|---|---|---|
| xlsx, "APPLICATION AND CERTIFICATE", G703 sheet, DD-SS-III codes | **AIA_G703** | Concord Homes — Madison Park (lender Arixa, fund control Phoenix Tide) |
| PDF, "Prime Contract Invoice – Fixed Lump Sum", numbered items, CO register pages | **PROCORE_PCI** | Elite Construction USA — Summa Elite ("Rock Creek Apartments"), likely Union Walk (verify first package) |
| Invoice stacks, no SOV grid | **LEGACY_STACK** | Rich Development — 12SB (historical only) |
Unknown format → do not force-fit; flag PR-043 with a sample of the header row.

## 1. AIA_G703 (Concord / Madison)
Columns, canonical order: Item No · Description · Scheduled Value · Work Completed
(Previous App / This Period) · Materials Presently Stored · Reallocation · Total Completed
& Stored (D+E+F−F.1) · % · Balance to Finish · Retainage.
STV template extensions to also capture: **Arixa Item crosswalk column** · Payment Tracking
block (Date / Draw / Amount / Funded / Variance) · "Horizontal Excluded from Billing" line
(per-draw base exclusions are real — carry them into fee-base math).
- Cost codes: `DD-SS-III` (109 known, e.g. 05-01-001) → GcCodeMap("Concord Homes", code).
- **Retainage: 5%** of completed + stored. Deviation = flag.
- **Dual numbering law:** GC draw N ≠ lender draw M (Draw 13 = Arixa Draw 6). Extract both;
  a package citing only one is incomplete.
- Developer Draw Summary = Contractor Billings + CM fee (5% × entity base) + **$1,000 draw
  fee**. Recompute the fee yourself: live Draw 6 billed $15,407.03 against $306,140.50 →
  5% = $15,307.03. A $100 error, found on the first real sheet. Expect more.
- Known signer: Samuel A Drown (Concord, lic. 9801383-5501).

## 2. PROCORE_PCI (Elite / Summa Elite)
Header block: Original Contract Sum + Approved COs = Revised Contract · Gross Invoiced ·
Retainage · Previous Invoices · Current Invoice · Balance to Finish.
Line grid: Item # (1–115) · Description · Value · Previous (Work / Material / Total) ·
Current (Work / Material / **Total Less Retain.**) · Total Billed · Balance · % Comp.
Then TWO more sections — parse all three:
- **Billed Change Orders** (CO#-keyed): every billed CO must exist in the approved CO
  register (Revised − Original must equal ΣCOs). A billed CO not in the register = flag.
- **Retainage Summary by CSI MasterFormat** (01 00 00 … 33 00 00): a third taxonomy —
  crosswalk separately; the CSI rollup must tie to Σ(line retainage).
- **Retainage: 10%** of current work (Less Retain. = 90% of Total). Deviation = flag.
- Work vs Material split matters: material-only billings (insurance items 114–115 billed
  100% as material day one) are legitimate but pattern-worthy — note them.
- Expect per-sub **conditional lien waivers (CLW)** in the same folder/email; missing
  waivers = flag, not blocker. Known signers: Tamirys Mayers ↔ Zach Coverston.
- Alias law: "Rock Creek Apartments" on Elite paper = **Summa Elite** the entity, never
  Rock Creek Acquisitions.

## 3. CANONICAL OUTPUT (what reconcile_draw_sheet receives)
Per line: `{gc_code, description, scheduled_value, prev_total, this_period_work,
this_period_material, stored, retainage_this_period, total_billed, pct_complete,
qb_item?}` + header: `{gc, project, gc_draw_no, lender_draw_no, period, retainage_rate,
contract_original, co_total, format}`. Unmappable gc_code → qb_item stays null + flag;
never invent a mapping (that's how the 5% markup hid last time).

## 3.5 EXTRACTION HUMILITY (60-day law)
Every extracted line carries a confidence score; sub-high-confidence lines flag with the
raw text quoted. For the first 60 days, every reconciliation gets mandatory human tie-out
regardless of PASS — extraction trust is earned per GC format, never assumed. New format
variant → prove it against `ProofRail/Historical Examples/` before trusting it live.

## 4. THE SIX CHECKS you narrate before physics rules
1. Fee math: CM fee = 5% × entity base (exclusions honored). Penny-exact or flag.
2. Retainage rate matches the GC's known rate (5% Concord / 10% Elite).
3. Both draw numbers present and sequential vs history.
4. COs billed ⊆ COs approved; Revised = Original + ΣCOs.
5. Σline math: totals, %complete = billed/value, balance = value − billed.
6. Member-vendor scan: any sub on the pay app who holds a contract contribution in the
   entity's Exhibit A → flag "member-vendor — cash vs contract equity."

## NEVER
Force an unknown format · guess a crosswalk · treat lender and GC draw numbers as one ·
accept a fee line without recomputing it · skip the CO register because the total "looks
right."
