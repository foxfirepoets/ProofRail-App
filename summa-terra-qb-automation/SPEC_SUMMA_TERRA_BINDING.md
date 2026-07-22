# AI Accounting Hub — Summa Terra Domain Binding (Design Specification)

```
Spec Title:        AI Accounting Hub × QuickBooks Enterprise (Summa Terra Ventures) — Domain Binding
Version:           2.0.2  (binds AI-layer SPEC.md v1.0.0 to QB Summa Terra SPEC.md v2.2.0; +spec-review fixes; +fee-structure source-of-truth reconciliation + 3 canonical report names)
Author:            Ben Stone (via Claude Code spec-superstar)
Last Updated:      2026-06-27
Status:            In Design (new build: dimensioned canonical model + Draw-Package fee engine)
                   on top of Build-phase architecture (AI Accounting Hub SPEC.md v1.0.0, already built)
Timeline:          Phase 2.5 of the AI Hub roadmap — ~3–4 weeks after Phase 1 read-only sync is live
Confidence Level:  ~92% — domain rules are fully resolved & owner-confirmed in the QB spec (every flip-point
                   closed there). Remaining unknowns are the same two AI-layer environment spikes (QBWC poll
                   cadence; Rightworks poller approval) plus one CPA policy input (capitalize-vs-expense the 5%)
                   that the schema already parameterizes either way.
Next Steps:        Land Phase 1 read-only sync (AI SPEC.md), then build the dimensioned canonical model (§6/§13)
                   and the Draw-Package fee engine (§5.3) behind the existing 4 proof gates.
Source of truth:   AI architecture  → C:\Users\Administrator\Desktop\AI Accounting Hub\SPEC.md (v1.0.0)
                   QB domain config  → C:\Users\Administrator\Desktop\QB Summa Terra\SPEC.md (v2.2.0)
                                       + Chart_of_Accounts.md + Cost_Codes_and_Items.md (cost codes 001–069)
                                       + Hunters Landing Draw #29.pdf (the anchor draw, total $962,845.68)
```

> **Relationship to the two parent specs.** This is a *binding* spec, not a replacement. The QB Summa Terra
> spec stays the authority on **how QuickBooks itself is structured** (file-per-entity, COA, Items, Classes,
> Customer:Job, the 5/2/1 split, the Draw Package model). The AI Accounting Hub `SPEC.md` stays the authority on
> **the operating layer** (canonical Postgres = system of record, async QBWC transport, Temporal commit
> boundary, the 4 SwarmSync proof gates). This document specifies the **third thing neither covers: how the AI
> layer is made natively aware of the Summa Terra domain** — so the AI Hub generates, gates, and writes back
> *exactly the entries the QB spec prescribes*, and closes the developer-fee leak automatically instead of by
> hand. Where this spec and a parent disagree, the parent wins for its own scope and this spec is corrected.

---

## DELIVERABLE MAP (what this binding adds, and where it plugs into the parents)

| # | Binding deliverable | This spec | Binds AI SPEC | Binds QB SPEC |
|---|---------------------|-----------|---------------|---------------|
| 1 | Dimensioned canonical model (cost code / class / job / draw #) | §6, §13 | §6 (bills/vendors) | §6.1–6.7 |
| 2 | Cost-code catalog as canonical data (001–069 + lifecycle) | §6.4, §13 | — | `Cost_Codes_and_Items.md` |
| 3 | Draw Package object (the virtual draw, keyed by Draw #) | §5.2, §6.5 | §6 (bills) | §6.7 |
| 4 | Automated Draw-Package **fee engine** (5% / 2% / 1% split) | §5.3, §12.4 | §5 (intents) | §5.3, §12.4 |
| 5 | Intercompany Due-To/Due-From auto-pairing + net-zero gate | §5.4, §6.6, §16 | §6 (allocations) | §4.3, §12.9 |
| 6 | Domain-aware InvoiceProof gate (CoA / cost-code / draw checks) | §7, §9, §12 | §9 Gate 1 | §6.4, §9 |
| 7 | "No approved draw without its fee" as a continuous gate | §3, §7, §16 | §9 gates | §7 golden rule, §16.1 ★ |
| 8 | Commission-on-partnership = hard-block validation | §7, §9 | §9 fail-closed | §7, §9.1 |
| 9 | qbXML mapping for dimensioned write-back (Bill/JE) | §12, §13 | §4.2 write path | §13 list build |
| 10 | Migration of QB lists → canonical catalogs (IIF/CSV ingest) | §11, §13 | §11 rollout | §19 Import_Files |

---

## 1. EXECUTIVE SUMMARY

The QuickBooks Enterprise redesign for Summa Terra Ventures (QB spec v2.2.0) closes the firm's developer-fee
leak **structurally but manually**: when the construction manager and CEO Mike Watson approve a GC Draw
Package, the accounting manager keys memorized transactions — a 5% developer-fee bill in the partnership file,
and a 5% income entry plus 2%/1% executive-commission accruals in the parent file. The control works only as
well as the human remembers to run it on every draw.

This binding spec makes the **AI Accounting Hub do that work automatically and provably.** It extends the AI
Hub's canonical Postgres model with the real QuickBooks dimensions (cost code, class/phase, Customer:Job,
Draw #), teaches the Hub the actual chart of accounts and the 001–069 cost-code catalog, and adds a
**Draw-Package fee engine**: the moment an approved draw lands, the Hub computes the 5% / 2% / 1% off the
approved package total, drafts the *exact* journal entries the QB spec prescribes (partnership books 5% only;
parent books 5% income + 2% CEO + 1% President), routes them through the existing four proof gates, blocks for
human approval, and writes them back to the correct company files over QBWC — while a continuous canonical
query enforces the QB spec's golden rule: **no approved draw may exist without its fee, or a logged exception.**

**Business outcome:** the "0 missed developer fees" target stops depending on human discipline and becomes a
system invariant with a tamper-evident proof behind every fee entry. Intercompany Due-To/Due-From auto-pairs
and is gated to net zero. Every posted cost carries Customer:Job + Class + Item or it cannot pass the gate.
**Primary users:** the accounting manager (approver), Mike Watson + Porter Christensen (fee recipients /
approvers), and the AI agents (actors). **Why now:** the QB redesign is handoff-ready and the AI Hub's
Phase-1 read sync is the prerequisite that's already built — this is the wedge that turns a clean ledger into
an autonomous, verified one.

---

## 2. SCOPE DEFINITION & NON-SCOPE

### In scope (this binding)
- A **dimensioned canonical model**: cost-code catalog (Items 001–069 + lifecycle), class/phase list,
  Customer:Job hierarchy, Draw # as a first-class field, and bill **line items** carrying all four dimensions.
- A **Draw Package** canonical object (the virtual draw of QB spec §6.7) and its lifecycle
  (submitted → approved → fee-generated → funded → reconciled).
- The **automated fee engine**: compute + draft the 5% (partnership) and 5%/2%/1% (parent) entries off the
  approved package total, exactly per QB spec §5.3 / §12.4; gate; approve; write back.
  *Status: implemented in **shadow mode** (CHUNK_6, `app/draw_engine/`) — drafts + proof bundles +
  3 reconciliation reports + exception engine, idempotent, NO QBWC write-back yet (gated on the two
  poller spikes). Live-verified on migration 20260628_1000.*
- **Intercompany** auto-pairing (`Due To <X>` ⇄ `Due From <X>`) and the **net-zero** close gate.
- **Domain-aware InvoiceProof** (Gate 1): cost-code/CoA validity, CIP-bucket mapping, duplicate-within-draw,
  retainage math so bill net = Amount Due, and the **commission-account-on-partnership hard block**.
- **Catalog migration**: ingest the QB `Import_Files/` IIF/CSV (COA, classes, items, vendors, jobs) into the
  canonical catalogs as the seed of record.
- **qbXML mapping** for dimensioned write-back of bills and the fee JEs to the correct file.

### Out of scope (unchanged from the parents)
- Everything the AI SPEC.md §2 excludes: 1000-company **Desktop** operation, live non-QBO adapters, payroll,
  tax filing, bank-feed ingestion, vendor portals, any inbound connection to Rightworks, any paid integration
  above $5–10/mo.
- Everything the QB SPEC.md §2 excludes: the AIA G702/G703 / lender-portal **assembly** itself, tax-return
  preparation, payroll system selection. (QB feeds the data; the AI Hub feeds QB.)
- **Changing the QuickBooks structure.** The COA, Items, Classes, Customer:Job conventions, and the 5/2/1 split
  are *owner-confirmed and frozen* in the QB spec. This binding consumes them; it does not redesign them.
- The percentages themselves (5/2/1) and the recognition trigger (construction-manager + Mike Watson approval)
  are **fixed company policy** — encoded, never "optimized."

### Dependencies
- **AI Accounting Hub SPEC.md v1.0.0 must be live through Phase 1** (read-only sync of one file's vendors +
  bills into canonical Postgres). This binding is Phase 2.5 — it presumes the canonical store, the adapter
  seam, Temporal, and the proof spine exist.
- **QB Summa Terra spec v2.2.0 lists are authoritative.** The `Import_Files/` (IIF/CSV) are the seed data.
- **One CPA policy input:** capitalize the 5% to `15500 CIP — Developer Fee Capitalized` vs. expense it to
  `60100 Developer Fee Expense`. The schema carries a per-company flag; both paths ship. Default = capitalize.

---

## 3. BUSINESS CONTEXT & ACCEPTANCE CRITERIA

**Business goal:** convert the QB spec's manual, discipline-dependent fee control into an **automated,
proof-backed system invariant**, and make every project cost natively dimensioned so cross-entity reporting and
the Draw vs. Fee Reconciliation run themselves.

**Success metrics & targets (inherited + binding-specific):**

| Metric | Baseline | Target |
|--------|----------|--------|
| Missed developer-fee rate | Manual control, human-dependent | **0** — enforced by a continuous gate, not a checklist |
| Fee entries carrying a valid proof | 0% (manual JEs) | **100%** (AuditProof/AIVS row per fee entry) |
| Approved-draw → fee latency | Days (next time the manager runs it) | **< 1 poll cycle** after approval lands in canonical |
| Commission booked on a partnership file | Possible human error | **Structurally impossible** (hard-block gate) |
| Intercompany net per pair at close | Frequently off | **$0**, gated before period lock |
| Cost lines missing Job/Class/Item | Common | **0** can pass the write-back gate |
| Draw vs. Fee Reconciliation assembly | Manual report | **Automatic** canonical query, always current |

**Acceptance criteria (testable):**
- [ ] Ingesting `Import_Files/QB_Import_Partnership_Template.iif` populates the canonical cost-code catalog with
      all 001–069 + lifecycle Items, each mapped to exactly one of the four CIP buckets, 0 orphans.
- [ ] Posting **Hunter's Landing Draw #29** ($962,845.68) auto-drafts: partnership `FEE-DEV` = **$48,142.28**;
      parent `FEE-DEV-INC` = $48,142.28, `FEE-CEO` = **$19,256.91**, `FEE-PRES` = **$9,628.46** — to the exact
      accounts in QB spec §12.4, no ad-hoc JE.
- [ ] A draft that would post `60200/60300/21100/21200` (commission accounts) into a **partnership** file is
      **rejected at the gate** before write-back (impossible-state guard).
- [ ] The "No approved draw without its fee" query returns 0 unresolved gaps after a fee engine run, or each
      gap has a logged exception row.
- [ ] Each fee entry's write-back carries an AIVS audit row linking *approved draw → AI draft → human approval
      → qbXML TxnID*; chain validates.
- [ ] Intercompany pair (`Due To — Summa Terra` in partnership ⇄ `Due From — <Partnership>` in parent) nets to
      $0 in the canonical view.
- [ ] A bill line missing Customer:Job, Class, or Item cannot reach `approved`.
- [ ] Retainage line makes canonical bill net == the draw's Amount Due column.

**Spec status:** design-phase for the new canonical model + fee engine (build to this); build-phase-fixed for
the architecture and the 5/2/1 domain rules it sits on (do not deviate). If the CPA chooses *expense* over
*capitalize*, flip the per-company flag — no schema change.

---

## 4. ARCHITECTURE & SYSTEM INTEGRATION

### 4.1 Where the binding sits
The binding adds **domain knowledge and one new workflow** to the existing layered architecture (AI SPEC.md
§4.1). Nothing about the layer order changes; the canonical store gets richer and the proof gates get
domain-aware.

```
   AI agents ──emit INTENTS──▶  (create_bill | record_draw_package | generate_draw_fees | settle_intercompany)
        │
        ▼
   SwarmSync Proof Spine (HARD GATES)  ──now domain-aware──┐
     Gate1 InvoiceProof  → cost-code/CoA valid? dup-in-draw? retainage math? commission-on-partnership?
     Gate2 AuditProof    → AIVS row per fee entry & per dimensioned bill
     Gate3 VerifyAPI     → CoA drift, fee-base = approved package total, 5/2/1 arithmetic, net-zero IC
     Gate4 ATEP          → vendor bank-change tier (unchanged)
        │
        ▼
   Temporal commit boundary  → human approves the draw's fee batch / the dimensioned bill
        │
        ▼
   Canonical Postgres (SYSTEM OF RECORD)  ── + cost_codes, classes, customer_jobs, draw_packages,
        │                                       bill_lines, fee_entries, intercompany_links  (§6/§13)
        ▼
   Adapter (qbXML/QBWC, outbound poll)  → writes dimensioned BillAdd + the fee JEs to the CORRECT file
        ▼
   QuickBooks Enterprise Desktop (Rightworks)  = batch sink, structured per QB spec v2.2.0
```

### 4.2 Data flow — the new path: approved draw → automated fees
1. The approved Draw Package (Draw #, project, package total, approver, approval timestamp) lands in canonical
   — sourced either from an AI agent intent, from OCR of the approved pay application, or (Phase 1 reality)
   keyed/confirmed by the accounting manager. Recognition trigger = **construction-manager + Mike Watson
   approval**, never first submission (QB spec §5.3).
2. The **fee engine** (Temporal workflow) computes `5% / 2% / 1% × package_total` and drafts `fee_entries`:
   one partnership-book entry (5% → `15500`/`60100` Dr, `21000` Cr) and three parent-book entries
   (5% income → `12200` Dr, `40200` Cr; 2% → `60200` Dr, `21100` Cr; 1% → `60300` Dr, `21200` Cr).
3. **Gate 3 VerifyAPI** checks: fee base equals the approved package total; arithmetic is exact; target
   accounts exist in each target file's CoA; **no commission account is targeted at a partnership file**;
   intercompany legs pair. **Gate 2 AuditProof** appends an AIVS row per entry.
4. Temporal **blocks for human approval** of the whole fee batch (one approval, the controller sees the draw +
   the four entries + green proofs).
5. On approval, entries commit to canonical; the adapter enqueues the partnership 5% bill (to the partnership
   file) and the parent JEs (to the parent file) as **separate company-file write-backs**; QBWC drains each on
   its poll cadence; TxnIDs reconcile back.
6. The **Draw vs. Fee Reconciliation** is a standing canonical query — it's correct the instant step 5 commits,
   no report build.

### 4.3 Integration points (additions)
- **IIF/CSV ingest** (`Import_Files/`): one-time + re-runnable loader → canonical catalogs (§13.4).
- **invoice2data → dimensioned bill**: OCR fields map to vendor + cost-code Item + Customer:Job + Class + Draw #
  (the AI proposes the coding; Gate 1 validates it).
- **qbXML dimensioned write-back**: `BillAdd` with `ItemLineAdd` (cost code), `CustomerRef` (Customer:Job),
  `ClassRef` (phase), and the Draw # custom field; `JournalEntryAdd` for the parent commission accruals.

### 4.4 Ownership map (additions)
Fee engine + intercompany logic: backend. Cost-code/CoA catalogs + reconciliation queries: backend.
Dimensioned coding model (AI proposes Item/Class/Job): AI orchestration. qbXML dimensioned mapping: integration
engineer. Approval UX for the fee batch: frontend. Domain rules authority (5/2/1, trigger): company policy,
encoded — never changed by code.

---

## 5. USER FLOWS & HAPPY PATH

### 5.1 Dimensioned project cost (vendor bill) — AI-assisted
**Actor:** AI agent drafts; accounting manager approves. **Precondition:** vendor + Customer:Job + cost-code
catalog exist in canonical.
1. invoice2data extracts vendor, amount, line detail from the invoice PDF.
2. AI proposes the coding: cost-code Item (e.g., `019 Electrical`), Customer:Job (`Hunter's Landing`),
   Class (defaults from the Item — `30 MEP Trades`), Draw # if part of a draw.
3. **Gate 1 InvoiceProof** validates: cost code exists, maps to a valid CIP bucket, no duplicate within the same
   Draw #, line math, retainage line (if any) so net = Amount Due, vendor bank unchanged.
4. Temporal blocks → manager approves on phone (bill + green proof).
5. Commit → AIVS row → adapter writes dimensioned `BillAdd` → TxnID reconciled.
**Postcondition:** cost hits the right CIP bucket, is job/phase/draw-coded, appears in Project Cost Detail by
Draw #. A line lacking Job/Class/Item never reaches step 4.

### 5.2 Record an approved Draw Package
**Actor:** AI/manager. **Precondition:** draw approved by construction manager + Mike Watson.
1. Create the `draw_packages` row: `draw_number` (`D-2025-29`), `customer_job`, `package_total`
   ($962,845.68), `approved_by`, `approved_at`, `status=approved`.
2. Each payee line becomes a dimensioned bill (§5.1) stamped with the Draw #; the GC lump line is split into
   its component cost codes (003/004/026/056/060/067/068) per QB spec §6.7; retainage rides on the line.
3. Loan funding recorded against `22000 Construction Loan Payable` / `10200` funding account.
4. **Approval of the package status=approved is the event that arms the fee engine (5.3).**
**Postcondition:** the virtual package is assembled by `draw_number`; every line reconciles to the lender's
Amount Due; the fee engine is ready to fire exactly once.

### 5.3 CRITICAL — automated developer-fee + parent-commission generation
**Actor:** fee engine (AI), accounting manager approves. **Precondition:** `draw_packages.status=approved`,
`package_total = D`, no existing `fee_entries` for this Draw # (idempotency key).

**Step 1 — Partnership book (5% only), drafted automatically:**
- One entry, vendor `IC — Summa Terra Ventures`, Item `FEE-DEV` = **5% × D**, stamped Draw #.
- Posts **Dr `15500 CIP — Developer Fee Capitalized`** (or `60100` if the company's `expense_dev_fee` flag is
  set) **/ Cr `21000 Due-To Summa Terra`.** No commissions, ever, in this file.

**Step 2 — Parent book (income + receivable + own commissions), drafted automatically:**
- **Dr `12200 Due-From <Partnership>` / Cr `40200 Developer Fee Income`** = 5% × D.
- **Dr `60200 CEO Commission Expense` (2% × D) / Cr `21100 Commission Payable — Mike Watson`.**
- **Dr `60300 President Commission Expense` (1% × D) / Cr `21200 Commission Payable — Porter Christensen`.**

**Step 3 — Gate + approve + write back:**
- Gate 3 verifies base = D, arithmetic exact, accounts valid per target file, **commission accounts NOT in a
  partnership file**, intercompany legs pair. Gate 2 appends an AIVS row per entry.
- Temporal blocks; controller approves the batch once.
- Adapter writes the partnership 5% bill to the partnership file and the parent JEs to the parent file.

**Worked example — Draw #29, D = $962,845.68:**

| Book | Entry | Amount |
|------|-------|--------|
| Partnership | Dr `15500` CIP — Dev Fee / Cr `21000` Due-To Summa Terra | **$48,142.28** (5%) |
| Parent | Dr `12200` Due-From / Cr `40200` Developer Fee Income | $48,142.28 (5%) |
| Parent | Dr `60200` CEO Commission / Cr `21100` Payable — Watson | $19,256.91 (2%) |
| Parent | Dr `60300` President Commission / Cr `21200` Payable — Christensen | $9,628.46 (1%) |
| | **Summa Terra net after commissions** | **$19,256.91 (2%)** |

**Postcondition:** every approved draw carries its fee with a proof; the reconciliation query is current;
leakage is structurally impossible.

> **Edge — denied/revised draw:** if `draw_packages.status` moves to `denied`/`revised` after fees posted, the
> engine drafts **reversing** entries on *both* books and logs an exception (QB spec §7). Recognition stays at
> approval; the engine never fires on first submission or on funding.

### 5.4 Intercompany settlement
**Actor:** AI proposes, controller approves at close.
1. Canonical view nets each `Due To <X>` ⇄ `Due From <X>` pair.
2. AI drafts the cash settlement (transfer clearing the pair) and, where the parent paid a partnership cost,
   the `Due-To/Due-From` reimbursement entry per QB spec §12.9.
3. **Close gate:** the period cannot lock until every pair nets $0 (or carries a documented exception).

---

## 6. DATA MODELS & SCHEMA (the binding extensions)

Extends AI SPEC.md §6. Existing tables (`companies`, `vendors`, `bills`, `proof_bundles`, `audit_rows`) keep
their columns; this binding **adds catalogs, lines, draw packages, fee entries, and intercompany links**, and
adds a few columns to `bills`/`companies`.

### 6.1 `companies` — additions
| Column | Type | Notes |
|---|---|---|
| role | VARCHAR(16) NOT NULL | `parent` \| `partnership` \| `master` \| `archive` (QB spec §4) |
| qb_entity_code | VARCHAR(16) | e.g., `014`; drives file naming `STV — <code> <name>` |
| expense_dev_fee | BOOLEAN NOT NULL DEFAULT false | CPA policy: false=capitalize 5% to `15500`, true=expense to `60100` |

> **Invariant:** commission accounts (`60200/60300/21100/21200`) and `40200 Developer Fee Income` /
> `12200 Due-From` exist **only** where `role='parent'`. Enforced at catalog-load and at the gate (§7).

### 6.2 `accounts` — canonical chart of accounts (mirrors `Chart_of_Accounts.md`)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| company_id | UUID FK→companies | scoped per file (COA is identical in partnerships, +extras in parent) |
| number | VARCHAR(8) NOT NULL | e.g., `15300`, `21000` |
| name | VARCHAR(128) NOT NULL | e.g., `CIP — Hard Costs` |
| acct_type | VARCHAR(32) NOT NULL | Bank/AR/OtherCurrentAsset/AP/OtherCurrentLiability/LongTermLiability/Equity/Income/COGS/Expense/Other |
| statement | CHAR(2) NOT NULL | `BS` \| `PL` |
| is_cip_bucket | BOOLEAN DEFAULT false | true for `15100/15200/15300/15400/15500` |
| parent_only | BOOLEAN DEFAULT false | true for commission + dev-fee-income + due-from accounts |
| UNIQUE(company_id, number) | | |

### 6.3 `classes` — development phases (QB spec §6.3)
`id, company_id, code, name` — seeds: `00 Acquisition … 90 Parent Overhead`. UNIQUE(company_id, code).

### 6.4 `cost_codes` — the Item catalog 001–069 + lifecycle (mirrors `Cost_Codes_and_Items.md`)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| company_id | UUID FK→companies | ships in the template, identical per file |
| code | VARCHAR(20) NOT NULL | `003`, `019`, `068`, `100`, `FEE-DEV`, `RETAINAGE-HELD`(14), `FEE-DEV-INC`(11), … |
| name | VARCHAR(128) NOT NULL | QB item Description (the FEE-DEV description runs ~74 chars) |
| name | VARCHAR(64) NOT NULL | `Concrete (Site Concrete)`, `Electrical`, `Construction Profit (GC)` |
| maps_to_account | VARCHAR(8) NOT NULL | the account this Item posts to: a CIP bucket `15100/15200/15300/15400/15500` for draw/most lifecycle codes; `70700`/`50200` for disposition; `20200` for `RETAINAGE-HELD`; `15500` for `FEE-DEV`. (Renamed from `cip_account_number` — it is not always a CIP account.) |
| default_class_code | VARCHAR(8) | e.g., `10` for site, `30` for MEP |
| kind | VARCHAR(16) NOT NULL | `draw` \| `lifecycle` \| `fee` \| `retainage` |
| fee_role | VARCHAR(24) | for `kind=fee`: `dev_5_partnership`(17) \| `dev_inc_5_parent` \| `ceo_2_parent` \| `pres_1_parent` |
| UNIQUE(company_id, code) | | |

> **Hard rule (catalog invariant):** every `kind='draw'` row's `maps_to_account` ∈ {15200,15300} (verified
> against `Cost_Codes_and_Items.md`: 0 draw codes map to 15100/15400); every Item resolves to exactly one
> account; `068 Construction Profit` is `kind='draw'`/Soft (the GC's profit) and is
> **never** a `fee_role` — it is not the developer fee. Mirrors `Cost_Codes_and_Items.md` §2.

### 6.5 `draw_packages` — the virtual draw (QB spec §6.7)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| company_id | UUID FK→companies | the **partnership** that owns the draw |
| draw_number | VARCHAR(32) NOT NULL | `D-2025-29` |
| customer_job | VARCHAR(128) NOT NULL | `Hunter's Landing` |
| package_total | DECIMAL(14,2) NOT NULL CHECK (package_total >= 0) | **the fee base** |
| status | VARCHAR(16) NOT NULL | `submitted` → `approved` → `fee_generated` → `funded` → `reconciled` (+`denied`/`revised`) |
| approved_by | VARCHAR(64) | must reflect construction-manager + Mike Watson approval |
| approved_at | TIMESTAMPTZ | recognition timestamp |
| UNIQUE(company_id, draw_number) | | **idempotency anchor for the fee engine** |

### 6.6 `bills` additions + `bill_lines`
`bills` adds: `draw_package_id UUID FK→draw_packages NULL`, `net_amount_due DECIMAL(14,2)` (post-retainage),
`approval_id VARCHAR(64)`.

**`bill_lines`** (new — the dimensioned detail; one bill can have a cost line + a retainage line):
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| bill_id | UUID FK→bills ON DELETE CASCADE | |
| cost_code_id | UUID FK→cost_codes NOT NULL | the Item |
| account_number | VARCHAR(8) NOT NULL | resolved posting account (denormalized from `cost_code.maps_to_account`; `20200` on retainage lines) |
| class_code | VARCHAR(8) NOT NULL | phase |
| customer_job | VARCHAR(128) NOT NULL | project |
| amount | DECIMAL(14,2) NOT NULL | gross for this code (kept intact for budget-vs-actual) |
| is_retainage | BOOLEAN DEFAULT false | true → posts to `20200 GC Retainage Payable` |

> **Line invariant:** a non-retainage line MUST carry cost_code + class_code + customer_job (the QB spec's
> "require Class / require Job / require Item"). Σ(amount) over a bill's lines = bill net = the draw's Amount Due.

### 6.7 `fee_entries` — the engine's output (one row per posted entry)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| draw_package_id | UUID FK→draw_packages NOT NULL | |
| book_company_id | UUID FK→companies NOT NULL | the file this entry posts to |
| fee_role | VARCHAR(24) NOT NULL | `dev_5_partnership`/`dev_inc_5_parent`/`ceo_2_parent`/`pres_1_parent` |
| percent | NUMERIC(5,4) NOT NULL | 0.0500 / 0.0200 / 0.0100 |
| amount | DECIMAL(14,2) NOT NULL | percent × package_total |
| dr_account | VARCHAR(8) NOT NULL | e.g., `60200` |
| cr_account | VARCHAR(8) NOT NULL | e.g., `21100` |
| intercompany_link_id | UUID FK→intercompany_links NULL | set for the 5% pair |
| proof_bundle_id | UUID FK→proof_bundles | the gate result |
| qb_txn_id | VARCHAR(128) | after write-back |
| status | VARCHAR(16) NOT NULL | `drafted`→`verified`→`approved`→`synced`→`reversed` |
| UNIQUE(draw_package_id, fee_role) | | **prevents duplicate fee on the same draw** |

### 6.8 `intercompany_links` — Due-To/Due-From pairs (QB spec §4.3, §12.9)
`id, partnership_company_id, parent_company_id, partnership_account (21000/22500), parent_account
(12200/12500), amount, source_ref`. **Net-zero is NOT a stored column** — it spans two rows in two files, so a
`GENERATED` column cannot express it. It is proven by a reconciliation **view** `v_intercompany_net` that sums
the paired legs per counterparty; the value must be $0 (the close gate in §16 reads this view). Each row is the
canonical assertion that one leg is equal and opposite to its mirror.

### 6.9 Validation rules (binding)
- Fee engine arithmetic: `amount = round(percent * package_total, 2)` (HALF_UP). The **distinct economic
  charge** is 5% + 2% + 1% = **8%** of the package total. The 5% developer fee is recorded **once per book** as
  a mirrored intercompany pair (partnership cost ⇄ parent income) that **nets to $0 in consolidation**, so it
  counts once, not twice. Per-book *debit* totals: partnership = 5% (`FEE-DEV`); parent = 8% (5% receivable +
  2% + 1%). ⚠ Do **not** sum all four `fee_entries.amount` rows expecting 8% — that double-counts the mirrored
  5% and yields 13%. (For Draw #29: 5+2+1 distinct = $77,027.65; naive 4-row sum = $125,169.93 = 13%.)
- A `fee_entry` with a parent-only `fee_role` and `book_company_id.role='partnership'` is **invalid** (gate hard-block).
- `bill_lines` Σ must equal `bills.net_amount_due`; retainage line(s) reconcile the gross to Amount Due.
- `draw_packages` cannot reach `fee_generated` unless exactly 1 partnership entry + 3 parent entries exist and pass gates.

### 6.10 Example (valid `record_draw_package` + `generate_draw_fees` intent)
```json
{ "intent":"generate_draw_fees", "draw_number":"D-2025-29",
  "company_id":"<hunters-landing-partnership-uuid>", "package_total":"962845.68",
  "approved_by":"ConstructionMgr+MikeWatson", "approved_at":"2025-09-10T00:00:00Z" }
```
→ engine emits 4 `fee_entries` (5% partnership; 5%/2%/1% parent) as in §5.3.

---

## 7. ERROR HANDLING & EDGE CASES

Extends AI SPEC.md §7. New domain failure modes (all fail-closed):

| Scenario | Code | Status | Behavior |
|---|---|---|---|
| Commission account targeted at a **partnership** file | COMMISSION_ON_PARTNERSHIP | 422 (gate) | **Hard block** before write-back; cannot approve; alert. The §3 impossible-state guard. |
| Approved draw with no `fee_entries` | DRAW_FEE_MISSING | 200 (gate) | Reconciliation query flags it; engine drafts the four entries, or a logged exception is required before close. |
| Duplicate fee on same Draw # | DRAW_FEE_DUPLICATE | 409 | Rejected by `UNIQUE(draw_package_id, fee_role)`; engine is idempotent on Draw #. |
| `068 Construction Profit` mis-coded as the developer fee | FEE_VS_GC_PROFIT | 422 | Gate distinguishes `kind='draw'` (068, a cost line) from `fee_role` entries; reject. |
| Cost code unknown / maps to no CIP bucket | COST_CODE_INVALID | 422 | Reject coding; surface to mapping fix (new draw line → new catalog Item first). |
| Bill net ≠ draw Amount Due (retainage wrong) | RETAINAGE_MISMATCH | 422 | Reject; require retainage line so Σ lines = Amount Due. |
| Line missing Job/Class/Item | DIMENSION_MISSING | 422 | Cannot reach `approved` (QB spec "require" rules). |
| Fee base ≠ approved package total | FEE_BASE_MISMATCH | 422 | Gate 3 rejects; base is `draw_packages.package_total` only. |
| Intercompany pair ≠ 0 | INTERCOMPANY_IMBALANCE | 200 (gate) | Block period lock; investigate the unmatched leg. |
| CoA drift (target account absent in file) | COA_DRIFT | 422 | (inherited) VerifyAPI catches pre-write; flag mapping fix. |
| Draw denied/revised after fees posted | DRAW_REVERSAL | 200 | Engine drafts reversing entries on both books; log exception. |

**Golden rule (encoded from QB spec §7):** *No approved draw may exist without (a) the partnership's 5% entry
AND the parent's 5% income + 2%/1% accruals, or (b) a documented exception.* Here it is a **continuous gate**,
not a monthly review.

---

## 8. PERFORMANCE & SCALABILITY

Inherits AI SPEC.md §8 (the one-file-per-session physics ceiling and the canonical-mirror read path are
unchanged). Binding-specific notes:
- **Fee engine is O(1) per draw** — four entries; arithmetic is trivial; the bottleneck is the QBWC write-back
  cadence, not computation. A draw's fees are *drafted and gated in <2s*; they *land in QB* on the next poll.
- **Reconciliation is a query, not a job** — the Draw vs. Fee report is a view over `draw_packages` ⨝
  `fee_entries`; always current, sub-100ms. Three canonical report surfaces (names binding across all docs,
  see QB `Month_End_Checklist.md` §B/§F):
  - **Partnership Draw vs. Developer Fee Reconciliation** — verifies the **5% only** (partnership book; zero
    commission lines).
  - **Parent Commission Register** — verifies **Mike 2% + Porter 1%** (parent book).
  - **Cross-book Draw Fee/Commission Reconciliation** — verifies all three fees exist in the correct books per
    Draw #; counts the mirrored 5% **once** (distinct charge = 8%, not the 13% double-count).
- **Catalog size is tiny** — ~70 cost codes + ~36 accounts + ~10 classes per file; far under any limit.
- **Write-back ordering:** the partnership 5% bill and the three parent JEs target **different files** → they
  queue to different QB sessions and do not serialize against each other.
- Scale path unchanged: Desktop is the bootstrap; the dimensioned model is backend-agnostic and rides the same
  adapter seam to QBO/Intacct later.

---

## 9. SECURITY & COMPLIANCE

Inherits AI SPEC.md §9 in full (hard fail-closed gates; AIVS/VCAP wire formats; bank fingerprints not raw
details; supabase-aihub MCP only). Binding additions:

- **Gate 1 InvoiceProof, domain-aware:** in addition to dup/math/PO/bank checks, validate cost-code validity,
  CIP-bucket mapping, retainage math (net = Amount Due), and the duplicate-within-draw check keyed on
  `draw_number + vendor + cost_code`.
- **Gate 3 VerifyAPI, fee-aware:** fee base = approved package total; 5/2/1 arithmetic exact; target accounts
  exist per file; **commission-account-on-partnership hard block**; intercompany legs pair.
- **Separation of duties:** the recognition trigger (construction-manager + Mike Watson approval) is an input
  the engine *requires* (`approved_by`/`approved_at`) — the AI never self-approves a draw into fee-eligibility.
- **Least privilege per file:** the adapter writes commission/dev-fee-income/due-from entries only to
  `role='parent'` companies; capability tokens are scoped per company_id + action.
- **Audit:** every fee entry, dimensioned bill, and intercompany settlement carries an AIVS row; the chain links
  approved draw → AI draft → human approval → qbXML TxnID. Retained indefinitely.
- **PII/secrets:** unchanged — store vendor bank **fingerprints**; never log raw bank fields or proof secrets;
  set `VCAP_SHARED_SECRET` / capability signing secrets to ≥32 bytes in production.

---

## 10. TESTING STRATEGY

Extends AI SPEC.md §10.
- **Unit (100% on fee/money paths):** 5/2/1 arithmetic incl. rounding (Draw #29 must yield exactly
  48,142.28 / 19,256.91 / 9,628.46); commission-on-partnership rejection; cost-code→CIP mapping; retainage
  reconciliation; idempotency on Draw #; denied-draw reversal.
- **Integration:** `record_draw_package` → `generate_draw_fees` → gates → Postgres → adapter queue (mocked
  QBWC), asserting the four entries hit the correct files and accounts; intercompany pair nets 0.
- **Catalog ingest:** load `Import_Files/QB_Import_Partnership_Template.iif` → assert all 001–069 + lifecycle
  Items present, 0 orphans, each mapped to one CIP bucket; assert partnership template has **no** commission
  accounts (mirrors QB spec §19 split-at-file-level).
- **E2E:** OCR a Draw #29 payee line → AI codes it → Gate 1 pass → approve → dimensioned `BillAdd` to QB
  sandbox → TxnID reconciled; then the whole-package fee batch end-to-end.
- **Property test:** for random package totals, the **distinct** charge (5% + 2% + 1%) = 8%; the 5% appears
  once per book and the partnership↔parent 5% pair nets to $0; commissions appear only on the parent. (Do
  **not** assert Σ of all four `amount` rows = 8% — the mirrored 5% makes that 13%; see §6.9.)

---

## 11. DEPLOYMENT & ROLLOUT STRATEGY

- **Pre-req:** AI Hub Phase 1 (read-only sync) live; QB spec template built and `Import_Files/` available.
- **Step 1 — Catalogs:** ingest IIF/CSV into canonical catalogs for the **parent + one pilot partnership**
  (Hunter's Landing). Validate 0 orphans, split-at-file-level holds.
- **Step 2 — Read-dimensioned:** sync existing dimensioned bills read-only; confirm cost-code/class/job coding
  round-trips losslessly via `raw_extensions`.
- **Step 3 — Fee engine in shadow mode:** on each approved draw, *draft and gate* the fee entries but **do not
  write back** — compare to what the accounting manager keys manually (parallel run, QB spec §10 parallel-run
  discipline). Success = AI entries match manual to the penny.
- **Step 4 — Enable gated write-back** of the fee batch on the pilot partnership + parent only; monitor
  EditSequence conflicts, sync lag, gate failures.
- **Step 5 — Expand** to remaining active entities wave-by-wave (mirrors QB spec §11 phasing).
- **Rollback:** canonical is SoR; a bad fee-engine release rolls back without data loss (entries replay from
  Temporal). **Never auto-retry a fee write-back on rollback — re-gate first.** Reversal entries handle any
  posted-then-wrong fee (denied draw).
- **Comms:** notify the controller before enabling write-back; the proof bundle per fee entry is the trust
  artifact.

---

## 12. API DOCUMENTATION (binding additions to the internal surface)

Extends AI SPEC.md §12.

**POST /intents** — now accepts domain intents: `record_draw_package`, `generate_draw_fees`,
`settle_intercompany`, and dimensioned `create_bill` (with `bill_lines[]`). Auth: capability token scoped to
company_id + action. → `202 { workflow_id }`.

`generate_draw_fees` body: `{ draw_number, company_id, package_total, approved_by, approved_at }` →
drafts the four `fee_entries`; 409 `DRAW_FEE_DUPLICATE` if already generated; 422 `FEE_BASE_MISMATCH` /
`COMMISSION_ON_PARTNERSHIP` on gate failure.

**GET /draws/{draw_number}/reconciliation** — the automated Draw vs. Fee Reconciliation for one draw:
`{ package_total, dev_fee_5, parent_income_5, ceo_2, pres_1, collected, outstanding, status }`. → 200.

**GET /reconciliation/draw-vs-fee?company_id=&period=** — portfolio view: every approved draw with its
fee status or exception. Powers the headline control (QB spec §16.1 ★).

**GET /intercompany/balances?period=** — Due-To/Due-From by pair with net; the close gate reads this. → 200.

**Adapter (qbXML) — dimensioned mapping (additions):**
- Bill: `BillAddRq → BillAdd → ItemLineAdd{ ItemRef(cost_code), Amount, ClassRef(class_code),
  CustomerRef(customer_job) }` + Draw # via the configured custom field (DataExt).
- Parent commissions: `JournalEntryAddRq → JournalEntryAdd` with the Dr/Cr lines from `fee_entries`
  (`60200`/`21100`, `60300`/`21200`, `12200`/`40200`).
- Partnership fee: `BillAdd` from `IC — Summa Terra Ventures`, Item `FEE-DEV`, posting `15500`/`60100` → `21000`.

---

## 13. DATABASE MIGRATIONS

Builds on AI SPEC.md §13 (`20260626_1200_init_canonical`). New migration:

**`20260627_1300_summa_terra_binding` — UP (abbreviated DDL; full types per §6):**
```sql
-- role is added NULLABLE with NO blanket default: a DEFAULT 'partnership' would silently mis-tag the
-- existing parent company row, and the §6.1 invariant + §13.4 loader would then wrongly reject the parent's
-- own commission/income accounts. Backfill explicitly, THEN enforce NOT NULL.
ALTER TABLE companies
  ADD COLUMN role VARCHAR(16),
  ADD COLUMN qb_entity_code VARCHAR(16),
  ADD COLUMN expense_dev_fee BOOLEAN NOT NULL DEFAULT false;

-- Backfill (parametrize the parent's qb_file_id at deploy):
-- UPDATE companies SET role='parent'      WHERE qb_file_id = :parent_qb_file_id;
-- UPDATE companies SET role='partnership' WHERE role IS NULL;
-- ALTER TABLE companies ALTER COLUMN role SET NOT NULL;

CREATE TABLE accounts ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  number VARCHAR(8) NOT NULL, name VARCHAR(128) NOT NULL, acct_type VARCHAR(32) NOT NULL,
  statement CHAR(2) NOT NULL, is_cip_bucket BOOLEAN NOT NULL DEFAULT false,
  parent_only BOOLEAN NOT NULL DEFAULT false, UNIQUE(company_id, number) );

CREATE TABLE classes ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  code VARCHAR(8) NOT NULL, name VARCHAR(64) NOT NULL, UNIQUE(company_id, code) );

CREATE TABLE cost_codes ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  code VARCHAR(20) NOT NULL, name VARCHAR(128) NOT NULL, maps_to_account VARCHAR(8) NOT NULL,
  default_class_code VARCHAR(8), kind VARCHAR(16) NOT NULL, fee_role VARCHAR(24),
  UNIQUE(company_id, code) );

CREATE TABLE draw_packages ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id),
  draw_number VARCHAR(32) NOT NULL, customer_job VARCHAR(128) NOT NULL,
  package_total DECIMAL(14,2) NOT NULL CHECK (package_total >= 0),
  status VARCHAR(16) NOT NULL DEFAULT 'submitted',
  approved_by VARCHAR(64), approved_at TIMESTAMPTZ, UNIQUE(company_id, draw_number) );

ALTER TABLE bills
  ADD COLUMN draw_package_id UUID REFERENCES draw_packages(id),
  ADD COLUMN net_amount_due DECIMAL(14,2), ADD COLUMN approval_id VARCHAR(64);

CREATE TABLE bill_lines ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bill_id UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  cost_code_id UUID NOT NULL REFERENCES cost_codes(id),
  account_number VARCHAR(8) NOT NULL, class_code VARCHAR(8) NOT NULL,
  customer_job VARCHAR(128) NOT NULL, amount DECIMAL(14,2) NOT NULL,
  is_retainage BOOLEAN NOT NULL DEFAULT false );

CREATE TABLE intercompany_links ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partnership_company_id UUID NOT NULL REFERENCES companies(id),
  parent_company_id UUID NOT NULL REFERENCES companies(id),
  partnership_account VARCHAR(8) NOT NULL, parent_account VARCHAR(8) NOT NULL,
  amount DECIMAL(14,2) NOT NULL, source_ref VARCHAR(64) );

CREATE TABLE fee_entries ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draw_package_id UUID NOT NULL REFERENCES draw_packages(id),
  book_company_id UUID NOT NULL REFERENCES companies(id),
  fee_role VARCHAR(24) NOT NULL, percent NUMERIC(5,4) NOT NULL, amount DECIMAL(14,2) NOT NULL,
  dr_account VARCHAR(8) NOT NULL, cr_account VARCHAR(8) NOT NULL,
  intercompany_link_id UUID REFERENCES intercompany_links(id),
  proof_bundle_id UUID REFERENCES proof_bundles(id), qb_txn_id VARCHAR(128),
  status VARCHAR(16) NOT NULL DEFAULT 'drafted',
  UNIQUE(draw_package_id, fee_role) );

CREATE INDEX idx_costcodes_company ON cost_codes(company_id);
CREATE INDEX idx_billlines_bill ON bill_lines(bill_id);
CREATE INDEX idx_feeentries_draw ON fee_entries(draw_package_id);
CREATE INDEX idx_drawpkg_company ON draw_packages(company_id);
```
**DOWN:** `DROP TABLE fee_entries, intercompany_links, bill_lines, draw_packages, cost_codes, classes,
accounts CASCADE;` then `ALTER TABLE bills DROP COLUMN draw_package_id, net_amount_due, approval_id;`
`ALTER TABLE companies DROP COLUMN role, qb_entity_code, expense_dev_fee;`

### 13.4 Catalog loader (IIF/CSV ingest — the migration of QB lists)
A re-runnable loader reads `QB Summa Terra/Import_Files/`:
- `CSV_Chart_of_Accounts_*` → `accounts`. Set `parent_only=true` for **every account whose source COA `File`
  column = `P` / `P only`** — the loader reads the flag from the COA, it does **not** hard-code a list. Verified
  against `Chart_of_Accounts.md`, that is **10 accounts**: `12200, 21100, 21200, 40200, 40300, 40400, 60200,
  60300, 70100, 70200` (the fee/commission/due-from set **plus** mgmt-fee income `40300`, reimbursement income
  `40400`, and parent payroll/overhead `70100/70200`). An earlier draft listed only the 6 fee accounts — that
  was incomplete.
- `CSV_Classes.csv` → `classes`.
- `CSV_Items_*` (001–069 + lifecycle + `FEE-*`/`RETAINAGE-HELD`) → `cost_codes` (set `maps_to_account`,
  `default_class_code`, `kind`, `fee_role`).
- `CSV_Vendors_*`, `CSV_Customers_Jobs.csv` → `vendors`, Customer:Job values.
- **Split-at-file-level assertion:** a `role='partnership'` company must load **zero** `parent_only` accounts
  and zero `fee_role IN (dev_inc_5_parent,ceo_2_parent,pres_1_parent)` cost codes (mirrors QB spec §19).

---

## 14. KNOWN LIMITATIONS & FUTURE WORK

- **Recognition trigger is an input, not a sensor.** The Hub requires `approved_by`/`approved_at` reflecting
  construction-manager + Mike Watson approval; it cannot *observe* the approval. Until an approval feed exists,
  the manager confirms the draw's approved status. (Future: ingest the approval signal directly.)
- **Capitalize-vs-expense the 5%** is a CPA policy carried by `companies.expense_dev_fee`; both paths ship,
  default capitalize. The decision is the CPA's, not code's.
- **Cash-basis tax partnerships** need a year-end accrual-to-cash adjustment (QB spec §14) — out of scope here.
- **Retainage** modeling assumes the lender/GC contracts use it (conditional, per QB spec).
- **Same two AI-layer spikes still gate write-back:** QBWC poll cadence + Rightworks persistent-poller approval
  (AI SPEC.md §14). Until resolved, the fee engine runs in **shadow mode** (draft + gate, no write-back) — which
  is itself a usable deliverable (catches missed fees without touching QB).
- **Deferred:** budget-vs-actual automation (QB spec §12.8 estimates), AIA G702/G703 assembly, multi-project
  entities (the schema supports >1 Customer per file but flows assume single-asset partnerships), and the
  master reporting roll-up (Class=entity) as a canonical cross-entity report.

**Spec evolution:** living document; bump to v2.1.0 when shadow-mode parallel-run results are in, or when the
catalog loader is validated against all 10 files.

---

## 15. GLOSSARY & TERMS

Inherits AI SPEC.md §15 and QB SPEC.md §15. Binding-specific:
- **Draw Package (canonical):** the `draw_packages` row + the bills sharing its `draw_number`; the virtual
  draw of QB spec §6.7, made queryable.
- **Fee engine:** the Temporal workflow that, on an approved draw, drafts the four fee entries (5% partnership;
  5%/2%/1% parent) and routes them through the gates.
- **CIP bucket:** one of `15100/15200/15300/15400/15500`; every cost-code Item maps to exactly one.
- **Split-at-file-level:** the invariant that commission + dev-fee-income + due-from accounts exist only in
  `role='parent'` companies (QB spec §19); enforced at catalog load and at the gate.
- **Shadow mode:** the fee engine drafts + gates entries but does not write back — used until the write-back
  spikes resolve and during parallel run.
- **`fee_role`:** `dev_5_partnership` | `dev_inc_5_parent` | `ceo_2_parent` | `pres_1_parent`.

---

## 16. MONITORING, METRICS & OBSERVABILITY

Extends AI SPEC.md §16. Binding metrics:
- **Missed-fee gauge (headline):** count of `draw_packages.status='approved'` with no complete `fee_entries`
  set and no exception → **alert if > 0**. This is the QB spec golden rule as a live metric.
- **Fee-entry proof coverage:** % of `fee_entries` with a validating AIVS row → target 100%.
- **Commission-on-partnership block events:** any `COMMISSION_ON_PARTNERSHIP` rejection → notify (should be
  rare; indicates an upstream coding bug).
- **Intercompany net drift:** max abs net across pairs → alert if ≠ 0 approaching close.
- **Shadow-mode variance:** during parallel run, |AI fee entry − manual entry| per draw → must be 0.00.
- **Draw→fee latency:** time from `status=approved` to `fee_entries` drafted → target < 1 poll cycle.

Standing reports (canonical queries, mirror QB spec §16.1): Approved Draw Register, Developer Fee Register,
CEO/President Commission Registers (parent), **Draw vs. Fee Reconciliation ★**, Outstanding Fee Receivables,
Intercompany Balances, Missing Job/Class/Item.

---

## 17. ALTERNATIVE DESIGNS CONSIDERED

**Alt A — Keep fees manual; AI only flags missed ones.** *Pros:* minimal build; no write-back risk. *Cons:*
re-introduces the human-discipline dependency the whole effort exists to remove; flagging ≠ closing the leak.
**Partially adopted as shadow mode (a stepping stone), not the end state.**

**Alt B — Store QB dimensions only in `raw_extensions` (no first-class catalogs).** *Pros:* no schema work;
lossless. *Cons:* you cannot *gate* on cost-code validity, CIP mapping, the commission-on-partnership block, or
run the reconciliation as a query if the dimensions are opaque JSON. The gates are the product. **Rejected** —
promote the dimensions to first-class tables.

**Alt C — One combined fee entry on the partnership (all 5/2/1).** *Pros:* one document. *Cons:* puts CEO/
President commissions on the partnership's books — **wrong**, contaminates the 1065 (QB spec §17 Alt 5).
**Rejected** — the binding enforces the split as a hard gate.

**Alt D — Recognize fees at funding/cash receipt instead of approval.** *Pros:* collectibility conservatism.
*Cons:* that's exactly where fees vanish today (QB spec §17 Alt 3). **Rejected** — trigger = approval, fixed.

**Alt E — Model the draw as a single canonical bill.** *Pros:* fewer rows. *Cons:* a draw is 40+ payees with
per-line invoice #s and retainage (QB spec §6.7 / Alt 6). **Rejected** — `draw_packages` + per-payee
`bills`/`bill_lines` keyed by `draw_number`.

**Chosen rationale:** promote the QB dimensions to first-class canonical catalogs so the proof gates can
enforce the QB spec's rules automatically; model the draw as a virtual package; and make the 5/2/1 split,
the recognition trigger, and the split-at-file-level invariant **hard gates** rather than conventions — turning
the QB spec's strongest manual control into a system invariant with a proof behind every entry.

---

## 18. FINAL BUILD CHECKLIST

**Catalogs & schema (build first):**
- [ ] Migration `20260627_1300_summa_terra_binding` applied (accounts, classes, cost_codes, draw_packages,
      bill_lines, fee_entries, intercompany_links; bills/companies columns).
- [ ] IIF/CSV catalog loader ingests parent + Hunter's Landing; 0 orphans; every Item → one CIP bucket.
- [ ] Split-at-file-level assertion passes (no `parent_only`/parent `fee_role` rows in a partnership).

**Fee engine:**
- [ ] `generate_draw_fees` drafts the 4 entries to the correct accounts/files; Draw #29 yields
      48,142.28 / 48,142.28 / 19,256.91 / 9,628.46 exactly.
- [ ] `UNIQUE(draw_package_id, fee_role)` idempotency proven; denied-draw reversal proven.
- [ ] Gate 3 rejects `FEE_BASE_MISMATCH`, `COMMISSION_ON_PARTNERSHIP`, `FEE_VS_GC_PROFIT`.
- [ ] AIVS row per fee entry; chain validates.

**Dimensioned bills + intercompany:**
- [ ] `create_bill` with `bill_lines[]` enforces Job/Class/Item; retainage makes net = Amount Due.
- [ ] Intercompany pairs auto-link and the net-zero close gate blocks lock on imbalance.

**Reconciliation & write-back:**
- [ ] Draw vs. Fee Reconciliation query live; missed-fee gauge alerts on > 0.
- [ ] Shadow-mode parallel run on the pilot matches the manual entries to the penny.
- [ ] Gated write-back: dimensioned `BillAdd` + parent `JournalEntryAdd` land in the correct files; TxnIDs
      reconcile.

**Cross-cutting (inherited):**
- [ ] All gates fail-closed under proof-service outage; 100% money/security-path coverage; no raw bank/secret
      logging; `VCAP_SHARED_SECRET`/signing secrets ≥32 bytes in prod.

---

## CONSISTENCY CHECK RESULTS

Checked against both parent specs and internally.

- ✓ §6 dimensioned model aligns with QB SPEC §6 (file=entity via `companies.role`; vendor=payee; Item=cost code
  001–069; Class=phase; Customer:Job=project; Draw # field) — no dimension double-assigned.
- ✓ §5.3 fee engine produces **exactly** the entries in QB SPEC §12.4 (partnership 5% → `15500`/`60100`→`21000`;
  parent 5% `12200`→`40200`, 2% `60200`→`21100`, 1% `60300`→`21200`); worked example matches Draw #29.
- ✓ §7 `COMMISSION_ON_PARTNERSHIP` + §6.1 invariant align with QB SPEC §9.1 "commission accounts parent-only"
  and §19 split-at-file-level.
- ✓ §3 "0 missed fees" / §16 missed-fee gauge align with QB SPEC §7 golden rule and §16.1 ★ reconciliation.
- ✓ §2 scope (no QB structural change; percentages & trigger fixed) aligns with QB SPEC §2/§14 confirmed rules.
- ✓ §4/§8/§11 ride AI SPEC.md unchanged: canonical = SoR, async QBWC poll, fail-closed gates, one-file-per-
  session physics, shadow mode honors the two open write-back spikes.
- ✓ §6.5 single-fee-per-draw (`UNIQUE(draw_package_id, fee_role)`) aligns with QB SPEC §6.7 "package total is
  the fee base, computed once."
- ✓ §13 migration extends AI SPEC.md §13 init migration; UP/DOWN present; reuses pgcrypto/pg_trgm.
- ✓ One genuine external input (capitalize-vs-expense the 5%) is parameterized (`companies.expense_dev_fee`),
  not silently assumed — no contradiction, a flagged decision with a default.

**Status: 0 unresolved contradictions. Domain rules consumed verbatim from the owner-confirmed QB spec; AI
architecture consumed unchanged from SPEC.md v1.0.0. Binding is design-ready; build after Phase 1 read-sync,
starting in shadow mode (no write-back) so it delivers value before the two write-back spikes resolve.**

---

## SPEC-REVIEW / TRUTH-AUDIT PASS (v2.0.0 → v2.0.1, 2026-06-27)

Every load-bearing claim was checked against the source files (not the spec's own prose). Method + verdict:

**GREEN — verified true (live-checked against sources):**
- ✓ **Fee arithmetic** (Python `Decimal` HALF_UP on $962,845.68): 5%=`48,142.28`, 2%=`19,256.91`, 1%=`9,628.46`
  — match §5.3 to the penny; parent net (5−2−1)=2% reconciles.
- ✓ **All 13 account numbers** (`15500/60100/21000/12200/40200/60200/21100/60300/21200/20200/22000/10200` +
  CIP buckets) match `Chart_of_Accounts.md` exactly.
- ✓ **Cost-code→bucket invariant**: grep confirms **0** draw codes (001–069) map to `15100`/`15400`, so
  `kind='draw' ⇒ maps_to_account ∈ {15200,15300}` is genuinely true, not assumed.
- ✓ **068 Construction Profit** is Soft/`kind='draw'`, explicitly **not** the developer fee — matches source ⚠.
- ✓ **Split-at-file-level**: partnership carries `FEE-DEV` but no parent `fee_role`/commission accounts — matches
  QB §19 import-file split.
- ✓ **18/18 sections present and substantive**; domain rules trace 1:1 to QB spec sections.

**YELLOW — real defects found & FIXED in v2.0.1:**
1. **§6.9/§10 arithmetic invariant was ambiguous** — "sum to 8%" invited a 4-row sum = **13%** (double-counts the
   mirrored 5%). → Restated as *distinct charge 5+2+1=8%, 5% mirrored once per book, nets to $0*; added the trap warning.
2. **§13 migration `role … DEFAULT 'partnership'`** would silently mis-tag the existing **parent** row → loader/
   invariant would then reject the parent's own accounts. → Changed to nullable + explicit backfill + `SET NOT NULL`.
3. **§6.8 `net_zero BOOLEAN GENERATED`** is not implementable (spans two rows/two files) and was absent from the
   §13 DDL. → Replaced with reconciliation **view `v_intercompany_net`**; §6.8 ↔ §13 reconciled.
4. **§13.4 loader set `parent_only` for only 6 fee accounts** — source COA has **10** (`+40300/40400/70100/70200`).
   → Loader now reads `parent_only` from the COA `File=P` column; the 10 are enumerated and verified.
5. **`cip_account_number` was a misnomer** (holds `20200`/`70700`/`50200`/`15500` for retainage/disposition/fee).
   → Renamed to `maps_to_account` across §6.4/§6.6/§13/§13.4.

**Truth-audit honesty check (no overclaim):** the spec is **design-phase, no code, no live evidence** — and says
so. The "automatic + provable" headline is correctly bounded by **shadow mode** (§14): until the two write-back
spikes (QBWC cadence, Rightworks poller) resolve, the engine drafts + gates but does not write to QB. The
recognition trigger is honestly disclosed as an **input, not a sensor** (§14). Capitalize-vs-expense is a flagged
CPA decision with a default, not a silent assumption. **No claim in the spec asserts working software.**

**Post-fix verdict: GREEN for a design spec.** Build-ready as Phase 2.5; the only true unknowns are the two
inherited AI-layer environment spikes, which shadow mode is explicitly designed to tolerate.
```
