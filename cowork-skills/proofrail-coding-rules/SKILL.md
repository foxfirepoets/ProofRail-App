---
name: proofrail-coding-rules
description: Coding judgment for STV invoices and costs flowing into ProofRail/QBO — choose the correct legal entity (Location), project (Customer-Job), and cost code (Item); enforce the OAEA fee matrix v2 grounded in the 7-2-2026 OAEA refresh (universal 5% dev/CM fee to STV CM, LLC); navigate STV entity naming traps (12SB vs HLN vs HLE, Summa Elite vs Rock Creek Acquisitions); vendor-member cross-checks; and raise pre-gate suspicion on BEC/duplicate/markup signals. Triggers - "code this invoice", "which entity", "which cost code", "fee matrix", "who gets the developer fee", any invoice/draw coding decision in an Inbox Run.
---

# proofrail-coding-rules v2 — where every dollar goes, per the CURRENT OAEAs
*Grounded in the 7-2-2026 OAEA refresh read directly from Drive. Supersedes v1 entirely —
v1's fee matrix described the pre-restructure world and was WRONG about 12SB and Summa Elite.*

Coding = a triple: **entity (Location) · project:phase (Customer:Job) · cost code (Item)**.
When in doubt: flag (PR-043), never guess.

> **Realms:** Realm A = the STV **partnership/projects** QBO company; Realm B = **parent/corporate**.
> Canonical definition (realm IDs, env vars, dimensional law) lives in `docs/COWORK_START_HERE.md §2` —
> this skill only *uses* the terms. When a rule below says "realm A," it means the partnership company.

## 1. ENTITY (Location) — naming traps, updated
| If you see | It means | NOT |
|---|---|---|
| Hunters Landing (the building, Ogden) | **12SB** | HLN |
| Hunters Landing **North** / HLN | **HLN** (separate LLC) | 12SB |
| Hunters Landing **East** / HLE | **HLE** — PARENT file, class 16 (held for sale) | either |
| **Summa Elite** | 754-unit Gainesville TX project (Providence = Executive Member); appears as **"Rock Creek Apartments"** on Elite pay apps | Rock Creek Acquisitions |
| **Rock Creek Acquisitions** | SEPARATE TX land entity, Gainesville (AW1 25 / QC Denton 50 / DWM 25) | Summa Elite |
| Union Walk / Union Station | **Union** | — |
| The Carlo / Washington | **Carlo** (AW1 + Erin Hendricks, 50/50) | — |
| Camden Crossing | its own entity (Lazarus line) — exists, verify before coding | — |
| Ensign | partnership class 18 — SOLD; wind-down/final-K-1 postings only | active project |
Resolution order: explicit project/address → `lookup_coding` history → vendor default → FLAG.
Never infer entity from sender.

## 2. FEE MATRIX v2 (the 7-2-2026 restructure — this is law now)
**Universal rule:** a 5% developer & construction-management fee is payable to
**STV CM, LLC** (Utah LLC, formed 4-2-2026) under each project's current OAEA
"Developer's Fee" clause. Confirmed by direct read: **12SB ✓, Summa Elite ✓, Madison ✓.**
All other project OAEAs were refreshed 7-2-2026 on the same template — treat as
STV CM payee, but **verify each entity's clause during EntityRegistry build** and store
`oaea_doc_url + effective_date + fee_base` per entity.
- **Fee BASE varies by OAEA — read it, don't assume:** 12SB = "professional costs, site
  work, and construction costs" (NO land/acquisition); Madison & Summa Elite = "total hard
  and soft costs." The engine computes on the entity's own base.
- **Draw fee:** flat $1,000/draw to STV CM (live in Madison Arixa draws — verify per OAEA/lender).
- **Two more STV CM revenue streams in the template:** Accounting fee — $50/hr capped at
  **$500/mo per entity**; Property-management oversight fee — **1.0% (Summa Elite) /
  1.5% (Madison) of gross operating income** post-certificate-of-occupancy. Rates vary
  per OAEA — capture per entity.
- **NO fee:** Rock Creek Acquisitions (land venture — full read confirms no fee clause).
  Carlo / EJH / Dominus / Camden Crossing: unverified — flag, don't post.
- Timing: fee rides each construction draw; if accrued instead, payable immediately after
  construction-loan payoff and BEFORE capital returns/distributions.
- v1's hard refusals for 12SB and Summa Elite are **REVOKED**. The refusal principle
  survives in better form: *the fee engine pays only what an EntityRegistry row sourced
  from a current OAEA authorizes.* No row, no fee — for anyone.
- Commissions (parent-side internal, never a project cost): **Zach Coverston 2% · Mike Watson 2%
  · Porter Christensen 1%** of the assessed 5% dev fee — RESOLVED by Ben 2026-07-06 (Coverston
  already added in QBO Realm B). Parent realm only; the partnership realm never books them.

## 3. COST CODE (Item) — unchanged from v1
Vendor default → line-description keywords override (say why) → families: 001–049 hard ·
050–069 soft/GC · 100s land/acq · 110 A&E · 120–122 financing · 200s disposition.
**068 GC Construction Profit ≠ FEE-DEV** (the 5% now = STV CM's fee). Retainage held =
RETAINAGE-HELD negative line. Uncertain line → submit with notes, never launder into
General Conditions.

## 4. PROJECT:PHASE — unchanged
Construction entities: `{Project}:{Acquisition|Sitework|Vertical|Disposition}`; operating
assets: `:Operations`; Dominus: `Dominus:Operations`. Madison GC = **Concord Homes** (its
fee may convert to capital per OAEA §7 — see §5). GC-dealings spokesperson = Mike Watson;
**Aubrey Palmer = Authorized Signatory** on draws/bills/bank docs across these entities —
her signature on draw docs is expected, others are anomalies.

## 5. VENDOR–MEMBER CROSS-CHECK (new, from Exhibit A reads)
Many cap tables include SUBCONTRACTORS as members via "contract contributions"
(e.g., Summa Elite: LB Drywall, Proficient Concrete, EM Building, Elegant Granite,
MPS Construction, Houston Window Fashions, AR Trim; Elite Construction 401k plans).
**A member-vendor's invoice may be satisfied by equity, not cash.** Before coding a
member-vendor's invoice for payment: check the entity's Exhibit A; if the vendor holds a
contract-contribution line, FLAG with note "member-vendor — confirm cash vs contract
equity treatment." Paying cash against a contract contribution is a double-pay.

## 6. EQUITY MAP (holding → project, corrected from ledger + Exhibits A)
Madison: Lykos 73.55% (Executive) + AW1 1% + Lazarus 4.07% + 8 outside lines.
Summa Elite: Providence 42.165% (Executive) + DM Capital 42.165% + ~35 outside lines
incl. **STV LLC 1.039%** and **Elephant Rock LLC 1.615%** (intercompany equity!).
Rock Creek Acq: AW1/QC Denton/DWM. Carlo: AW1 + Erin Hendricks. Ledger sheet-3 totals:
Providence $3.08M/5 deals · Lazarus $3.49M/4 · STDG $2.76M/3 · AW1 $347K/2 · STV $13.7K/1.
Capital sub-accounts must follow current Exhibit A, not memory — every OAEA has 8–40 members.

## 7. PRE-GATE SUSPICION — unchanged from v1 (bank-change, dup shapes, look-alike domains,
draw markup vs basis, no-invoice->no-pay >$1k, **amount >2x the vendor's trailing average -> WARN**) plus: any fee invoice NOT from STV CM
claiming to be the developer fee = flag loudly.

## 8. HARD REFUSALS v2
Never code to: Ask My Accountant · accounts outside the COA · a fee without an
EntityRegistry row sourced to a current OAEA · HLE or corporate entities inside the partnership realm (Realm A — see COWORK_START_HERE §2) ·
the Arixa $317,137.06 plug (labeled, frozen, CPA-owned). Litigation entities (12SB, Union):
precision over speed; line notes written as future exhibits.
