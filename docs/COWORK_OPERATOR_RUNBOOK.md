# COWORK_OPERATOR_RUNBOOK — Ben's step-by-step operating manual

Each step names the prompt to paste (from `cowork_prompts/`) and what "done" looks like.
Cadence: Morning Brief daily → Inbox Runs ~hourly 9–5 MT → Approval Session when the queue has
items → Bank/CC weekly → Dev-fee monitor per draw → Month-end per calendar → Retro Friday PM.

## 1. Morning routine (~10 min)
1. Open Co-work, paste `01_MORNING_BRIEF.md`.
2. Co-work reports: new mail by class, quarantine count, pending approvals, exceptions aging,
   yesterday's QBO sandbox postings (with audit-log refs), anything stuck.
3. You decide the day's priorities; anything urgent goes straight to an Approval Session.
**Done:** brief delivered, priorities acknowledged, audit event logged.

## 2. Inbox review (hourly-ish)
1. Paste `02_HOURLY_INBOX_RUN.md`.
2. Co-work: classify → label → save attachments to Drive (label↔folder 1:1) → extract → run
   InvoiceProof packets on invoices → queue PASS items for approval → quarantine FAIL items →
   draft (never send) replies → log everything with source citations.
**Done:** zero unlabeled new mail; every attachment filed; `ProofRail/Processed` only on
fully-completed items.

## 3. Invoice review
Paste `04_VENDOR_BILL_REVIEW.md` for the queue, or `05_INVOICEPROOF_REVIEW.md` for one invoice.
Review the packet: extracted fields, InvoiceProof verdict + findings, proposed coding
(entity/Location/Class/project/item), source citation. FLAG items need your written override
reason. FAIL items stay quarantined.
**Done:** every queue item is approved / rejected / escalated with a note.

## 4. Draw review
Paste `03_DRAW_REVIEW.md` with the draw email/PDF reference. Co-work runs the six checks
(fee math penny-exact, retainage rate, dual numbering, COs, line arithmetic, member-vendor) and
marks HISTORICAL vs CURRENT. Historical → Do Not Post, filed as fixtures. Current → approval
packet with CM/Mike approval status and the 5% dev-fee calculation.
**Done:** verdict + packet, or a written exception.

## 5. Approval session (you initiate)
1. Paste `06_QBO_SANDBOX_HANDOFF.md`.
2. Co-work lists approved-and-ready items, each with the EXACT script command.
3. You say "approved: items 1,3" — Co-work records approval (approver, timestamp, source) in
   the audit log, then runs the commands **with `--execute-sandbox`**.
4. Co-work reports QBO IDs and verifies with a report read.
**Done:** every executed command has an audit line with RequestId + QBO ID; failures reported
verbatim, never papered over.

## 6. QBO sandbox posting test (the standing proof)
Weekly (or after any script change) run the smoke pair:
`python scripts/qbo_create_sandbox_bill.py … --execute-sandbox` (one coded test bill) and
`python scripts/qbo_read_report_by_location.py --realm A` (it shows up in the right column).
**Done:** bill visible under the right Location; audit log has the trail.

## 7. Bank / credit card review (weekly)
Paste `07_BANK_CC_REVIEW.md` after dropping bank/CC CSV exports into `00_Inbox`.
Co-work categorizes, matches to bills/draws/known flows, suggests Location/Class/Item coding,
flags duplicates and missing support, and builds an approval packet. **No auto-posting** —
everything waits for you. (Manual-entry banks — STDG MACU/Granite, STVE — stay manual.)
**Done:** matched list + exception list + packet.

## 8. Developer fee monitor (per draw / monthly)
Paste `08_DEV_FEE_MONITOR.md`. Co-work recomputes 5% of each entity's fee base riding current
draws, compares to what's booked in both realms (A payable vs B income — must mirror), and
flags variances (the Madison Draw 6 $100 catch is the standard). Commission rates are confirmed
(Watson 2%, Coverston 2%, Christensen 1% — parent realm only; see `OWNER_UPDATES_2026-07-06.md`);
accounts exist but nothing books without Ben's per-run approval.
**Done:** per-entity fee table, variances flagged, zero *unapproved* commission postings.

## 9. Exception cleanup (as needed, at least weekly)
Review `10_Exceptions`. For each: resolve (with note) → item re-enters the pipeline; or
escalate (CPA/counsel/owner). **Every cleared exception requires a written note** — no silent
clears; Co-work refuses to clear one without a note.

## 10. Month-end close
Paste `09_MONTH_END_CLOSE.md` (spec: docs/MONTH_END_CLOSE_SPEC.md). Bank recs, CC recs, loan
tie-outs, intercompany netting (Due To/From mirrors must net 0.00), dev-fee compliance,
unapproved bills, missing coding, uncategorized transactions, AP/AR review → close packet.
**Done:** checklist all green or exceptions written; close packet PDF in `12_Month_End_Close`.

## 11. Daily summary (end of day)
Co-work appends the daily summary event: volumes by class, InvoiceProof pass rate, postings
made, exceptions opened/cleared, approvals pending, tomorrow's carry-over. It's the first thing
tomorrow's Morning Brief reads.

## Friday PM: Weekly retro
Paste `10_WEEKLY_RETRO.md`. Volumes, proof pass rate, exception causes, your coding
corrections → Co-work proposes 1–3 playbook edits. **Edits are adopted only after you confirm**
— that's the learning loop.
