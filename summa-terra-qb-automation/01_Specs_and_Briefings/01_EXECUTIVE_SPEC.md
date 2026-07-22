# Summa Terra Ventures — Autonomous Real Estate Accounting OS
## Complete System Architecture & Build Specification
**Date:** 2026-06-17
**Prepared by:** 10-Agent Expert Panel (AI-Assisted)

---

# EXECUTIVE SUMMARY AND CURRENT STATE PROBLEMS


---

# TECHNICAL SPECIFICATION
## Autonomous Real Estate Development Accounting Operating System
### Summa Terra Ventures — Internal Systems Architecture
**Version 1.0 | Confidential**

---

# 1. EXECUTIVE SUMMARY

## What This System Is

The Autonomous Real Estate Development Accounting Operating System (ARDAOS) is a PostgreSQL-anchored, API-integrated financial operating layer built specifically for Summa Terra Ventures' multi-entity real estate development business. It replaces a fragmented stack of 
disconnected QuickBooks Online files, Google Sheets waterfalls, and manual draw packages with a single source of truth that spans all partnerships, tracks developer fee receivables through a five-stage revenue pipeline, automates construction loan draw assembly, and produces investor-grade reporting without manual aggregation. The system integrates directly with QBO's API across all legal entities, enforces a unified chart of accounts, and exposes a real-time CFO dashboard covering consolidated cash, inter-company balances, capital account accuracy, and fee capture status — making the CFO's job a matter of review and decision rather than data assembly.

---

## The Business Case

At $15–50M in annual project volume, Summa Terra Ventures operates in a financial complexity band where manual processes have compounding failure modes. The quantified exposure across the firm's current operating model is as follows:

| Leakage Category | Low Estimate | High Estimate | Driver |
|---|---|---|---|
| Developer fee miss-rate (5% overhead, 15–30% miss) | $112,500/yr | $750,000/yr | Wrong GL coding, missing project tags, soft cost exclusions |
| Draw delay carry cost (1-week avg delay, 8% on $10M loan) | $15,000/draw | $75,000/yr | Manual assembly across 5–8 projects |
| Inter-company mispostings (audit-grade errors) | $50,000/incident | $200,000+/yr | No consolidated ledger, no automated reconciliation |
| LP waterfall errors (legal exposure, restatement risk) | $25,000/incident | Unbounded | Formula drift in Google Sheets, no version control |
| Accounting manager overtime / turnover risk | 1.0 FTE | 1.5 FTE | Operating at 3–4x sustainable throughput |
| **Total quantified annual exposure** | **~$200,000** | **~$1,000,000+** | |

A system that captures even 50% of fee leakage and eliminates one draw cycle delay per project per year generates a 5–20x return on implementation cost in year one. This is not a productivity argument — it is a revenue recovery and legal risk argument.

---

## Five Core Operating Principles

**1. The Database Is the System of Record — Not QBO, Not Sheets.**
QuickBooks Online is a data source and a presentation layer. PostgreSQL owns the canonical transaction record, capital accounts, fee pipeline, and draw state. QBO is written to; it does not govern.

**2. Every Dollar Has a Project Code From the Moment It Moves.**
No transaction enters the system without an entity, project, cost code, and GL account. The fee capture engine runs at ingestion, not at month-end. Untagged transactions are an exception condition requiring human resolution — not a normal operating state.

**3. Automation Handles Volume; Humans Handle Judgment.**
Draw assembly, bank reconciliation, capital account updates, and fee opportunity creation are automated. The accounting manager's time is spent on exception review, lender relationships, and investor communication — not data entry.

**4. Consolidated Visibility Is Non-Negotiable.**
The CFO sees all entities, all cash positions, all inter-company balances, and all LP capital accounts in a single dashboard updated daily. No manual aggregation. No emailed spreadsheets. No waiting until month-end to know where the firm stands.

**5. Investor-Grade Accuracy Is a System Property, Not a Human Effort.**
LP capital account balances, preferred return accruals, promote calculations, and waterfall distributions are computed by the database on a defined schedule. The output is auditable, versioned, and reproducible. Investor statements are generated from the same engine that runs the general ledger — not from a separate spreadsheet that drifts.

---

## The Transformation Promise

| Dimension | Before (Current State) | After (ARDAOS) |
|---|---|---|
| Developer fee capture | Sporadic, 70–85% captured | Systematic, 95–98% captured |
| Draw request assembly time | 8–12 days manual | Under 4 hours automated |
| Consolidated CFO view | Monthly, 3-day lag, manual | Daily, real-time, automated |
| LP capital account accuracy | Spreadsheet-dependent, drift-prone | Database-owned, audit-ready |
| Accounting manager throughput | 3–4x overloaded | Operating at sustainable 1x |
| Inter-company reconciliation | Quarterly, error-prone | Continuous, automated |
| Investor reporting cycle | 5–10 days manual per quarter | Same-day generation |
| Legal/audit exposure | High (waterfall errors, fee disputes) | Low (single source of truth) |

---

# 2. CURRENT STATE PROBLEMS

---

## Problem 1: Transaction Scatter Across Legal Entities

**Description**

Each partnership operates as a legally distinct entity — which is correct for liability and tax purposes — but the consequence in the current operating model is that each entity has its own QBO file, its own bank accounts, and its own coding conventions. There is no automated mechanism to view transactions across all entities simultaneously. When a vendor invoice is paid from the parent operating account on behalf of a partnership, it may be coded as a parent expense, a partnership expense, or split — inconsistently and without a systematic inter-company reimbursement workflow. The same cost code may mean different things in different entity files because there is no enforced chart of accounts standard across the portfolio.

**Business Impact**

- Consolidated P&L and balance sheet require manual export from each QBO file, manual reformatting, and manual aggregation — a process that takes 2–4 days per month and introduces transcription errors.
- Inter-company receivables and payables are frequently miscoded as income or expense, distorting entity-level financials. A $500K inter-company loan posted as an expense has appeared in developer audits at this firm class at least once per firm per year, creating restatement risk and audit fees of $15,000–$50,000.
- Lender compliance reporting — required by most construction loan agreements — becomes a multi-day manual exercise rather than a same-day query.

**Root Cause**

QBO is designed for single-entity small businesses. Multi-entity real estate development requires a consolidation layer that QBO does not natively provide. In the absence of that layer, each entity operates as a silo.

**Current Workaround**

The accounting manager exports reports from each QBO file and aggregates them in a Google Sheet. This workaround is inadequate because: (a) it is not reproducible — the same export on two different days may yield different results depending on when transactions were posted; (b) it is not auditable — there is no version history; (c) it scales linearly with entity count, so adding a new project adds a proportional manual burden rather than being absorbed automatically by the system.

---

## Problem 2: Google Sheets Dependency for Critical Financial Functions

**Description**

Partnership waterfall calculations, preferred return accruals, promote threshold tracking, LP capital account balances, and developer fee estimates all live in Google Sheets. These are not reporting outputs from a system — they are the system. Changes to deal terms, capital call timing, or distribution policies require manual formula updates in Sheets. Multiple versions of waterfall models exist across the firm with no authoritative file clearly designated. The accounting manager, the CFO, and outside counsel may be working from different versions of the same model without knowing it.

**Business Impact**

- Formula drift is endemic. A single broken SUMIF or an incorrectly anchored cell reference can silently miscalculate an LP's capital account balance for one or more quarters before discovery. Restating an LP's account after they have received a statement creates legal exposure and relationship damage. Legal fees for a dispute arising from a waterfall calculation error range from $25,000 to over $200,000 depending on the LP's position size and disposition.
- LP statements generated from Sheets cannot be independently audited. There is no way to reproduce a prior-period statement from the same inputs without re-running the same sheet — which may have been modified in the interim.
- At $15–50M project volume with 5–15 LP relationships, the probability of a material waterfall error in any 12-month period under the current model approaches certainty.

**Root Cause**

Waterfall models are complex and were originally built by deal sponsors or outside accountants in Excel/Sheets for one-time use. They were never migrated to a durable, versioned system because no such system existed in the firm's stack. Sheets is where complex calculations go to die slowly.

**Current Workaround**

Periodic manual review by the CFO and occasional reconciliation against QBO totals. This workaround is inadequate because it is reactive — errors are caught after the fact, often after LP statements have been distributed. There is no continuous validation.

---

## Problem 3: Developer Fee Leakage — The Silent Revenue Loss

**Description**

Developer fees are typically structured as a percentage (commonly 5%) of total project costs, recoverable from the project budget and funded through construction draws. These fees represent a primary revenue stream for the development entity — not a bonus, not overhead recovery, but contractually owed compensation. In the current state, fee opportunities are identified manually and sporadically, often by the accounting manager reviewing a project budget near draw submission time. Expenses that are eligible for the overhead fee load are frequently missed because: (a) they are coded to the wrong GL account in QBO, so they never appear in the fee calculation base; (b) they are posted in the parent entity rather than the partnership, so they are invisible at the project level; (c) vendor invoices arrive without project codes and are coded to a default account; (d) soft costs — legal, architectural, permitting — are excluded by error when they are in fact eligible under the loan agreement.

**Business Impact**

At 5% developer fee with a 15–30% miss rate on eligible costs:

| Annual Project Volume | Miss Rate | Annual Fee Leakage |
|---|---|---|
| $15M | 15% | $112,500 |
| $15M | 30% | $225,000 |
| $30M | 15% | $225,000 |
| $30M | 30% | $450,000 |
| $50M | 15% | $375,000 |
| $50M | 30% | $750,000 |

This leakage is largely unrecoverable after project closeout. Unlike an accounts payable error that can be corrected in a future period, a developer fee not captured in a draw is typically gone — the loan is closed, the budget is exhausted, and the lender will not reopen a funded line item.

**Root Cause**

There is no fee receivables system. Developer fees are treated as a calculation exercise rather than a receivables pipeline. There is no mechanism to track which expenses have generated a fee opportunity, which have been invoiced, which have been funded, and which were missed — in real time, at the transaction level.

**Current Workaround**

Quarterly or project-milestone fee calculations in a spreadsheet. This workaround is inadequate because by the time the calculation is performed, the window for fee recovery on missed items may have closed. The accounting manager is not tracking fee opportunities at the transaction level because there is no system to do so.

---

## Problem 4: Manual Accounting Work at Unsustainable Volume

**Description**

A single accounting manager covering the parent entity plus 5–8 active partnerships is responsible for: transaction coding across all QBO files, monthly bank reconciliations (one per entity per bank account — typically 10–20 reconciliations per month), draw request assembly for 3–5 active construction loans, developer fee tracking, inter-company journal entries, LP capital account updates, and investor reporting. These functions are performed largely through manual data entry, manual export/import cycles between QBO and Sheets, and manual document assembly in Word or PDF.

**Business Impact**

- The accounting manager is operating at 3–4x sustainable capacity. This is not a staffing problem that hiring resolves — it is a process problem. Hiring a second accountant at $65,000–$85,000/year without fixing the underlying process doubles the cost without resolving the throughput constraint.
- Work performed at high speed under time pressure produces errors. In accounting, errors compound: a miscoded transaction in Month 1 propagates into bank rec, into fee calculations, into draw requests, and into LP statements before it is caught.
- The single-person dependency creates catastrophic concentration risk. If the accounting manager leaves — a high probability event given the workload — the firm faces a 60–90 day gap in financial operations during which draws may be delayed, fees missed, and investor reporting lapsed.
- Estimated annual cost of the current model, fully loaded: $85,000 (salary/benefits) + $50,000 (error correction, restatements, missed fees) + $30,000 (opportunity cost of CFO time spent on financial assembly rather than deal execution) = $165,000+ for a function that a well-designed system reduces to review-and-approval.

**Root Cause**

Every function the accounting manager performs is manually triggered, manually executed, and manually validated. There are no automated workflows, no system-generated exceptions, and no straight-through processing for routine transactions.

**Current Workaround**

Extended working hours, deferred reconciliations, and prioritization of draw deadlines over everything else. Investor reporting is the first thing to slip when capacity is constrained. This workaround is inadequate by definition — it is the problem, not a solution to it.

---

## Problem 5: No Unified Real-Time Visibility

**Description**

The CFO currently has no consolidated view of cash, receivables, payables, inter-company balances, LP capital accounts, or fee pipeline across all entities at any given moment. Obtaining this view requires requesting exports from the accounting manager, waiting for aggregation, and accepting that the data is already 1–30 days stale by the time it is reviewed. Decisions about capital calls, inter-company transfers, draw timing, and LP distributions are made on the basis of incomplete or lagged information.

**Business Impact**

- Cash management decisions made on stale data create overdraft risk, missed investment windows, and unnecessary credit line draws. At a blended cost of capital of 8–10%, a $1M cash misallocation held for 30 days due to visibility lag costs $6,700–$8,300 in direct carry — plus the opportunity cost of not deploying that capital on a higher-return use.
- Without a real-time view of inter-company loan balances, the parent entity may over-fund or under-fund partnerships, creating tax complications (constructive distributions) and lender covenant violations (loan-to-cost ratios).
- Capital call timing — the most sensitive operational event in LP relationships — is managed by gut feel and manual cash flow spreadsheets rather than by a system-generated 13-week forecast. A poorly timed capital call damages LP trust and, in extreme cases, triggers default provisions.

**Root Cause**

Data lives in disconnected systems with no automated aggregation layer. The CFO dashboard does not exist as a system artifact — it is assembled on demand by a human.

**Current Workaround**

Ad hoc reporting requests to the accounting manager, supplemented by the CFO's direct QBO access to individual entity files. This workaround is inadequate because multi-entity QBO access still requires manual consolidation and does not surface inter-company net positions, fee pipeline status, or LP capital account accuracy.

---

## Problem 6: Reconciliation Friction and Draw Delay

**Description**

Construction loan draws are the primary cash inflow mechanism for active projects. A draw request typically requires: a schedule of values update, cost-to-date by line item, supporting invoices, lien waivers, title endorsement, inspection certification, and a reconciliation of prior draw disbursements against actual expenditures. This package is assembled manually from QBO exports, vendor files, and prior draw records stored in a shared drive. The process takes 8–12 days and is performed by the accounting manager as the primary assembler, with the CFO reviewing and the project manager supplying supporting docs — a three-way coordination exercise with no workflow system managing the handoffs.

**Business Impact**

- Each one-week delay in a draw request on a $10M construction loan at 8% interest costs $15,000 in additional carry. Across 4–6 active loans with an average of 6 draws per project per year, systemic draw delays of 1–2 weeks cost $180,000–$540,000 annually in avoidable carry.
- Lender relationships are damaged by late or error-prone draw packages. Construction lenders have discretion to delay funding pending cure of deficiencies in the draw package. A lender that perceives a borrower as disorganized applies heightened scrutiny to future draws, creating additional latency.
- Draw errors — wrong cost code mapping, prior draw reconciliation mismatches, missing invoices — require resubmission, adding 1–2 weeks to an already delayed cycle.

**Root Cause**

Draw assembly is a document-intensive, multi-source aggregation process that is performed entirely manually because there is no system mapping cost codes to draw line items, tracking invoice status against draw submissions, or automating the reconciliation of prior draw disbursements.

**Current Workaround**

The accounting manager maintains a draw tracker spreadsheet per project. This workaround is inadequate because it does not integrate with QBO (requiring manual data entry), does not track invoice/lien waiver status in real time, and does not generate the draw package — it merely tracks its status.

---

## Problem 7: Investor Reporting — Manual, Delayed, and Error-Prone

**Description**

Quarterly investor reports, annual K-1 support packages, and ad hoc LP capital account statements are produced manually. The accounting manager pulls QBO reports for each partnership, the CFO runs waterfall calculations in Sheets, and a report is assembled in Word or PowerPoint. This cycle takes 5–10 business days per quarter per partnership. With 5–8 active partnerships and multiple LPs per partnership, investor reporting consumes 25–80 accounting-manager-days per year — roughly 10–30% of total annual capacity — on a function that should be a system output, not a human production.

**Business Impact**

- Delayed investor reporting — a quarterly report delivered 45 days after quarter-end — signals operational disorganization to sophisticated LPs. In a market where LP capital is competed for, reporting quality is a retention and re-up signal. A firm that delivers clean, timely, accurate reports commands a reputational premium; a firm that delivers late, inconsistent reports loses re-investment and referrals.
- K-1 packages produced from Sheets-derived capital account calculations that do not tie to the QBO trial balance create tax preparer reconciliation issues, adding $5,000–$15,000 in CPA fees per entity per year and delaying LP tax filing.
- The manual production process creates no version history. If an LP disputes a prior-period statement, there is no audit trail to reconstruct the computation — only the final PDF. This is a legal liability.

**Root Cause**

Investor reporting is treated as a communication function rather than a data function. Because LP capital accounts, waterfall calculations, and preference tracking live in Sheets rather than in a database, producing an investor report requires a human to run a Sheets model, transcribe results, and format a document — rather than a system to query a database and render a template.

**Current Workaround**

The accounting manager and CFO produce reports on a best-effort basis, often deferring to the 45-day mark after quarter-end. Quality control is a single-pass CFO review before distribution. This workaround is inadequate because it consumes irreplaceable senior time, produces no audit trail, and scales linearly — each new LP relationship or partnership adds proportional manual burden rather than being absorbed by a system designed to handle volume.

---

*End of Sections 1–2. Sections 3–8 (System Architecture, Data Model, Integration Specifications, Fee Capture Engine, Draw Automation, and Implementation Roadmap) follow in subsequent specification chapters.*

---

# ENTITY RELATIONSHIP DIAGRAM AND DATA ARCHITECTURE


# Section 3 — Entity Relationship Diagram

## Notation Key
- PK = Primary Key
- FK = Foreign Key
- UQ = Unique constraint
- IDX = Index
- Cardinality: ||--o{ = one-to-many, }o--o{ = many-to-many (via junction), ||--|| = one-to-one

---

## 3.1 Complete Entity Definitions

---

### organizations
```
TABLE organizations
  id                UUID          PK
  parent_id         UUID          FK -> organizations.id (self-referencing; NULL = root)
  name              VARCHAR(255)  NOT NULL
  legal_name        VARCHAR(255)  NOT NULL
  entity_type       ENUM('llc','lp','gp','corp','partnership','trust')
  ein               VARCHAR(20)   UQ
  state_of_formation CHAR(2)
  formed_date       DATE
  status            ENUM('active','dissolved','inactive')
  qbo_realm_id      VARCHAR(50)   UQ  -- QuickBooks Online company ID
  default_currency  CHAR(3)       DEFAULT 'USD'
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: parent_id, status, qbo_realm_id
```

---

### projects
```
TABLE projects
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  name              VARCHAR(255)  NOT NULL
  project_code      VARCHAR(50)   UQ NOT NULL
  project_type      ENUM('ground_up','renovation','acquisition','land','mixed_use')
  status            ENUM('pre_dev','entitlement','construction','lease_up','stabilized','disposition','closed')
  address_line1     VARCHAR(255)
  city              VARCHAR(100)
  state             CHAR(2)
  zip               VARCHAR(10)
  county            VARCHAR(100)
  parcel_number     VARCHAR(100)
  acquisition_date  DATE
  expected_close_date DATE
  actual_close_date DATE
  total_budget      NUMERIC(18,2)
  revised_budget    NUMERIC(18,2)
  pro_forma_irr     NUMERIC(8,4)
  pro_forma_em      NUMERIC(8,4)
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, status, project_code
```

---

### bank_accounts
```
TABLE bank_accounts
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  project_id        UUID          FK -> projects.id (NULL = operating account not project-specific)
  institution_name  VARCHAR(255)  NOT NULL
  account_number_last4 CHAR(4)
  routing_number    VARCHAR(9)
  account_type      ENUM('checking','savings','money_market','construction_escrow','reserve','disbursement')
  plaid_account_id  VARCHAR(255)  UQ
  plaid_access_token_enc TEXT
  qbo_account_id    VARCHAR(50)
  balance_current   NUMERIC(18,2)
  balance_available NUMERIC(18,2)
  balance_as_of     TIMESTAMPTZ
  is_active         BOOLEAN       DEFAULT TRUE
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, project_id, plaid_account_id, is_active
```

---

### chart_of_accounts
```
TABLE chart_of_accounts
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  parent_account_id UUID          FK -> chart_of_accounts.id
  account_number    VARCHAR(20)   NOT NULL
  account_name      VARCHAR(255)  NOT NULL
  account_type      ENUM('asset','liability','equity','revenue','expense','cogs')
  account_subtype   VARCHAR(100)
  is_active         BOOLEAN       DEFAULT TRUE
  qbo_account_id    VARCHAR(50)   UQ
  normal_balance    ENUM('debit','credit')
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

UNIQUE (organization_id, account_number)
IDX: organization_id, parent_account_id, account_type, qbo_account_id
```

---

### transactions
```
TABLE transactions
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  project_id        UUID          FK -> projects.id
  bank_account_id   UUID          FK -> bank_accounts.id
  plaid_transaction_id VARCHAR(255) UQ
  qbo_transaction_id   VARCHAR(50)
  transaction_date  DATE          NOT NULL
  posted_date       DATE
  amount            NUMERIC(18,2) NOT NULL
  description       TEXT
  merchant_name     VARCHAR(255)
  category_plaid    VARCHAR(100)
  account_id_coa    UUID          FK -> chart_of_accounts.id
  reconciliation_status ENUM('unreconciled','matched','reconciled','disputed','excluded') DEFAULT 'unreconciled'
  reconciliation_session_id UUID  FK -> reconciliation_sessions.id
  source            ENUM('plaid','manual','qbo_import','payroll','loan_draw','capital_call','distribution')
  memo              TEXT
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, project_id, bank_account_id, transaction_date, reconciliation_status, plaid_transaction_id, source
```

---

### journal_entries
```
TABLE journal_entries
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  project_id        UUID          FK -> projects.id
  entry_date        DATE          NOT NULL
  reference_number  VARCHAR(100)
  description       TEXT
  status            ENUM('draft','posted','reversed','voided')
  source_type       ENUM('manual','transaction_auto','loan_draw','capital_call','distribution','payroll','developer_fee','reconciliation','qbo_sync')
  source_id         UUID
  qbo_journal_entry_id VARCHAR(50)
  posted_by         UUID          FK -> employees.id
  posted_at         TIMESTAMPTZ
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, project_id, entry_date, status, source_type

TABLE journal_entry_lines
  id                UUID          PK
  journal_entry_id  UUID          FK -> journal_entries.id NOT NULL
  account_id        UUID          FK -> chart_of_accounts.id NOT NULL
  debit_amount      NUMERIC(18,2) DEFAULT 0
  credit_amount     NUMERIC(18,2) DEFAULT 0
  memo              TEXT
  line_order        INT

CONSTRAINT: debit_amount >= 0 AND credit_amount >= 0
IDX: journal_entry_id, account_id
```

---

### loans
```
TABLE loans
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  project_id        UUID          FK -> projects.id NOT NULL
  lender_name       VARCHAR(255)  NOT NULL
  loan_type         ENUM('construction','bridge','permanent','mezzanine','preferred_equity','heloc','land')
  loan_number       VARCHAR(100)
  commitment_amount NUMERIC(18,2) NOT NULL
  amount_drawn      NUMERIC(18,2) DEFAULT 0
  interest_rate     NUMERIC(8,5)  NOT NULL
  rate_type         ENUM('fixed','floating','prime_plus','sofr_plus')
  spread_bps        INT
  origination_date  DATE
  maturity_date     DATE
  extension_options JSONB
  recourse_type     ENUM('full','partial','non_recourse')
  guarantor_ids     UUID[]
  bank_account_id   UUID          FK -> bank_accounts.id
  status            ENUM('term_sheet','approved','closed','in_draw','paid_off','defaulted','extended')
  origination_fee   NUMERIC(18,2)
  exit_fee          NUMERIC(18,2)
  prepayment_penalty JSONB
  covenants         JSONB
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, project_id, status, maturity_date
```

---

### investors
```
TABLE investors
  id                UUID          PK
  organization_id   UUID          FK -> organizations.id NOT NULL
  legal_name        VARCHAR(255)  NOT NULL
  display_name      VARCHAR(255)
  investor_type     ENUM('individual','entity','trust','ira','fund_of_funds','family_office','institutional')
  ssn_ein_enc       TEXT
  accredited_status BOOLEAN
  accredited_verified_date DATE
  address_line1     VARCHAR(255)
  city              VARCHAR(100)
  state             CHAR(2)
  zip               VARCHAR(10)
  email             VARCHAR(255)  NOT NULL
  phone             VARCHAR(20)
  portal_user_id    UUID
  preferred_distribution_method ENUM('ach','wire','check')
  bank_routing_enc  TEXT
  bank_account_enc  TEXT
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, email, accredited_status
```

---

### investor_capital_accounts
```
TABLE investor_capital_accounts
  id                UUID          PK
  investor_id       UUID          FK -> investors.id NOT NULL
  project_id        UUID          FK -> projects.id NOT NULL
  organization_id   UUID          FK -> organizations.id NOT NULL
  committed_capital NUMERIC(18,2) NOT NULL DEFAULT 0
  contributed_capital NUMERIC(18,2) NOT NULL DEFAULT 0
  distributions_paid NUMERIC(18,2) NOT NULL DEFAULT 0
  current_balance   NUMERIC(18,2) GENERATED ALWAYS AS (contributed_capital - distributions_paid) STORED
  ownership_pct     NUMERIC(8,5)  NOT NULL
  preferred_return_rate NUMERIC(8,4)
  accrued_preferred NUMERIC(18,2) DEFAULT 0
  waterfall_tier    INT           DEFAULT 1
  admission_date    DATE
  status            ENUM('active','withdrawn','transferred','pending')
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

UNIQUE (investor_id, project_id)
IDX: investor_id, project_id, organization_id, status
```

---

### developer_fees
```
TABLE developer_fees
  id                UUID          PK
  project_id        UUID          FK -> projects.id NOT NULL
  organization_id   UUID          FK -> organizations.id NOT NULL
  fee_type          ENUM('acquisition','development','construction_management','asset_management','disposition')
  calculation_basis ENUM('fixed','pct_of_costs','pct_of_revenue','pct_of_equity')
  basis_amount      NUMERIC(18,2)
  fee_rate          NUMERIC(8,5)
  total_fee_earned  NUMERIC(18,2) NOT NULL
  amount_deferred   NUMERIC(18,2) DEFAULT 0
  amount_accrued    NUMERIC(18,2) DEFAULT 0
  amount_paid       NUMERIC(18,2) DEFAULT 0
  amount_waived     NUMERIC(18,2) DEFAULT 0
  state             ENUM('earned','accrued','deferred','approved','paid') NOT NULL DEFAULT 'earned'
  milestone_trigger VARCHAR(255)
  milestone_date    DATE
  accrual_date      DATE
  deferral_reason   TEXT
  approval_date     DATE
  approved_by       UUID          FK -> employees.id
  payment_date      DATE
  journal_entry_id  UUID          FK -> journal_entries.id
  transaction_id    UUID          FK -> transactions.id
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: project_id, organization_id, state, fee_type
```

---

### budget_lines
```
TABLE budget_lines
  id                UUID          PK
  project_id        UUID          FK -> projects.id NOT NULL
  organization_id   UUID          FK -> organizations.id NOT NULL
  parent_budget_line_id UUID      FK -> budget_lines.id
  account_id        UUID          FK -> chart_of_accounts.id
  line_code         VARCHAR(50)   NOT NULL
  description       VARCHAR(255)  NOT NULL
  budget_category   ENUM('hard_costs','soft_costs','land','financing','contingency','developer_fee','carry')
  original_budget   NUMERIC(18,2) NOT NULL DEFAULT 0
  approved_changes  NUMERIC(18,2) NOT NULL DEFAULT 0
  revised_budget    NUMERIC(18,2) GENERATED ALWAYS AS (original_budget + approved_changes) STORED
  committed_costs   NUMERIC(18,2) DEFAULT 0
  costs_to_date     NUMERIC(18,2) DEFAULT 0
  paid_to_date      NUMERIC(18,2) DEFAULT 0
  forecasted_cost   NUMERIC(18,2)
  version           INT           NOT NULL DEFAULT 1
  status            ENUM('active','revised','closed')
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

UNIQUE (project_id, line_code, version)
IDX: project_id, organization_id, parent_budget_line_id, account_id, budget_category
```

---

### draw_requests
```
TABLE draw_requests
  id                UUID          PK
  project_id        UUID          FK -> projects.id NOT NULL
  loan_id           UUID          FK -> loans.id
  draw_number       INT           NOT NULL
  request_date      DATE          NOT NULL
  period_start      DATE
  period_end        DATE
  total_requested   NUMERIC(18,2) NOT NULL
  total_approved    NUMERIC(18,2)
  total_funded      NUMERIC(18,2)
  retainage_held    NUMERIC(18,2) DEFAULT 0
  status            ENUM('draft','internal_review','title_review','lender_review','approved','funded','rejected','cancelled')
  submitted_date    DATE
  approved_date     DATE
  funded_date       DATE
  lender_contact    VARCHAR(255)
  title_company     VARCHAR(255)
  inspector_report_url TEXT
  notes             TEXT
  created_by        UUID          FK -> employees.id
  approved_by       UUID          FK -> employees.id
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

UNIQUE (project_id, draw_number)
IDX: project_id, loan_id, status, request_date
```

---

### reconciliation_sessions
```
TABLE reconciliation_sessions
  id                UUID          PK
  bank_account_id   UUID          FK -> bank_accounts.id NOT NULL
  organization_id   UUID          FK -> organizations.id NOT NULL
  statement_date    DATE          NOT NULL
  statement_balance NUMERIC(18,2) NOT NULL
  book_balance_start NUMERIC(18,2)
  book_balance_end  NUMERIC(18,2)
  reconciled_balance NUMERIC(18,2)
  difference        NUMERIC(18,2) GENERATED ALWAYS AS (statement_balance - reconciled_balance) STORED
  status            ENUM('open','in_progress','reconciled','exception')
  started_by        UUID          FK -> employees.id
  completed_by      UUID          FK -> employees.id
  started_at        TIMESTAMPTZ
  completed_at      TIMESTAMPTZ
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

UNIQUE (bank_account_id, statement_date)
IDX: bank_account_id, organization_id, status, statement_date
```

---

### audit_log
```
TABLE audit_log
  id                BIGSERIAL     PK
  organization_id   UUID          NOT NULL
  actor_id          UUID          NOT NULL
  actor_type        ENUM('employee','system','api_key','integration')
  action            ENUM('create','update','delete','state_change','approve','void','post','reverse','login','export')
  entity_type       VARCHAR(100)  NOT NULL
  entity_id         UUID          NOT NULL
  old_values        JSONB
  new_values        JSONB
  ip_address        INET
  user_agent        TEXT
  request_id        UUID
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()

IDX: organization_id, entity_type, entity_id, actor_id, action, created_at
-- Partition by created_at monthly
-- Never DELETE or UPDATE rows in this table
```

---

## 3.2 Relationship Map (ERD Cardinality)

```
organizations ||--o{ organizations          (self: parent_id, hierarchy)
organizations ||--o{ projects               (one org owns many projects)
organizations ||--o{ bank_accounts          (one org has many bank accounts)
organizations ||--o{ chart_of_accounts      (one CoA set per org)
organizations ||--o{ vendors                (org-level vendor registry)
organizations ||--o{ employees              (org employs many people)
organizations ||--o{ investors              (org manages many investors)

projects      ||--o{ loans                  (project has multiple debt tranches)
projects      ||--o{ budget_lines           (project has line-item budget)
projects      ||--o{ draw_requests          (project submits draws to lender)
projects      ||--o{ developer_fees         (project generates dev fees)
projects      ||--o{ transactions           (all project-level cash flows)
projects      ||--o{ journal_entries        (all project accounting entries)

investors     ||--o{ investor_capital_accounts (investor has account per project)
developer_fees }o--|| journal_entries        (fee state change creates JE)
```

---

# Section 4 — Source of Truth Matrix

| Data Type | Source of Truth | Sync Direction |
|-----------|----------------|----------------|
| Bank account balance | Plaid (live feed) | Plaid -> system -> QBO |
| Transaction records | Plaid (raw import) | Plaid -> transactions table -> QBO |
| General ledger / journal entries | System (this DB) | System -> QBO (one-way push) |
| Chart of accounts | System (this DB), mirrored to QBO | System -> QBO |
| Project budgets | System (this DB) | System only |
| Loan balances and terms | System (this DB) | System only; QBO gets liability balance via JE |
| Construction draw requests | System (this DB) | System only |
| Investor capital balances | System (this DB) | System only; summary equity entries pushed to QBO |
| Developer fee accruals | System (this DB) | System -> QBO (JE per state transition) |
| Payroll figures | Payroll system (Gusto/Rippling/ADP) | Payroll system -> this DB -> QBO |
| Reconciliation status | System (this DB) | System -> QBO (cleared status) |
| Audit trail | System (this DB, append-only) | System only; never synced outbound |

---

# Section 5 — Data Flow Architecture

## 5.1 Bank Feed Flow (Plaid -> System -> QBO)

```
BANK INSTITUTION
        |
        v
PLAID API (transactions/sync endpoint, delta mode)
        |
        | Webhook: transactions.created / modified / removed
        v
INGEST SERVICE (background worker, every 15 min + webhook-triggered)
  - Validate Plaid webhook signature
  - Deduplicate on plaid_transaction_id (upsert pattern)
  - Write raw record to transactions table, source='plaid', status='unreconciled'
  - Emit event: transaction.ingested
        |
        v
CATEGORIZATION ENGINE
  - Apply rule engine: merchant + amount + account -> chart_of_accounts mapping
  - Apply ML classifier for uncategorized TXs
  - Flag low-confidence assignments (confidence < 0.85) for human review
  - Update transactions.account_id_coa and project_id
  - Emit event: transaction.categorized
        |
        v
AUTO-JOURNAL ENGINE
  - Generate draft journal_entry + lines per categorized transaction
  - Auto-post if confidence > 0.95 AND amount < auto-post threshold
  - Queue for human review otherwise
        |
        v
QBO SYNC SERVICE
  - Batch finalized JEs every 15 min
  - Call QBO JournalEntry API
  - Store qbo_journal_entry_id
  - On conflict: system wins on financial amounts
```

---

## 5.2 Developer Fee Capture Flow (5-State Machine)

```
MILESTONE TRIGGER
  - PM marks project milestone complete
  - System creates developer_fees row with state='earned'
  - Emits alert: developer_fee.earned
          |
          v
       ACCRUED
  - Accountant confirms calculation
  - JE: DR Developer Fee Receivable / CR Developer Fee Revenue
  - developer_fees.state -> 'accrued'
          |
          v (may defer per LP agreement)
       DEFERRED
  - JE: DR Developer Fee Receivable / CR Deferred Developer Fee Liability
  - developer_fees.state -> 'deferred', deferral_reason logged
          |
          v
       APPROVED
  - GP approval recorded, payment queued
  - developer_fees.state -> 'approved'
          |
          v
         PAID
  - ACH/wire initiated
  - Transaction matched to developer_fees record
  - JE: DR Deferred Dev Fee Liability / CR Cash
  - developer_fees.state -> 'paid'

STATE TRANSITION RULES:
  earned -> accrued (accountant action only)
  accrued -> deferred (accountant action with reason)
  accrued -> approved (direct path if no deferral)
  deferred -> approved (GP action)
  approved -> paid (treasurer/controller + cash confirmation)
  Any state -> prior state: BLOCKED (forward-only machine)
```

---

## 5.3 Construction Draw Flow

```
PROJECT MANAGER
  - Enters vendor bills, system validates W-9 + lien waivers + budget availability
  - Creates draw_request, assigns vendor_bills
          |
          v
INTERNAL REVIEW (Controller)
  - Reviews budget-to-actual, commitment report, prior draws
  - draw_requests.status -> 'internal_review' -> 'title_review'
          |
          v
LENDER SUBMISSION
  - System generates AIA G702/G703-style draw package (PDF)
  - draw_requests.status -> 'lender_review'
          |
          v
LENDER APPROVAL + FUNDING
  - Lender wires funds to construction escrow
  - Plaid detects incoming wire -> auto-matches to loan_draws
  - JE: DR Construction Escrow Cash / CR Construction Loan Payable
  - loan_draws.status -> 'funded', loans.amount_drawn updated
          |
          v
DISBURSEMENT
  - Vendor bills paid from escrow
  - JE: DR Construction in Progress / CR Construction Escrow
  - budget_lines.paid_to_date updated
```

---

## 5.4 Key Architectural Constraints

**Immutability rules:**
- audit_log: no UPDATE or DELETE ever; insert-only
- Posted journal_entries: cannot be edited; must be reversed with offsetting JE
- Funded loan_draws: amounts locked; status changes only
- Paid distributions: locked; reversal creates new record

**Encryption at rest (column-level):**
- ssn_enc, ein_enc, bank_account_enc, bank_routing_enc, plaid_access_token_enc
- AES-256-GCM; key managed in AWS KMS or equivalent

**Multi-tenancy boundary:**
- organization_id on every business entity
- Row-level security (RLS) enforced at DB layer
- Cross-organization queries permitted only for parent->child hierarchy traversal

**Balancing enforcement:**
- journal_entry_lines: DB trigger verifies SUM(debit) = SUM(credit) before insert/update
- investor_capital_accounts.current_balance: generated column ensures no drift
- budget_lines.revised_budget: generated column

---

# 6. REVENUE LEAKAGE PREVENTION SYSTEM

---

## 6.1 The Fee Capture Problem

### Quantified Revenue at Risk

On a $20M annual project expense base at a 5% fee rate, total addressable developer fee revenue is $1,000,000 per year. Industry benchmarks document that manual tracking fails to identify 15–35% of eligible expenses. At 25% miss rate:

```
$20,000,000 total project expenses
x 25% average miss rate
= $5,000,000 unreviewed eligible expense base per year
x 5% developer fee rate
= $250,000 in uncaptured developer fee revenue per year
```

This is permanent revenue loss. Once an LPA's invoicing window closes (typically 60–90 days post-expense), the fee is contractually waived.

### Why Manual Tracking Fails

1. **Expense Origination Mismatch.** Most missed eligible expenses originate in the parent entity's GL — not in the individual project partnership's books. Internal overhead allocations, allocated insurance, and legal fees are posted to the parent first. No human review step reliably catches them.

2. **Time Decay of Awareness.** Eligible expense recognition requires someone to check expenses for fee eligibility during monthly close. By that point, invoicing windows are partially consumed.

3. **No Taxonomy Enforcement at Entry.** Expense coding and fee eligibility evaluation are completely decoupled in manual systems. This structural separation guarantees leakage.

4. **LPA Variation Across Projects.** Each LPA may define the fee base differently. A human reviewer must hold all variations in working memory. Automated rule application per LPA eliminates this failure mode.

---

## 6.2 Fee Eligibility Rules Engine

### Eligible Expense Categories

| # | Expense Category | Eligible Rationale |
|---|---|---|
| 1 | Project management salaries | Developer's core management service |
| 2 | Internal overhead allocation | Represents real cost of managing the project |
| 3 | Architectural fees | Direct soft cost of development |
| 4 | Engineering fees — civil, structural, MEP | Design costs are standard eligible soft costs |
| 5 | Permit fees | Government-imposed development costs |
| 6 | Environmental studies | Required to execute the project |
| 7 | Geotechnical and survey fees | Required due diligence |
| 8 | General contractor hard construction costs | Largest single eligible category |
| 9 | Hard cost change orders — approved | Eligible if properly documented |
| 10 | Carrying costs — capitalized interest | Eligible when LPA allows capitalization |
| 11 | Real estate taxes during construction | Property carrying cost |
| 12 | Insurance premiums allocated per project | Direct project cost |
| 13 | Legal fees — entitlement, zoning | Development-enabling legal costs |
| 14 | Legal fees — partnership formation | Organizational costs |
| 15 | Title and escrow fees | Transaction costs attributable to the project |
| 16 | Appraisal fees | Required for financing |
| 17 | Market studies and feasibility reports | Pre-development soft cost |
| 18 | Utility connection fees and impact fees | Government-mandated development costs |
| 19 | Accounting and audit fees — project-level | Cost of managing the partnership |
| 20 | Model unit and leasing office buildout | Part of project construction cost |

### Ineligible Expense Categories

| # | Expense Category | Exclusion Rationale |
|---|---|---|
| 1 | Land acquisition cost | Most LPAs explicitly exclude land from the fee base |
| 2 | Loan origination fees and financing points | Cost of capital, not cost of development |
| 3 | Lender required reserves | Reserve funding, not project expense |
| 4 | Sales commissions | Disposition cost, not development cost |
| 5 | Post-closing operating costs | Development phase has ended |
| 6 | Fees paid TO Summa Terra or affiliates (circular) | Circular payment; must not be double-counted |
| 7 | Loan repayment — principal and interest | Debt service is not a project expense |
| 8 | Equity distributions to LPs | Return of/on capital, not an expense |
| 9 | Income taxes | Tax obligation, not a project development expense |
| 10 | Personal expenses of principals | Not a project expense |

### Edge Cases

**Edge Case 1: Related-Party Expense**
- Default: Eligible (e.g., architectural fees)
- Flag: Related-party transaction -> CONDITIONAL OPPORTUNITY
- Resolution: Accounting manager confirms arm's-length per LPA

**Edge Case 2: Legal Fees Spanning Acquisition and Development**
- Must be apportioned by line item or documented time-and-effort split
- If cannot be apportioned: CONDITIONAL, escalates with 5-day SLA

**Edge Case 3: Capitalized Interest**
- Eligible only if LPA language explicitly includes capitalized interest
- If LPA is silent: CONDITIONAL

**Edge Case 4: Soft Cost Overruns Exceeding LP Approval Authority**
- Within developer's authority: Eligible automatically
- Exceeding authority without LP consent: CONDITIONAL

### Override Process

Any override requires: (1) CFO or Accounting Manager authority only; (2) reason code from defined list; (3) immutable audit log entry. If same category accumulates >3 overrides in 90 days, system flags for quarterly rules engine review.

---

## 6.3 The 5-State Fee State Machine

```
[QBO Expense Posted]
        |
        v
   [OPPORTUNITY] -----(no invoice by day 45)-----> [MISSED]
        |                                               ^
        | (invoice draft created)                      |
        v                                              |
    [PENDING] -----(no send by day 45)--------------->-+
        |
        | (invoice sent)
        v
   [INVOICED] -----(no payment, abandoned)----------->-+
        |
        | (payment received)
        v
     [PAID]
```

**STATE 1: OPPORTUNITY**
- Trigger: Automatic within 30 seconds of QBO transaction post via webhook
- SLA: Review within 15 business days
- System actions: Create record, notify accounting manager, begin aging clock

**STATE 2: PENDING**
- Trigger: Accounting manager confirms eligibility, initiates invoice preparation
- SLA: Invoice must be sent within 30 days of expense post. Hard MISSED trigger at day 45 regardless.
- System actions: Lock fee calculation, generate QBO draft invoice, escalate to CFO at day 40

**STATE 3: INVOICED**
- Trigger: Invoice marked as sent in QBO
- SLA: Payment expected per LPA terms (typically net 30). Watch at 30 days, At-Risk at 60, Critical at 90.
- System actions: Create AR record, begin AR aging, send reminders

**STATE 4: PAID**
- Trigger: QBO records matching payment via bank feed reconciliation
- Terminal state — revenue recognized. Close OPPORTUNITY, update KPIs.

**STATE 5: MISSED**
- Trigger: Hard automatic trigger at day 45 from expense post with no invoice transmitted. Non-waivable.
- System actions: Immediate CFO alert, add to Cumulative MISSED YTD, require root cause within 5 business days

---

## 6.4 Fee Capture Engine — Technical Specification

### Detection Algorithm

**Step 1 — Ingestion:** QBO fires webhook on new/modified expense. Engine extracts project identifier to route to correct partnership LPA ruleset.

**Step 2 — LPA Layer:** Loads LPA ruleset (fee rate, eligible inclusions/exclusions, invoice timing, fee cap, related-party provisions). If no ruleset loaded: CONDITIONAL OPPORTUNITY + SYSTEM ALERT.

**Step 3 — Category Layer:** Maps GL account code to master taxonomy (~80 expense codes). Returns ELIGIBLE, EXCLUDED, or CONDITIONAL.

**Step 4 — Transaction Flags:** Evaluates related-party vendor list, memo text patterns, and amount threshold ($50K+ = automatic CONDITIONAL).

**Step 5 — Determination:**
- All ELIGIBLE -> confirmed OPPORTUNITY
- Any CONDITIONAL -> CONDITIONAL OPPORTUNITY with accounting manager assignment
- Any EXCLUDED (no CONDITIONAL override) -> EXCLUDED log record, no notification

**Step 6 — Cap Tracking:** Maintains running total per partnership. If new opportunity + running total exceeds LPA cap, OPPORTUNITY created for cap-remaining amount only.

### Calculation Logic

```
Developer Fee Opportunity Amount = Eligible Expense Amount x LPA Fee Rate

Example:
  Architectural invoice: $180,000
  x 5% fee rate
  = $9,000 developer fee opportunity
```

### Batch Processing Schedule

| Batch Process | Frequency | Purpose |
|---|---|---|
| Aging sweep | Daily at 6:00 AM | Trigger Watch/At-Risk/Critical/MISSED state changes |
| Cap recalculation | Daily at 6:00 AM | Update cap-remaining figures |
| Parent entity allocation scan | Weekly Monday | Catch parent-entity expenses not webhook-triggered |
| LPA ruleset validation | Monthly 1st | Flag expiring or amended LPAs |
| Missed pattern analysis | Monthly 1st | Identify category and workflow patterns |
| QBO reconciliation | Monthly during close | Cross-reference PAID records against QBO payments |

---

## 6.5 Revenue Leakage Dashboard KPIs

**KPI 1: Fee Capture Rate**
- Formula: (PAID + INVOICED) / (PAID + INVOICED + MISSED) x 100
- Target: >= 95% | Green: >=95% | Yellow: 90-94.9% | Red: <90%
- Alert: Fires when rate drops below 95% for any 30-day rolling period

**KPI 2: Average Days to Invoice from Expense Post Date**
- Formula: Sum(Invoice Send Date - Expense Post Date) / Count of INVOICED+PAID records
- Target: <= 21 days | Green: <=21 | Yellow: 22-30 | Red: >30
- Alert: Fires when rolling 90-day average exceeds 21 days

**KPI 3: Aging Exposure by Bucket**
- Buckets: Current (0-30 days), Watch (31-60), At-Risk (61-90), Critical/MISSED (90+)
- Target: Watch + At-Risk combined < $50,000 at any time
- Alert: At-Risk > $0 triggers weekly digest; Critical > $0 triggers immediate CFO alert

**KPI 4: Disputed Fee Rate**
- Formula: Total DISPUTED invoices / Total INVOICED x 100
- Target: <= 3% | Green: <=3% | Yellow: 3.1-7% | Red: >7%
- Alert: Fires when rolling rate exceeds 3%

**KPI 5: Cumulative MISSED Dollars YTD**
- Target: $0 target; <$25,000 acceptable; >$25,000 unacceptable
- Display: Large dollar figure, prominently displayed. Resets January 1.
- Alert: Any MISSED event fires immediate alert regardless of amount

---

## 6.6 Aging Analysis

**Current (Days 0-30):** Within normal workflow. No escalation. Dashboard: Blue.

**Watch (Days 31-60):** Alert fires to accounting manager on entry. Weekly Monday digest listing all Watch records. System action: if PENDING record reaches day 40 without INVOICED, escalation to CFO.

**At-Risk (Days 61-90, INVOICED only):** Weekly digest to accounting manager + CFO. Accounting manager must document collection action within 5 business days.

**Critical / MISSED (Days 90+):** Immediate CFO alert. CFO must make collection strategy decision within 5 business days.

### Disputed Fee Workflow

1. LP raises dispute -> accounting manager creates DISPUTED record within 2 business days
2. Dispute categorization: LPA Interpretation / Expense Eligibility / Calculation Error / Timing
3. Accounting manager response SLA: 10 business days with supporting documentation
4. Resolution: Accept (credit memo), Reject (documentation package to LP), or Partial (revised invoice)
5. Pattern analysis: 3+ disputes on same category in 12 months -> "LPA AMBIGUITY" flag

---

# Section 7: AI ACCOUNTING COPILOT SPECIFICATION

---

## 7.1 Architecture

### LLM Selection and Rationale

**Primary Reasoning Engine: Claude claude-sonnet-4-6 (Anthropic)**
Deployed for transaction classification, developer fee eligibility adjudication, and natural-language query response generation. Selected for: (1) superiority on multi-step financial reasoning chains requiring intermediate justification; (2) reliable system prompt adherence for complex business rules; (3) 200K token context window allows full project cost ledgers to be passed inline.

**Embedding Model: text-embedding-3-small (OpenAI)**
Used for vendor name disambiguation, transaction description clustering, and semantic similarity matching. Cost: $0.00002/1K tokens. Embeddings pre-computed at document ingestion and stored in pgvector.

**OCR Engine: Google Document AI (Form Parser)**
Purpose-built structured extraction for AIA G702/G703 forms, lien waivers, and vendor invoices. Returns typed field extractions (invoice_number, amount, date, vendor_name, line_items).

**Anomaly Detection: Isolation Forest (scikit-learn, self-hosted)**
Unsupervised ML for flagging statistically anomalous transactions. Features: amount, cost code, vendor frequency, draw period, day-of-week, amount-to-budget-ratio. Contamination parameter: 0.05 (top 5% flagged). Retrains monthly on confirmed-clean transactions.

### Vector Database: pgvector (PostgreSQL)

Decision: pgvector over Qdrant and Weaviate. Rationale:
- PostgreSQL is already the single operational source of truth
- pgvector stores embeddings in the same row as the transaction or vendor record — single JOIN retrieves semantic match + financial metadata
- At projected scale (<500K vectors), pgvector with HNSW indexing provides sub-100ms query performance
- Supabase manages pgvector natively

Schema addition:
```sql
ALTER TABLE transactions ADD COLUMN description_embedding vector(1536);
ALTER TABLE vendors ADD COLUMN name_embedding vector(1536);
CREATE INDEX ON transactions USING hnsw (description_embedding vector_cosine_ops);
CREATE INDEX ON vendors USING hnsw (name_embedding vector_cosine_ops);
```

### Response Generation Pipeline

1. **Intent Classification** (Claude claude-sonnet-4-6, ~200ms) — classify query, extract entities
2. **Data Retrieval** (PostgreSQL, ~150-400ms) — execute pre-templated SQL (LLM does NOT generate SQL in production)
3. **Context Assembly** (~50ms) — assemble retrieved data with benchmarks and active alerts
4. **Response Generation** (Claude claude-sonnet-4-6, ~800-1,200ms) — format with source citations
5. **Confidence Annotation** (~50ms) — verify every stated number has traceable source citation
6. **Audit Log** (~30ms) — log query, intent, data, response, user_id

**Total Pipeline Latency Target: <2,000ms**

---

## 7.2 Query Catalog

### GROUP A: Transaction Search

**A1: Find Transaction by Description Keyword**
Example: "Find all payments to Alpine Excavation in Q1"
Data Sources: transactions, vendors, bank_feeds
Response: Table of matching transactions with date, amount, invoice, cost code, project, status

**A2: Duplicate Transaction Detection**
Example: "Are there any duplicate invoices from Harmon Concrete this month?"
Response: Flagged matches with confidence score and recommended action

**A3: Unmatched Transaction Search**
Example: "What bank transactions from last week don't have a matching bill?"
Response: Table of unmatched items with days-outstanding and suggested next action

**A4: Transaction Lineage Trace**
Example: "Show me the full audit trail for transaction TXN-20250214-0847"
Response: Ordered chain from source document through GL posting to bank match

---

### GROUP B: Project Financial Review

**B1: Budget vs. Actual by Cost Code**
Example: "What's the variance on Parcel 7 concrete work?"
Response: Original budget, approved COs, revised budget, committed, paid to date, remaining, projected final, overrun flag

**B2: Developer Fee Tracking**
Example: "How much developer fee has been captured on Mesa View so far?"
Response: Eligible costs, fee rate, earned fee, invoiced, unbilled earned fee with ACTION REQUIRED flag

**B3: Draw Package Status**
Example: "Is the Parcel 7 Draw 5 package ready to submit?"
Response: Checklist of required components with complete/missing/flagged status

**B4: Cash Flow Projection**
Example: "When does Parcel 7 run out of construction loan draws?"
Response: Month-by-month projection with burn rate assumption and sensitivity analysis

**B5: Capitalization Period Status**
Example: "What phase is Ridgeline Commons in for ASC 970 purposes?"
Response: Current phase, transition date, next trigger, flagged incorrect postings

---

### GROUP C: Investor Queries

**C1: Capital Account Balance**
Example: "What is Meridian Capital's capital account balance in Parcel 7 LP?"
Response: Commitment, funded, unfunded, distributions received, current balance, book/tax difference flag

**C2: Capital Call Schedule**
Example: "When is the next capital call for Mesa View?"
Response: Next call date, projected amount, calculation basis, notification deadline

**C3: Distribution Waterfall Preview**
Example: "If Mesa View sells at $18M, what does Meridian Capital receive?"
Response: Step-by-step waterfall calculation. Always flagged as projection.

**C4: Investor Report Generation**
Example: "Generate the Q2 investor report for Parcel 7"
Response: Structured report draft routed to accounting manager queue. Cannot auto-send.

---

### GROUP D: Executive Summary Queries

**D1: Portfolio Dashboard**
Example: "Give me a snapshot of all five projects right now"
Response: Summary table — Project | Phase | Budget Utilization | Fee Captured | Next Draw | Flag Count | Cash Runway

**D2: Monthly Financial Summary**
Example: "Summarize last month's financial activity"
Response: Narrative (3-5 sentences) + structured metrics

**D3: Revenue Leakage Estimate**
Example: "How much developer fee did we miss this quarter?"
Response: Missed fees breakdown + pending classification exposure

**D4: Cross-Entity Financial Rollup**
Example: "What's the total overhead allocation across all entities this month?"
Response: Matrix showing each entity's allocated overhead and elimination entries required

---

### GROUP E: Anomaly Investigation

**E1: Explain a Flagged Transaction**
Example: "Why was transaction TXN-20250219-0341 flagged?"
Response: Anomaly reasons, Isolation Forest score, recommended action. Always includes: "This is a statistical flag, not a finding of fraud."

**E2: Change Order Velocity Analysis**
Example: "Are there any unusual change order patterns on Parcel 7?"
Response: CO count and dollar volume by month, late-project concentration flag

**E3: Lien Waiver Date Consistency Check**
Example: "Are all lien waivers in Draw 4 dated correctly?"
Response: Table of each waiver with waiver date, completion date from inspection report, pass/fail

**E4: Vendor Concentration Analysis**
Example: "Are we over-concentrated with any single vendor?"
Response: Top 10 vendors by total spend, flag if any single vendor exceeds 15% of project budget

---

### GROUP F: Compliance and Audit Queries

**F1: ASC 970 Capitalization Review**
Example: "List all transactions expensed but that may need to be capitalized"
Response: Table with one-click reclassification action (requires accounting manager approval)

**F2: Audit Trail Request**
Example: "Pull the complete audit trail for all Q4 entries in Parcel 7"
Response: Chronological log in machine-readable format, downloadable as CSV or PDF

**F3: Intercompany Elimination Check**
Example: "Are all intercompany transactions properly eliminated for consolidation?"
Response: For each intercompany pair, show receivable, corresponding payable, elimination entry status

**F4: Bank Reconciliation Status**
Example: "What accounts have items unreconciled more than 5 business days?"
Response: Table with oldest unreconciled item date, count, total dollar exposure

---

## 7.3 Copilot Integration Points

### Web UI Chat Interface

- Embedded chat panel within accounting dashboard
- Context injection: active project/entity automatically scoped to every query
- Action buttons rendered inline with AI responses (approve reclassification, add to review queue, export)
- Confidence indicator on each response: green/yellow/red

**Hard Limits (enforced at API level, not by prompt):**
- Cannot post journal entries (read-only to GL)
- Cannot approve draw packages
- Cannot release investor reports
- Cannot modify vendor records
- Cannot send external communications

### Slack Integration

**Slash Commands:**
- `/stv query [question]` — free-form copilot query
- `/stv project [name]` — set active project context
- `/stv alerts` — pull current alert summary
- `/stv draw [project] [draw_number]` — draw package status
- `/stv fee [project]` — developer fee capture status

### Scheduled Digest Reports

**Morning Executive Digest (6:30 AM daily)**
- Portfolio-level cash position change from prior day
- Active alerts by severity count
- Developer fee captured yesterday and MTD
- Draw packages requiring action
- Items in accounting manager queue older than 48 hours

**Accounting Manager Morning Queue (7:00 AM daily)**
- 4-6 prioritized queue items ordered by: blocking items, high-confidence anomalies, fee eligibility decisions, routine approvals

**Weekly Project Financial Digest (Monday 8:00 AM)**
- Project-specific budget variance, draw status, fee status, capital call schedule. Reviewed by accounting manager before send.

**Monthly Investor Package (1st business day of month, manual trigger)**
- Prior month actuals, budget variance, draw activity, capital account balances. Released via one-click approval.

---

# Section 8: INTERNAL CONTROLS FRAMEWORK

---

## 8.1 Preventive Controls

**PC-01: Cost Code Assignment Enforcement at Transaction Entry**
Every transaction must carry a valid cost_code_id before saving. GL account mapping applied automatically. No human override of GL account mapping at transaction entry — overrides require a journal entry with separate approval.

**PC-02: Duplicate Invoice Block Before Payment**
Four-dimensional check: exact invoice number, fuzzy amount (+-2%), approximate date (+-30 days), cross-entity scope. Block on confidence >0.85. Accounting manager can override with documented reason code.

**PC-03: Developer Fee Eligibility Gate**
Every transaction over $500 passes through the five-layer eligibility classifier. Claude classifications are not auto-applied — require human confirmation.

**PC-04: Capitalization Period Enforcement**
Phase transitions recorded as immutable events with accounting manager approval. Transactions posted in wrong period require reversing journal entry with documented reason.

**PC-05: Partnership Agreement Terms Locked at Project Onboarding**
Fee rate, fee basis, preferred returns, waterfall structure stored in partnership_agreements table. Immutable except through change control (accounting manager entry + executive approval).

**PC-06: Intercompany Transaction Type Tagging**
IC transactions must identify source and counterparty entity. Validated that corresponding receivable/payable exists. Elimination entry auto-generated; accounting manager approves.

**PC-07: Vendor Onboarding Controls**
New vendors require legal name, EIN/W-9, vendor type classification, and accounting manager approval before payment. Related-party vendors trigger enhanced scrutiny on all transactions. Embedding deduplication at onboarding (>0.92 cosine similarity triggers merge warning).

**PC-08: Draw Package Completeness Gate**
Required: AIA G702/G703, unconditional lien waivers (subs >$10K), conditional lien waivers for current draw, inspection report (within 30 days), sworn contractor's statement, budget-to-actual variance explanation (>10% variance).

---

## 8.2 Detective Controls

**DC-01: Isolation Forest Anomaly Detection (Nightly)**
Runs nightly at 2:00 AM. Features per transaction: amount, amount-to-average-for-vendor ratio, amount-to-budget ratio, day-of-week, days-since-last-invoice, draw-period-proximity. Top 5% flagged. Scores >0.80 auto-added to morning queue.

**DC-02: Bank Feed Reconciliation Surveillance (Daily)**
Bank transactions matched against bill/payment ledger. Unmatched items trigger alert at day 5, escalation at day 10.

**DC-03: Lien Waiver Date Cross-Reference (Per Draw)**
Lien waiver date cross-referenced against inspection report date. Waiver dated before inspection = draw_fraud_flag. Zero tolerance.

**DC-04: Change Order Velocity Analysis (Per Draw Submission)**
>20% of total COs submitted in final 25% of project timeline triggers review flag. >15% CO-to-original-contract ratio triggers accounting manager review.

**DC-05: Cross-Entity Duplicate Payment Detection (Weekly)**
Full 90-day cross-entity scan. Exact invoice number match across different entities = immediate flag.

**DC-06: Developer Fee Recognition vs. Invoicing Drift (Monthly)**
If earned > invoiced by >$25,000: unbilled_revenue_flag. If invoiced > earned: deferred_revenue_flag.

**DC-07: GL Account Mapping Drift Detection (Monthly)**
Monthly comparison of current GL mappings to baseline. Any change listed with user, timestamp, old vs. new mapping.

**DC-08: Related-Party Transaction Completeness Review (Quarterly)**
All related-party transactions cross-referenced against documented intercompany agreements and ASC 850 disclosure requirements.

---

## 8.3 Automated Alert Catalog

| Alert | Trigger | Threshold | Recipient | Escalation |
|---|---|---|---|---|
| ALERT-01: High-Confidence Duplicate | confidence >= 0.90 on new bill | Any | Accounting Mgr | 4hr no-action -> re-alert + morning queue |
| ALERT-02: Budget Overrun (Cost Code) | committed+paid > revised_budget x threshold | >90% warning; >100% critical | Acct Mgr + PM; + Exec on critical | Critical: exec if no CO in 2 days |
| ALERT-03: Bank Rec Unmatched >5 Days | posted_date + 5 biz days < today AND unmatched | 5 days warning; 10 days critical | Acct Mgr; + Exec on critical | Flag as control failure at 15 days |
| ALERT-04: Lien Waiver Date Inconsistency | waiver_date < inspection_date for same period | Any (zero tolerance) | Acct Mgr, PM, Exec | Draw BLOCKED; escalate to legal if fraud suspected |
| ALERT-05: Unbilled Earned Fee >$25K | fee_earned - fee_invoiced > $25K | $25K warning; $50K critical | Acct Mgr, Exec | If not invoiced in 5 days: critical to exec |
| ALERT-06: Anomaly Score High | Isolation Forest score > 0.80 | >0.80 morning queue; >0.90 immediate | Acct Mgr; immediate on >0.90 | Related-party + >0.90: immediate exec |
| ALERT-07: Post-Completion Capital Cost | project_phase=post_completion AND capitalizable account | Any | Acct Mgr | If unresolved 10 days: exec alert |
| ALERT-08: IC Transaction No Counterparty | IC transaction AND no counterparty entry in 2 days | 2 business days | Acct Mgr | 5 days: exec weekly digest |
| ALERT-09: CO Late-Project Concentration | COs in final 25% > 30% of total CO value | >30% | Acct Mgr, PM, Exec | Mandatory enhanced review per CO |
| ALERT-10: Capital Call Past Due | due_date < today AND unfunded | Any past-due | Acct Mgr, Exec; + Legal at 10 days | 10 days: legal counsel per LP default provisions |
| ALERT-11: Bank Feed Connection Failure | Last successful sync > 24 hours | 24hr warning; 48hr critical | Acct Mgr; + Exec on critical | Auto-retry every 2 hours; manual import at 48hr |
| ALERT-12: Related-Party No Documentation | related-party vendor AND no agreement linked AND >$5K | $5,000 | Acct Mgr, Exec | Payment HELD; exec at 3 days |

---

## 8.4 Segregation of Duties Matrix

| Action | ACCT_MGR | EXEC | PM | INVESTOR | SYSTEM |
|---|---|---|---|---|---|
| Create vendor record | Initiate | Approve (related-party) | Request | None | None |
| Approve bill for payment | Approve | Approve (>$100K) | None | None | None |
| Post journal entry | Initiate | Approve | None | None | None |
| Approve journal entry | None | Approve | None | None | None |
| Approve draw package | Approve | Countersign | Mark period complete | None | Compile |
| Release investor report | Approve | Release | None | View | Draft |
| Record phase transition | Initiate | Approve | Request | None | None |
| Override duplicate payment block | Approve | Countersign if >$50K | None | None | None |
| Classify fee eligibility (AI cases) | Approve | None | None | None | Recommend |
| Issue capital call | Initiate | Approve | None | None | None |
| Approve capital distribution | None | Approve | None | None | None |
| SYSTEM can never approve or release anything | | | | | |

---

## 8.5 Fraud Detection Patterns

**FDP-01: Cross-Draw Duplicate Invoice (High Priority)**
Same invoice number or near-duplicate (altered last digit) across different draw periods. Requires full project history matching — human memory cannot bridge 6-month gaps between draws.

**FDP-02: Lien Waiver Pre-Dating (High Priority)**
Contractor submits waiver dated before inspection certification. FIRREA violation in bank-financed construction. System blocks draw; zero tolerance.

**FDP-03: Late-Project Change Order Inflation (Medium Priority)**
Batch of COs in final 20-25% of project when owner oversight is lowest. Individual COs may be legitimate; pattern is the fraud indicator. Requires independent cost estimate for COs >$25K in final 25% of timeline.

**FDP-04: Cross-Entity Invoice Shifting (Medium Priority)**
Invoice assigned to entity with most available budget rather than entity that received services. Vendor-month cross-entity scan catches simultaneous billing.

**FDP-05: Ghost Vendor / Fictitious Payee (Lower Priority)**
Vendor with similar name but different bank account details. Prevention: W-9 gate + EIN validation + embedding deduplication at onboarding. Any bank account change triggers re-verification.

**FDP-06: Unauthorized GL Reclassification (Lower Priority)**
Architectural, not rule-based. PostgreSQL is event-sourced (append-only). No mechanism for silent reclassification — any change requires reversing JE + new entry, creating an audit trail by design.

---

# DASHBOARD SPECIFICATIONS AND AUTOMATION ROADMAP

# 9. DASHBOARD SPECIFICATIONS

---

## 9.1 Accounting Manager Dashboard

### Design Philosophy
One screen. One queue. Zero ambiguity. The dashboard is an action dispatch center, not a reporting surface.

### Global Layout (Desktop, 1440px)

**Top Bar:** Entity selector dropdown | Global Search (Cmd+K) | Alert bell | Last sync timestamp

**Left Sidebar:** Daily Action Queue | Fee Capture Pipeline | Bank Reconciliation | Uncoded Transactions | Draw Package Review | Project Review Mode | Reports | Settings

**Main Content — Three Columns:**
- Column A (480px): Daily Action Queue — primary work surface
- Column B (480px): Contextual detail panel
- Column C (240px): Status rail (alerts, bank rec, entity health)

### Panel 1: Daily Action Queue

**Sort Logic (weighted priority score):**
1. Revenue at risk (fee opportunity dollar x days aging x 0.4 weight)
2. Compliance risk (overdue reconciliation, lender deadlines x 0.35 weight)
3. Time sensitivity (today's due items x 0.25 weight)

**Queue Item Card (72px tall):**
- Left accent bar (4px): Red=critical, Orange=fee opportunity, Blue=reconciliation, Gray=routine
- Type icon + type label
- Primary description (bold 14px)
- Sub-line (12px gray): dollar impact, days pending
- Right: dollar impact badge + action button
- Action options: "Capture Fee" / "Match Now" / "Reconcile" / "Review Draw" / "Resolve"

### Panel 2: Alert Inbox

**Critical (red, pulsing):** SMS + push + email simultaneously. "Acknowledge" button required. Cannot be batch-dismissed.

**Warning (amber):** Push + email. "View" and "Dismiss" buttons.

**Info (gray, collapsed):** Email only. Unread count shown.

### Panel 3: Bank Reconciliation Status

One row per connected bank account. Fields: bank + account (last 4), entity badge, last reconciled date, status (Current/Gap Detected/Overdue/Pending Review), unmatched count.

### Panel 4: Uncoded Transaction Queue

**Left panel (40%):** Transaction list, sorted by dollar amount descending.
- Row background: white (unreviewed), light green (AI suggestion), light yellow (needs manual review)

**Right panel (60%):** Selected transaction detail
- Raw bank description, matched vendor, category selector, project/job code, fee eligibility toggle, notes
- "Approve & Next" (keyboard shortcut: Shift+Enter)

### Panel 5: Fee Opportunity Queue (Kanban)

**5 Columns:**
1. Opportunity — light blue
2. Pending — yellow
3. Invoiced — blue
4. Paid — green
5. **Missed — RED (always visible, never collapsible, never archivable)**

**Missed Column:** Red header, bold dollar total. Each card shows project, original expense, fee amount forfeited, days since opportunity closed. Monthly counter resets but trailing 12-month total shown.

**Card design:** Project name + entity badge, vendor + invoice ref, eligible expense amount, fee amount (green), days in current stage, assignee avatar, quick action button.

### Panel 6: Project Review Mode (5-Step Wizard)

Slides in as full-height drawer (600px wide). Remains open while dashboard is visible behind it.

**Step 1 — Budget vs Actual:** One number (variance). Green/Yellow/Red status.
**Step 2 — Cash Position:** One number (current balance). Runway status color.
**Step 3 — Outstanding Draws:** One number (pending draw value). Days-pending status.
**Step 4 — Unpaid Fees:** One number (outstanding developer fees). Days oldest.
**Step 5 — Open Alerts:** One number (unresolved alert count). Top 2 alerts listed.

Target: trained user completes all 5 steps in under 2 minutes. Auto-records review with timestamp.

---

## 9.2 Controller / CFO Dashboard

### Panel 1: Cash Position (Multi-Entity)

Stacked bar chart — one bar per entity, color-coded by runway status. Total consolidated cash as large number above chart. Table below: Entity | Cash Balance | 30-Day Burn | Runway | Status. CFO-configurable minimum cash reserve threshold line.

### Panel 2: Project Profitability Panel

Horizontal bar chart — one bar per active project. Bar = projected profit margin %. Reference line at company target margin (default 18%). Color: dark green (>5% above target), light green (at target), yellow (within 5% below), red (>5% below or projected loss).

**Drill-down:** Revenue breakdown, cost breakdown, S-curve (expected vs actual cost progression), completion percentage, projected final margin.

### Panel 3: Budget Variance Panel

Table: Project | Budget | Actual to Date | Variance $ | Variance % | Forecast at Completion.

**Level 1 drill-down:** Cost category breakdown (Hard/Soft/Financing/Overhead)
**Level 2 drill-down:** Full line-item view with original budget, approved COs, revised budget, committed, costs to date, paid, forecast, variance explanation field (required for >10% variance)

### Panel 4: Developer Fee Capture Panel

- Large number: "Fees Captured YTD"
- Below in red: "Fees Missed YTD"
- Capture rate donut chart
- Mini kanban counts (item count + dollar value per stage)
- 6-month bar chart with 90% target line
- Banner if trailing 30-day capture rate drops below 70%

### Panel 5: Upcoming Draws Panel

Timeline/Gantt view — one row per active draw request. Columns: Project | Draw # | Amount | Submitted | Lender | Expected Approval | Status. Color: Green (on track), Yellow (<7 days to deadline), Red (past expected date).

### Panel 6: Inter-Entity Balance Panel

Matrix table — entities across rows and columns. Intersection cells show outstanding balance. Color by age: <30 days (white), 30-60 days (yellow), >60 days (red). "Settle Selected" triggers journal entry workflow.

---

## 9.3 Owner / Executive Dashboard

### Design Philosophy
Mobile-first. Answers three questions only: Are we making money? Are we on schedule? Is there a problem I need to handle?

### Panel 1: Company-Wide Cash Snapshot

Total cash across all entities — 48px font, Green/Yellow/Red by runway. Three subsidiary numbers: Operating cash | Project cash | Reserve cash. Trend: "Up/Down $X from last week."

### Panel 2: Project Health Scorecard (Traffic Light)

One card per active project. Each card: project name, phase label, three traffic lights (Budget/Schedule/Cash), one-line status, "Review Project" button.

Overall portfolio indicator: "Portfolio Status: [X] Green / [Y] Yellow / [Z] Red"

### Panel 3: Revenue Leakage Summary

- "Revenue Recovered This Month: $X" (green, large)
- "Revenue Still at Risk: $X" (amber)
- "Revenue Lost (Unrecoverable): $X" (red, smaller but always visible)
- Annual projection: "At current rate: $X. At 90% capture: $Y. Gap: $Z."

### Panel 4: Expected Distributions Timeline

12-month forward-looking timeline. Each month: projected distribution events, estimated amounts, confidence level (High/Medium/Low). High confidence = solid bar, Medium = hatched, Low = dotted outline.

### Panel 5: Comparative Project Performance

Table: Project | Type | Total Cost | Revenue | Profit | Margin % | IRR | Duration | Status. Company average as highlighted reference row. Export to PDF for investor presentations.

---

## 9.4 Investor Self-Service Portal

### Design Philosophy
Zero training required. Three tabs. No transaction-level data. No jargon without definitions.

**Login:** Dedicated subdomain, email magic link, session timeout 8 hours, read-only, investor-scoped.

### Tab 1: My Investment

**Hero:** "Your Current Equity Value" — large, centered. "As of [date]."

**Three-column summary:** Total Capital Contributed | Total Distributions Received | Preferred Return Earned to Date

**Capital Account Detail:** Opening balance by year, contributions, distributions, allocated income/loss, closing balance. Current year expanded; prior years collapsed.

**Next expected distribution:** Month Year + confidence indicator. No dollar amount shown unless High confidence.

### Tab 2: Project Status

One section per project. Each: project name + address + type, phase badge, three traffic lights (read-only), one-paragraph narrative (manually authored, max 200 words, timestamped), key milestones checklist.

No budget line items. No transaction data. No draw detail.

### Tab 3: Documents

File library: Document Type | Project | Period | Date Posted | Action.

Document types: K-1s (sorted to top always), Quarterly Reports, Annual Reports, Capital Call Notices, Distribution Notices, Operating Agreements, Amendment Notices.

K-1 visibility rule: not visible until explicitly published. Placeholder shown: "K-1 for [Year]: Not yet available — expected [date]."

Every download logged with timestamp and session ID (compliance only, investor cannot see log).

---

# 10. AUTOMATION ROADMAP

---

## Priority Matrix Methodology

Score = (Weekly Hours Saved x $75/hr + Annual Revenue Impact + Annual Risk Reduction) / Implementation Days

---

## Priority Tier 1: Immediate Build (Weeks 1-8)

### Automation 1: Transaction Auto-Categorization with AI Confidence Scoring
- **Trigger:** New transaction synced from any bank account
- **Process:** Extract description/amount/date/account/entity -> query historical patterns -> NLP vendor name matching -> assign QBO account code with confidence score -> assign project/job code -> flag for fee eligibility -> auto-post if confidence >90%; queue if 70-90%; escalate if <70%
- **Time Saved:** 12 hrs/week
- **Revenue/Risk:** $40K/year in fees recovered earlier
- **Tools:** n8n + OpenAI GPT-4o-mini + QBO API + Supabase
- **Complexity:** 14 days

### Automation 2: Developer Fee Opportunity Detection
- **Trigger:** Transaction categorized as hard cost, soft cost, or overhead expense above $5,000
- **Process:** Check fee eligibility rules matrix -> calculate 5% developer fee -> deduplicate -> create Opportunity card in Fee Capture Pipeline -> assign to Accounting Manager -> set aging timer (Warning at Day 14, Missed at Day 45)
- **Time Saved:** 8 hrs/week
- **Revenue/Risk:** $150K/year in recovered developer fees (conservative)
- **Tools:** n8n + fee eligibility rules engine in Supabase configuration table
- **Complexity:** 12 days

### Automation 3: Bank Reconciliation Gap Detection
- **Trigger:** QBO bank feed sync completion (every 15 minutes)
- **Process:** Pull QBO bank register balance -> pull Plaid real-time balance -> calculate variance -> if variance >$0: query uncleared transactions -> if unexplained: create reconciliation gap alert with severity (<$500 Info, $500-$5K Warning, >$5K Critical) -> dispatch via appropriate channel -> create accounting manager queue item
- **Time Saved:** 6 hrs/week
- **Revenue/Risk:** $15K/year risk reduction
- **Tools:** n8n + Plaid API + QBO API + Twilio + Firebase + SendGrid
- **Complexity:** 10 days

### Automation 4: Loan Payment Due Date Monitoring
- **Trigger:** Daily scheduled run at 6:00 AM
- **Process:** Query loan obligation schedule -> calculate days until payment -> 14-day warning (push + email) -> 7-day warning (push + email) -> 1-day warning (SMS + push + email + CFO) -> on payment date: verify by 3:00 PM -> if not confirmed: Critical alert to Controller and CFO
- **Time Saved:** 2 hrs/week
- **Revenue/Risk:** $75K/year in avoided penalties
- **Complexity:** 7 days

### Automation 5: Draw Package Assembly
- **Trigger:** "Prepare Draw" button clicked or scheduled by draw calendar
- **Process:** Pull all categorized hard cost transactions since last draw -> group by cost category/budget line -> apply 5% overhead calculation -> pull lender-required documents from repository -> generate draw request summary in lender-specified format -> flag line items over budget -> present in side-by-side review UI -> on approval: generate PDF, send to lender -> create draw tracking record
- **Time Saved:** 7.5 hrs/week (30 hrs/month)
- **Revenue/Risk:** $68K/year in reduced carry cost
- **Tools:** n8n + custom PDF (Puppeteer) + QBO API + document storage + lender template library
- **Complexity:** 18 days

### Automation 20: Regulatory and Insurance Compliance Calendar (Tier 1 override due to tail risk)
- **Trigger:** Daily check at 7:00 AM from manually-seeded compliance dates
- **Process:** Check all active deadlines (entity annual reports, insurance, licenses, lender reporting, tax filings) -> 60-day notice (email) -> 30-day notice (push + email) -> 7-day notice (SMS + push + email) -> day-of Critical alert -> log acknowledgment required -> unacknowledged critical escalates to Owner after 24 hours
- **Revenue/Risk:** $200K+/year in avoided catastrophic risk (lapsed insurance, covenant default)
- **Complexity:** 8 days

---

## Priority Tier 2: Build Weeks 8-16

### Automation 6: Investor Portal Auto-Update on Milestone Completion
- Trigger: Milestone marked complete. Process: Identify all investors, update portal milestone checklist, generate notification email, log to audit trail. If distribution-triggering: trigger Distribution Notice workflow.
- Time Saved: 3 hrs/week | Revenue/Risk: $52K/year | Complexity: 8 days

### Automation 7: Monthly Financial Package Auto-Generation
- Trigger: 5th business day of month, 6:00 AM. Process: Verify prior month QBO close -> pull QBO data -> generate consolidated P&L -> calculate budget variances -> assemble CFO package and investor package -> deliver and publish.
- Time Saved: 3.75 hrs/week | Revenue/Risk: $30K/year | Complexity: 20 days

### Automation 8: Distribution Notice and Capital Account Update
- Trigger: Distribution approved in dashboard (manual approval required — no auto-distribution).
- Process: Calculate per-investor amounts per waterfall rules -> generate distribution notice PDF -> update capital account balances in portal -> send email with PDF -> create ACH/wire file -> log to audit trail.
- Time Saved: 1.85 hrs/week | Revenue/Risk: $30K/year | Complexity: 22 days

### Automation 9: Vendor Invoice Capture and Three-Way Match
- Trigger: Invoice received in accounting email inbox or uploaded to document portal.
- Process: OCR extraction -> vendor master lookup -> PO match -> contract rate check -> duplicate check -> create QBO bill -> route for approval (>$25K: Controller; >$100K: Owner).
- Time Saved: 8 hrs/week | Revenue/Risk: $40K/year | Complexity: 16 days

### Automation 10: Inter-Entity Transaction Auto-Recording
- Trigger: Transaction with inter-entity indicator detected.
- Process: Identify originating and receiving entity -> create matching journal entries in both QBO entities -> update inter-entity balance matrix -> alert if counterparty not confirmed in 3 days.
- Time Saved: 4 hrs/week | Revenue/Risk: $20K/year | Complexity: 12 days

### Automation 13: Accounts Receivable Aging and Collection Workflow
- Daily check at 8:00 AM. Collection schedule: Day 30 friendly reminder, Day 45 second notice + Controller CC, Day 60 final notice + Owner, Day 75 flag for legal review. Developer fee invoices: escalate to Fee Capture Pipeline "aging" at Day 14.
- Time Saved: 3 hrs/week | Revenue/Risk: $14K/year | Complexity: 10 days

### Automation 14: Budget Amendment Workflow and Approval Routing
- Route by threshold: <$10K (Accounting Mgr), $10K-$50K (Controller), >$50K (Owner). Direct approve/reject buttons in notification. On approval: update budget, recalculate variances. Maintain immutable amendment log.
- Time Saved: 2 hrs/week | Revenue/Risk: $10K/year | Complexity: 8 days

---

## Priority Tier 3: Build Weeks 16-28

### Automation 11: AI Copilot Financial Query Engine
- FastAPI /ai/query endpoint. NL to pre-templated SQL (LLM does NOT generate SQL). Query PostgreSQL. Format results with Claude. Source-cite every number.
- Time Saved: 5 hrs/week | Revenue/Risk: $30K/year | Complexity: 25 days

### Automation 12: Construction Loan Draw Compliance Monitoring
- Per draw and daily at 7:00 AM. Checks: LTV, completion percentage, lien waiver presence. Block draw initiation on any failure.
- Time Saved: 3 hrs/week | Revenue/Risk: $60K/year | Complexity: 18 days

### Automation 15: K-1 Preparation Data Package Assembly
- January 15 trigger (manual confirmation required). Pull full-year capital account activity + allocated income/loss per investor. Generate CPA-ready Excel workbook. Flag anomalies. Deliver securely to CPA.
- Time Saved: 0.4 hrs/week | Revenue/Risk: $25K/year | Complexity: 14 days

### Automation 16: Cash Flow Forecasting Model Auto-Update
- Trigger: Any new transaction, draw approval, budget amendment, or weekly Monday 6:00 AM.
- Process: Current cash balances + known future outflows + expected inflows -> 13-week rolling forecast per entity -> flag weeks with projected negative cash -> weekly "Cash Position Summary" email Monday.
- Time Saved: 6 hrs/week | Revenue/Risk: $100K/year | Complexity: 20 days

### Automation 17: New Vendor Onboarding and W-9 Collection
- Auto W-9 request email with secure upload link. Day 7, Day 14 follow-up. OCR W-9 extraction. Flag for 1099 reporting.
- Time Saved: 2 hrs/week | Revenue/Risk: $5.6K/year | Complexity: 12 days

### Automation 18: Project Close-Out Financial Reconciliation
- Trigger: Project marked "Disposition Complete." Reconcile all transactions against budget -> calculate final IRR and equity multiple -> settle inter-entity balances -> generate close-out package -> archive documents -> update comparative performance panel.
- Time Saved: 0.8 hrs/week | Revenue/Risk: $35K/year | Complexity: 22 days

### Automation 19: Expense Report and Reimbursement Processing
- OCR receipt extraction -> route to project code -> verify against expense policy -> flag violations -> route for approval -> on approval: create QBO bill payable to employee.
- Time Saved: 3 hrs/week | Revenue/Risk: $8K/year | Complexity: 14 days

---

## Master Priority Table

| Rank | Automation Name | Weekly Hours Saved | Annual Impact | Impl Days |
|------|----------------|-------------------|--------------|-----------|
| 1 | Transaction Auto-Categorization | 12 hrs | $40K | 14 |
| 2 | Developer Fee Opportunity Detection | 8 hrs | $150K | 12 |
| 3 | Bank Rec Gap Detection | 6 hrs | $65K | 10 |
| 4 | Loan Payment Monitoring | 2 hrs | $75K | 7 |
| 5 | Draw Package Assembly | 7.5 hrs | $68K | 18 |
| 6 | Investor Portal Auto-Update | 3 hrs | $52K | 8 |
| 7 | Monthly Financial Package | 3.75 hrs | $30K | 20 |
| 8 | Distribution Notice + Cap Account | 1.85 hrs | $30K | 22 |
| 9 | Vendor Invoice Three-Way Match | 8 hrs | $40K | 16 |
| 10 | Inter-Entity Auto-Recording | 4 hrs | $20K | 12 |
| 11 | AI Copilot Query Engine | 5 hrs | $30K | 25 |
| 12 | Draw Compliance Monitoring | 3 hrs | $60K | 18 |
| 13 | A/R Aging and Collections | 3 hrs | $14K | 10 |
| 14 | Budget Amendment Workflow | 2 hrs | $10K | 8 |
| 15 | K-1 Data Package Assembly | 0.4 hrs | $25K | 14 |
| 16 | Cash Flow Forecasting Auto-Update | 6 hrs | $100K | 20 |
| 17 | Vendor W-9 Onboarding | 2 hrs | $5.6K | 12 |
| 18 | Project Close-Out Reconciliation | 0.8 hrs | $35K | 22 |
| 19 | Expense Report Processing | 3 hrs | $8K | 14 |
| 20 | Compliance Calendar | 2 hrs | $200K | 8 |

**Total weekly hours reclaimed (all 20 automations fully deployed): 82.5 hours/week**
**Total estimated annual financial impact: $1,077,600**
**Estimated 12-month build cost: $168,000-$177,000**
**Payback period: approximately 4 months after full deployment**

---

# BUILD PLAN AND TOOL STACK SPECIFICATION

# 11. TOOL STACK SPECIFICATION

---

## 11.1 Core Stack Decision Matrix

| Layer | Paid Option | FOSS Option | Recommendation | Reason |
|-------|------------|-------------|----------------|--------|
| Accounting Core | QuickBooks Online Advanced ($235/mo) | ERPNext (Frappe) | **Hybrid: QBO now, ERPNext migration at 5+ entities** | QBO is fastest path to working multi-entity ledger. ERPNext wins on total cost at scale but requires 150-300 hours configuration. |
| Database | Self-hosted PostgreSQL on VPS | Supabase (managed, $25/mo Pro) or Neon (serverless, free-$19/mo) | **Recommended: Supabase Pro ($25/mo)** | Supabase bundles PostgreSQL + PostgREST (auto REST API) + Row Level Security + Auth + Storage — replacing 4 separate tools. Neon is better for pure PostgreSQL with branch-per-environment. See Section 11.4 for full comparison. |
| Bank Feeds | Plaid ($300-$1,500/mo at volume) | QBO Bank Feed API (included in QBO subscription) | **Free: QBO API** | QBO already connects to all bank accounts for reconciliation. Pull transactions via QBO REST API v3 into PostgreSQL. Zero additional cost — included in existing QBO Advanced subscription. ofxclient (Python, free) as secondary pull for any institution not in QBO. |
| Automation / Workflow | Make ($200-$800/mo) / Zapier | n8n (self-hosted, fair-code) | **FOSS: n8n (Docker on $20-40/mo VPS)** | n8n handles bank feed ingestion, transaction routing, QBO API writes, investor report dispatch. Replace Make/Zapier entirely after MVP. |
| AI / LLM | GPU instance vLLM ($160-240/mo) | Claude API (Haiku) + Groq free tier + Ollama CPU | **Free: Claude Haiku API + Groq** | A 1-3 person team generates ~30-50 NL queries/day. At Claude Haiku pricing ($0.25/M input, $1.25/M output), 50 queries × 2K tokens = ~$4-8/mo — absorbed in existing Claude API budget. Groq free tier (6,000 req/day on Llama 3.1 70B) handles transaction classification batch jobs at $0. No GPU instance needed. |
| Dashboards (Internal) | Power BI / Metabase Pro ($575/mo) | Apache Superset | **FOSS: Apache Superset (Docker, self-hosted)** | Connects directly to PostgreSQL, supports multi-entity parameterized dashboards. |
| Investor Portal | Metabase Pro / Power BI Embedded | Evidence | **FOSS: Evidence (templated, version-controlled quarterly reports)** | Evidence renders LP packets from SQL queries as polished static reports. No live RLS gap. |
| E-Signatures | DocuSign ($25-40/mo + per-envelope) | DocuSeal (self-hosted, Docker) | **Free: DocuSeal** | Full DocuSign equivalent: signature fields, audit trail, email delivery, completed PDF storage, API. 14,000+ GitHub stars. Deploy in 10 min on existing VPS. $0 forever, no per-envelope fees. |
| Physical Mail | Lob ($0.75-1.50/piece) | Local print + USPS | **Free: Local print** | At 10-50 investors with 1-2 physical mailings/year (K-1s), volume does not warrant an API. Print PDF locally, stamp, mail. ~$1-2/letter twice/year. All other delivery via email (Resend). |
| Transactional Email | Postmark ($15/mo) | Resend free tier | **Free: Resend** | 3,000 emails/month, 100/day free forever. Sufficient for 1-3 person team + investor notifications. Clean API, React email templates, good deliverability. n8n Resend community node available. |
| Object Storage | Backblaze B2 ($7/mo) | Cloudflare R2 (free tier) + MinIO (self-hosted) | **Free: Cloudflare R2** | 10GB storage, 1M Class A ops, 10M Class B ops free forever. Zero egress fees. S3-compatible API — n8n S3 nodes work unchanged, just update endpoint URL. MinIO as self-hosted fallback if R2 ever costs anything. |
| Alerts | PagerDuty / Slack | Apprise + Telegram Bot API | **FOSS: Apprise + Telegram** | Apprise supports 80+ channels. Telegram bot already in user's stack. |
| Search | Algolia | Meilisearch (self-hosted) | **FOSS: Meilisearch (Docker)** | Sub-10ms, self-hosted, minimal configuration. |
| API Layer | Retool / Custom | PostgREST + FastAPI | **FOSS: FastAPI + PostgREST** | FastAPI exposes developer fee engine, waterfall logic, QBO sync endpoints. PostgREST auto-generates REST API from PostgreSQL schema. |
| Internal UI / Admin | Retool ($10-$50/user/mo) | Appsmith (self-hosted) | **FOSS: Appsmith** | Connects to PostgreSQL, FastAPI, and QBO API for internal admin screens. |

---

## 11.2 QuickBooks Online Integration Spec

**QBO's role:** QBO is the accounting record-of-truth for the GL, AP, AR, bank reconciliation, and financial statements. It is not the transaction classification engine, the developer fee calculator, the investor reporting layer, or the data warehouse. Every dollar of logic sits upstream in PostgreSQL. QBO receives only clean, pre-classified, pre-split transactions via API.

**What QBO does:**
- Holds the authoritative double-entry GL per legal entity
- Generates QBO-native P&L by Class, Balance Sheet by Location, and AR/AP aging
- Provides bank reconciliation interface
- Feeds accountant and CPA workflows

**What QBO does not do:**
- Classify or split construction loan draws
- Calculate developer fees
- Consolidate across entities
- Produce investor LP reports or waterfall distributions
- Detect inter-entity transfers

**API Integration Requirements:**
- One OAuth 2.0 token per QBO company file. N entities = N OAuth flows managed in n8n with tokens stored encrypted in PostgreSQL.
- QBO REST API v3: /v3/company/{companyId}/query (IQL) for reads; journalentry, purchase, payment endpoints for writes.
- Rate limit: 500 requests/minute per company file.
- Webhook subscription per company file for real-time change detection. Conflict resolution: PostgreSQL staging record wins. Manual QBO edit triggers Slack/Telegram alert.
- Sync frequency: nightly full reconciliation (2:00 AM). Intraday: webhook-driven for new bank feed transactions only.

**Chart of Accounts Structure (4-segment, non-negotiable):**

```
[Entity Prefix] - [Account Type Code] - [Cost Category] - [Phase]

Entity Prefixes: STV (parent), LP01 through LP0N (per partnership)
Account Type Codes:
  1000-1999 = Assets
  2000-2999 = Liabilities
  3000-3999 = Equity
  4000-4999 = Revenue
  5000-5999 = COGS / Direct Project Costs
  6000-6999 = Operating Expenses
  7000-7999 = Developer Fee Accruals (custom)
  8000-8999 = Inter-Entity (Due To/Due From)
Cost Category: LAND, HARD, SOFT, FIN
Phase: 00 (pre-development), 01 (entitlement), 02 (construction), 03 (closeout)

Example: LP03-5100-HARD-02 = Partnership 3, Direct Project Cost, Hard Cost, Construction Phase
```

**Class / Location Strategy:**
- Classes = Projects (one Class per development project)
- Locations = Legal Entities (one Location per partnership LLC)
- Do NOT use QBO's "Projects" feature — it cannot consolidate across company files.

**Inter-Entity Transfer Convention:**

Machine-parseable memo field format enforced by n8n before journal entry reaches QBO:
```
[Receiving Entity Code]-[Sending Entity Code]-[YYYYMM]-[Sequence]
Example: LP03-STV-202506-001
```

**QBO Limitations and Workarounds:**

| Limitation | Workaround |
|-----------|-----------|
| Bank feed auto-categorizes transfers as income/expense | n8n polls QBO Transactions API. IC transfers identified by payee pattern and routed to 8000-8999 accounts before QBO write-back. |
| Construction draws appear as revenue | n8n identifies lender ACH payees from PostgreSQL lender_patterns table. All matching transactions pre-classified as loan_draw type before staging. |
| No native consolidation | PostgreSQL aggregates GL balances nightly. Superset renders consolidated view. |
| No developer fee logic | PostgreSQL fee engine creates paired developer fee accrual entry in QBO as separate JE. |
| Split transactions | n8n intercepts Plaid webhook. Creates multi-line QBO JournalEntry via API with all cost code splits. |
| 500 req/min rate limit | All QBO writes batched nightly. Token-bucket rate limiter in FastAPI layer. |

---

## 11.3 Database Choice: Neon vs Supabase vs Self-Hosted PostgreSQL

Both Neon and Supabase are viable managed PostgreSQL options that replace a self-hosted VPS database. Here is the honest comparison for this system specifically.

### Supabase — Recommended

**What it is:** Managed PostgreSQL with a bundled platform: PostgREST (auto REST API), Row Level Security (enforced at DB layer), Auth (JWT + magic links), and Storage (S3-compatible object storage).

**Why it fits this system better than alternatives:**

| Supabase Feature | Replaces in This Stack | Cost Saved |
|-----------------|----------------------|-----------|
| PostgREST (auto REST API from schema) | Separate PostgREST deployment | ~$10/mo VPS |
| Built-in Row Level Security UI | Manual RLS config management | Engineering time |
| Supabase Auth (magic links, JWT) | Separate auth service for investor portal | $0-$50/mo |
| Supabase Storage (S3-compatible) | MinIO self-hosted or Cloudflare R2 | $0 (R2 is free anyway) |
| Database branching | Separate staging database | ~$10/mo |

**Pricing:**
- Free tier: 500MB database, 2 projects, pauses after 1 week of inactivity. Not suitable for production.
- **Pro tier ($25/mo): 8GB database, no pausing, daily backups, no connection limits.** This is the right tier for this system.
- At 10-20 entities with moderate transaction volume, 8GB is sufficient for 12+ months before needing a storage upgrade.

**Multi-entity RLS pattern for this system:**
```sql
-- Each entity has a schema. RLS enforces entity isolation.
ALTER TABLE transactions_staging ENABLE ROW LEVEL SECURITY;

CREATE POLICY entity_isolation ON transactions_staging
  USING (organization_id = current_setting('app.current_org_id')::uuid);

-- Accounting manager role: all entities
-- Partnership staff role: single entity via session variable
```

**Investor portal:** Supabase Auth handles magic-link login for the investor self-service portal. Investor-scoped RLS enforced at DB layer — investors can only query their own capital account rows. No separate auth service needed.

**Recommendation: Use Supabase Pro ($25/mo).** The bundled platform eliminates 3-4 separate tool deployments, reduces ops burden, and the $25/mo is recovered by dropping MinIO, a separate PostgREST VPS, and a separate auth service.

---

### Neon — Best for Dev/Staging

**What it is:** Serverless PostgreSQL with autoscaling, scale-to-zero, and database branching.

**Key differentiator:** Neon's branching feature lets you create a copy of the production database (schema + data snapshot) in seconds for each development environment. This is powerful for testing schema migrations against real data without touching production.

**Why it's better for dev, not production (for this use case):**
- Free tier: 0.5GB storage, 1 compute hour/day. Production workload (nightly batch jobs, bank feed sync, fee calculations) will hit this limit quickly.
- Paid tier: $19/mo for 10GB, no compute limits. Cheaper than Supabase Pro but does not include PostgREST, Auth, or Storage.
- Scale-to-zero is excellent for infrequent workloads but nightly batch jobs at 2:00 AM (QBO sync, fee calculations) require cold-start tolerance.

**Best use pattern for this system:** Neon for development/staging environment (branch from prod snapshot to test migrations). Supabase Pro for production.

---

### Self-Hosted PostgreSQL on VPS — Viable but Ops-Heavy

**Pros:** Full control, lowest cost at scale ($10-20/mo Hetzner).
**Cons:** You own backups, failover, replication, connection pooling, and security patching. For a 1-3 person accounting team, this operational burden is not worth the $5-15/mo saved vs Supabase Pro.

**Verdict:** Use Supabase Pro for production. The platform removes ops burden that does not belong in a small accounting team's priorities.

---

## 11.4 Zero-Cost Tool Replacements — Implementation Summary

The following paid tools have been eliminated from the stack. This section is the authoritative reference for each replacement's implementation.

### Plaid → QBO Bank Feed API

**Why Plaid costs $500-1,500/mo:** $4-15 per connected institution per month × 10-20 bank accounts.
**Why QBO API is free:** QBO already connects to all bank accounts for reconciliation. The bank feed connection exists. You are paying for it inside your QBO Advanced subscription. The QBO Transactions API surfaces that same data.

**Implementation:**
```
n8n Cron (daily 6:00 AM, per entity):
  → QBO API: SELECT * FROM Transaction WHERE TxnDate >= '{last_sync_date}'
  → normalize: map QBO fields to transactions_staging schema
  → INSERT INTO transactions_staging (entity_id, qbo_txn_id, date, amount, payee, memo, qbo_account, raw_payload)
  → flag: WHERE amount > 10000 → review_required = true
  → flag: WHERE payee MATCHES lender_ach_patterns → transaction_type = 'loan_draw'
```

QBO API endpoint: `GET /v3/company/{realmId}/query?query=SELECT * FROM Transaction WHERE TxnDate >= '2026-01-01'`
Rate limit: 500 req/min per company file. Nightly batch for all entities runs sequentially with 200ms delay between requests.

Fallback for banks not in QBO: `ofxclient` (Python, MIT license). Configured per bank with stored credentials in n8n credential vault.

---

### ERPNext / Frappe Cloud → NocoDB

**Why Frappe Cloud costs $100-200/mo:** Managed hosting for ERPNext. Software is free; this is the cloud tax.
**Why NocoDB is free:** Open source, self-hosted, runs on your existing VPS alongside PostgreSQL.

**What NocoDB replaces in this system:**
- Project budget tracking (was: ERPNext project module)
- Vendor management and PO tracking (was: ERPNext purchase module)
- Draw request status tracking (was: ERPNext custom module)
- Construction cost tracking by line item (was: Google Sheets)
- Loan tracking (was: Google Sheets)

**Implementation:**
```bash
docker run -d --name nocodb \
  -p 8080:8080 \
  -e NC_DB="pg://localhost:5432?u=nocodb&p=secret&d=nocodb" \
  nocodb/nocodb:latest
```

NocoDB connects to the same PostgreSQL instance. Tables exposed in NocoDB are the same tables PostgreSQL uses — no sync required. Accounting manager uses NocoDB for data entry; FastAPI and n8n read the same tables for automation.

---

### GPU Instance / vLLM → Claude API + Groq Free Tier

**Why GPU costs $160-240/mo:** A10G GPU on spot instances × 200 hrs/mo for running Mistral/Llama via vLLM.
**Why this is unnecessary:** A 1-3 person accounting team generates ~30-50 NL queries/day. Claude Haiku at $0.25/M input tokens costs ~$4-8/mo for this volume.

**Cost math:**
```
50 queries/day × 2,000 tokens/query × 30 days = 3,000,000 tokens/month
Claude Haiku input cost: 3M × $0.25/M = $0.75
Claude Haiku output cost: 0.5M × $1.25/M = $0.63
Total copilot cost: ~$1.38/month
```

**Routing:**
- Transaction classification (high volume, batch): Groq API free tier (Llama 3.1 70B, 6,000 req/day, $0)
- AI Copilot NL queries (low volume, user-facing): Claude Haiku (~$4-8/mo)
- Complex financial analysis (rare): Claude Sonnet (on demand)

**No GPU instance. No vLLM deployment. No infrastructure to maintain.**

---

### DocuSign → DocSeal (Self-Hosted)

**Why DocuSign costs $25-40/mo + per-envelope:** SaaS e-signature with per-document pricing.
**DocSeal:** Open source full equivalent. 14,000+ GitHub stars. Production-ready.

```bash
docker run -p 3000:3000 -v docuseal:/data docuseal/docuseal:latest
```

**Integration:**
```
n8n → DocSeal API POST /api/templates/{id}/submissions
  → document sent to signer via email
  → signer completes in browser (no account needed)
  → webhook POST to n8n on completion
  → signed PDF stored in Cloudflare R2
  → PostgreSQL: UPDATE documents SET signed_at = NOW(), r2_key = '{key}'
```

Use for: lien waivers, draw authorizations, vendor contracts, internal approvals, employee expense approvals.

---

### Postmark → Resend Free Tier

**Why Postmark costs $15/mo:** Dedicated IP, guaranteed deliverability SLA.
**Resend free tier:** 3,000 emails/month, 100/day. Sufficient for 1-3 person team + investor notifications.

**Setup:** Configure SPF, DKIM, DMARC on your domain (one-time, free). Install n8n Resend community node. Replace all Postmark API calls with Resend API calls (identical structure, just update API key and endpoint).

Alert emails, monthly investor reports, draw status notifications, fee capture alerts — all fit within 3,000/month free tier at this team size.

---

### Backblaze / Physical Mail (Lob) → Cloudflare R2 + Local Print

**Cloudflare R2 (replaces Backblaze B2):**
- Free: 10GB storage, 1M writes, 10M reads/month. Zero egress fees.
- S3-compatible: update n8n S3 node endpoint to `https://{accountId}.r2.cloudflarestorage.com`. No other code changes.
- Stores: signed documents, draw packages, investor reports, construction photos.

**Local print (replaces Lob):**
- Lob is an API for physical mail. At 10-50 investors receiving 1-2 physical mailings/year, that is 50-100 pieces annually.
- Generate personalized PDFs via Gotenberg (already in stack). Print. Stamp. Mail. Cost: ~$30-60/year.
- No API. No subscription. No per-piece fee.

---

## 11.5 Open Source Stack Configuration

**PostgreSQL via Supabase Pro (Data Spine)**
- Deployment: Supabase Pro ($25/mo). Includes managed PostgreSQL, PostgREST, Auth, Storage, and daily backups. Replaces: separate PostgREST VPS, MinIO or Backblaze, auth service.
- Schema: one schema per legal entity (lp01, lp02, stv_parent). PostgreSQL RLS enforces entity isolation. `consolidated` schema for cross-entity views (CFO role only). Investor portal uses Supabase Auth magic links + investor-scoped RLS.
- Core tables: transactions_staging, transactions_classified, developer_fee_accruals, interentity_transfers, draw_schedules, qbo_sync_log, investor_distributions.
- Alternative: self-hosted PostgreSQL on $10-20/mo Hetzner VPS if Supabase's bundled features are not needed and ops overhead is acceptable.

**n8n (Automation Engine)**
- Deployment: Docker on $20/mo VPS (2 vCPU, 4GB RAM). Queue mode with Redis for reliability.
- Key workflows: (1) QBO Bank Feed Sync (daily 6 AM) -> Staging -> AI Classification via Groq API -> Split Rules -> QBO Write-back; (2) Nightly QBO GL Pull -> Sync log -> Conflict detector; (3) Developer Fee Calculation (nightly, posts accrual JEs); (4) Due To/Due From Aging Check (weekly); (5) Investor Report Generation (monthly via Resend); (6) Budget Variance Monitor (daily).
- Bank feed source: QBO Transactions API (SELECT * FROM Transaction WHERE TxnDate > last_sync), not Plaid. All bank accounts already connected to QBO for reconciliation — this reuses that connection at $0 additional cost.

**LiteLLM Proxy (AI Gateway)**
- Deployment: Docker container (~256MB RAM).
- One virtual API key per legal entity (mapped to partnership cost centers). Per-entity budget caps enforced.
- Model routing: default (high-volume transaction classification) -> Groq API free tier (Llama 3.1 70B, 6,000 req/day free); AI Copilot NL queries -> Claude Haiku API (~$4-8/mo at small-team query volume); complex financial analysis -> Claude Sonnet API. No GPU instance required.
- Estimated monthly LLM cost: $8-25/mo total (Groq free for classification batch; Claude API absorbs copilot queries).

**Apache Superset (Internal BI)**
- Deployment: Docker Compose on $20/mo VPS (4 vCPU, 8GB RAM).
- Required dashboards (Week 4): Multi-entity consolidated P&L, developer fee accrual tracker, draw schedule actuals vs budget, inter-entity Due To/Due From aging, bank feed reconciliation status per entity.
- Row-level security: enforced at PostgreSQL schema level, not in Superset.

**Evidence (Investor Reporting)**
- Deployment: Node.js on same VPS, or static site on Cloudflare Pages (free tier).
- Templates: quarterly LP report, annual K-1 cover letter, capital call notice.
- Output: Evidence builds static HTML/PDF per investor per entity. Gotenberg converts HTML to PDF. Email delivery via Resend (free tier, 3K/mo). Physical copies: printed locally and mailed via USPS for investors requiring hard copy (K-1 season, ~1-2x/year). No Lob API, no Postmark subscription.

**Appsmith (Internal Admin UI)**
- Deployment: Docker on same VPS (~1GB RAM).
- Key screens: Transaction Review Queue, Developer Fee Approval Workflow, Inter-Entity Transfer Entry Form, QBO Sync Status Dashboard, Draw Schedule Management.

**DocuSeal (Document Execution)**
- Deployment: Docker, single container on existing VPS.
- Use for: all e-signatures — lien waivers, draw authorizations, vendor contracts, LP subscription agreements, loan closing docs, internal approvals.
- DocuSign eliminated entirely. DocSeal produces legally valid e-signatures with full audit trail (IP, timestamp, signer identity). No per-envelope fee.

---

# 12. MVP BUILD PLAN (30 DAYS)

---

## Week 1: Foundation

**Objective:** PostgreSQL live, QBO structured, Plaid connected, n8n receiving bank feeds.

**Tasks:**
1. Provision database (Supabase Pro or self-hosted PostgreSQL). Create per-entity schemas. Implement Row Level Security. Create core tables (transactions_staging, qbo_sync_log, developer_fee_accruals, interentity_transfers).
2. Set up QBO Advanced per legal entity. Build 4-segment Chart of Accounts. Configure Classes = Projects, Locations = Legal Entities. Create Due To/Due From accounts (8000-8999).
3. QBO OAuth: implement token acquisition and refresh per company file. Test IQL queries against all entity files. **Bank feed source: QBO Transactions API, not Plaid.** QBO is already connected to all bank accounts — this reuses that connection at zero cost.
4. n8n deployment. Build Workflow 1: QBO Transactions API poll (daily 6 AM, per entity) → normalize → transactions_staging. Basic ruleset: flag transfers >$10K, identify lender ACH codes via payee/memo pattern matching.
5. LiteLLM Proxy: configure Groq API (free tier) as default for classification batch jobs. Claude Haiku API as copilot route. No GPU instance required.
6. Verify end-to-end: transactions flow from QBO bank feed → staging → classification queue → review dashboard.

**Acceptance Criteria:**
- QBO API poll delivers last 24h transactions into transactions_staging for each entity
- IQL query against each QBO file returns valid P&L response
- Transfers >$10K flagged "Review Required" in staging table
- LiteLLM routes test classification request via Groq and returns valid GL account code
- No Plaid account, no per-connection fees

---

## Week 2: Core Integration

**Objective:** AI transaction classification live, QBO write pipeline working, split-transaction logic operational.

**Tasks:**
1. Build AI classification pipeline: for each transactions_staging record, call LiteLLM with transaction description + context. Return QBO account code, Class, Location, cost category, phase, review flag. Write to transactions_classified.
2. Build QBO write workflow: consume transactions_classified where review_flag = false. Construct QBO Purchase or JournalEntry payload. Post via API. Write result to qbo_sync_log.
3. Build split-transaction engine: when single Plaid transaction maps to multiple cost codes, n8n loads splitting rules from PostgreSQL, constructs multi-line QBO JournalEntry, posts split, suppresses raw transaction from QBO bank feed.
4. Implement transaction review queue in Appsmith.
5. Build nightly full GL pull: n8n IQL queries all company files since last sync. Alert via Telegram on any QBO transaction not in PostgreSQL.

**Acceptance Criteria:**
- 95%+ of routine transactions classified without human review over 48-hour test run
- Construction draw test transaction splits across 3+ cost codes in QBO correctly
- Manual entry in QBO triggers Telegram alert within 24 hours
- Review queue surfaces flagged transactions and accepts overrides

---

## Week 3: Fee Capture + Alerts

**Objective:** Developer fee engine live, inter-entity workflow enforced, budget variance alerts operational.

**Tasks:**
1. Build developer fee calculation engine in FastAPI: accepts classified transactions for entity/period. Applies fee-eligibility rules. Returns eligible transactions, eligibility rationale, fee accrual amount. Writes to developer_fee_accruals.
2. Build nightly developer fee workflow: FastAPI fee engine per entity -> create QBO JournalEntry (DR Developer Fee Receivable 7xxx; CR Developer Fee Revenue 4xxx).
3. Build inter-entity transfer workflow in Appsmith: form enforces naming convention. On submit: writes to interentity_transfers, creates Due To/Due From JEs in both QBO files, sends Telegram confirmation.
4. Build Due To/Due From aging check: weekly job, alerts at 30-day unmatched threshold.
5. Build budget variance monitor: daily job compares draw schedule actuals vs classified transaction totals per cost code per project. Alerts at >10% variance.
6. Build bank feed health monitor: alert if any entity has no new transactions for 48 hours.

**Acceptance Criteria:**
- Fee engine correctly calculates 5% on test transactions, excluding ineligible categories
- Accrual JE appears in both QBO accounts within 24 hours of eligible expense posting
- Inter-entity transfer form rejects entries not matching naming convention regex
- Variance alert fires correctly on manually injected test overage

---

## Week 4: Dashboard + Testing

**Objective:** Superset dashboards live, end-to-end system test, security hardening.

**Tasks:**
1. Deploy Apache Superset. Connect to PostgreSQL consolidated schema. Build five required dashboards.
2. Deploy Meilisearch. Index QBO transaction exports. Wire Appsmith search widget.
3. End-to-end system test: simulate month of transactions across 2 test entities. Verify full chain.
4. Security hardening: rotate all API keys and OAuth tokens to production. Enforce HTTPS via Caddy + Let's Encrypt. Implement API key auth on all FastAPI endpoints. Verify PostgreSQL RLS.
5. CPA access: create read-only QBO access. Create read-only PostgreSQL role.
6. Write runbook: Plaid token refresh, QBO OAuth re-authorization, n8n workflow recovery, inter-entity naming convention.

**Acceptance Criteria:**
- Superset consolidated P&L matches sum of QBO P&L by Class across test entities within $0.01
- Entity-scoped PostgreSQL role cannot read another entity's schema
- All API endpoints return 401 on unauthenticated requests
- Runbook sufficient for new engineer to recover from Plaid token expiry

---

# 13. PHASE 2 BUILD PLAN (90 DAYS)

---

## Month 2: AI Copilot + Advanced Controls

1. **NL-to-SQL AI Copilot (Weeks 5-6):** FastAPI /ai/query endpoint. Converts NL to SQL via few-shot prompt with database schema context. Executes against consolidated schema. Returns structured results. Appsmith widget exposes to finance staff and partners. LLM used only for formatting structured query results — not for freeform financial interpretation.

2. **AI Copilot query volume review (Week 6):** At 60-day mark, audit actual Claude API spend. Expected: $8-25/mo. If query volume has grown significantly, evaluate Groq-only routing for all classification or Ollama CPU-mode on existing VPS for $0 marginal cost. No GPU instance — the cost does not justify the savings at small-team query volumes.

3. **Construction Loan Draw Management Module (Weeks 6-7):** Build draw_schedules table. Build Appsmith draw request form. n8n workflow: draw created -> DocuSeal lien waiver package -> on completion, QBO JournalEntry (DR Project Costs; CR Construction Loan Payable). Build Superset draw schedule dashboard.

4. **AIA G702/G703 Pay Application Generation (Week 7):** FastAPI endpoint generates AIA G702 and G703 as PDFs via Gotenberg HTML templates. Output: completed pay application PDF ready for lender submission.

5. **Enhanced reconciliation controls (Week 8):** Three-way reconciliation: Plaid balance vs QBO bank balance vs transactions_classified running balance. Any mismatch triggers immediate Telegram alert.

6. **Document storage layer (Week 8):** Deploy MinIO (Docker, S3-compatible) or configure Backblaze B2. Entity-scoped prefixes. Appsmith document browser.

---

## Month 3: Investor Portal + Full Automation

1. **Waterfall Distribution Engine (Weeks 9-10):** FastAPI waterfall calculation module. Inputs: partnership agreement parameters. Outputs: per-investor distribution amounts, IRR, capital account balance. Validated against manual spreadsheet calculations for 2 existing partnerships before production use. Pure Python with Pydantic schemas.

2. **Investor Portal (Weeks 9-10):** Evidence templates for quarterly LP report. Monthly n8n workflow: PostgreSQL → Evidence build → Gotenberg PDF → Cloudflare R2 storage → email via Resend (free tier) → physical copy printed locally and mailed via USPS for hard-copy-required investors (~1-2 mailings/year; no Lob API needed at this volume).

3. **Investor Self-Service Portal (Weeks 10-11):** Read-only web portal. Unique login per investor. Shows capital account balance, distribution history, project status, downloadable reports. Data served from PostgreSQL via PostgREST with investor-scoped RLS.

4. **Automated Monthly Close Checklist (Week 11):** n8n workflow on 1st of month: (1) three-way reconciliation check; (2) developer fee calculation and accruals; (3) Due To/Due From aging; (4) QBO P&L and Balance Sheet snapshot; (5) Evidence report builds; (6) "Monthly Close Status" Telegram with pass/fail per checklist item. Human sign-off in Appsmith gates investor report distribution.

5. **NocoDB Internal Admin Layer (Weeks 11-12):** Deploy NocoDB (Docker on existing VPS) connected directly to PostgreSQL. Configure project-facing views: project budgets, draw tracking, vendor management, loan tracking, construction cost views. NocoDB replaces ERPNext for the data-entry and project management layer — same underlying PostgreSQL tables, with a spreadsheet-style front end for non-technical users. $0 additional cost. ERPNext is not required; QBO handles the accounting ledger and NocoDB handles the operational data management layer.

6. **Automation gap closure (Week 12):** Retire Make and Zapier entirely. All workflows in n8n. Every workflow has error branch writing to workflow_errors PostgreSQL table + Telegram alert. No silent failures.

---

# 14. ULTIMATE LONG-TERM VISION (12 MONTHS)

**Accounting Layer:**
- QBO remains the accounting backbone for CPA-facing reporting and bank reconciliation. PostgreSQL handles all consolidation, fee calculation, and investor accounting logic.
- If entity count exceeds 8 and QBO per-entity licensing becomes prohibitive, evaluate **self-hosted ERPNext** (not Frappe Cloud managed) on Oracle Cloud Always Free ARM instance ($0 compute). Migration trigger: QBO multi-entity cost > $1,500/mo.
- NocoDB fully deployed as the operational data management layer: project budgets, draw tracking, vendor management — all pointing at the same PostgreSQL schema.
- Full double-entry audit trail for every transaction with no manual entry required for routine transactions.

**AI Layer:**
- Fine-tuned domain-specific model checkpoint (Qwen3-72B fine-tuned on 12 months of labeled Summa Terra transaction data) handling 95%+ of classification.
- AI copilot in investor portal: LPs can ask NL questions about capital account, project status, projected distributions.
- Automated anomaly detection: ML model trained on historical patterns flags outliers before they become reconciliation problems.

**Construction Finance:**
- Full AIA G702/G703 automated generation for all active projects.
- Lender draw package automation: n8n assembles complete draw request package as PDF bundle and emails to lender on approval. Eliminates 4-6 hours of manual assembly per draw.
- Change order tracking integrated with draw schedules.

**Investor Relations:**
- Full LP lifecycle automation: capital call notices, wire instructions, distribution letters, K-1 cover packets — all generated from PostgreSQL data.
- Investor self-service portal includes distribution reinvestment election, ACH account management, secure document vault.
- IRR and equity multiple calculations updated in real time as project actuals are posted.

**Consolidation:**
- ERPNext native multi-company consolidation replacing the PostgreSQL consolidation workaround.
- Intercompany eliminations automated through ERPNext.

**Compliance:**
- Full transaction audit log: immutable record from QBO bank feed source through GL posting. Export on demand for CPA or LP audit.
- Annual K-1 generation fully automated: PostgreSQL → FastAPI tax allocation engine → Gotenberg PDF → bulk email delivery via Resend + local print/mail for hard-copy-required investors.



---

## Ongoing Operating Cost (Monthly at Steady State)

| Item | Original Estimate | Revised (Zero-Cost Stack) | Tool |
|------|------------------|--------------------------|------|
| Database | $10-$20 (self-hosted) | $25 | Supabase Pro (bundles PostgREST + Auth + Storage) |
| n8n VPS | $20 | $20 | Hetzner VPS (unchanged) |
| Superset + Appsmith VPS | $20-$40 | $20-$40 | Self-hosted (unchanged) |
| GPU instance (vLLM) | $160-$240 | **$0** | Eliminated — Groq free tier + Claude API |
| Bank feeds (Plaid) | $500-$1,500 | **$0** | QBO Transactions API (included in QBO sub) |
| QBO Advanced (per entity) | $235/entity | $235/entity | Unchanged |
| ERPNext Frappe Cloud | $100-$200 | **$0** | Eliminated — NocoDB self-hosted on existing VPS |
| Claude/OpenAI API | $50-$200 | $8-$25 | Claude Haiku (copilot) + Groq free tier (classification) |
| LiteLLM Proxy VPS | $10 | $0 | Runs on existing n8n VPS |
| DocuSign | $25-$40 | **$0** | DocSeal (self-hosted Docker) |
| Lob (physical mail) | $20-$50 | **$0** | Local print + USPS (~$30/yr, not monthly) |
| Postmark (email) | $15 | **$0** | Resend free tier (3K emails/mo) |
| Backblaze B2 (storage) | $7 | **$0** | Cloudflare R2 free tier (10GB) |
| **Total Monthly (1 entity)** | **~$1,280-$3,010** | **~$308-$345** | |
| **Total Monthly (5 entities, $235 × 5 QBO)** | **~$2,450-$4,185** | **~$1,200-$1,250** | |

**Savings from zero-cost replacements alone: $830-$2,035/month**
**Comparison to incumbent paid stack (QBO Advanced x5 + Yardi/AppFolio + Power BI + Make + DocuSign + Retool): ~$8,000-$15,000/month.**
**Monthly savings vs. incumbent at steady state: $6,750-$13,750/month.**

---

## ROI Calculation

**Revenue from Developer Fee Capture:**
Conservative assumption: system captures $50,000-$150,000/year in developer fees that would otherwise be missed.

**Time Savings:**

| Task | Annual Savings |
|------|----------------|
| Monthly bank reconciliation (5 entities) | $42,000 |
| Construction draw package assembly | $4,725 |
| Quarterly LP reports | $13,200 |
| Inter-entity journal entry management | $3,150 |
| Developer fee tracking | $5,040 |
| **Total Annual Time Savings** | **~$68,000/year** |

**Total Annual Value Generated:**

| Source | Conservative | Optimistic |
|--------|-------------|-----------|
| Developer fee capture | $50,000 | $150,000 |
| Time savings | $68,000 | $100,000 |
| Software cost reduction vs. incumbent stack | $60,000 | $144,000 |
| Risk reduction | $30,000 | $80,000 |
| **Total Annual Value** | **$208,000** | **$474,000** |


*End of Summa Terra Ventures — Autonomous Real Estate Accounting OS Complete System Architecture & Build Specification*
*Version 1.0 | Confidential | 2026-06-17*
