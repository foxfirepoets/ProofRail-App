---
name: stv-monthly-close
description: Execute STV's recurring monthly accounting cycle in Claude Cowork during the bridge period (July 2026 onward, until ProofRail is proven) — Adam Ludvigson's 33 recurring tasks translated into Cowork procedures with per-task dispositions (bridge / absorbed-by-ProofRail / human-only), the 13-step bank reconciliation, monthly financial packages, accrual JEs, cash calls, loan ties, and the payment calendar. Triggers - "monthly close", "run the close", "July close", "bank rec", "reconcile the month", "financial package", "cash call", "accrue property tax", "loan balance update", "Adam's tasks", "recurring monthly tasks".
---

# stv-monthly-close — the bridge: Adam's cycle, run by Cowork, graded by gates

You are replacing a departed human accountant for a few months while ProofRail earns trust.
Run his cycle faithfully, but with ProofRail's laws already in force. Instruments:
/google-sheets-mastermind (workbooks) · /google-workspace (Drive) · /gmail (statements,
notices, packages) · /pdf-mastery (statements, packets) · /proofrail-coding-rules (every
coding decision) · /stv-oaea-registry (task 10) · /proofrail-drawsheets (task 12).

## RESUME (crash / interrupted session — read before doing anything mid-close)
The close is multi-session; state NEVER lives in chat. It lives in two durable places: the
CLOSE-TRACKER sheet (per-entity status, §4.5) and the audit log (`logs/cowork_audit_*.jsonl`,
`close_step`/posting events). On any restart during a close:
1. Read the tracker → each entity's status. Read the last close_step + posting events.
2. For any entity mid-step, VERIFY the last action actually landed before continuing: check
   `09_QBO_Results` for the QBO Id / RequestId. If it's there, it posted — do NOT re-post
   (idempotency is the guard, verification is the proof). If it's missing, redo the step.
3. Never resume a posting from memory; re-derive from tracker + `09_QBO_Results`.
4. If the tracker and the audit log disagree, STOP and write an exception. Trust the audit
   log (physics) over the tracker (cognition).
5. Log `close_step: resumed — picked up at <entity>/<step>` before continuing.

## THE PAYMENT LAW (absolute)
Cowork NEVER executes a payment — no checks, ACH, wires, autopay changes. For every
payment task: verify due date + confirm funds + prepare the record + remind Ben/Aubrey →
a human pays → Cowork records and marks paid. Same money boundary as ProofRail itself.

## MONTH SHAPE
Days 1–5: prior-month statements arrive → per-entity recon (§1). Days 5–12: close tasks
(§2). By the 15th: packages out (§3), commissions computed (task 25). Throughout: §4
calendar + AP. Every artifact filed to Drive in the same folders Adam used; every
completed entity logged in a close-tracker sheet (create July's from Adam's pattern).

## §1 — TASK 1: Bank & CC Reconciliation (the 13 steps, per entity ~16×)
1 Pull statements (Gmail/portals; manual-entry banks: STDG MACU+Granite, STVE) →
2 match transactions to support; missing invoice/receipt → ONE consolidated ask to Aubrey
per entity, not per item (draft, Ben releases; log the ask timestamp). **SLA:** no reply in
2 business days → ONE reminder draft. Still silent 2 business days after that (4 total) →
open a `10_Exceptions` item "awaiting docs — Aubrey unresponsive since <date>", set the
entity RED, and surface it in the Morning Brief as a close-blocker. The entity CANNOT go
GREEN while that exception is open; the close proceeds for every other entity. Closing an
entity on an estimate instead is Ben's written call, logged. → 3 set transaction types per /proofrail-coding-rules (triple:
entity·project:phase·item) → 4 tie sheet to statement to the penny → 5 enter/reconcile in
QB → 6 export + save recon PDF to Drive → 7 email Mike one recon per LLC (draft for Ben's
release — money-adjacent) → 8 update project-cost sheets (task 15) → 9 OAEA cap-table rec
= run /stv-oaea-registry diff (task 10) → 10 bill-tracker sweep for cleared-but-unmarked
(task 2) → 11 loan balances tie to lender statements (task 7) → 12 dev-fee worksheet: four
STV CM streams per EntityRegistry — 5%×feeBase / draw fees / $500-cap accounting / PM GOI
(task 8) → 13 retainage balances tie (5% Concord / 10% Elite per /proofrail-drawsheets).
**Never clear the HLN Arixa $317,137.06 plug. Litigation entities (12SB, Union): exhibit-
grade notes.**

## §2 — CLOSE TASKS (each = one checklist line per entity)
- **T3 cash calls rec:** contributions received vs registry capitalMap vs QB — three-way tie.
- **T4 W-9s:** new vendors this month → request via Gmail draft; log in vendor tracker.
- **T5 Dev/Imp vendor tag:** every Dev/Imp-coded txn has a vendor. (ProofRail makes this
  structural later; verify manually now.)
- **T6 PM T-12:** ingest Cornerstone/NXT P&Ls; tie prior T-12; post the memorized T-12 JE
  pattern; update rolling 12-mo.
- **T9 property-tax accrual JE:** EXPENSE for operating entities, CAPITALIZED (item 122)
  for development — Adam's rule, verbatim.
- **T11 internal-loan interest:** compute per internal loan agreement; post JE; show math
  in the memo.
- **T14 cash-flow forecast:** refresh per entity (sheets-mastermind).
- **T16 receivables:** status check each contract/note receivable.
- **Contribution/distribution recap:** per entity, month's owner contributions in and
  distributions out, tied to cash-call ledger and registry capitalMap.
- **T17 QB backup:** while on Desktop, after close, remind Ben (flash-drive step is
  physical). Dies at QBO cutover.
- **T24 cash calls (due ~9th–16th):** compute pro-rata from registry capitalMap; DRAFT
  notices with breakdown + due date (money-content: Ben releases every send); track
  receipts; follow up past-due as drafts.
- **T25 CM-fee commissions (by the 15th):** commission accrues on every ASSESSED 5% fee (GROSS
  — incl. contract-contribution fees, regardless of cash collection) at the work-submitted date.
  **Rates RESOLVED by Ben 2026-07-06: Zach Coverston 2% · Mike Watson 2% · Porter Christensen 1%**
  of the assessed fee (supersedes the old 3%/Zach worksheet practice; Coverston now in QBO Realm B).
  Tally the month's assessed fees × each rate, net prior payments per recipient, present for Ben's
  approval; a human pays. Parent-side (Realm B) only — the partnership realm never books commissions.

## §3 — TASK 18: Monthly Financial Package (the deliverable Mike judges)
Per entity: P&L · Balance Sheet · payment-tracking report · rent roll + T-12 (operating).
Assemble via pdf-mastery into one packet per LLC; email drafts to Mike (+ Hunter; + lender
where required, e.g. covenant reporting). Bridge months: export from Rightworks memorized
report group. Post-cutover: BS-by-Location + P&L-by-Location from QBO. File every packet
to Drive.

## §4 — THROUGHOUT THE MONTH (calendar + AP)
Payment calendar (verify funds 3 business days prior; remind; record after human pays):
insurance — Freeman 1st · Union Walk 20th · HLN 22nd · Quincy 24th · 12SB 26th; loans —
HLN/Quincy/Vic-Copa 1st · Union Walk 24th · Summa Elite/Rock Creek 31st; autopays — CoStar
~2nd, Zoom, HL insurance, NRG. Biweekly: verify STVE UCCU payroll funds (T26). Continuous:
AP routing (invoice → Zach confirms work → Mike approves → human pays → record) — this IS
ProofRail F1; run it through submit_intake the moment the pipeline is live, manually until
then. Wires in: apply to correct entity same day; maintain cash-position line for the
Morning Brief (T23).

## §4.5 — THE CLOSE-TRACKER (what "green" means — binary)
One row per entity in July's close-tracker sheet (built from Adam's pattern). Columns:
Entity · BankRec · CCRec · LoanRec · IC-Tie · DevFee · Retainage · Accruals(T6/T9/T11) ·
Package · OpenExceptions · Status. Each cell is GREEN / YELLOW / RED — never blank once the
entity is opened:
- **GREEN** = the check ties to the penny (recs) or is filed/drafted (package), with its
  audit-log event written.
- **YELLOW** = started, not yet tied.
- **RED** = blocked (has an open item in `10_Exceptions`).

An ENTITY is GREEN only when: every §1 13-step rec ties · every applicable §2 line for that
entity is checked · its §3 package is filed or drafted · and it has ZERO open exceptions in
`10_Exceptions`. Any RED cell, or any open exception, keeps the entity YELLOW/RED — never
green. The CLOSE is "done" only when all ~16 entities are GREEN, or Ben waives a specific
entity in writing with a logged reason (`close_step: waived <entity> — <reason>`).
Estimated/accrued figures are not GREEN unless Ben records the estimate as accepted.

## §5 — DISPOSITIONS (what happens to each task as ProofRail proves out)
ABSORBED by ProofRail: T2→AP queue · T5→coding triple mandatory · T8→Fee Engine ·
T10→oaea-registry · T12/13→F3+F6+DrawPackage · T21→F1 · T1 integrity checks→nightly gates
G-A..G-F. REMAINS monthly (new-era §13 of the spec): formal bank rec, close packet, accrual
JEs (Trigger.dev), PM T-12, loan ties, forecast, registry drift, payment calendar.
HUMAN-FOREVER: all payment execution (T19/20/21/29), physical mail (T28), PM calls (T27).
Bridge exit test: one full month where every ABSORBED task was completed by ProofRail with
proofs, and the close packet ties without manual correction.

## NEVER
Execute a payment · send money-content email without Ben's release · clear the Arixa plug ·
skip an entity because it was quiet (quiet entities still accrue, still reconcile) · mark
the close done without the tracker showing all ~16 entities green.
