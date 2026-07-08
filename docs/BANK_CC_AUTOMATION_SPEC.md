# BANK_CC_AUTOMATION_SPEC — bank / credit-card CSV review (suggest-only; nothing auto-posts)

## Import

Ben drops bank/CC CSV exports into `00_Inbox` (or Co-work saves statement attachments from
`ProofRail/Statements`). Naming: `{YYYYMM}_{ENTITY}_{BANK}_{last4}_stmt.csv`. Full account
numbers are never transcribed — last-4 only (append_audit_log masks anything longer).
Manual-entry banks (STDG MACU/Granite, STVE) stay manual — Co-work reconciles what Ben keys,
it does not invent feeds.

## Categorize & match (per transaction, in priority order)

1. **Vendor bill match** — amount+vendor+date-window against posted sandbox bills (09_QBO_Results)
   and pending packets (05/07): exact → MATCHED; ±3 days or cents-off → NEAR (flag).
2. **Draw funding match** — deposits matching draw totals → the draw's funding event.
3. **Loan activity** — lender names/loan patterns → loan account per entity.
4. **Contribution/distribution** — member/partner names → equity accounts (judgment: FLAG for Ben).
5. **Intercompany** — transfers between entity accounts → Due To/From mirror pair (both sides
   or exception).
6. **Recurring knowns** — utilities, insurance, software from history.
7. **UNMATCHED** → exception with best-guess candidates listed, never auto-coded.

## Suggest coding (never guess into QBO)

For each matched/categorized row: Location (entity from account ownership) · Class (phase;
operations default 90 only when history supports it) · Item where item-driven. Confidence <high
→ FLAG. Coding suggestions cite their evidence (matched bill, history pattern).

## Detect

Duplicates (same amount+date+counterparty twice; or already-posted bill also hitting bank) ·
missing support (spend with no invoice/receipt on file → `ProofRail/Missing-Docs` chase) ·
bank-change canaries (payee account changes vs history → Risk-BankChange protocol) ·
anomalies (>2× trailing average for that counterparty → WARN).

## Output

**Approval packet** (`05_Pending_Approval`): matched table + suggested coding + duplicate/
missing-support flags + unmatched exceptions, every row citing its source CSV line.
**QBO sandbox handoff** (`07_QBO_Sandbox_Handoff`, only after Ben approves): expense/bill
commands per approved row — DRY RUN first, `--execute-sandbox` in the approval session.
This test build posts NO bank transactions automatically; the packet is the deliverable.
Audit: every import, match decision, and approval is logged with the CSV filename + row.
