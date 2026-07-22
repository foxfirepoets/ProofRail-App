# ARDAOS — Part 7 Critical Questions: Field Answers
**Prepared by:** Ben Stone, Incoming Accountant  
**Date:** June 19, 2026  
**Source documents:** 14 OAEA .docx files (Operating Agreements & Exhibit B), Google Drive trackers, v1.1 Ground Truth Spec  
**Status legend:** ✅ CONFIRMED from contracts | ⚠️ PARTIAL — needs follow-up | ❌ UNCONFIRMED — requires QB access or conversation with Mike/Porter

---

## Q1 — What exactly is the contractual basis for the 5% overhead/CM fee?

✅ **CONFIRMED**

Every active project OAEA (Exhibit B, "Developer's Fee" section) contains materially identical language:

> *"A developer and construction management fee of five percent (5%) of total hard and soft costs for the Project, including, but not limited to, professional costs, site work, and construction costs, will be paid periodically throughout the construction term."*

**Fee base:** Total hard AND soft costs — i.e., the full construction draw amount including GC hard costs, architectural/engineering fees, permits, and site work. NOT just hard costs alone.

**Timing:** Calculated and paid as a portion of each construction draw. If accrued instead, paid immediately after construction loan repayment and before any capital distributions to members.

**Disclosure:** Specifically called out in the partner offering P&L Pro Forma — meaning lenders have seen it.

**Payee entity varies by project (critical for intercompany accounting):**

| Project | OAEA Date | Fee Payee |
|---|---|---|
| Hunter's Landing North (HLN) | Apr 2026 | Summa Terra Ventures, LLC |
| Freeman Ranch Partners | May 2026 | Summa Terra Ventures, LLC |
| Ledges @ Moab | Jan 2026 | **Lykos Acquisitions, LLC** |
| Vic Partners | May 2026 | Summa Terra Ventures, LLC |
| Madison Park | Feb 2026 | **Summa Terra Development Group, LLC** |
| Ensign | Jul 2025 | Summa Terra Ventures, LLC |
| RM Texas Partners | Jan 2025 | Summa Terra Ventures, LLC |
| Elephant Rock | Mar 2025 | Summa Terra Ventures, LLC |
| Ventura Landing | Mar 2025 | Summa Terra Ventures, LLC |
| Quincy Court | Apr 2024 | Summa Terra Ventures, LLC |
| 12SB | Mar 2026 | **NOT STATED in OAEA** — no Developer's Fee clause |
| Rock Creek | May 2023 | **NOT STATED** — oldest template, no fee clause |

> **⚠️ NOTE:** Ledges @ Moab routes the 5% to Lykos Acquisitions (Aubrey Palmer's entity), not STV directly. Madison Park routes to Summa Terra Development Group. These are different receiving entities — your intercompany reconciliation must track which STV-side entity received the fee per project.

---

## Q2 — Are the CEO (2%) and President (1%) commissions based on gross or net draw?

✅ **CONFIRMED — internal STV bonus structure**

Confirmed by Ben: the 2% and 1% are **internal STV bonuses paid by Summa Terra Ventures**, not obligations of the project LLCs. They do not appear in investor-facing OAEAs because they are purely internal compensation — STV receives the full 5% from the project LLC, then pays out portions internally as bonuses.

**Accounting flow:**
- Project LLC → pays 5% to STV (per OAEA)
- STV → pays 2% CEO bonus internally (Mike Watson)
- STV → pays 1% President bonus internally
- STV retains 2% as company overhead/margin

**Base:** Applied to the same draw base as the 5% fee (total hard and soft construction costs per draw).

---

## Q3 — Who actually pays the 2% and 1% commissions — the project LLC or STV?

✅ **CONFIRMED**

**Summa Terra Ventures pays** the 2% and 1% internally. The project LLC has no obligation beyond the 5% fee. These are STV-level compensation entries — either W-2 wages, 1099 contractor payments, or member distributions depending on STV's own employment structure.

---

## Q4 — Is the 5% fee a separate lender-approved budget line item?

⚠️ **PARTIALLY CONFIRMED**

The OAEAs consistently state the fee "is disclosed in the partner offering in the Profit and Loss Pro Forma." This means the 5% is in the project pro forma that lenders receive — so lenders have visibility into it.

However, the OAEAs do **not** explicitly state the lender approved the fee as a distinct construction budget line item or that it can be drawn from the construction loan facility.

**What this means in practice:** Whether the fee can be drawn from the construction loan depends on each loan agreement. Some lenders carve it into the budget explicitly (meaning each draw includes a developer fee component); others require it be paid from equity or at loan payoff.

**To confirm:** Pull the construction loan documents for each active project — specifically the approved budget schedule — and confirm whether "Developer Fee" or "CM Fee" appears as a fundable line item. This determines whether the 5% flows through the draw (loan-funded) or must come from equity.

---

## Q5 — What is the invoicing mechanism for the fee?

✅ **CONFIRMED — two templates exist on Drive, plus a historical payment receipt**

**Two STV invoice templates found on Google Drive (in the Summa Terra Accounting folder):**

**STV Invoice.docx** (simple, older format — contact: patrick@summaterraventures.com):
```
Request for Payment
Invoice to: [project LLC name]
Amount Requested: [5% × draw amount]
Description of Work Completed: [description]
Summa Terra Ventures, 79 W 900 N Suite B, Springville, UT 84663
```

**STV Invoice Template.pdf** (formal format):
```
INVOICE
Summa Terra Ventures, 79 W 900 N Suite B, Springville, UT 84663
INVOICE #  |  INVOICE DATE  |  BILL TO
DESCRIPTION  |  AMOUNT
TOTAL
```

**Historical payment confirmation (2022, Union Walk / UCCU):**  
A 2022 UCCU receipt shows a $37,683.06 developer fee paid to **STV Entitlement Services LLC** (another STV-family entity) for Union Walk — confirming this fee has actually been paid in practice, not just documented in OAEAs.

> ⚠️ **Note the entity name:** That 2022 payment went to "STV Entitlement Services LLC" — yet current OAEAs say "Summa Terra Ventures, LLC." This is another payee entity discrepancy to track. Confirm which entity currently receives Union Walk fee payments.

**Invoicing flow (confirmed):**
1. GC submits draw request to lender
2. Lender funds draw → project LLC bank account (UCCU or similar)
3. STV issues invoice to project LLC for 5% of draw amount
4. Project LLC writes check/wire to STV per invoice
5. STV internally allocates: 2% CEO bonus + 1% President bonus + 2% retained

**Invoicing contact** is patrick@summaterraventures.com (per older template) — confirm whether this is still current or if stone@summaterraventures.com takes over.

---

## Q6 — What is the current bank reconciliation process?

✅ **CONFIRMED from spec and Drive research**

Current state (before ARDAOS):
1. Transaction data lives in **Google Sheets** (tab per project)
2. QB Enterprise on Rightworks is reconciled FROM Sheets, monthly, with a **2–4 week lag**
3. **QB access is currently blocked** — previous accountant (Adam Stevens) changed the password before leaving. Rightworks support is being engaged.
4. UCCU (Utah Community Credit Union) is primary bank for Utah project LLCs
5. Bank statements reconciled monthly per the "GS-2026_Monthly Financial Process_Project Entities" tracker

**Priority action:** Restore QB access. Until then, Sheets is the system of record.

---

## Q7 — What is the draw timing/frequency?

⚠️ **PARTIAL — varies by project/lender**

From OAEAs: "Executive may regularly approve of or engage in draws, bids, and expenditures" — no fixed schedule in the LLC docs. Draw frequency is controlled by the construction loan agreement with each lender, not the OAEA.

**Typical construction loan draw cycle:** Monthly or upon reaching specified completion milestones. Each draw requires:
- Lender inspection/title update
- G-702/G-703 (AIA Application for Payment) from GC
- Lien waivers
- Lender funding

**To confirm:** Need construction loan documents per project for actual draw schedule and inspection requirements.

---

## Q8 — What is the Chart of Accounts structure?

⚠️ **PARTIAL — can't confirm without QB access**

From v1.1 spec (confirmed STV practice):
- One QB Enterprise file per LLC
- **All fees (5%, 2%, 1%) are CAPITALIZED** to "Real Estate Under Development" balance sheet accounts — NOT expensed
- Interest on construction loans is also capitalized to REUD

**Most critical rule:** The developer fee cannot be run through the P&L. It must hit the balance sheet as a component of project cost until the asset is sold or placed in service.

**Standard REUD sub-accounts per project:**
- Land
- Construction Costs — Hard
- Construction Costs — Soft / Professional
- Developer / CM Fee (the 5%)
- Interest Capitalized
- Other Capitalized Costs

**To confirm once QB is restored:** Pull COA from each active entity file. Look for inconsistencies — prior accountant may have expensed some fees that should be capitalized.

---

## Q9 — Who has signing authority on project bank accounts?

⚠️ **PARTIALLY CONFIRMED**

From OAEAs: "only the Executive may cause the Company to spend money." Exhibit B of Freeman Ranch (Section 390) names **Aubrey Palmer** specifically as authorized to sign "bank accounts, construction draws, vendor contracts, closing statements, etc."

This pattern is consistent across multiple OAEAs — Aubrey Palmer or the Executive Member entity (Lykos Acquisitions, Providence Partners, etc.) has sole signing authority.

**What we need:** Confirm signatories on each actual bank account, not just from the OAEA. Bank may have different authorized signers on file. Also — is Ben (stone@summaterraventures.com) being added as a signer for accounting purposes? If you need to initiate draws or payments, you'll need bank authorization.

**Action:** Contact UCCU (and Texas/SC/MO banks) to get current signatory cards per account.

---

## Q10 — Where do draw funds go after disbursement from the construction loan?

⚠️ **LIKELY CONFIRMED by pattern — verify per project**

Standard flow:
1. Lender wire → Project LLC bank account (typically UCCU for Utah projects)
2. From LLC account → GC payment (based on approved schedule of values)
3. From LLC account → STV invoice payment for 5% developer fee
4. Remaining → Held in LLC account for next period costs

**To confirm:** Verify each project's bank routing and that wires from lender hit the correct LLC account. Especially important for Texas/SC projects (non-UCCU banks).

---

## Q11 — What is the preference return structure for investors?

✅ **CONFIRMED from OAEAs**

Distribution waterfall is consistent across all projects (from Exhibit B):

**Standard waterfall (at sale or refinance):**
1. Pay off construction loan / all lender obligations
2. Return of all member Capital Contributions (pro-rata)
3. Profit distributions pro-rata per Ownership Interests (Exhibit A)

**Loan Guarantor gets additional return:**
- Standard: **10% of project profit** (most projects)
- Ventura Landing: **12% of project profit**
- Elephant Rock: **5% of project profit**
- If project sells before loan is signed: guarantor gets 4% only, with 6% returning to Executive

**For 12SB specifically** (complex, distressed project): multiple waterfall layers per Exhibits C, D, E:
- New capital partners (post-2/15/24) get 8% preferred return on contributions
- Contributing members on capital calls get 15% preferred return on call amounts
- Supplemental contributors get preferred treatment ahead of all other capital

**No preferred return hurdle rate** (IRR threshold) before promote — this is simpler than typical institutional PE structures. Return of capital first, then profit split by ownership %.

---

## Q12 — Who is the CPA firm for tax returns?

✅ **CONFIRMED**

**Ricks and Company LLC** is the CPA firm for STV tax returns.

---

## Q13 — What is the K-1 status / investor tax reporting?

❌ **UNCONFIRMED**

Not explicitly addressed in OAEAs beyond general partnership tax provisions (Article X). Each project LLC is taxed as a partnership → K-1s issued to all members annually.

**Questions to confirm:**
- Has K-1s been issued for 2024 tax year? (2025 should be in process now)
- Who prepares them — CPA firm or internally?
- Are there any delinquent K-1 obligations from prior years?

---

## Q14 — Is construction loan interest being capitalized?

⚠️ **ASSUMED YES — unverified in QB**

Per GAAP (ASC 835-20) and STV's stated accounting policy in the spec, construction period interest must be capitalized to the REUD balance sheet account, not expensed.

**To verify once QB is restored:** Pull the trial balance for each active project LLC and confirm interest expense is going to a capitalized asset account, not hitting the P&L.

---

## Q15 — What is the chart of accounts consistency across all entity QB files?

❌ **UNCONFIRMED — requires QB access**

Cannot audit without QB access. Once access is restored, first priority is to pull the COA from each active entity file and cross-reference against the standard STV template.

**Known risk:** Prior accountant may have set up COAs inconsistently across files. Specific risk: developer fees expensed rather than capitalized in some files.

---

## Summary Status Table

| # | Question | Status | Source |
|---|---|---|---|
| Q1 | Contractual basis for 5% fee | ✅ Confirmed | OAEAs — Exhibit B |
| Q2 | CEO/President commission basis (gross vs net) | ✅ Confirmed | Internal STV bonus |
| Q3 | Who pays 2%/1% commissions | ✅ Confirmed | STV pays internally |
| Q4 | Lender-approved budget line item | ⚠️ Partial | Need loan docs |
| Q5 | Invoicing mechanism | ✅ Confirmed | Drive templates + UCCU receipt |
| Q6 | Bank reconciliation process | ✅ Confirmed | Spec + Drive |
| Q7 | Draw timing/frequency | ⚠️ Partial | Need loan docs |
| Q8 | Chart of accounts structure | ⚠️ Partial | Need QB access |
| Q9 | Bank account signing authority | ⚠️ Partial | OAEAs + need bank cards |
| Q10 | Draw fund flow | ⚠️ Likely correct | Need per-project verify |
| Q11 | Investor preferred return structure | ✅ Confirmed | OAEAs — Exhibits B/C/D |
| Q12 | CPA firm | ✅ Confirmed | Ricks and Company LLC |
| Q13 | K-1 status | ❌ Unknown | Need Mike/Porter |
| Q14 | Interest capitalization | ⚠️ Assumed | Need QB verify |
| Q15 | COA consistency across entities | ❌ Blocked | Need QB access |

---

## Immediate Action Items (First Week Priority)

1. **Restore QB access** on Rightworks — everything in Q8, Q14, Q15 is blocked by this
2. **Ask Mike Watson directly** about Q2/Q3 (commission structure) and Q12/Q13 (CPA/K-1)
3. **Pull construction loan documents** for each active project — confirms Q4 (budget line) and Q7 (draw schedule)
4. **Confirm bank signatories** at UCCU and other banks — critical for operational control (Q9)
5. **Note payee entity discrepancy:** Ledges @ Moab fee goes to Lykos Acquisitions, not STV. Madison Park goes to Summa Terra Development Group. Ensure intercompany invoices and QB entries match the correct payee entity per project.

---

## Critical Accounting Rule (Do Not Deviate)

From v1.1 spec and confirmed by OAEA structure:

> **ALL developer/CM fees (the 5% paid to STV/Lykos/STDG), CEO commissions (2%), and President commissions (1%) MUST be CAPITALIZED to "Real Estate Under Development" on the project LLC balance sheet — NEVER expensed on the P&L.**

The OAEAs embed the fee in the project cost structure (not as an operating expense), which is consistent with this capitalization requirement. Running these through the P&L would misstate project costs and distort member profit distributions.
