# STV Accounting — Session Briefing for New Claude Instance
**Last updated:** June 22, 2026  
**Prepared by:** Ben Stone (stone@summaterraventures.com) — incoming accountant  
**Read these files first:** `STV_Part7_Critical_Questions_Answers.md`, then the two spec files in uploads if available  

---

## Who Is Ben / Who Is Adam

- **Ben Stone** = stone@summaterraventures.com = YOU ARE TALKING TO BEN. He is the NEW incoming accountant.
- **Adam Stevens** = adam@summaterraventures.com = the OUTGOING accountant. He quit, changed the QB password, and left. The OneDrive folder is under Adam's Windows profile but Ben is now using it.
- **Mike Watson** = CEO of Summa Terra Ventures
- **Aubrey Palmer** = Mike Watson's wife, signs most documents as Executive on behalf of STV entities (Lykos Acquisitions, Providence Partners, etc.)
- **Porter Christensen** = porter@summaterraventures.com — works at STV, point of contact for some matters
- **patrick@summaterraventures.com** — was the invoice contact; may be transitioning to stone@

---

## What STV Is

Summa Terra Ventures, LLC is a real estate development company based in Springville, UT (79 W 900 N Suite B). They develop multifamily apartment projects. Each project has its own LLC, own bank account, and own QuickBooks Enterprise file. STV corporate is the developer/manager that collects fees from each project LLC.

**QB platform:** QuickBooks Enterprise on Rightworks (hosted VPS) — NOT QuickBooks Online. This is a critical architectural difference.

**QB access status:** CURRENTLY LOCKED OUT. Adam changed the password before quitting. Rightworks support is working on restoring access. Until then, Google Sheets is the source of truth.

**CPA firm:** Ricks and Company LLC

**Connected tools in this Cowork session:**
- Google Drive MCP (adam@summaterraventures.com account) — tool prefix: `mcp__f9cb23ed-f990-4f02-b855-38134eecbf97__*`
- Gmail MCP (stone@summaterraventures.com) — tool prefix: `mcp__b9c3941a-4756-4665-aec3-40ed85dfdf05__*`

---

## Entity Structure

**STV Corporate entities (all "Aubrey" entities on the entity list):**
- Summa Terra Ventures, LLC — main operating entity, receives developer fees from most projects
- Lykos Acquisitions, LLC — Aubrey Palmer's entity, receives fees on some projects (e.g., Ledges @ Moab), signs as Executive on most OAEAs
- Providence Partners, LLC — used as Executive entity on some projects (e.g., Freeman Ranch)
- Summa Terra Development Group, LLC — receives fees on Madison Park
- STV Entitlement Services LLC — received fees historically (2022 Union Walk payment)
- BAP MF LLC — used to hold/contribute land to projects
- STV Employee Fund — employee investment vehicle

**28 total affiliated entities** per the "Summa Terra and Affiliated Entities" spreadsheet on Drive. ~16 tracked in the monthly process, ~8-9 currently active in construction.

---

## Active Projects (from "GS-2026_Monthly Financial Process_Project Entities" on Drive)

| Short Name | Full Name | State | Status |
|---|---|---|---|
| 12SB | 12SB, LLC (Hunter's Landing / 407 12th St, Ogden) | UT-Weber | Active — distressed, multiple capital call amendments |
| HLN | Hunter's Landing North, LLC | UT-Weber | Active |
| Ledges@Moab | Ledges at Moab, LLC | UT-Grand | Active |
| Madison/Sunset | Madison Park, LLC | UT-Utah | Active |
| Union Walk | Union Walk / Union Station | UT-Weber | Active |
| Freeman Ranch | Freeman Ranch Partners, LLC | SC-Greenville | Active |
| Vic Partners | Vic Partners | TX-Tarrant | Active |
| Ensign | Ensign | TX-Ellis | Active |
| RM Texas | RM Texas Partners | TX | Active |
| Rock Creek | Rock Creek / Summa Elite | TX-Cooke | Older — unclear if still active |
| Quincy Court | Quincy Court | TX-Denton | Older |
| Elephant Rock | Elephant Rock LLC | MO | Active |
| Ventura Landing | Ventura Landing | DE | Active |
| Carlo@Washington | Carlo @ Washington | UT-Weber | Possibly wind-down |
| Hart City | Hart City | — | — |
| HLN | HLN | UT-Weber | Active |

---

## The Fee Machine — Most Critical Accounting Facts

### The 5% Developer / CM Fee
- **Every construction draw triggers a 5% fee** paid to STV (or Lykos/STDG depending on project)
- **Fee base:** Total hard AND soft costs on the draw (professional costs, site work, construction costs)
- **Contractual source:** Exhibit B "Developer's Fee" section of each project OAEA
- **Payee varies by project** — see the Part 7 answers doc for the full table
- **Payment timing:** With each draw, or accrued and paid after construction loan payoff (before capital distributions)
- **Invoicing:** STV issues an invoice to the project LLC per draw. Two templates exist on Drive: "STV Invoice.docx" (simple) and "STV Invoice Template.pdf" (formal). Contact was patrick@summaterraventures.com.

### The 2% + 1% Internal Bonuses
- After STV receives the 5%, STV internally pays:
  - **2% CEO bonus** (Mike Watson)
  - **1% President bonus** (internal STV — confirm who holds President title)
  - **2% retained** by STV as overhead
- These do NOT appear in investor-facing OAEAs — they are pure STV internal compensation
- Project LLC has NO obligation beyond the 5%

### MOST CRITICAL RULE — CAPITALIZATION
> **ALL fees (5%, 2%, 1%) must be CAPITALIZED to "Real Estate Under Development" on the project LLC balance sheet. NEVER expensed on the P&L.**

This applies to:
- The 5% developer fee posted at the project LLC level
- Construction loan interest
- All other development-period costs

---

## Current Accounting Workflow (Pre-ARDAOS)

1. Transactions recorded in **Google Sheets** (tab per project)
2. QB Enterprise reconciled FROM Sheets, monthly, **2–4 week lag**
3. Bank: **UCCU** (Utah Community Credit Union) for Utah projects; Texas/SC/MO projects have local banks
4. Draws: GC submits → lender funds to LLC account → LLC pays GC + pays STV invoice
5. Monthly checklist tracked in "GS-2026_Monthly Financial Process_Project Entities" on Drive

---

## Key Drive Files (Google Drive — adam@summaterraventures.com)

| File | Drive ID | Notes |
|---|---|---|
| Summa Terra and Affiliated Entities.xlsx | 1So6bPeu4YSYPMaYvcbY-4b4K6ZfB3fLK | 28-entity master list |
| CM / Development Fees Summary by Entity | 13jhf_nfkfYQ3JKhCO4Tt11NV99HLMQnSI5cMdkaqxhw | ALL BLANK — revenue leak confirmed |
| GS-2026_Monthly Financial Process | 1VUAGKf5zidHNeY26PC6asbK1WAk0qda6pI92iZL6y1U | 16-project monthly checklist |
| STV Invoice.docx | 1Tps9b1HD1iZkvoEZzvssLz8T-XwRvXKV | Simple invoice template |
| STV Invoice Template.pdf | 1CJzsDOW7D37wfRTXf2s1ZQut7nHLSct0 | Formal invoice template |
| Operating Agreements folder | 1CYQJ0utBPqSHBEWgDckeSLlrxDwdfkzd | Shortcuts only (not actual files) |
| Notes Transfer folder | 1m5vAYO46R_XWpY5MPNGk1UytZEuX7vWR | This folder — session handoff docs |

---

## Local Files (OneDrive Folder)

- `Operating Agreements/` — 14 OAEA .docx files, readable via bash + python-docx (NOT the Read tool — .docx are binary)
- Two spec files were uploaded by Ben at session start (not in this folder — need to re-upload):
  - `01_EXECUTIVE_SPEC.md` — v1.0 theoretical spec (assumes QBO — incorrect)
  - `01_EXECUTIVE_SPEC_v1.1_GROUND_TRUTH.md` — v1.1 corrected spec (QB Enterprise, confirmed fee structure, 15 critical questions)

---

## What's Still Pending / Open Questions

**Needs QB access (currently blocked):**
- Q8: Chart of accounts structure across all entity files
- Q14: Confirm construction loan interest is being capitalized (not expensed)
- Q15: COA consistency check across all ~8-9 active entity QB files

**Needs conversation with Mike Watson or Porter:**
- Q13: K-1 status — has 2024 K-1s been issued? Who prepares them (Ricks and Company)?
- Who holds the President title (for the 1% internal bonus)?
- What entity/method are the 2% and 1% bonuses paid through (payroll, 1099, draws)?

**Needs construction loan documents per project:**
- Q4: Confirm 5% fee is an approved budget line item (lender-fundable)
- Q7: Draw schedule and inspection requirements per project

**Needs bank confirmation:**
- Q9: Current authorized signatories on each project bank account
- Whether Ben (stone@) is being added as a signer

**Revenue leak — immediate priority:**
- The CM/Development Fees Summary on Drive has ALL BLANK data cells — fees are going untracked
- Priority: build a fee tracking reconciliation (Draw amount × 5% = expected fee per draw, per project, per period)

---

## How to Use .docx Files in This Folder

The Read tool cannot open .docx (binary). Use bash + python-docx:

```bash
pip install python-docx --break-system-packages -q
python3 -c "
from docx import Document
doc = Document('/sessions/.../mnt/Summa Terra Accounting Brainstorm/Operating Agreements/FILENAME.docx')
print('\n'.join([p.text for p in doc.paragraphs if p.text.strip()]))
"
```

Fee language is always in **Exhibit B, "Developer's Fee" section** — skip to around paragraph 350-420 depending on the document.

---

## What ARDAOS Is

The end goal Ben is building toward: an **Autonomous Real Estate Development Accounting OS** — a system that auto-processes draws, calculates and posts fees, reconciles bank statements, and produces real-time dashboards across all project LLCs. The two spec files describe the architecture. The v1.1 spec is the authoritative ground-truth version.
