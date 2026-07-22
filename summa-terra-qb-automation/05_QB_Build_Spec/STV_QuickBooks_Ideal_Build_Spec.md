# Summa Terra Ventures — QuickBooks Ideal-State Build Specification

```
Spec Title:        STV QuickBooks Desktop Enterprise — Ideal-State Build-Out
Version:           1.0.0
Author:            Ben Stone (incoming accountant) + Claude
Last Updated:      2026-06-25
Status:            In Design — for partner/CPA ratification of the 3 open decisions (Section 14)
Confidence Level:  ~85% — structure is sound; final entity-to-file mapping needs the CPA's
                   return-filing list (which entities file their own 1065 vs. are disregarded)
Next Steps:        Ratify Section 4 file-structure decision -> build the master template file ->
                   roll out entity by entity
Scope size:        Authoritative blueprint (design-phase). Build is phased (Section 11).
```

> **Purpose of this document.** This is the "how it *should* be" target picture for STV's books — independent of how QuickBooks is set up today. It is written so a competent accountant or bookkeeper can build it without guessing, and so the partners and CPA can see and approve the structure. Where a choice exists, the recommended option is stated first with rationale; alternatives are in Section 17.

---

## 1. EXECUTIVE SUMMARY

Summa Terra Ventures (STV) is a Utah multifamily real-estate **developer and operator** running **40+ legal entities** — project LLCs, multi-member partnerships, a development company (STDG), an entitlement/management company (STVE), and treasury/holding entities (Liberation, Wealth Follows Worth, Aubrey Partners). Each project carries its own bank accounts, construction loan, partner group, and tax return.

The ideal QuickBooks build gives STV **one clean, consistent, auditable set of books per tax-filing entity**, with a shared template so every entity looks the same, **standardized project/job and intercompany tracking**, a **disciplined monthly close and reconciliation**, **partner-capital and K-1-ready equity tracking**, and a **read-only automation bridge** (QODBC / QuickBooks Web Connector) that feeds reporting and tools without manual re-keying.

**Business outcome:** financials the partners and lenders can trust on demand; clean K-1s; no year-end scramble; less manual labor; and the ability to produce per-project and consolidated reporting automatically.

**Primary users:** Ben Stone (accountant/controller — full access); the partners, esp. **Mike & Aubrey** (read-only reporting); the **outside CPA** (year-end / external-accountant access).

---

## 2. SCOPE DEFINITION & NON-SCOPE

**In scope (the build):**
- Company-file architecture across all STV entities (how many files, how entities map to them).
- A **master chart of accounts (COA)** template with account numbering.
- **Class** and **Customer:Job** conventions for projects/phases and cost tracking.
- **Bank/credit-card account** setup + naming convention (UCCU, Mountain America, Granite, Central, AMEX).
- **Intercompany ("Due to/from")** framework and elimination method.
- **Construction-loan, draw, and capitalized-cost** accounting.
- **Partner equity** (contributions, distributions, capital accounts, K-1 mapping).
- **Developer fee / Construction-Management (CM) fee** accounting (the 5% fees).
- **Reconciliation workflow**, **month-end close**, and **period-lock** controls.
- **Reporting**: per-entity, consolidated, per-project job cost, partner-capital statements, weekly partner dashboard.
- **Users/roles/permissions** and audit-trail settings.
- **Automation / data bridge** (QODBC, Web Connector, scheduled exports).

**Out of scope (explicitly):**
- The Q2-2026 catch-up data entry itself (that's the separate `04_Catch_Up` workstream).
- Tax-return preparation (the CPA owns the returns; this spec makes the books *return-ready*).
- Property-management operational software (rent roll, leasing) beyond how it posts to QB.
- Migrating historical detail older than the agreed conversion date (Section 13).
- Payroll system design (note integration points only).

**Dependencies:**
- QuickBooks Desktop **Enterprise** (Rightworks-hosted VPS).
- The CPA's list of which entities file their own returns (drives Section 4).
- Bank online-banking access for feeds (UCCU, MACU, Granite, Central, AMEX).

---

## 3. BUSINESS CONTEXT & ACCEPTANCE CRITERIA

**Business goal:** Trustworthy, timely, audit- and lender-ready multi-entity books with minimal manual effort and clean partner/K-1 tracking.

**Success metrics (measurable):**
- **Close speed:** monthly close completed by **the 10th business day** of the following month.
- **Reconciliation:** **100%** of active bank/CC accounts reconciled monthly, variance = $0 (or documented).
- **Intercompany:** every "Due to/from" pair **nets to zero across the entity group** at month-end.
- **Equity:** each member's capital account ties to the prior K-1 + current-year activity, **to the dollar**.
- **Automation:** trial balance + key reports exportable **without manual re-keying** (QODBC).
- **No plugs:** **zero** balances parked in "Ask My Accountant" at close (the $317K Arixa plug is the cautionary tale).

**Acceptance criteria (the build is "done" when):**
- [ ] A documented entity→company-file map exists and is approved by the CPA.
- [ ] A **master template company file** exists with the standard COA, classes, memorized reports, and roles.
- [ ] Every active entity is on the template; COA is consistent across files (same numbers mean the same thing).
- [ ] Every bank/CC account follows the naming convention and ties to a real statement.
- [ ] Intercompany accounts exist in matched pairs and reconcile to zero group-wide.
- [ ] Partner capital accounts exist per member with contribution/distribution sub-accounts.
- [ ] Closing-date password, user roles, and audit trail are enabled in every file.
- [ ] A monthly close checklist and reconciliation SOP are written and in use.
- [ ] The QODBC/Web Connector bridge produces a clean trial-balance export.

**Spec status:** Design-phase. If the build surfaces a conflict, update this spec (Section 14 evolution rule), don't drift silently.

---

## 4. ARCHITECTURE & SYSTEM INTEGRATION (the foundational decision)

### 4.1 Company-file structure — **RECOMMENDED: one company file per tax-filing entity**

Each entity that **files its own federal return / issues K-1s gets its own QuickBooks company file.** Rationale:
- Each multi-member partnership files a **1065** and issues **K-1s** — separate capital accounts and a clean trial balance per return are far safer in separate files than as classes in one commingled file.
- **Lenders and auditors** expect standalone financials per borrowing entity (each project has its own construction loan).
- Limits blast radius: a problem (or a fraud event like HLN's) is contained to one file.
- QuickBooks **Classes can be unreliable** as the *only* separator of legal entities (easy to post class-less transactions that silently commingle entities).

**Disregarded single-member entities** (100%-owned by another STV entity, no separate return) **do not need their own file** — carry them as a **Class** inside their owner's file, or as their own file only if banking/lender separation demands it. *The CPA's return list decides this per entity.*

**Treasury/holding entities** (Liberation, WFW, Aubrey Partners) each get a file (they hold intercompany balances and member activity).

**Naming convention for files:** `STV — [Legal Entity Name] — [EIN last4]` so files are unambiguous on the hosted desktop.

> ⚠️ **Open decision #1 (Section 14):** exact entity→file mapping. Needs the CPA's list of which entities file 1065s vs. are disregarded. The *structure* above is fixed; only the per-entity assignment is pending.

### 4.2 Within each file — Classes & Jobs

- **Class = project phase / building / cost center** within that entity (e.g., "Phase 1", "Phase 2", "Operations"). Make **class required on every transaction** (Preferences → Accounting → "require class").
- **Customer:Job = cost-tracking unit** where job costing is wanted (e.g., a GC contract or unit). Use Items for hard/soft cost categories so job-cost reports work.
- **Location/region:** not needed (single state); skip to avoid clutter.

### 4.3 Intercompany framework

- For every pair of entities that transact, create matched balance-sheet accounts:
  - Asset: **`1500 · Due From [Entity]`**
  - Liability: **`2500 · Due To [Entity]`**
- A transfer between two STV entities is booked in **both** files the same day (one's Due From = the other's Due To, equal and opposite).
- At consolidation these **eliminate** (Section 16). Monthly intercompany tie-out is part of close (Section 11).

### 4.4 Data-flow / integration map

```
Bank/CC (UCCU, MACU, Granite, Central, AMEX)
   │  (a) Web Connect / Direct Connect feed  -> QuickBooks bank feed
   │  (b) Monthly .QBO/.PDF download         -> reconciliation source of truth
   ▼
QuickBooks Desktop Enterprise (per-entity files, on Rightworks VPS)
   │  QODBC (read-only)  ->  CSV/Sheets exports  ->  Google Drive (stone@)
   ▼
Reporting layer: consolidated workbook / Looker Studio dashboard / partner pack
   │
   └─ Claude / tooling read exports for reconciliation checks & analytics (read-only)
```

**External dependencies:** Rightworks (hosting), QODBC driver (already installed), QB Web Connector v34 (installed), Google Drive (stone@). No Excel on the VPS — exports go to CSV/Google Sheets, not native xlsx on the server.

---

## 5. USER FLOWS & STANDARD WORKFLOWS (happy paths)

**5.1 Record a bank transaction (per entity)**
1. Transaction clears the bank → appears in the bank feed (or is found on the monthly .QBO).
2. Bookkeeper assigns **account + class** (+ Customer:Job if cost-tracked); adds payee + memo.
3. If it's an intercompany move, book the matching Due To/From entry in the other entity's file the same day.
4. Transaction is matched/added; running balance updates.

**5.2 Construction-loan draw**
1. Lender (e.g., **Arixa**) funds a draw.
2. Book: **Dr** Construction in Progress (CIP) / specific cost item (by class), **Cr** Construction Loan Payable – [Lender].
3. Capitalized loan fees → **Loan Costs (asset)**, amortized over loan term; **interest reserve** drawn → interest expense or capitalized per policy.
4. Every draw ties to the **lender draw schedule**; the settlement statement is the source document (no plugs).

**5.3 Partner contribution / distribution**
1. Member wires capital in → **Dr** Cash, **Cr** `3xxx · [Member] Capital – Contributions`.
2. Distribution out → **Dr** `3xxx · [Member] Capital – Distributions`, **Cr** Cash.
3. Capital account roll-forward stays current → feeds the K-1 at year-end.

**5.4 Developer / CM fee (intercompany)**
1. Project entity owes STDG/STVE a **5% developer fee / CM fee**.
2. Project file: **Dr** Development Cost – Dev Fee (capitalized to CIP), **Cr** Due To STDG/STVE.
3. STDG/STVE file: **Dr** Due From [Project], **Cr** Dev Fee Income / CM Fee Income.
4. Eliminates on consolidation; nets intercompany to zero.

**5.5 Month-end close** — see Section 11.

**Alternate/edge flows:** account migration mid-year (e.g., Central Bank → UCCU) — open the new account, transfer balance via Due-To/From or a clearing account, mark the old account inactive after final reconciliation (don't delete). Fraud/closed account — see Section 7.

---

## 6. DATA MODELS & SCHEMA (Chart of Accounts + lists)

**6.1 Account numbering** — turn ON (Edit → Preferences → Accounting → "Use account numbers"). Standard real-estate developer COA:

| Range | Category | Examples |
|---|---|---|
| **10000–14999** | **Assets — Cash & receivables** | 10xxx Bank accounts (one per real account, see naming below); 12000 Accounts Receivable; 1500/15xxx **Due From [Entity]**; 13000 Tenant/Other receivables |
| **15000–17999** | **Assets — Project & fixed** | 16000 **Construction in Progress (CIP/WIP)** (sub by class); 16500 Land; 17000 Buildings & Improvements; 17500 Accumulated Depreciation |
| **18000–18999** | **Assets — Other** | 18000 **Capitalized Loan Costs**; 18100 Prepaid Expenses; 18200 Escrow/Reserves; 18300 Earnest Money Deposits |
| **20000–24999** | **Liabilities — Current** | 20000 Accounts Payable; 21000 Accrued Liabilities; 22000 Security Deposits; 2500/25xxx **Due To [Entity]** |
| **25000–27999** | **Liabilities — Debt** | 26000 **Construction Loan Payable – [Lender]** (e.g., Arixa); 26100 Interest Reserve (contra/loan); 27000 Notes Payable – Related |
| **30000–39999** | **Equity** | 30000 Members' Capital; **3x · [Member] Capital**, with sub-accounts **– Contributions** / **– Distributions**; 35000 Syndication Costs; 39000 Retained Earnings / Members' Equity |
| **40000–49999** | **Income** | 40000 Rental Income; 41000 **Developer Fee Income**; 42000 **CM Fee Income**; 43000 Interest Income; 49000 Gain/Loss on Sale |
| **50000–59999** | **Development / Direct costs** | 50000 Hard Costs (sub by trade); 51000 Soft Costs; 52000 **Recording Fees**; 53000 Architecture/Engineering; 54000 Permits & Licenses |
| **60000–69999** | **Operating expenses** | 60000 Management Fees; 61000 **Professional Fees** (legal/CPA); 62000 Insurance; 63000 Property Taxes; 64000 Utilities; 65000 Bank/Merchant Fees; 69000 **Ask My Accountant (must be $0 at close)** |
| **70000–79999** | **Other income/expense** | 70000 Interest Expense; 71000 Depreciation/Amortization |

Same number = same meaning in **every** entity file. Lock the master; entities add only entity-specific leaf accounts under the standard parents.

**6.2 Bank/credit-card account naming convention**
`[Entity] – [Bank] [Type] –[last4]` — e.g.:
- `STVE – UCCU Checking –1980`
- `STVE – UCCU Money Market –2000`
- `STVE – Mountain America Checking –S0059`
- `STDG – Granite Checking –6799`
- `HLN (Hunters Landing North) – UCCU Checking –8560`

Routing reference: **[ROUTING-REDACTED] = UCCU**, **[ROUTING-REDACTED] = Mountain America (MACU)**, Granite = separate. Never identify an account by last-4 alone (e.g., **…7470 belongs to BOTH Ventura and Dominus** — always pair last-4 with entity + bank). The authoritative account list lives in `04_Catch_Up/UCCU_Pull_List_accounts_numbers_dates.csv`.

**6.3 Lists discipline**
- **Vendors/Customers:** one record each, no duplicates (e.g., "Ricks & Co. CPA" once); merge dupes.
- **Items:** cost-code item list for job costing (hard/soft cost categories) shared across files.
- **Classes:** the project/phase list per file; keep short and meaningful.

---

## 7. ERROR HANDLING & EDGE CASES (controls & how problems are handled)

| Situation | Correct handling | Control that prevents it |
|---|---|---|
| Balance won't tie / unknown amount | Investigate to source; **never** park in "Ask My Accountant" as a permanent plug | Account 69000 reviewed every close; must be $0 |
| Plug like the **$317K Arixa** item | Trace to settlement statement; reclass to loan/contra or capitalize — not expense | Loan entries require the lender settlement statement as source doc |
| Posting to the wrong entity (last-4 collision) | Catch at reconciliation; reverse + repost | Account naming includes entity+bank; class required |
| Duplicate payment (e.g., the **2nd $800 Rock Creek**) | Pull check image; if dup, stop-payment/recover; book only the real one | Duplicate-detection on import; two-step bill-pay review |
| Bank account closed (e.g., **HLN …92090 fraud, 12/05/2025**) | Final-reconcile, transfer balance to new **…48560**, write off fraud loss / set up receivable for recovery, mark old account **inactive** (never delete) | Fraud runbook; closed-account checklist |
| Intercompany doesn't net to zero | Find the unmatched leg; book the missing side | Monthly intercompany tie-out report |
| Editing a closed period | Blocked unless authorized | **Closing-date password** |
| Bank-feed miscategorization | Reviewed before "Add"; rules used cautiously | No auto-add without review |

**Edge cases:** mid-year bank migration (Central→UCCU) handled via clearing/Due-To-From; an entity with **two checking accounts** (e.g., Summa Elite …9290 and …9280) gets two distinct cash accounts; loan-only relationships (e.g., Union's Granite loans) are **liabilities, not bank accounts**.

---

## 8. PERFORMANCE & SCALABILITY (operational targets)

- **Close cycle:** ≤ 10 business days monthly; quarterly review pack ≤ 15 days.
- **Reconciliation backlog:** never more than **1 month** behind on any active account (today's ~4-month gap is the anti-target).
- **File health:** keep each company file performant — periodic **Verify/Rebuild**, condense only with CPA sign-off, archive prior years.
- **Scale:** structure must absorb new project entities by **cloning the master template** (target: stand up a new entity's books in < 1 day).
- **Users:** Enterprise supports the needed simultaneous users on Rightworks; size the Rightworks plan to actual concurrent logins.

---

## 9. SECURITY, ROLES & COMPLIANCE

**Users & roles (QuickBooks Enterprise role-based permissions):**
- **Controller/Admin (Ben):** full access, all files.
- **Bookkeeper (if added):** transaction entry + reconciliation; **no** ability to delete or change closed periods or chart of accounts.
- **Partners (Mike, Aubrey, others):** **read-only / reports-only** access to their relevant entities.
- **Outside CPA:** **External Accountant** user (sees everything, can't see customer credit-card numbers, leaves a clean audit trail).

**Controls:**
- **Closing-date password** set in every file after each close.
- **Audit Trail / "Always on"** logging enabled (never disabled).
- **Segregation of duties** where staffing allows (entry vs. approval vs. reconciliation).
- **Bill-pay approval** step before disbursement (prevents duplicate/again-fraud).
- **Bank security:** post-fraud — dual control on wires, positive pay if the bank offers it, restricted online-banking roles.

**Compliance / records:** keep per-entity reconciliations, statements, settlement statements, and signed financials; retain per CPA/IRS guidance (generally 7 years). Books must remain **return-ready** (K-1-able) at all times.

**Access hygiene:** STV/Ben-specific credentials live in STV-controlled accounts only (the outgoing accountant's personal accounts must hold no STV data — see the OneDrive/Drive cleanup already performed).

---

## 10. TESTING / VALIDATION STRATEGY (how we prove the books are right)

- **Reconciliation = the primary test:** every active account reconciles monthly to the statement, variance $0.
- **Intercompany tie-out:** group-wide Due-To/From nets to zero each month.
- **Trial-balance review:** scan for negative balances where impossible, "Ask My Accountant" ≠ 0, uncategorized class/account.
- **Equity roll-forward check:** each member's capital = prior K-1 + contributions − distributions ± allocated income.
- **Loan tie-out:** each construction loan balance = lender's statement / draw schedule.
- **Sample audit:** monthly, pull N transactions and confirm account+class+job+memo+source doc.
- **Pre-close checklist sign-off** (Section 11) before the period is locked.
- **CPA review** at year-end as the external validation gate.

---

## 11. DEPLOYMENT & ROLLOUT (build + monthly close)

**Build rollout (phased):**
- **Phase 0 — Decide:** ratify Section 4 file map with the CPA (Open decision #1).
- **Phase 1 — Master template:** build one model company file: numbered COA, classes, items, memorized reports, roles, preferences (account numbers on, class required, closing-date password). This is the gold copy.
- **Phase 2 — Core entities first:** STVE, STDG, then the largest project entities (12SB, HLN, Summa Elite). Clone template, load opening balances at the **conversion date**, reconcile.
- **Phase 3 — Remaining entities:** roll out the rest from the template; bring each current.
- **Phase 4 — Automation:** stand up QODBC exports + Web Connector bank feeds + reporting dashboard.
- **Phase 5 — Steady state:** monthly close cadence; deprecate manual slide decks for live reporting.

**Monthly close checklist (every entity):**
1. All transactions entered & classified (account + class).
2. All bank/CC accounts reconciled to statements (variance $0).
3. Intercompany Due-To/From tie-out = 0 group-wide.
4. Accruals, prepaids amortized, depreciation, loan interest/amortization booked.
5. "Ask My Accountant" cleared to $0.
6. Review trial balance + P&L/BS for anomalies.
7. Post AJEs; save reconciliation PDFs + statements to Drive.
8. **Set closing-date password** (lock the period).
9. Produce reporting pack.

**Rollback / safety:** scheduled **backups** before any major change (COA edits, condense, merges); test restores; never edit a locked period without explicitly rolling the closing date and documenting why.

---

## 12. AUTOMATION & "API" INTERFACES (the data bridge)

This is STV's version of an API layer — how data moves in and out without manual re-keying.

- **Inbound (bank → QB):** QuickBooks **Web Connect / Direct Connect** feeds per bank where supported (UCCU, MACU, AMEX). Where not supported, monthly **.QBO import** + PDF statement.
- **Outbound (QB → reporting/tools):** **QODBC** (read-only) queries the company files on the VPS → scheduled **CSV / Google Sheets** exports to Drive (stone@). No Excel on the VPS, so target CSV/Sheets, not server-side xlsx.
- **Standard export set:** Trial Balance, P&L, Balance Sheet, A/R & A/P aging, intercompany balances, per-class job cost — per entity + consolidated.
- **Cadence:** nightly or weekly scheduled export; on-demand for close.
- **Consumers:** the partner dashboard (Section 16) and reconciliation/analytics tooling (incl. Claude), all **read-only**.
- **Controls:** QODBC user is read-only; exports never write back to QB; credentials in STV-controlled storage.

---

## 13. "MIGRATIONS" — FILE SETUP & OPENING BALANCES

QuickBooks equivalent of database migrations = how each entity's file is created and seeded.

- **Conversion date:** pick a clean cutover (recommended: **start of the current fiscal year**, or a reconciled month-end). Enter **opening trial balance** as of that date from the last reconciled financials; keep prior-year detail archived, not re-keyed.
- **Per-entity setup steps (repeatable):**
  1. Clone the **master template** (COA, classes, items, roles, preferences, memorized reports).
  2. Enter opening balances (assets, liabilities, loans, member capital) as of conversion date.
  3. Add the entity's specific **bank/CC accounts** (naming convention) and **classes/jobs**.
  4. Reconcile each bank account to the conversion-date statement.
  5. Verify equity = last K-1 capital; verify loans = lender balances.
  6. Turn on closing-date password once opening balances are signed off.
- **Validation after setup:** trial balance balances; opening equity ties to prior return; no "Ask My Accountant" balance carried in.

---

## 14. KNOWN LIMITATIONS, OPEN DECISIONS & FUTURE WORK

**Open decisions for partner/CPA ratification:**
1. **Entity → company-file mapping** (Section 4): which entities get their own file vs. ride as a class of a parent. Needs the CPA's return-filing list. *Highest-priority decision; everything else clones from the template regardless.*
2. **Consolidation method** (Section 16): QuickBooks "combine reports for multiple files" vs. a third-party consolidator (Qvinci/Fathom) vs. a QODBC-fed Google Sheet/Looker model. Recommended: start with QODBC-fed consolidation workbook; revisit a paid tool if volume warrants.
3. **Capitalization policy** for loan fees and interest (capitalize to project vs. expense) — confirm with CPA per GAAP/tax treatment; apply consistently.

**Known limitations:**
- Multiple company files mean **intercompany must be booked twice** (both sides) — disciplined process, not automatic. Mitigation: monthly tie-out + checklist.
- QuickBooks Desktop class-based reporting is good but not a substitute for true consolidation eliminations — handled in the consolidation layer.
- Bank-feed coverage varies by institution; some accounts will stay monthly-import.

**Future work:** automated draw-schedule tracking; a property-management → QB posting integration; an automated partner-capital/K-1 estimator; positive-pay/dual-control wire workflow.

---

## 15. GLOSSARY

- **STVE** — STV Entitlement Services (= Summa Terra Ventures LLC); entitlement/management company; main file.
- **STDG** — STV Development Group; the development company (earns dev/CM fees).
- **HLN** — **Hunters Landing North** (project entity; suffered the Dec-2025 fraud).
- **12SB** — a Hunters Landing project entity (distinct from HLN).
- **CIP / WIP** — Construction in Progress / Work in Progress (capitalized project costs).
- **Due To / Due From** — paired intercompany payable/receivable accounts.
- **Developer fee / CM fee** — the ~5% fees STDG/STVE earn from project entities.
- **K-1** — partner's share of partnership income/loss; driven by the capital accounts.
- **QODBC** — read-only ODBC driver to query QuickBooks data.
- **Web Connect (.QBO)** — bank-download format QuickBooks imports.
- **Class** — QuickBooks tag used here for project/phase/cost-center within an entity.
- **Disregarded entity** — single-member LLC with no separate return (rides as a class of its owner).
- **Banks:** UCCU = Utah Community CU (rt [ROUTING-REDACTED]); MACU = Mountain America (rt [ROUTING-REDACTED]); Granite = Granite CU.

---

## 16. REPORTING, MONITORING & OBSERVABILITY

**Per-entity (every month):** Balance Sheet, P&L (vs. budget where available), A/R & A/P aging, reconciliation reports, member-capital statement.

**Per-project (job cost):** P&L by Class / job-cost detail; budget vs. actual on development costs; draw vs. spend.

**Consolidated (group):** combined Balance Sheet & P&L with **intercompany eliminations**; intercompany balance matrix (must net to zero); total debt by lender.

**Partner pack (weekly — replaces manual slides):** a **live, auto-updating dashboard** (QODBC → Google Sheet → Looker Studio, or a connected Sheet) showing per-project status, cash position, draw status, and capital balances. Keep a one-page summary slide for the meeting, **fed from live data** — not hand-built. *(This directly addresses the current pain of hand-built weekly Google Slides.)*

**Health monitoring (the "alerts"):** at each close, flag — any account not reconciled; "Ask My Accountant" ≠ 0; intercompany ≠ 0; negative cash; uncategorized class/account; loan balance ≠ lender statement; member capital not tying. These are the dashboards Ben watches.

---

## 17. ALTERNATIVE DESIGNS CONSIDERED

**Alt 1 — Single company file, one Class per entity.**
*Pros:* one login, simplest consolidation, cheapest. *Cons:* dangerous for 40+ **separate tax returns/K-1s** (commingling risk; a missing class silently merges entities); weak lender/audit separation; one corrupted file risks everything. **Rejected** for STV's many filing entities (acceptable only for grouping *disregarded* single-member LLCs under their parent).

**Alt 2 — One file per *bank account* or per *project regardless of entity*.**
*Pros:* granular. *Cons:* explodes file count, breaks tax-return alignment, intercompany nightmare. **Rejected.**

**Alt 3 — Move off QuickBooks to a real-estate ERP (Yardi/AppFolio/Sage Intacct).**
*Pros:* native multi-entity consolidation, property management built in. *Cons:* large cost + migration; the team is on QuickBooks Enterprise now. **Deferred** — revisit if entity count/complexity outgrows QB; this spec maximizes what Enterprise can do first.

**Chosen:** **one file per tax-filing entity, cloned from a master template, with classes for projects and a QODBC-fed consolidation/reporting layer** — best balance of tax-return cleanliness, lender/audit separation, consistency, and automation, on the platform STV already runs.

---

## 18. FINAL BUILD CHECKLIST

**Decide & template**
- [ ] CPA confirms entity→file map (Open decision #1)
- [ ] Capitalization policy + consolidation method confirmed (Open decisions #2, #3)
- [ ] Master template file built: numbered COA, classes, items, memorized reports
- [ ] Preferences set: account numbers ON, class required, audit trail ON
- [ ] Role set defined: Controller, Bookkeeper, Partner (read-only), External Accountant

**Per entity (repeat)**
- [ ] Clone template; create file `STV — [Entity] — [EIN last4]`
- [ ] Bank/CC accounts added with naming convention; opening balances entered at conversion date
- [ ] Each bank account reconciled to conversion-date statement (variance $0)
- [ ] Member capital accounts set to last K-1 balances; loans set to lender balances
- [ ] Intercompany Due-To/From accounts created; classes/jobs set up
- [ ] Closing-date password set after sign-off

**Automation & reporting**
- [ ] Bank feeds (Web Connect/Direct Connect) live where available; monthly .QBO process documented elsewhere
- [ ] QODBC read-only export set scheduled to Drive
- [ ] Consolidated workbook + partner dashboard built and feeding from live data
- [ ] Weekly partner pack switched from hand-built slides to live data

**Process**
- [ ] Monthly close checklist + reconciliation SOP written and adopted
- [ ] Fraud/closed-account runbook documented
- [ ] First full monthly close completed under the new structure within 10 business days

---

## CONSISTENCY CHECK RESULTS

All 18 sections generated and cross-checked.

✓ Scope (2) ↔ Architecture (4): multi-file design matches the per-entity reporting in Section 16.
✓ Acceptance (3 "zero plugs") ↔ Error Handling (7) ↔ Reporting (16): "Ask My Accountant = $0" enforced consistently.
✓ Security roles (9) ↔ Users in Exec Summary (1) and Close controls (11): controller/partner/CPA roles align.
✓ Bank naming (6) ↔ Edge cases (7): last-4 collision (Ventura/Dominus …7470) handled by entity+bank naming.
✓ Automation (12) ↔ Constraints (no Excel on VPS): exports target CSV/Sheets, not server xlsx.
⚠️ Dependency, not a contradiction: final **entity→file mapping (4 / 14 Open decision #1)** is pending the CPA's return list. Structure is fixed; only per-entity assignment is open. **This is the one item to resolve before Phase 2 build.**

**Status:** Ready for partner/CPA review. No internal contradictions; one external input (return-filing list) needed to lock Section 4 assignments.
```
