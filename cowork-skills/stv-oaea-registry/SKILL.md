---
name: stv-oaea-registry
description: Convert STV operating agreements (OAEAs) and their amendments into ProofRail EntityRegistry rows, cap-table snapshots, and MemberVendor entries — extract the Developer's Fee clause verbatim (all four STV CM streams plus each entity's exact fee base), Exhibit A capital tables (cash vs contract vs IRA lines), executive member, authorized signatory, loan guarantor, and named GC; then diff against the current registry row so amendments flow into ProofRail the day they're signed. Triggers - "OAEA", "operating agreement", "amendment", "new exhibit A", "update the registry", "fee clause", "cap table changed", "who are the partners in", any OAEA document arriving in an Inbox Run.
---

# stv-oaea-registry — documents as law, kept alive

STV's OAEAs are living documents: 150+ amendments logged since 2022, and the entire fee
regime was restructured in a single 7-2-2026 refresh. Any rule sourced from memory dies in
days. Your job: read the document, extract the law, emit the registry row, and show the
diff — so ProofRail believes only what the current paper says. **No registry row = no fee,
for any entity, any stream. This skill is how rows are born and changed.**

## 0. DOCUMENT TRIAGE (before extracting anything)
- Confirm you hold the **governing version**: latest effective date wins; filenames
  prefixed `[OLD]` or `DO NOT USE` are never authoritative; an executed PDF outranks a
  same-date working docx. If two candidates conflict, STOP and present both to Ben.
- Note doc identity for the row: Drive URL, filename date, executed vs draft, signers.
- Cross-check the **OAEA Update Ledger** (Operating Agreements folder): if the ledger
  shows an amendment newer than the doc in hand, you're reading stale law — flag.

## 1. EXTRACT — the fee law (Exhibit B / body clauses), VERBATIM
| Field | What to capture | Why verbatim matters |
|---|---|---|
| `fee_base` | the exact base sentence — e.g. 12SB: "professional costs, site work, and construction costs" (no land); Madison/Summa Elite: "total hard and soft costs" | the 5% is constant; the BASE is where entities differ and where fee errors hide |
| `fee_rate` / payee | 5% → **STV CM, LLC** (post-4-2-2026 regime); anything else = flag loudly | a non-STV-CM payee in a current doc means the regime changed again |
| fee timing | rides each draw, or accrues → payable after loan payoff, before distributions | drives FeeRun scheduling |
| `draw_fee` | flat per-draw fee if stated (Madison practice: $1,000) | stream 2 |
| `acct_fee_cap_mo` | $50/hr capped (typ. $500/mo/entity) | stream 3 |
| `pm_fee_rate` | 1.0–1.5% of GOI post-CO — rate is per-entity | stream 4 |
| Absence | **the absence of a clause is data** — record `NO_FEE` explicitly (Rock Creek Acquisitions pattern), never null-and-guess | absence is what the old hard blocks should have been sourced to |

## 2. EXTRACT — governance & operations fields
Executive Member (Madison: Lykos · Summa Elite: Providence) · Authorized Signatory
(Aubrey Palmer across current docs — F6 expects her signature) · Partnership
Representative (Michael Watson) · Loan Guarantor (e.g. 12SB: Jason Winkler) ·
named GC + spokesperson (Madison: Concord Homes; GC dealings: Mike Watson) ·
distribution waterfall order · buyout/Regius clauses (80% targeted-return members
change distribution math — note them).

## 3. EXTRACT — Exhibit A (the cap table)
Every line: member name (entity spelling exact) · **cash vs contract vs IRA** contribution
· amount · ownership % · targeted return if stated. Then derive:
- **Holding-LLC lines** → Investment-in-Projects mapping (parent file) + Partner Capital
  subs (partnership file).
- **Contract-contribution lines** → `MemberVendor` rows. A sub on the cap table is a
  double-pay trap: their invoices may be satisfied by equity. (Summa Elite alone: ~15.)
- **Intercompany equity** → flag explicitly (Elephant Rock LLC holds 1.615% of Summa
  Elite; STV LLC 1.039%) — these lines create IC eliminations the CPA must see.
- Count check: Σ ownership % ≈ 100.00 (tolerance 0.01) — Exhibit A that doesn't foot = flag.

## 4. EMIT — the row and the diff
Output one block Ben can approve at a glance. It is **strict, parseable YAML** whose field names
mirror the Prisma schema **exactly** (`EntityRegistry`, `MemberVendor`) — so the same block a
human eyeballs is the block a migration generator can consume. Quoted `"<…>"` = fill from the doc.
Example filled for Summa Elite:
```yaml
registry:                               # -> EntityRegistry row (field names = schema)
  entity: "Summa Elite"                 # @id
  locationA: "Summa Elite"              # exact realm-A QBO Location name
  feeRate: 0.0500                       # Decimal(5,4); null = NO_FEE
  feePayee: "STV CM, LLC"               # null = NO_FEE
  feeBase: "total hard and soft costs"  # VERBATIM from the OAEA
  oaeaDocUrl: "<drive link>"
  oaeaEffective: "2026-07-02"
  drawFee: 1000.00                      # Decimal(8,2) or null
  acctFeeCapMo: 500.00                  # Decimal(8,2) or null
  pmFeeRate: 0.0100                     # Decimal(5,4) or null (null pre-CO)
  lender: "<per doc>"
  capitalMap:                           # Json: holding -> pct per current Exhibit A
    Providence: 42.165                  # (subset shown; full Exhibit A foots to 100.00)
    "DM Capital": 42.165
    "STV LLC": 1.039
    "Elephant Rock LLC": 1.615
member_vendors:                         # -> MemberVendor rows (entity implied); [] if none
  - vendor: "LB Drywall"
    contractContribution: "<$ from Exhibit A>"   # Decimal(12,2)
    exhibitAUrl: "<drive link>"
  - vendor: "Proficient Concrete"
    contractContribution: "<$ from Exhibit A>"
    exhibitAUrl: "<drive link>"
governance_extracted:                   # §2 fields with NO EntityRegistry column yet — see note
  executive: "Providence"
  signatory: "Aubrey Palmer"
  guarantor: "<per doc>"
  gc: "Elite Construction USA"
  feeTiming: "per-draw"                 # per-draw | accrued (drives FeeRun, not a registry column)
diff_vs_current:                        # human-readable summary; [] on first emit
  - "pmFeeRate ADDED (was null)"
  - "feePayee UNCHANGED"
  - "capitalMap: Providence 42.165 (was 43.2)"
```
`registry:` and `member_vendors:` map 1:1 to the Prisma models. **`governance_extracted` and
`feeTiming` have no EntityRegistry column today** — they're captured for F6/close use and the
approval record only; if ProofRail should store them structurally, add columns in a schema
migration first. Registry changes ship as migrations (git = audit trail) — never a manual UPDATE. The diff
is the deliverable: **an amendment nobody diffs is a rule nobody knows changed.**

## NEVER
Extract from an [OLD]/draft when an executed version exists · paraphrase a fee base ·
record a fee for an entity whose doc you haven't read (template-presumption is a flag
state, not a row) · silently overwrite a row — every change is a shown diff · treat a
missing clause as "probably 5%" — absence is NO_FEE until a document says otherwise.
