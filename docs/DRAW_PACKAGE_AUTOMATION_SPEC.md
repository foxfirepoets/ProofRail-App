# DRAW_PACKAGE_AUTOMATION_SPEC — draw classification, six checks, fee math, and the Do-Not-Post guard

## Pipeline

1. **Classify the draw email** (Inbox Run): DRAW_SHEET → label `ProofRail/Draws`.
   Format detect: `AIA_G703` (G702/G703) · `PROCORE_PCI` · `LEGACY_STACK` — extraction trust is
   earned per GC format, never assumed.
2. **Save the PDF** to `02_Draw_Packages/{project}/Draw N - {Lender} Draw #M/` with filename
   `{PROJECT}_DRAW{NN}_{YYYYMMDD}_{LENDER}.pdf` (dual numbering: our N, lender's M).
3. **Historical/current gate (FIRST, before any math):** anything marked or inferable as
   historical/example/superseded → mark **Do Not Post / Historical Example**, file to
   `13_Historical_Examples` (labeled corpus, fixture use only) or `14_Do_Not_Post`. The
   pipeline ends there for those documents. `classify_attachment.py` enforces this
   (`do_not_post: true` → HARD STOP).
4. **Extract** (pdf extraction, every line carries a confidence score): project ·
   draw number(s) · date · lender · total · vendor lines (vendor, cost code, this-period,
   retainage) · retainage rate · change orders. Sub-high-confidence lines FLAG; for the first
   60 days every reconciliation gets mandatory human tie-out regardless of PASS.
5. **Six checks** (all must pass or the draw is an exception):
   | # | Check | Detail |
   |---|---|---|
   | 1 | Line total ties | Σ vendor lines (net of retainage) == draw total, to the penny |
   | 2 | Fee math penny-exact | CM/dev fee on the sheet == 5% × fee base. Canonical catch: Madison Draw 6 billed $15,407.03 vs 5% = $15,307.03 → $100 variance FLAG |
   | 3 | Retainage rate | per-GC (Concord 5% / Elite 10%); wrong rate = FLAG |
   | 4 | Dual numbering | our draw N ↔ lender draw M consistent with history |
   | 5 | COs billed ⊆ approved | change orders billed must be within approved set |
   | 6 | Member-vendor scan | lines to member vendors flagged (double-pay trap) |
   Plus anomaly screen: any line >2× vendor trailing average → WARN on the packet.
6. **Approval tracking:** construction-manager approval (from the package or email) and
   **Mike approval** (email is Mike's channel; APPROVAL-classified reply = gate evidence).
   Both recorded via `append_audit_log.py` before the draw can advance.
7. **Developer fee calculation:** 5% × entity fee base per its OAEA (base varies — 12SB
   excludes land; entities without a verified fee clause are REFUSED, not guessed). Produces
   the two-realm fee packet (see DEV_FEE_QBO_WORKFLOW.md).
8. **Commissions:** parent-side (Realm B) ONLY. Rates confirmed 2026-07-06 — Mike Watson 2%
   (21100/60200), Zach Coverston 2% (21300/60400), Porter Christensen 1% (21200/60300); accounts
   exist (see `OWNER_UPDATES_2026-07-06.md`). Still book NOTHING automatically — each commission
   posting needs Ben's per-run approval, class 90 Parent Overhead. **The partnership realm never
   books commission expense/payable under any circumstances.**
9. **Approval packet** → `05_Pending_Approval`: extraction table, six-check results, fee calc,
   approval status, source citations (email msgid + Drive path), exceptions.
10. **QBO sandbox transaction packet** → after Ben's approval, `07_QBO_Sandbox_Handoff`
    holds the exact commands: per-vendor-line bills (`qbo_create_sandbox_bill.py`) coded
    Location=entity, Class=phase, Customer=project:phase, Item=cost code; retainage to
    `GC Retainage Payable` (25300-style) via the retainage item; dev-fee pair via
    `qbo_create_dev_fee_test.py`. All DRY RUN first, `--execute-sandbox` only in the approval
    session.

## Do Not Post guard (multiple layers)

filename/subject regex (`historical|example|sample|do not post|superseded|void`) → terminal
folder `14_Do_Not_Post` → scripts never read from 13/14 for posting → approval packet template
requires a "current-document" attestation line → audit log records the gate decision.
