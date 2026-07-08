# SPEC AMENDMENT — ProofRail v1.3.0: Fee Regime v2 + Per-GC Pay-App Adapters

```
Amends: v1.0–v1.2 | Date: 2026-07-04 | Status: Ready for Build
Source of truth: 7-2-2026 OAEA refresh + live draw packages read from Drive
(Madison Draw 13/Arixa 6 template · Rock Creek Pay App 022 · Arixa Draw #6 CM Fee doc).
Change class: DOMAIN LOGIC. Deletes v1.0's fee-payee matrix and 12SB/SummaElite refusals.
```

## C1. Fee Regime v2 (what the OAEAs now say)
One payee: **STV CM, LLC** (formed 4-2-2026). Four revenue streams, all classed `15 STV CM`:
| Stream | Rule | Evidence |
|---|---|---|
| Dev/CM fee | 5% of the entity's OAEA-defined base, riding each draw | verified in 12SB, Summa Elite, Madison 7-2-26 OAEAs; base VARIES (12SB = professional+sitework+construction, excludes land; Madison/SummaElite = total hard+soft) |
| Draw fee | flat $1,000/draw | Madison Arixa Draw #6 summary + template "Draw Fee Adjusted: $1,000" |
| Accounting fee | $50/hr, cap $500/mo/entity | OAEA template |
| PM oversight | 1.0–1.5% of GOI post-CO (rate per OAEA) | Summa Elite 1.0% / Madison 1.5% |
**Governing invariant (replaces the old hard blocks):** *no fee of any stream posts without
an `entity_registry` row citing the current OAEA.* Rock Creek Acquisitions has no clause;
Carlo/EJH/Dominus/Camden unverified → no rows → engine refuses, with the same force the
12SB block used to have, but sourced to documents instead of memory.

## C2. Schema deltas (Prisma)
```prisma
model EntityRegistry {           // ADD fields
  feeBase        String?        // OAEA's exact base definition, verbatim
  oaeaDocUrl     String?        // Drive link to governing OAEA
  oaeaEffective  DateTime?      // e.g. 2026-07-02
  drawFee        Decimal? @db.Decimal(8,2)   // 1000.00 where applicable
  acctFeeCapMo   Decimal? @db.Decimal(8,2)   // 500.00
  pmFeeRate      Decimal? @db.Decimal(5,4)   // 0.010 / 0.015, null pre-CO
}
model FeeRun {                   // payee stays (audit trail) but is always "STV CM, LLC";
  stream  FeeStream @default(DEV_CM)         // NEW: DEV_CM | DRAW | ACCOUNTING | PM
}
enum FeeStream { DEV_CM DRAW ACCOUNTING PM }

model GcCodeMap {                // NEW — the crosswalk F6 lives on
  id       String @id @default(uuid())
  gc       String                // "Concord Homes" | "Elite Construction USA" | ...
  gcCode   String                // "05-01-001" | "63" | "22 00 00"
  gcDesc   String
  qbItem   String                // STV item, e.g. "017 Plumbing"
  @@unique([gc, gcCode])
}
model DrawReconcile {            // ADD fields
  gcDrawNo     String?           // "13"  — GC's number
  lenderDrawNo String?           // "6"   — Arixa's number (dual numbering is real)
  retainageRate Decimal? @db.Decimal(4,3)    // 0.05 Concord / 0.10 Elite
  format       String?           // adapter used: AIA_G703 | PROCORE_PCI | ...
}
model MemberVendor {             // NEW — the double-pay trap
  id        String @id @default(uuid())
  entity    String
  vendor    String
  contractContribution Decimal @db.Decimal(12,2)
  exhibitAUrl String?
  @@unique([entity, vendor])
}
```
Trigger.dev additions: `monthly-accounting-fee` (day 1, cap-aware), `pm-fee-on-GOI`
(monthly, only entities with `pmFeeRate` set + CO reached). Tests INVERTED: delete
"12SB fee → refused"; add "fee for entity without registry row → refused (all 4 streams)"
and "12SB DEV_CM on land-inclusive base → refused (base violation)".

## C3. F6 v2 — per-GC format adapters (the pay-app formats found)
| GC / Project | Format | Parse targets | Retainage | Quirks |
|---|---|---|---|---|
| **Concord Homes** — Madison (lender Arixa, fund control Phoenix Tide) | **AIA G702/G703** in STV's xlsx draw template | Item No · Description · Scheduled Value · Prev App · This Period · Materials Stored · Reallocation · Total Completed&Stored · % · Balance · Retainage; STV extensions: Arixa-item crosswalk col, Payment Tracking (Date/Draw/Amount/Funded/Variance) | **5%** completed + stored | Cost codes `DD-SS-III` (109 codes, e.g. 05-01-001); **dual numbering** (GC Draw 13 = Arixa Draw 6); "Horizontal Excluded from Billing" line = per-draw base exclusions; GC signer Samuel A Drown (lic. 9801383-5501); Developer Summary = Contractor Billings + CM fee + $1,000 draw fee |
| **Elite Construction USA** — Summa Elite/Rock Creek Apts (and presumably Union Walk — verify one package) | **Procore Prime Contract Invoice, Fixed Lump Sum** | Contract summary (Original + COs = Revised) · line grid: Item# 1–115, Value, Prev(Work/Mat/Total), Current(Work/Mat/Total/Less Retain.), Total Billed, Balance, %Comp · separate **CO register** · retainage summary by **CSI MasterFormat** (01 00 00…33 00 00) | **10%** current work | Numeric items ≠ CSI ≠ STV codes — needs BOTH crosswalk layers; per-sub conditional lien waivers (CLW) accompany each pay app; signers Tamirys Mayers ↔ Zach Coverston |
| **Rich Development** — 12SB (legacy) | invoice-stack draws (historical) | already modeled by draw-vs-check ledger | n/a | winding down; F6 replay test #10 uses this history |
F6 v2 pipeline: detect format → adapter parses to canonical lines → map via GcCodeMap →
reconcile vs QBO basis + prior draws + SOV → **fee-math check** (5% × entity base vs billed
CM fee — the live Madison Draw 6 sheet shows $15,407.03 vs computed $15,307.03, a **$100
variance F6 would flag**) → retainage-rate check per GC → CO-register awareness (billed COs
must exist in the approved register) → member-vendor cross-check → verdict + proof.

## C4. Cowork skill touch-ups (apply to v2 skills)
Inbox Run DRAW_SHEET step: identify format first (AIA xlsx vs Procore PDF); extract BOTH
draw numbers; expect CLW attachments with Elite pay apps (missing waivers = flag, not
blocker). Coding-rules §1: "Rock Creek **Apartments** = Summa Elite's project name on Elite
pay apps" — one more alias for the trap table.

## C5. COA v4 (shipped alongside)
Partnership: classes 16 Rock Creek Acquisitions + 17 Camden Crossing; Summa Elite class
renamed (no "(Rock Creek)"); capital subs per current Exhibits A (SummaElite: Providence
42.165 Executive / STV 1.039 / ElephRock 1.615 IC / Outside incl. DM Capital; Madison:
+Lazarus 4.07 + Outside; Carlo: AW1 + Hendricks); IC fee vendors collapsed to **IC - STV CM**;
FEE-DEV rewritten; FEE-DRAW added. Parent: class **15 STV CM**; Member Equity:STV CM; four
income accounts (Dev 40200 / Draw 40210 / Accounting 40220 / PM 40230) + matching items;
Investment subs for RockCreekAcq-AW1, SumElite-ElephRock, Camden-Lazarus, Carlo-AW1.

## C6. Open verifications (registry build, not blockers)
Per-entity fee-clause read for HLN/Union/Quincy/Ledges/Freeman/Ventura/Vic/Ensign/Elephant
Rock/RM Texas (template presumed, verbatim base required) · Union Walk GC format (open one
package) · whether CEO 2%/Pres 1% now live inside STV CM's own OA · Camden Crossing status.
