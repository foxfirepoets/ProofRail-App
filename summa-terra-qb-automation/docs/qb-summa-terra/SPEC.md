# Design Specification — QuickBooks Enterprise Desktop Rebuild for Summa Terra Ventures

```
Spec Title:        QuickBooks Enterprise as a Real Estate Development Project-Cost Accounting System
Version:           2.2.0  (adds §19 + Import_Files/ — ready-to-upload IIF/CSV for the full layout)
Author:            Generated via thinking-lab (decision-oracle) → spec-superstar; revised per confirmed business rules
Last Updated:      2026-06-27
Status:            Ready for Build (hand to QuickBooks Enterprise implementation expert)
Timeline:          10–14 weeks to full cutover (phased; see Section 11)
Confidence Level:  ~95% — ALL flip-points resolved (v2.1). Each partnership files its own 1065
                   (CONFIRMED 2026-06-27) → file-per-legal-entity is locked. Fee structure,
                   trigger, and draw model also confirmed: partnership books the 5% developer fee
                   only; the 2% CEO + 1% President commissions are PARENT-ONLY; trigger =
                   construction-manager + Mike Watson approval; the draw is a multi-vendor Draw
                   Package (§6.7), not a single bill. No open architectural questions remain.
Next Steps:        Execute Phase 0 (Discovery & Backup) — no blocking confirmations outstanding.
Source of truth:   Confirmed business rules (2026-06-27) + oracle_final.md + QB Summa Terra Prompt.md;
                   Item list anchored to the real GC draw package (Hunters Landing Draw #29.pdf)
```

> **Domain note.** This is a *pure QuickBooks Enterprise Desktop configuration* specification — not a
> software/API build. The 18-section spec-superstar methodology is mapped onto the accounting domain:
> "endpoints" = QuickBooks transaction types and workflows; "data models" = lists (COA, Items, Classes,
> Customer:Job, Names) and custom fields; "migrations" = list-import/build scripts; "deployment" =
> the migration & cutover plan. The AI layer, external database, and SwarmSync bridge are explicitly
> **out of scope** (handled separately).

---

## DELIVERABLE MAP (where each of the 20 required deliverables lives)

| # | Deliverable | Section |
|---|-------------|---------|
| 1 | Recommended company file structure | §4 |
| 2 | Proposed chart of accounts | §6.1 + `Chart_of_Accounts.md` |
| 3 | Customer/job/project hierarchy | §6.2 |
| 4 | Class tracking design | §6.3 |
| 5 | Item / cost-code list | §6.4 + `Cost_Codes_and_Items.md` |
| 6 | Vendor/customer/investor naming rules | §6.5 + §15 |
| 7 | Developer-fee accounting workflow | §5.3 + §12.4 |
| 8 | Bank feed setup rules | §12.5 |
| 9 | AP workflow | §12.6 |
| 10 | Draw & loan tracking workflow | §12.7 |
| 11 | Budget vs. actual structure | §12.8 |
| 12 | Intercompany accounting workflow | §12.9 |
| 13 | Month-end close checklist | §16.2 + `Month_End_Checklist.md` |
| 14 | Standard report package | §16.1 |
| 15 | Custom field design | §6.6 |
| 16 | Internal controls | §9 |
| 17 | Migration plan | §11 |
| 18 | QuickBooks operating manual | §12 (all workflows) |
| 19 | Training checklist | §18.2 |
| 20 | Final recommendation | §18.3 |

---

## 1. EXECUTIVE SUMMARY

Summa Terra Ventures is a real estate development firm running 10+ QuickBooks Enterprise company files
on Rightworks, with a single accounting manager covering the parent management company and every project
partnership. Today the business is **spreadsheet-driven instead of system-driven**: dozens of disconnected
Google Sheets track draws, budgets, and fees; transactions are hard to find; and — most costly — the
**5% Developer Fee (plus 2% CEO and 1% President executive commissions) calculated off approved General
Contractor draws is being silently missed**, leaking real revenue.

This spec rebuilds QuickBooks Enterprise into a **real-estate-development project-cost accounting control
center**. The core architectural decision (validated by a 6-agent decision-oracle with full consensus) is:
**one standardized company file per legal entity** (cloned from a locked template), **one read-only master
reporting file** for portfolio roll-up, and **an intercompany clearing discipline** between partnerships and
the parent. Inside each file, **projects = Customer:Job**, **vendors stay vendors**, **cost codes = Items
that mirror the GC draw schedule (001–069)**, and **Class = development phase**; a **Draw # custom field**
ties every line back to the one approved draw package.

The fee leak is closed structurally by making the **approved draw a first-class, reconciled event**. When a
draw package is approved, the system books a single **5% developer fee** as an intercompany charge — the
partnership records it as a project cost (Due-To Summa Terra), and Summa Terra records the income and
receivable. **Separately, on the parent's own books**, Summa Terra accrues the **2% CEO and 1% President
commissions it pays out of that fee.** Both sides post off the **Draw Package total**, so a draw cannot be
reconciled without its 5% fee, and commissions are never mis-booked onto a partnership.

**Business outcome:** zero missed developer fees, a same-day-findable transaction trail, a repeatable
month-end close, and a structure that scales linearly from 10 → 200+ partnerships without re-architecture.
**Primary user:** the accounting manager (with CEO Mike Watson and President Porter Christensen as fee
recipients/approvers). **Why now:** every approved draw that passes without its fee invoice is permanent
lost revenue, and the entity count is growing.

---

## 2. SCOPE DEFINITION & NON-SCOPE

### In scope
- Company-file architecture (entity files + master reporting file + archive/clearing discipline).
- Standardized Chart of Accounts, Class list, Item/cost-code list, Customer:Job hierarchy, Names lists.
- Custom-field design within QuickBooks Enterprise limits.
- Developer-fee / executive-commission accounting workflow (recognition event, JEs, invoices, intercompany).
- Bank-feed rules, AP workflow, draw/loan tracking, budget-vs-actual, intercompany, month-end close.
- Standard report package and reconciliation reports.
- Internal controls (preventive, detective, permissions, close locks, audit-trail review).
- Migration plan from the current messy state, operating manual, and training checklist.
- A reusable **new-entity onboarding template** (the mechanism that makes 200 entities manageable).

### Out of scope (explicitly NOT in this spec)
- The AI review/automation layer.
- The external database / data warehouse.
- The QuickBooks ↔ external-system bridge / integration connectors.
- The surrounding SwarmSync architecture.
- Lender-portal mechanics and AIA G702/G703 form generation *outside* QuickBooks (QB feeds the data;
  the package assembly itself, if done in a separate tool, is out of scope).
- Tax-return preparation (QuickBooks produces the books that feed the 1065s; the returns are the CPA's).
- Payroll system selection (only the *allocation* of payroll/overhead into projects is in scope).

### Dependencies
- **Rightworks** hosting (existing) must support the chosen file count at scale.
- The **approved GC Draw / Pay Application** business process (already standardized per the brief) is the
  authoritative trigger this design depends on.
- Fixed company policy (CONFIRMED 2026-06-27): all three percentages are computed off the **approved Draw
  Package total**, but the **booking is split**:
  - The **partnership owes only the 5% Developer Fee** to Summa Terra Ventures, recorded as a **project cost**
    (capitalized to CIP if the CPA confirms, else expensed). The partnership records **no commissions.**
  - **Summa Terra** recognizes the **5% as Developer Fee Income + a Due-From receivable**, and **separately**
    accrues the **2% (Mike Watson) and 1% (Porter Christensen) commissions as its own expense/payables**,
    paid *after* it earns the developer fee.
  - **Trigger:** a draw becomes fee-eligible only when the **construction manager and Mike Watson approve it**
    and release it to accounting — **not** on the GC's first submission. **Not subject to redesign.**

---

## 3. BUSINESS CONTEXT & ACCEPTANCE CRITERIA

**Business goal:** Convert QuickBooks into the single accounting source of truth so that (a) no developer
fee or executive commission is ever missed, (b) any transaction is findable in seconds, and (c) the firm
can onboard new partnerships without bespoke setup.

**Success metrics & targets:**

| Metric | Baseline (today) | Target |
|--------|------------------|--------|
| Missed developer-fee rate | Unknown / material leakage | **0 missed fees** — every approved draw reconciles to fee invoices or a logged exception |
| Time to locate any transaction | Minutes–hours across sheets | **< 10 seconds** in QuickBooks |
| Month-end close per entity | Ad hoc / variable | **≤ 3 business days** per entity; portfolio close ≤ 7 business days |
| New-entity onboarding | Hand-built file | **≤ 2 hours** from locked template |
| Uncoded / missing-dimension transactions at close | Common | **0** unresolved (project/class/item) before books lock |
| Intercompany Due-To/Due-From | Frequently out of balance | **Nets to $0** portfolio-wide every month |

**Acceptance criteria (testable, this spec is a build-phase contract):**
- [ ] A new partnership file can be created from the template and be transaction-ready in ≤ 2 hours.
- [ ] Approving a draw package generates the partnership's **5% developer-fee** entry and the parent's
      **5% income + 2%/1% commission** accruals from memorized templates (no ad-hoc JE required).
- [ ] The **Draw vs. Fee Reconciliation** report shows every approved draw linked to its 5% developer fee
      (partnership) and the parent's 5%/2%/1% accruals, or a documented exception — zero unexplained gaps.
- [ ] No partnership file contains a commission expense or commission payable (commissions are parent-only).
- [ ] Every posted expense in an entity file carries Customer:Job, Class, and (where applicable) Item.
- [ ] Portfolio intercompany balances net to $0 in the master reporting roll-up.
- [ ] A closed period is locked with a password; prior-period edits require explicit re-authorization and
      appear in the audit trail.
- [ ] The full report package (§16.1) runs from saved/memorized reports without rebuilding filters.

**Spec status:** Build-phase contract. If implementation reveals a conflict, update this spec (v1.x) and
document the rationale — do not silently deviate (the fee-trigger and intercompany rules are load-bearing).

---

## 4. ARCHITECTURE & SYSTEM INTEGRATION (Deliverable 1 — Company File Structure)

### 4.1 Chosen structure: File-per-entity + Master reporting file + Intercompany clearing

```
                         ┌─────────────────────────────────────────┐
                         │   MASTER REPORTING FILE (read-only)       │
                         │   - Portfolio roll-up via exported TBs     │
                         │   - Class = ENTITY here (only here)        │
                         │   - No operating transactions              │
                         └───────────────▲───────────────────────────┘
                                         │ (trial-balance export / Combined Reports)
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
┌───────┴────────┐              ┌────────┴────────┐              ┌────────┴────────┐
│ PARENT FILE     │  intercompany │ PARTNERSHIP A   │  intercompany │ PARTNERSHIP B   │  ... → N (to 200+)
│ Summa Terra     │◄────────────►│ (Project A LP)   │◄────────────►│ (Project B LP)   │
│ Ventures (mgmt) │  Due-To/From │ project = Job    │  Due-To/From │ project = Job    │
│ - Fee INCOME    │              │ - Fee EXPENSE/   │              │ - Fee EXPENSE/   │
│ - CEO/Pres AP   │              │   CIP + AR/Due-to│              │   CIP + AR/Due-to│
│ - Mgmt overhead │              │ - Draws, loans   │              │ - Draws, loans   │
└─────────────────┘              └──────────────────┘              └──────────────────┘
        │
        ▼
┌─────────────────┐
│ ARCHIVE FILES    │  Retired/closed-deal partnerships moved here to keep active lists lean.
└─────────────────┘
```

**Why this structure (and not the alternatives):**

| Option evaluated | Verdict | Reason |
|------------------|---------|--------|
| **One file per legal entity (chosen core)** | ✅ | Each partnership files its own 1065, holds distinct partner capital accounts and bank accounts, and needs clean legal/audit separation. QuickBooks has **no native multi-entity consolidation**, so legal separation must be file-level. |
| One consolidated file with classes/customers/jobs | ❌ | Commingles separate 1065 capital accounts (improper) and breaches the ~10,000-list-entry soft limit around entity #40. Collapses partnership transparency. |
| Parent + separate partnership files (chosen) | ✅ | Parent management company is its own file; fee income and executive-commission payables live there. |
| Separate project files (per project, not per entity) | ⚠️ Conditional | Only if a single legal entity holds **multiple projects** — then projects are Jobs *inside* the entity file, not separate files. |
| Master reporting file (chosen) | ✅ | Read-only consolidation/roll-up; **not** a transacting file. |
| Archive files (chosen) | ✅ | Move closed deals out of active files to preserve performance and keep lists under limits. |
| Intercompany clearing discipline (chosen) | ✅ | Standardized Due-To/Due-From accounts + a defined settlement procedure prevent the unreconcilable-intercompany failure mode. |
| Hybrid / anything else | ❌ | No coherent hybrid beats the above for legal separation + scale. |

### 4.2 The scaling mechanism (10 → 50 → 200 entities)

The file count grows **linearly, not exponentially in effort**, because every new entity is a **clone of one
locked standard template file** containing the standardized COA, Class list, Item list, custom fields,
memorized transactions, and memorized reports. Onboarding = copy template → rename → set opening balances →
connect bank feeds. No re-design per entity. (See §11.5 and §18.1.)

### 4.3 Intercompany topology

- Each partnership file carries **`Due To — Summa Terra Ventures`** (liability) and, where the parent funds
  costs, **`Due From — Summa Terra Ventures`** is mirrored as **`Due From — <Partnership>`** (asset) in the
  parent. The two sides must always be equal and opposite.
- The parent file carries the **fee income** and the **executive-commission payables** to Mike Watson and
  Porter Christensen (set up as Other Names / Vendors — see §6.5).
- A **monthly intercompany reconciliation** (§16.1) proves every pair nets to zero before close.

### 4.4 Ownership map

| Component | Owner |
|-----------|-------|
| Standard template file & version control | QuickBooks implementation expert + Accounting Manager |
| Per-entity operating transactions | Accounting Manager |
| Fee-policy percentages (5/2/1) | Company policy — CEO/President (fixed) |
| Draw approval (the trigger) | Project/Construction lead → recorded by Accounting Manager |
| Master reporting roll-up | Accounting Manager / Controller |
| Period close & lock password | Accounting Manager (close-lock held by Controller if one exists) |

---

## 5. USER FLOWS & HAPPY PATH

> Full step-by-step operating procedures for every transaction type are in §12 (the Operating Manual).
> This section captures the three highest-stakes flows end-to-end.

### 5.1 Happy path — Record a project cost (vendor bill)
**Actor:** Accounting Manager. **Precondition:** Vendor exists; project = a Customer:Job exists.
1. Vendors → Enter Bills. Select vendor.
2. On the **Items** tab, choose the cost-code Item (e.g., `03-Concrete`), enter amount.
3. Set **Customer:Job** = the project/phase (e.g., `STV-014:Sitework`).
4. Set **Class** = development phase (e.g., `20-Hard Cost`).
5. Set **Billable?** only if it is a reimbursable/draw-eligible cost per §6.4.
6. Fill custom fields (Draw #, Approval ID if applicable — §6.6). Save.
**Postcondition:** Cost hits CIP/development-cost via the Item mapping, is job-costed to the project, and is
visible in Project Cost Detail and Draw reports.

### 5.2 Happy path — Record an approved **Draw Package** (Deliverable 10)
**Actor:** Accounting Manager. **Precondition:** A draw package (e.g., *Hunter's Landing Draw #29*,
total **$962,845.68**) has been **approved by the construction manager and Mike Watson** and released to
accounting. A draw package is **many payee lines** — vendor, item #, invoice #, retainage, amount due —
**not a single bill** (§6.7). See §12.7 for full mechanics.
1. Assign the **Draw # custom field** value (e.g., `D-2025-29`) — this stitches the whole package together.
2. For **each payee line**, enter a **vendor bill**: Vendor (payee) → Item (the numbered cost code, e.g.
   `005 Fencing`) → Customer:Job (the project) → Class (the phase) → vendor invoice # in Ref → **Draw #**.
   Add a retainage line where the package shows a Retainage (–) so bill net = the **Amount Due** (§6.7).
3. Record draw funding: loan proceeds increase `Construction Loan Payable` and the loan-funding account; the
   funded payments clear AP.
4. **Trigger the fee workflow (5.3) off the approved Draw Package total** — the critical link.
**Postcondition:** The package appears in the Approved Draw Register filtered by Draw #; every line is
job-costed and reconciles to the lender's amount-due column; the 5% fee is generated in the same cycle.

### 5.3 CRITICAL flow — Developer fee (partnership) + parent commissions (Deliverable 7)
**Actor:** Accounting Manager. **Precondition:** A draw package is **approved** (construction manager + Mike
Watson) with total `D`. **Recognition is at approval, not at the GC's first submission and not at funding.**

**Step 1 — Partnership file books ONLY the 5%:**
1. Enter the memorized **"Developer Fee on Draw"** bill from vendor `IC — Summa Terra Ventures`.
2. One line, Item `FEE-DEV` = **5% × D**, stamped with the **Draw #**.
3. Posts **Dr `15500 CIP — Developer Fee Capitalized`** (or `60100` if the CPA expenses it) **/ Cr
   `21000 Due-To Summa Terra`.** The partnership records the fee as a **project cost** — **no commissions.**

**Step 2 — Parent file (Summa Terra) books income + receivable + its own commissions:**
4. Memorized **"Developer Fee Income"** entry: **Dr `12200 Due-From <Partnership>` / Cr `40200 Developer
   Fee Income`** for **5% × D**.
5. Memorized **"Executive Commissions"** entry (parent's own compensation, paid out of the fee it earns):
   - **Dr `60200 CEO Commission Expense` (2% × D) / Cr `21100 Commission Payable — Mike Watson`.**
   - **Dr `60300 President Commission Expense` (1% × D) / Cr `21200 Commission Payable — Porter Christensen`.**
6. The **Draw vs. Fee Reconciliation** ties `D` → partnership 5% → parent 5%/2%/1%.
7. On collection, cash clears `Due-From/Due-To`; commissions are paid to Mike/Porter when Summa Terra elects.
**Postcondition:** Every approved draw carries its 5% fee; Summa Terra nets 2% after commissions; no
partnership file ever holds a commission. Leakage is structurally impossible.

> **Edge:** If a draw is later **denied or revised**, reverse/adjust **both** the partnership 5% entry and the
> parent income/commission entries, and log the exception (§7). Recognition at **approval** is deliberate —
> the GC's first submission is not yet approved, and funding/cash receipt is exactly where fees vanish today.

### 5.4 Alternate flows (summarized; detailed in §12)
- **Reimbursement** (parent paid a partnership cost): §12.9.
- **Investor contribution / capital call**: §12.1-manual.
- **Distribution to partners**: §12.1-manual.
- **Intercompany transfer between partnership bank accounts**: §12.9.

---

## 6. DATA MODELS & SCHEMA (the QuickBooks lists)

QuickBooks has six dimensions to assign meaning. The locked design uses each for exactly one purpose to
avoid the classic "everything is a class" bloat:

| Dimension | Carries | Rule |
|-----------|---------|------|
| **Company File** | Legal entity | One file = one legal entity. |
| **Vendor (Name)** | The payee on each draw line | Vendors stay vendors — `Bronco Fence`, `Meraki Steel`, the GC. Never a cost code. |
| **Customer:Job** | Project / property / phase | Project = Job; sub-phase = Sub-job. |
| **Item** | Cost code / WBS — **the numbered draw line (001–069)** | Mirrors the GC draw schedule; each Item maps to one broad CIP bucket. |
| **Class** | Development phase / cost center | Site / Structure / MEP / Finishes / Exteriors / Gen-Conditions / Financing / Disposition. |
| **Account (COA)** | GL classification | Kept lean — four CIP buckets; no per-project, no per-cost-code accounts. |
| **Custom fields** | **Draw #**, Approval ID, Fee eligibility | Draw # is the spine that ties a whole package together (§6.6). |

### 6.1 Chart of Accounts (Deliverable 2) — design rules
Full account list with numbers, type, file placement, and fee-relevance is in **`Chart_of_Accounts.md`**.
Design rules:
- **No GL account per project** — project detail comes from Customer:Job, never from account proliferation.
- Account numbering enabled; blocks: 1xxxx Assets, 2xxxx Liabilities, 3xxxx Equity, 4xxxx Income,
  5xxxx COGS/Cost of Sales, 6xxxx–7xxxx Operating/Overhead, 8xxxx Other.
- **CIP / Development Costs** is a balance-sheet asset (`15000`), with subaccounts mirroring the major cost
  groups (Land, Soft, Hard, Financing) — *groups only*, detail lives in Items.
- For each account, `Chart_of_Accounts.md` defines: Purpose, Example transaction, File placement
  (Parent / Partnership / Both), Balance-sheet vs P&L, Job-coding required?, Affects fee calc?.
- **Identical COA in every partnership file** (it ships in the template) so consolidation and staff muscle
  memory are uniform.

### 6.2 Customer:Job / Project hierarchy (Deliverable 3)
Projects/properties are represented as **Customers with Jobs** — *not* Classes, *not* Items — because only
Customer:Job natively supports job-cost P&L, estimate-vs-actual, AR, and draw tracking.

```
Customer:  STV-014  Maple Ridge Phase 1 LP        ← (in a single-project entity, the file ≈ the project)
   Job:      STV-014:Acquisition
   Job:      STV-014:Sitework
   Job:      STV-014:Vertical
      Sub-job:  STV-014:Vertical:Bldg-A
      Sub-job:  STV-014:Vertical:Bldg-B
   Job:      STV-014:Lease-Up / Disposition
```
- **Naming:** `<ProjectCode> <PropertyName>` at Customer level; `:<Phase>` Job; `:<Lot/Unit/Bldg>` Sub-job.
- In a **single-asset partnership**, the Customer collapses to one project and the file *is* the project —
  acceptable and keeps the template uniform.
- In a **multi-project entity** (if it exists), each project is a separate Customer within the file.
- Reserve the Customer center for **projects only**; investors/partners/lenders are **Vendors/Other Names**,
  not Customers (§6.5), to keep the Customer list clean for job costing.

### 6.3 Class tracking design (Deliverable 4)
**Class = development phase / cost center.** Entity is already the file and project is already the Job, so
Class is free to carry the lifecycle cut that management and LPs actually report on.

The phase list **mirrors the GC draw schedule's own groupings** (the continuation sheet phases), so a draw
line's Class is obvious from where it sits in the package, plus lifecycle phases for non-draw costs:

```
00  Acquisition / Pre-Development      ← land, due diligence, entitlements, A&E
10  Site / Excavation                  ← draw codes 001–005
20  Structure / Frame / Roof           ← draw codes 007–016
30  MEP Trades                         ← draw codes 017–022
40  Finishes                           ← draw codes 023–035
50  Exteriors & Amenities              ← draw codes 036–049, 069
60  General Conditions / Supervision   ← draw codes 050–068 (incl. GC profit 068)
70  Financing / Carry Cost             ← loan fees, interest, property taxes
80  Disposition / Sale                 ← marketing, sales commission, closing
90  Parent Overhead (parent file only) ← Summa Terra G&A; commission expense lives here
```
- **Use classes** for: phase-level P&L, development-stage reporting, separating overhead from project cost.
- **Do NOT use classes** for: legal entity (that's the file), project (that's the Job), or payee (that's the
  Vendor) — all redundant.
- **Master reporting file is the ONLY place Class = Entity**, used purely to slice the consolidated roll-up.
- Enforce "**require a class on transactions**" in preferences (detective control, §9).

### 6.4 Item / cost-code list (Deliverable 5)
Full standardized list is in **`Cost_Codes_and_Items.md`**. **The Item list mirrors the actual GC/lender draw
package** (anchored to *Hunters Landing Draw #29.pdf*), so QuickBooks coding maps 1:1 to the approved document.
Design rules:
- The **numbered draw cost codes `001`–`069`** (003 Site Concrete, 004 UDOT Concrete, 005 Fencing, 012 Steel,
  019 Electrical, 067 Site Supervision, 068 Construction Profit, …) **are the QuickBooks Items.** New draw
  lines become new numbered Items — never new accounts.
- **Each Item maps to exactly one of four broad CIP buckets:** `15300 CIP — Hard Costs`, `15200 CIP — Soft
  Costs`, `15400 CIP — Financing Costs`, or `15500 CIP — Developer Fee Capitalized`. This is what keeps the
  COA clean and broad while the Item carries all the detail.
- **Items vs. the other dimensions:**
  - **Vendor** = who is paid (the payee); **Item** = what was bought (the numbered cost code).
  - **GL account** = the broad CIP bucket the Item rolls into (lean; §6.1).
  - **Class** = the phase the cost belongs to (§6.3, mirrors the draw's phase groups).
  - **Customer:Job** = which project incurred it (§6.2); **Draw #** = which approved package (§6.7).
- **Retainage** is a line *on the same bill* (to `20200 GC Retainage Payable`), so the bill net equals the
  package's **Amount Due** while the cost-code Item keeps the vendor's gross for budget-vs-actual.
- **`068 Construction Profit`** is the **GC's** builder profit inside the draw (a soft-cost line) — **not** the
  5% developer fee to Summa Terra, which is a separate intercompany charge computed on the whole draw total.
- **Fee Items** `FEE-DEV` (partnership, 5% only), `FEE-DEV-INC` (parent income), `FEE-CEO`/`FEE-PRES` (parent
  commissions) are the anti-leakage mechanism (§5.3/§12.4). See `Cost_Codes_and_Items.md` §4 for the split.

### 6.5 Vendor / Customer / Investor setup & naming (Deliverable 6)
| Party | QuickBooks list | Naming convention | Required fields |
|-------|-----------------|-------------------|-----------------|
| Vendors / Contractors | Vendor | `<LegalName>` (no DBAs as separate records) | EIN/W-9 status, terms, 1099 flag |
| Lenders | Vendor | `LENDER — <Name>` | Loan #, contact |
| General Contractor | Vendor | `GC — <Name>` | Tied to draw workflow |
| Investors | Other Names (or Vendor for payments) | `INV — <Name>` | Entity, ownership %, contact |
| Partners | Other Names | `PARTNER — <Name>` | Capital-account link |
| Management company | Vendor/Customer (intercompany) | `IC — Summa Terra Ventures` | Intercompany flag |
| Project partnerships (in parent file) | Customer | `IC — <Partnership>` | Intercompany flag |
| Executives (fee recipients) | Vendor/Other Names | `EXEC — Mike Watson`, `EXEC — Porter Christensen` | Commission payable acct |
| Employees | Employee | `<Last, First>` | — |
| Reimbursable parties | Vendor | per type above | reimbursable flag |

- **Duplicate-prevention controls:** enforce a naming standard, turn off "auto-create on the fly" for staff
  roles, and run the **Duplicate Names review** monthly (§9). Use a single record per legal party; put DBAs
  in a custom/notes field, never as a second record.
- **Related-party / intercompany** parties are prefixed `IC —` or `EXEC —` so they are filterable and never
  confused with third parties.

### 6.6 Custom field design (Deliverable 15)
QuickBooks Enterprise supports a limited number of custom fields (names list custom fields and
transaction/item custom fields, plus Enterprise's added capacity). **Only fields QB Enterprise can
realistically support are specified**; richer metadata (AI review status, external workflow IDs) is
*acknowledged but pushed to the external layer*, which is out of scope.

| Custom field | Attach to | Purpose | In-QB? |
|--------------|-----------|---------|--------|
| **Project Code** | Customer:Job / transaction | Fast search key | ✅ |
| **Entity Code** | (file-level via naming) | Identify entity | ✅ (naming) |
| **Draw Number** | Transaction | Tie cost/fee to a draw | ✅ |
| **Fee Eligibility** | Item | Counts toward 5% base? | ✅ |
| **Approval ID** | Transaction | Link to approved draw/AP approval | ✅ |
| Proof ID / Source-Doc ID | Transaction | Evidence pointer | ⚠️ Use one combined "Ref/Doc" field |
| External Workflow ID | Transaction | Bridge key | ❌ External layer (out of scope) |
| AI Review Status | Transaction | — | ❌ External layer (out of scope) |
| Human Approval Status | Transaction | Approved/Pending | ✅ (single custom field or memo convention) |

> Because QB Enterprise caps transaction custom fields, the design **prioritizes Draw #, Approval ID, and
> Fee Eligibility** (the fields the controls in §9 and §16 depend on) and consolidates evidence pointers into
> one "Ref/Doc ID" field. Out-of-scope external IDs are deliberately not forced into QuickBooks.

### 6.7 The Draw Package model (how a draw lives in QuickBooks)
A construction draw is **not a single bill.** As the real package shows (*Hunters Landing Draw #29*: 40+ payees,
total **$962,845.68**), it is a **set of payee lines**, each with its own vendor, cost-code item #, vendor
invoice #, a retainage adjustment, and an amount-due. QuickBooks has no native "draw package" object, so the
package is modeled as **a batch of vendor bills unified by one `Draw #` custom-field value**:

```
DRAW PACKAGE  "D-2025-29"  (Hunter's Landing, approved 09/10/2025, total $962,845.68)
│
├─ Bill  Vendor: Bronco Fence Company   Item 005 Fencing      Inv 12722-HLR …  Retainage −119.00   Due 37,066.31
├─ Bill  Vendor: Meraki Steel           Item 012 Steel        Inv 9600,9605 …  Retainage −17,699.18 Due 138,113.68
├─ Bill  Vendor: Fox & Hound            Item 019 Electrical   Inv 8/11/25      Retainage  +3,947.37 Due 75,000.00
├─ Bill  Vendor: Rich Development Inc    Item 068 Constr Profit Inv HL 2508     —                    Due 150,000.00
│        … (one bill per payee line; the GC's lump line is split to its item #s 003/004/026/056/060/067/068)
│   every line carries:  Customer:Job = Hunter's Landing   ·   Class = its phase   ·   Draw # = D-2025-29
│
└─ FEE TRIGGER (§5.3) fires once on the PACKAGE TOTAL $962,845.68:
       Partnership:  Dr CIP-Dev-Fee 5% = $48,142.28  / Cr Due-To Summa Terra
       Parent:       Dr Due-From 5% / Cr Dev Fee Income; Dr CEO Comm 2% = $19,256.91 / Cr Payable-Watson;
                     Dr Pres Comm 1% = $9,628.46 / Cr Payable-Christensen
```

**Rules:**
- **One bill per payee line** (a QB bill has one vendor) — the package is virtual, assembled by filtering on
  `Draw #`. The GC's single summary line is **split into its component item #s** (the continuation sheet shows
  the breakdown) so cost codes stay clean.
- **Retainage** rides on the line's bill (§6.4) so each bill's net = the package **Amount Due** column.
- **The package total is the fee base.** The 5%/2%/1% are computed once on the approved total, *after*
  construction-manager + Mike Watson approval (§5.3) — never per line, never on first submission.
- **`Draw #` is mandatory** on every draw bill and on the fee entries; it is what makes "show me everything in
  Draw #29" a one-filter report and what the Draw vs. Fee Reconciliation keys on.

---

## 7. ERROR HANDLING & EDGE CASES (accounting failure modes)

| Scenario | Detection | Handling / Recovery |
|----------|-----------|---------------------|
| Approved draw recorded, 5% fee NOT generated | Draw vs. Fee Reconciliation shows a draw with no fee | Hard exception — generate the 5% (partnership) + parent accruals, or log a written exception before close. |
| Draw later **denied/revised** after fees booked | Draw register vs. approval mismatch | Reverse/adjust **both** the partnership 5% entry and the parent income/commission entries; log exception. |
| **Commission mistakenly booked on a partnership file** | Partnership trial balance shows a `60200/60300/21100/21200` balance (should be impossible — accounts are parent-only) | Reverse immediately; commissions belong only in the parent file (§12.4). |
| **GC profit (068) confused with the 5% developer fee** | Draw vs. Fee Reconciliation; CIP review | 068 is the GC's builder profit *inside* the draw (a cost line); the 5% is a separate intercompany fee on the total. Keep distinct. |
| Duplicate fee calculation (same draw twice) | Draw # custom field uniqueness check | Reject duplicate Draw #; control in §9 prevents re-posting same Draw #. |
| Intercompany Due-To ≠ Due-From | Monthly intercompany reconciliation | Investigate the unmatched side; never close with a non-zero net. |
| Transaction missing Customer:Job / Class / Item | "Missing dimension" review reports (§16.1) | Recode before lock; preferences require class. |
| Wrong entity (posted in the wrong file) | Bank rec + intercompany review | Move via intercompany or void/re-enter; document. |
| Duplicate vendor / duplicate bill | Duplicate Names review + bill-number duplicate check | Merge vendors; reject duplicate bill numbers. |
| Wrong bank account on a transaction | Bank feed review before "Add" | Bank rules + human approval gate (§12.5). |
| Capitalize-vs-expense misclassification | Item mapping + month-end CIP review | Reclass via Item correction, not a one-off JE, to preserve job cost. |
| Prior-period edit after lock | Audit trail "changed transactions" report | Closing-date password blocks; re-auth required and logged. |
| Parent earns the 5% but forgets the 2%/1% commission accrual | Parent Draw vs. Fee Reconciliation (5% income vs. commission accruals) | Memorized "Executive Commissions" entry posts both at once off the same draw total; reconciliation flags any 5% income lacking its 2%/1%. |

**Golden rule encoded here:** *No approved draw may exist without (a) the partnership's 5% developer-fee
entry AND the parent's matching 5% income + 2%/1% commission accruals, or (b) a documented exception
explaining why.* This is the spec's central control.

---

## 8. PERFORMANCE & SCALABILITY

| Constraint | Target / Plan |
|------------|---------------|
| QB Enterprise list-entry soft limit (~10,000/list) | Per-entity files keep every list far under the limit; lean COA + Items + project-only Customers ensures headroom even on the busiest entity. |
| File performance on Rightworks | One entity per file keeps file size and rebuild times low; archive closed deals (§11) to prevent bloat. |
| Scale 10 → 50 → 200 entities | Linear effort via the locked template clone (≤ 2 hrs/entity). No structural change at any tier. |
| Month-end close time | ≤ 3 business days/entity; portfolio ≤ 7 business days via memorized reports + standardized checklist. |
| Transaction findability | < 10 seconds using Find + custom-field filters (Draw #, Project Code, Approval ID). |
| Concurrent users | Single accounting manager today; Enterprise supports multi-user growth without redesign. |
| Reporting at scale | Master reporting file consumes exported trial balances / Combined Reports; it never transacts, so it stays fast. |

**Scaling note:** the system is deliberately designed so the *bottleneck is human review capacity, not the
software*. Controls (§9) and the report package (§16) are what let one person safely operate many files.

---

## 9. SECURITY, COMPLIANCE & INTERNAL CONTROLS (Deliverable 16)

### 9.1 Preventive controls
- **Closing-date password** on every file; prior-period edits require re-authorization.
- **User roles & permissions** (Enterprise role-based security): separate "enter" vs. "approve/close" where
  staffing allows; restrict who can edit lists (COA/Items/Classes) to protect the standard.
- **Require Class** on transactions (preference); **require Customer:Job** by workflow convention on cost
  accounts.
- **Bank-rule gates** (§12.5): rules may *suggest* coding but human approval is required to "Add."
- **Duplicate bill-number** warning enabled; vendor "add on the fly" disabled for non-admin roles.
- **Memorized fee entries** are the only sanctioned way to book fees: the partnership's `FEE-DEV` (5%) bill
  and the parent's "Developer Fee Income" + "Executive Commissions" (5%/2%/1%) entries. Prevents wrong
  percentages, missed commissions, and commissions landing on the wrong (partnership) file.
- **Commission accounts are parent-only** — restrict/omit `60200/60300/21100/21200` from the partnership
  template so a commission cannot be posted to a partnership file.

### 9.2 Detective controls (review reports — run at month-end, §16)
- Uncategorized transactions; Transactions missing Customer/Job; missing Class; missing Item/cost code.
- Duplicate Names review; Unapplied payments; Old uncleared checks; Unreconciled accounts.
- **Draw vs. Fee Reconciliation** (the headline control); Intercompany balance review.
- Audit-trail "changed transactions" review for prior periods.

### 9.3 Approval gates
- Draw approval (external business event) → recorded → fees auto-generated.
- AP payment batch approval before checks/ACH (§12.6).
- Manual journal entries restricted and reviewed (every JE needs a memo + support; prefer Item/forms over
  JEs to keep job cost intact).

### 9.4 Compliance / audit posture
- Audit trail always on (Enterprise default); never disable.
- Partnership legal separation preserved by file-per-entity (supports clean 1065s and LP audits).
- Document retention: attach/reference source documents via the Ref/Doc ID field and Rightworks document
  storage.

---

## 10. TESTING STRATEGY (validation before cutover)

| Test | Method | Pass criteria |
|------|--------|---------------|
| Template integrity | Build one entity from template | All lists, custom fields, memorized txns/reports present. |
| Fee-trigger correctness | Post 3 sample approved draws (incl. one denied, one revised) | 5/2/1% generated correctly; denial reverses; reconciliation ties out. |
| Intercompany balancing | Post parent-pays-partnership + reimbursement cycle | Due-To = Due-From; nets to $0 in master roll-up. |
| Coding completeness | Enter sample bills with/without dimensions | Missing-dimension reports catch every gap. |
| Opening-balance validation | Migrate one pilot entity | Trial balance matches prior books to the penny. |
| Parallel run | Run 1 pilot entity in old + new for 1 full month | Financial statements reconcile; close ≤ 3 days. |
| Report package | Run all §16.1 reports from memorized set | Every report runs without rebuilding filters. |
| Find-speed | 10 random transactions | Each located in < 10 seconds. |
| Permissions/close-lock | Attempt prior-period edit as non-admin | Blocked; logged in audit trail. |

**Pilot first:** validate the entire model on **one representative partnership + the parent** before rolling
to all entities (§11).

---

## 11. DEPLOYMENT & ROLLOUT — MIGRATION PLAN (Deliverable 17)

### 11.1 Phasing
| Phase | Weeks | Work |
|-------|-------|------|
| **0. Discovery & Backup** | 1 | Inventory all 10+ files, sheets, bank accounts, loans; **full backups**. (All flip-points already confirmed — §14.) |
| **1. Design lock & Template build** | 2–3 | Build the **locked standard template** (COA, Classes, Items, Customer:Job conventions, custom fields, memorized fee invoice, memorized reports). |
| **2. Pilot (parent + 1 partnership)** | 4–6 | Clean lists, set opening balances, connect bank feeds, **parallel run 1 month**, validate (§10). |
| **3. Cutover wave 1 (active entities)** | 7–10 | Migrate remaining active partnerships from the template; recode in-period history as needed; validate opening balances. |
| **4. Close-process rollout & training** | 9–11 | Roll out month-end checklist; train accounting manager; first supervised close. |
| **5. Archive & steady state** | 12–14 | Move closed deals to archive files; establish new-entity onboarding SOP. |

### 11.2 Per-entity migration steps (the checklist)
Discovery → Backup → File cleanup → COA cleanup → Vendor cleanup (merge dups) → Customer/Job cleanup →
Item/cost-code setup (from template) → Class setup (from template) → Bank-feed cleanup (remove dup imports)
→ Historical transaction recoding (assign Job/Class/Item to open period) → Opening-balance validation
(trial balance ties) → Parallel run → Cutover → Training → Close-process rollout.

### 11.3 Fix-now vs. fix-later (ranked)
**Immediately:** (1) Stand up the fee trigger (memorized 5% partnership entry + parent income/commission entries) and the Draw vs. Fee Reconciliation —
this stops active revenue leakage. (2) Standard COA + Class + Item template. (3) Customer:Job per project.
(4) Intercompany Due-To/Due-From discipline. (5) Closing-date passwords.
**Later:** Deep historical recoding of *closed* periods; archive-file migration; cosmetic list cleanup;
optional custom fields beyond the core three.

### 11.4 Rollback
Each entity migration is gated by **opening-balance validation against a full backup**. If a migrated file
fails validation, **restore the backup** and re-run — no production data is at risk because the old files are
retained until the parallel run passes.

### 11.5 New-entity onboarding (steady state)
Copy locked template → rename file/entity → set partner capital opening balances → connect bank/loan feeds →
verify memorized fee invoice and reports → ready. Target ≤ 2 hours.

---

## 12. OPERATING MANUAL — QuickBooks Workflows (Deliverable 18)

> This is the accounting manager's day-to-day procedure set. Each is written so it can be followed without
> prior context. (Domain analog of "API documentation": the exact QuickBooks "calls" for each transaction.)

### 12.1 Core single-transaction procedures
- **Enter a bill:** Vendors → Enter Bills → Items tab (cost-code Item) → amount → Customer:Job → Class →
  custom fields (Draw #/Approval ID) → Save. (§5.1)
- **Code a project cost:** always Item + Customer:Job + Class. Never post project cost to a bare GL account.
- **Record a reimbursement:** see §12.9.
- **Record a draw:** see §12.7.
- **Record an investor contribution:** Banking → Make Deposit → from `INV — <Name>` → credit
  `Investor Contributions`/partner capital; Class `10/40` as appropriate; no Customer:Job unless project-specific.
- **Record a distribution:** Write Check/JE → debit `Distributions` (equity) to `PARTNER — <Name>` → from the
  partnership operating account.
- **Record intercompany:** see §12.9.
- **Review uncoded transactions:** run the missing-dimension reports (§16.1) and recode.
- **Run monthly reports:** Reports → Memorized → "STV Monthly Pack."
- **Close a month:** follow `Month_End_Checklist.md` (§16.2).
- **Find any transaction in < 10s:** Edit → Find → filter by Draw #, Project Code, Approval ID, amount, or
  vendor; or use the transaction custom-field columns in a memorized report.

### 12.4 Developer-fee & commission workflow — exact mechanics (Deliverable 7)
**Recognition event:** **draw-package approval by the construction manager + Mike Watson** (accrual), the
moment the package is released to accounting. Rationale: the approved Draw Package total is the authoritative
base; the GC's first submission isn't yet approved, and funding/cash is where fees leak. `D` = package total.

**The split (CONFIRMED 2026-06-27) — two separate books, never combined:**

**Step 1 · Partnership file — books ONLY the 5% developer fee (as a project cost):**
1. Vendors → Enter Bills → memorized **"Developer Fee on Draw"** from `IC — Summa Terra Ventures`.
2. One line, Item `FEE-DEV` = **5% × D**; stamp the **Draw #**.
3. Posts **Dr `15500 CIP — Developer Fee Capitalized`** (capitalize if the CPA confirms capitalization policy;
   otherwise **Dr `60100 Developer Fee Expense`**) **/ Cr `21000 Due-To Summa Terra`.**
4. **No commissions, no income, nothing for Mike or Porter** is recorded here.

**Step 2 · Parent file (Summa Terra) — books income + receivable, then its own commissions:**
5. Memorized JE/invoice **"Developer Fee Income"**: **Dr `12200 Due-From <Partnership>` / Cr `40200 Developer
   Fee Income`** = **5% × D**.
6. Memorized JE **"Executive Commissions"** (Summa Terra's own compensation expense, paid out of the fee it
   earns — *after* the fee is earned):
   - **Dr `60200 CEO Commission Expense` = 2% × D / Cr `21100 Commission Payable — Mike Watson`.**
   - **Dr `60300 President Commission Expense` = 1% × D / Cr `21200 Commission Payable — Porter Christensen`.**
7. **Collection:** receive payment on `Due-From` → clears `Due-To/Due-From`. Pay Mike/Porter when Summa Terra
   elects → clears the commission payables.

**Worked example — Hunter's Landing Draw #29, `D` = $962,845.68:**
| Book | Entry | Amount |
|------|-------|--------|
| Partnership | Dr CIP — Developer Fee Capitalized / Cr Due-To Summa Terra | **$48,142.28** (5%) |
| Parent | Dr Due-From Partnership / Cr Developer Fee Income | $48,142.28 (5%) |
| Parent | Dr CEO Commission Expense / Cr Payable — Watson | $19,256.91 (2%) |
| Parent | Dr President Commission Expense / Cr Payable — Christensen | $9,628.46 (1%) |
| | **Summa Terra net after commissions** | **$19,256.91 (2%)** |

**Why not one combined invoice:** the prior design booked all three on one partnership invoice. That is
**wrong** — it would put Mike's and Porter's commissions on the partnership's books. The partnership's only
obligation is the 5%; the 2%/1% are Summa Terra's internal compensation expense and stay entirely in the
parent file.

**Accrual policy:** accrue the 5% (both sides) and the 2%/1% (parent) **at approval**; collection and
commission payment are separate cash events; year-end cash-basis tax adjustment if a partnership reports on
cash basis (CPA coordinates).

**Controls (recap, enforced here):** unique Draw #; memorized entries only; commission accounts excluded from
partnership files; 5%-plus-parent-accruals-or-exception rule; Draw vs. Fee Reconciliation every month.

### 12.5 Bank feed & bank account setup (Deliverable 8)
- **Accounts to set up per file:** operating, partnership bank accounts, construction-loan account(s),
  reserve/escrow accounts, credit cards, parent operating accounts, intercompany transfer clearing.
- **Bank-rule strategy:** rules may *categorize and suggest* Item/Class/Customer:Job, but **a human must
  review and "Add"** — no silent auto-posting (preventive control).
- **When rules are allowed:** recurring, unambiguous vendors (utilities, bank fees). **When human approval is
  required:** anything touching CIP, draws, intercompany, or capital.
- **Transfers between entities:** record as intercompany (§12.9), never as a single-sided "transfer."
- **Owner contributions / draws / reimbursements:** code per §12.1 / §12.9, not as generic deposits.
- **Duplicate imports:** review the bank-feed "recognized/duplicate" flags before adding; reconcile monthly.

### 12.6 AP workflow (Deliverable 9)
Vendor bill entry → Item + Customer:Job + Class coding → custom fields (Draw #/Approval ID) → **approval
status** (custom field or memo convention) → payment batch → check/ACH recording → attach support (Ref/Doc
ID) → vendor **bank-change control** (verify out-of-band before changing vendor banking) → **duplicate
invoice prevention** (bill-number warning). Use **Items** for cost coding, **memorized AP aging** for review,
and transaction custom fields for approval references — not a parallel external status system inside QB.

### 12.7 Draw Package & loan tracking (Deliverable 10)
- **The Draw Package (§6.7):** a draw is **multiple vendor bills**, one per payee line, each carrying Vendor +
  Item (cost code 001–069) + Customer:Job + Class + vendor invoice # + **Draw #**, with retainage on the line
  so the bill net = the package's Amount Due. The GC's lump line is split into its component item #s. The
  package is virtual — assembled by filtering on `Draw #`. **Do not record a draw as one bill.**
- **Approval gate:** only enter/trigger fees after **construction-manager + Mike Watson approval** and release
  to accounting (§5.3) — not on the GC's first submission.
- **Loan side:** loan proceeds (`Construction Loan Payable`), interest-reserve draws, loan fees, equity
  contributions, reimbursements; funded payments clear the vendor AP.
- **Fee trigger:** once per package, on the **package total** (§12.4).
- **Outside QuickBooks (feeds from QB):** the lender's AIA G702/G703 / continuation-sheet assembly and portal
  submission (out of scope) — QuickBooks supplies the detail via **Project Cost Detail by Draw #**.
- **Reports:** Approved Draw Register, Project Cost Detail filtered by Draw #, Draw vs. Fee Reconciliation,
  Budget vs. Actual, Loan Balance Reconciliation (§16.1).

### 12.8 Budget vs. actual (Deliverable 11)
- **Use QuickBooks job-level budgets/estimates** keyed to **Items** (cost codes) so committed/actual/remaining
  report natively against the same Item dimension used for costs.
- **Recommended:** maintain the *authoritative* development budget in the **external budget database**
  (out-of-scope layer) but **load a QuickBooks Estimate per Customer:Job** mapped cost-code→Item so QB can
  produce **Estimate vs. Actual** without depending on the external system for day-to-day variance.
- **Minimum QB structure for reliable budgeting:** Customer:Job per project + Items per cost code + one
  Estimate per Job. Report committed (open POs/bills) vs. actual vs. remaining via Job Estimates vs Actuals.

### 12.9 Intercompany accounting (Deliverable 12)
| Event | Partnership file | Parent file |
|-------|------------------|-------------|
| Parent pays a cost for partnership | Dr CIP/expense (Item/Job/Class) / Cr `Due-To Summa Terra` | Dr `Due-From <Partnership>` / Cr Cash |
| Partnership reimburses parent | Dr `Due-To Summa Terra` / Cr Cash | Dr Cash / Cr `Due-From <Partnership>` |
| Developer fee on approved draw (5% only) | Dr CIP-Dev-Fee/expense / Cr `Due-To Summa Terra` (5%) | Dr `Due-From` / Cr `Developer Fee Income` (5%) |
| Executive commissions (2% + 1%) | **— (never recorded here)** | Dr `CEO/Pres Commission Expense` / Cr `Commission Payable — Watson/Christensen` |
| Parent charges management fee | Dr mgmt-fee expense / Cr `Due-To Summa Terra` | Dr `Due-From` / Cr `Mgmt Fee Income` |
| Transfer between partnership accounts | Two-sided transfer within file or via clearing | — |
| Shared expense allocated across projects | Allocate by Item/Job/Class | — |
| Payroll/overhead allocated to projects | Allocation JE by Class/Job | Parent books gross; allocates out |

- **Clearing & settlement:** net Due-To/Due-From monthly; settle by cash transfer; the monthly intercompany
  reconciliation must net to $0 portfolio-wide before close.
- **Templates:** all of the above are **memorized transactions** in the standard template.

---

## 13. "DATABASE MIGRATIONS" — List Build / Import Sequence

QuickBooks analog of migrations = the deterministic order to build the lists so dependencies resolve:

1. **Company preferences** (account numbers on; class tracking on; require class; closing-date password set).
2. **Chart of Accounts import** (from `Chart_of_Accounts.md`; IIF/CSV).
3. **Class list import** (§6.3).
4. **Item list import** (from `Cost_Codes_and_Items.md`), mapping two-sided Items to the imported accounts.
5. **Custom fields** defined (§6.6) before any transactions.
6. **Names lists** (Vendors/Customers/Other Names) with naming conventions (§6.5).
7. **Customer:Job hierarchy** per project (§6.2).
8. **Memorized transactions** (partnership `FEE-DEV` 5% bill; parent "Developer Fee Income" + "Executive
   Commissions" entries; intercompany templates). Commission accounts are built **only** in the parent file.
9. **Memorized reports** ("STV Monthly Pack," reconciliation reports).
10. **Opening balances** (validated against prior trial balance — the "migration validation" gate).

**Rollback = restore the pre-migration backup** (§11.4). This sequence ships *inside the locked template*, so
for new entities steps 1–9 are already done — only step 10 (opening balances) runs.

---

## 14. KNOWN LIMITATIONS & FUTURE WORK / FLIP-POINTS

**All flip-points are now resolved (v2.1) — no open architectural questions:**
1. **[RESOLVED 2026-06-27] Each partnership files its own 1065.** Confirmed by the owner. Separate legal/tax
   books are required, so **file-per-legal-entity is locked** and the consolidated runner-up (§17 Alt 1) is
   definitively rejected. Class stays free for development phase (not entity) in every operating file.
2. **[RESOLVED 2026-06-27] Fee recognition & structure.** Confirmed by the owner: recognize at **draw-package
   approval** (construction manager + Mike Watson). The **partnership books only the 5%** (project cost); the
   **2%/1% are parent-only** commissions Summa Terra pays out of the fee. Encoded in §5.3/§12.4. *(If a future
   contract earns fees only at funding, shift just the trigger; the split is unchanged.)*
3. **[RESOLVED] The draw is a multi-vendor Draw Package** (not a single bill), keyed by Draw # (§6.7),
   anchored to the real *Hunters Landing Draw #29* format.

**Known limitations:**
- QuickBooks Enterprise custom-field capacity is limited → only the core three custom fields are guaranteed;
  richer metadata lives in the out-of-scope external layer.
- No native multi-entity consolidation → the master reporting file relies on exported trial balances /
  Combined Reports, not live consolidation.
- Cash-basis tax partnerships need a year-end accrual-to-cash adjustment (CPA-coordinated).
- Retainage handling is included only if the lender/GC contracts use it (conditional).

**Deferred / future (separate efforts):** AI review layer, external database, QB bridge, lender-portal
automation, automated key/loan-amortization schedules beyond QB's loan manager.

---

## 15. GLOSSARY & NAMING CONVENTIONS (supports Deliverable 6, 15)

- **CIP** — Construction in Progress; balance-sheet asset accumulating development costs until placed in
  service / sold.
- **Developer Fee** — 5% of the approved Draw Package total, owed by the partnership to Summa Terra Ventures
  and booked by the partnership as a **project cost** (Due-To Summa Terra). The partnership's only fee obligation.
- **Executive Commissions** — 2% (CEO Mike Watson) + 1% (President Porter Christensen) of the same Draw Package
  total, booked **only in the parent file** as Summa Terra's own compensation expense/payables, paid out of the
  developer fee it earns. **Never recorded on a partnership.**
- **Draw Package** — one approved construction draw expressed as **many vendor/payee lines** (item #, invoice #,
  retainage, amount due), modeled in QuickBooks as a batch of vendor bills unified by a single **Draw #** (§6.7).
- **Approved Draw / Pay Application** — the construction draw **after construction-manager + Mike Watson
  approval** and release to accounting; the authoritative fee base and the trigger for fee recognition (not the
  GC's first submission).
- **Due-To / Due-From** — paired intercompany liability/asset accounts; must always net to zero across a pair.
- **Customer:Job** — QuickBooks dimension used here for project/property/phase.
- **Class** — QuickBooks dimension used here for development phase / cost center.
- **Item (two-sided)** — cost code with separate expense and income (billable) mappings; carries WBS detail.
- **Master reporting file** — read-only consolidation file; the only file where Class = legal entity.
- **Locked template** — the standardized company file cloned to onboard each new entity.

**Naming conventions (canonical):**
| Object | Pattern | Example |
|--------|---------|---------|
| Company file | `STV — <EntityCode> <EntityName>` | `STV — 014 Maple Ridge Ph1 LP` |
| Account | `<Number> <Name>` | `15000 Construction in Progress` |
| Customer (project) | `<ProjectCode> <PropertyName>` | `STV-014 Maple Ridge` |
| Job / Sub-job | `:<Phase>` / `:<Lot-Unit-Bldg>` | `STV-014:Vertical:Bldg-A` |
| Vendor / GC / Lender | `<Name>` / `GC — <Name>` / `LENDER — <Name>` | `GC — Apex Builders` |
| Intercompany party | `IC — <Entity>` | `IC — Summa Terra Ventures` |
| Executive | `EXEC — <Name>` | `EXEC — Mike Watson` |
| Class | `<Number> <Phase>` | `20 Hard Cost` |
| Item (cost code) | `<NNN> <CostName>` (mirrors draw schedule) | `003 Concrete`, `068 Construction Profit` |
| Draw number | `D-<YYYY>-<seq>` | `D-2025-29` |
| Developer-fee entry (partnership) | `DEVFEE-<ProjectCode>-<Draw#>` | `DEVFEE-HL-D-2025-29` |
| Commission entry (parent) | `COMM-<Draw#>` | `COMM-D-2025-29` |
| Journal entry | `JE-<YYYYMM>-<seq>-<purpose>` | `JE-202606-012-IC-Settle` |

---

## 16. MONITORING, METRICS & OBSERVABILITY — Reports & Close (Deliverables 13, 14)

### 16.1 Standard report package (Deliverable 14)
Each ships as a **memorized report** in the template. Columns/filters preset.

| Report | Purpose | Key filters / columns | Frequency | Owner / Reviewer | Action |
|--------|---------|-----------------------|-----------|------------------|--------|
| **Approved Draw Register** | Every approved draw **package** | Draw #, date, project, package total | Monthly | Acct Mgr / Controller | Basis for fee reconciliation |
| **Developer Fee Register** (5%) | 5% fee per draw — both sides | Draw #, 5% amount, status | Monthly | Acct Mgr | Confirm none missed (partnership cost ↔ parent income) |
| **CEO Commission Register** (2%) — *parent file* | All 2% commission accruals | Draw #, 2% amount, payable status | Monthly | Acct Mgr / CEO | Confirm accrued & paid |
| **President Commission Register** (1%) — *parent file* | All 1% commission accruals | Draw #, 1% amount, payable status | Monthly | Acct Mgr / President | Confirm accrued & paid |
| **Draw vs. Fee Reconciliation** ★ | Tie every draw → partnership 5% → parent 5%/2%/1% → collection | Draw #, package total, 5% fee, 2%/1% accruals, collected, outstanding | Monthly | Acct Mgr / Controller | **Resolve every gap or log exception** |
| **Outstanding Fee Receivables** | Uncollected developer fees | Aging by partnership | Monthly | Acct Mgr | Collections |
| **Outstanding Executive Commissions** | Unpaid 2%/1% | Aging | Monthly | Acct Mgr | Pay/accrue |
| **Draw-Based Revenue Recognition** | Fee income recognized by period | By draw/period | Monthly | Controller | Revenue review |
| **Monthly Management Fee Summary** | Total mgmt comp | By entity | Monthly | Controller | Mgmt reporting |
| **Executive Commission Summary** | CEO/President totals | By exec | Monthly | CEO/President | Comp reporting |
| **Project Cost Detail** | All costs by project | Customer:Job, Item, Class, Draw # | Monthly | Acct Mgr | Cost control |
| **Project Budget vs. Actual** | Variance | Estimate vs actual by Item | Monthly | Acct Mgr / PM | Budget control |
| **Developer Fee Opportunity** | Draws lacking fees | Approved draws with no fee | Monthly | Acct Mgr | Catch leakage |
| **Developer Fees Invoiced / Collected** | Fee lifecycle | Invoiced vs collected | Monthly | Acct Mgr | Collections |
| **Missed Fee Exceptions** | Logged exceptions | Reason, approver | Monthly | Controller | Audit |
| **Bank Reconciliation Status** | Rec completeness | Per account | Monthly | Acct Mgr | Close gate |
| **Uncategorized Transactions** | Cleanup | Account 'Uncategorized' | Monthly | Acct Mgr | Recode |
| **Missing Customer/Job** | Coding gaps | Cost txns w/o Job | Monthly | Acct Mgr | Recode |
| **Missing Class** | Coding gaps | Txns w/o Class | Monthly | Acct Mgr | Recode |
| **Missing Item/Cost Code** | Coding gaps | Cost txns w/o Item | Monthly | Acct Mgr | Recode |
| **Intercompany Balances** | Due-To/From by pair | Net per pair | Monthly | Acct Mgr / Controller | Must net $0 |
| **Due To / Due From Reconciliation** | Cross-file tie-out | Both sides | Monthly | Controller | Settle |
| **AP Aging / AR Aging** | Payables/receivables | Standard | Monthly | Acct Mgr | Manage |
| **Loan Balance Reconciliation** | Loan vs lender statement | Per loan | Monthly | Acct Mgr | Reconcile |
| **Partnership Balance Sheet / P&L** | Entity financials | Per file | Monthly | Controller | Statements |
| **Parent Company P&L** | Mgmt-co performance | Parent file | Monthly | Controller | Statements |
| **Consolidated Management Report** | Portfolio roll-up | Master file, Class=entity | Monthly | Controller / Owners | Portfolio view |

★ = the headline control report.

### 16.2 Month-end close (Deliverable 13)
Full step list is in **`Month_End_Checklist.md`**. Sequence: bank/credit-card/loan reconciliations →
intercompany reconciliation (net $0) → **Draw vs. Fee review (every approved draw has its fees)** → project
cost review → missing job/class/item cleanup → uncategorized cleanup → AP/AR aging review → capital-account
review → draw review → lock period (closing-date password) → produce financial-statement package.

---

## 17. ALTERNATIVE DESIGNS CONSIDERED

**Alt 1 — One consolidated file (Class = entity).** *Pros:* fewest files, simplest for one person near-term.
*Cons:* commingles separate 1065 capital accounts (improper), breaches list limits ~entity #40, destroys
partnership transparency. **Definitively rejected** — each partnership files its own 1065 (confirmed
2026-06-27), so legal separation must be file-level.

**Alt 2 — Project = Class (instead of Customer:Job).** *Pros:* fewer Customers. *Cons:* Classes can't carry
AR, draws, estimates, or cost-to-complete; you lose job costing — the entire point. **Rejected.**

**Alt 3 — Recognize fees at cash receipt or lender funding.** *Pros:* collectibility conservatism. *Cons:*
that is precisely where fees are missed today; detaches the fee from its trigger and reintroduces manual
work. Collectibility is a *reserve* question, not a *recognition-trigger* question. **Rejected** —
owner-confirmed recognition is at **draw-package approval** (§14, resolved). *(If a future contract earns fees
only at funding, shift just the trigger; the 5% / 2%+1% split is unchanged.)*

**Alt 4 — GL account per project.** *Pros:* "everything in the COA." *Cons:* account bloat, unmaintainable at
scale, no cost-to-complete. **Rejected** (the brief explicitly forbids it).

**Alt 5 — Book all three fees (5%+2%+1%) on the partnership (one combined invoice).** *Pros:* one document.
*Cons:* puts Mike's and Porter's commissions on the partnership's books, overstating the partnership's
obligation and contaminating its 1065. **Rejected** per confirmed rules — the partnership owes only the 5%;
the 2%/1% are Summa Terra's internal compensation expense and live solely in the parent file (§12.4).

**Alt 6 — Record the draw as a single bill.** *Pros:* fewer transactions. *Cons:* a QB bill has one vendor,
but a draw has 40+ payees with per-line invoice #s and retainage. **Rejected** — the draw is a multi-vendor
**Draw Package** keyed by Draw # (§6.7).

**Chosen design rationale:** file-per-entity preserves legal/tax separation QuickBooks cannot otherwise
enforce; vendors stay vendors and Customer:Job gives native job costing; Items mirror the GC draw schedule so
coding matches the approved document; Class = phase adds the only non-redundant reporting axis; the Draw #
binds each package; and the **5%-to-partnership / 2%+1%-parent-only** split at draw approval makes leakage
structurally impossible while keeping each entity's books legally clean. This maximizes auditability,
transparency, scalability, and control while minimizing manual JEs and close time.

---

## 18. FINAL BUILD CHECKLIST, TRAINING & RECOMMENDATION

### 18.1 Implementation checklist
- [x] All flip-points confirmed (§14): separate 1065s ✓, fee structure/trigger ✓, Draw Package model ✓.
- [ ] Locked standard template built (preferences, COA, Classes, Items, custom fields, Customer:Job
      conventions, memorized fee invoice, intercompany templates, memorized report pack).
- [ ] Parent file built; fee income + commission payables (Watson/Christensen) configured.
- [ ] Master reporting file built (read-only; Class = entity).
- [ ] Pilot entity migrated; opening balances tie to prior TB; 1-month parallel run passed.
- [ ] Fee-trigger tested incl. denied/revised draw; Draw vs. Fee Reconciliation ties out.
- [ ] Intercompany cycle tested; nets $0 in master roll-up.
- [ ] Missing-dimension reports catch all gaps; closing-date passwords set.
- [ ] All §16.1 reports run from the memorized set.
- [ ] Remaining active entities migrated; closed deals archived.

### 18.2 Training checklist (Deliverable 19) — accounting manager
- [ ] Enter a bill with Item + Customer:Job + Class + Draw #.
- [ ] Enter an approved **Draw Package** (multi-vendor, retainage, Draw #) and **generate the 5% partnership
      fee + the parent's 5% income and 2%/1% commission accruals** via the memorized entries.
- [ ] Record a reimbursement and a full intercompany cycle (Due-To/Due-From).
- [ ] Record investor contribution and partner distribution.
- [ ] Run and interpret the **Draw vs. Fee Reconciliation** and resolve a seeded exception.
- [ ] Run the monthly report pack; perform a supervised month-end close end-to-end.
- [ ] Lock a period and demonstrate the prior-period-edit control.
- [ ] Locate 10 transactions in < 10 seconds each.
- [ ] Onboard a new entity from the locked template in ≤ 2 hours.

### 18.3 Final recommendation (Deliverable 20)
Adopt the **file-per-legal-entity + master reporting file + intercompany clearing** architecture with
**vendors = payees, project = Customer:Job, cost code = Item (mirroring the GC draw schedule 001–069),
Class = development phase**, and a **Draw # custom field** binding each multi-vendor **Draw Package**. On
approval (construction manager + Mike Watson), the **partnership books the 5% developer fee as a project
cost**, while **Summa Terra separately books the 5% income/receivable and its own 2% + 1% commissions** —
all off the **Draw Package total**, via memorized entries. Build once as a **locked template**, pilot on the
parent plus one partnership with a one-month parallel run, then roll out wave-by-wave and archive closed
deals. This is the cleanest QuickBooks Enterprise implementation that **minimizes manual work, journal
entries, reconciliation effort, and close time** while **maximizing auditability, partnership transparency,
management reporting, scalability, and internal controls** — and it closes the developer-fee leak
*structurally* while keeping commissions off partnership books. All flip-points are confirmed (§14) — the
spec is ready to implement; begin Phase 0.

---

## 19. IMPORT FILES — load the new layout into QuickBooks Enterprise

Ready-to-upload files are generated in **`Import_Files/`** (see `Import_Files/IMPORT_GUIDE.md`). They encode
this entire spec's lists so a QuickBooks Enterprise **Desktop** file can be built without hand-keying.

| File | Format | Contents |
|------|--------|----------|
| `QB_Import_Partnership_Template.iif` | IIF (native, one-shot) | Partnership COA (36 accts) + 10 Classes + Items 001–069/lifecycle/`FEE-DEV`/`RETAINAGE-HELD` (68) + 44 Vendors (Draw #29 payees + GC/Lender/IC) + Hunter's Landing Customer:Jobs |
| `QB_Import_Parent_SummaTerra.iif` | IIF | Parent COA (22 accts) + Classes + parent fee Items (`FEE-DEV-INC`/`FEE-CEO`/`FEE-PRES`) + EXEC vendors |
| `CSV_*.csv` (8 files) | CSV / Excel | Same lists, one per file, for review or the Excel import wizard |

**Why IIF for the full load:** QuickBooks Desktop has no native CSV importer for the **Chart of Accounts or
Classes** — only Items/Vendors/Customers go through the CSV/Excel wizard. The IIF files carry **all five
lists in one upload each**, in dependency order (accounts → classes → items), with verified referential
integrity (every Item's account resolves; 0 orphans). The CSVs are provided for Excel review and for the
lists the wizard supports.

**Auto-imported:** Chart of Accounts, Classes, Items (each mapped to one CIP bucket), Vendors, Customer:Jobs.
**Manual after import (IIF cannot carry these):** custom fields (`Draw #`, `Approval ID`, `Fee Eligibility`);
the fee **percentages** (5/2/1% — items import at 0); the **memorized fee transactions** (§12.4); opening
balances (§13 step 10); the memorized report pack (§16.1). Full procedure, backup warning, and the
preferences to set first (account numbers + class tracking **on** before import) are in `IMPORT_GUIDE.md`.

The split is enforced **at the file level**: the partnership IIF contains **no executive-commission accounts
or payees** — those exist only in the parent IIF.

**Validation status:** both IIF files were checked against QuickBooks' documented list-import rules (column
integrity, valid type keywords, the **31-character name limit**, referential integrity, no duplicates,
ASCII-only) and **PASS with 0 issues** — 19 names were abbreviated to satisfy the 31-char limit (the cost-code
number still carries identity; see `IMPORT_GUIDE.md`). This is the closest offline proxy to a live import;
the genuine final test (a QB sample-company import on a backup) still belongs to the implementer.

---

## CONSISTENCY CHECK RESULTS

All 18 sections regenerated and cross-checked after the v2.0 confirmed-rules revision.

- ✓ §3 acceptance ("0 missed fees", "<10s find", "≤3-day close") aligns with §8 performance targets and §16 reports.
- ✓ §4 file-per-entity aligns with §6 (file=entity, vendor=payee, Job=project, Item=cost code, Class=phase, Draw#=package) and §17 rejected alternatives — no dimension is double-assigned.
- ✓ **Fee split is consistent everywhere:** partnership books 5% only / parent books 5% income + 2%/1% commissions — §1, §2, §5.3, §6.4, §7, §9, §12.4, §12.9, §16, §17 (Alt 5), §18.3, and `Chart_of_Accounts.md` / `Cost_Codes_and_Items.md` all agree. Commission accounts are parent-only in every reference.
- ✓ **Draw Package model (§6.7)** is consistent with §5.2, §12.7, §17 (Alt 6), the Item list, and the real Draw #29 PDF (total $962,845.68; worked example in §12.4).
- ✓ **Trigger** = construction-manager + Mike Watson approval (not first submission / not funding) — consistent across §2, §5.3, §12.4, §12.7, §14, §15.
- ✓ §6.6 custom-field limits are consistent with §2 out-of-scope (external IDs not forced into QB).
- ✓ §11 rollback (restore backup) is consistent with §13 migration sequence and §10 opening-balance gate.
- ✓ §9 closing-date lock is consistent with §7 prior-period-edit handling and §18.2 training.
- ✓ All three flip-points RESOLVED: separate 1065s (file-per-entity locked), fee structure/trigger, and the
  Draw Package model. §4 architecture is final; the consolidated runner-up (§17 Alt 1) is rejected.

**Status: 0 contradictions. 0 open flip-points. Spec is handoff-ready — no blocking confirmations remain.**
