# DRAW REVIEW — paste with a draw reference (email/PDF in 02_Draw_Packages)

Review draw package: **[Ben: paste gmail:<msgid> or drive:<path> here]**
Follow `docs/DRAW_PACKAGE_AUTOMATION_SPEC.md` exactly:

1. HISTORICAL/CURRENT GATE FIRST. Historical/example/superseded → mark "Do Not Post /
   Historical Example", file to `13_Historical_Examples` (fixture) or `14_Do_Not_Post`,
   log, STOP.
2. Detect format (AIA_G703 / PROCORE_PCI / LEGACY_STACK) and extract: project · our draw N ·
   lender draw M · date · lender · total · vendor lines (vendor, cost code, this-period,
   retainage) · retainage rate · change orders. Give each extracted line a confidence note;
   low-confidence lines are FLAGGED, and the whole reconciliation gets human tie-out (first-60-days rule).
3. Run the six checks and show the work:
   (1) Σ lines(net retainage) == draw total, to the penny
   (2) CM/dev fee on sheet == 5% × fee base (the Madison Draw 6 $100 variance is the canonical catch)
   (3) retainage rate per GC (Concord 5% / Elite 10%)
   (4) dual numbering consistent with history
   (5) COs billed ⊆ approved
   (6) member-vendor scan (double-pay trap)
   Plus: any line >2× vendor trailing average → WARN.
4. Approval status: CM sign-off present? Mike approval email on file? (cite msgids)
5. Fee: compute 5% dev fee on this entity's verified OAEA base. No verified base → REFUSE the
   fee section and open an exception ("no OAEA row → no fee").
6. Commissions: state "parent-side only (Realm B); rates confirmed (Watson 2%, Coverston 2%,
   Christensen 1%); accounts exist; nothing booked without Ben's per-run approval" — always.
7. Output the approval packet to `05_Pending_Approval`: extraction table, six-check results,
   fee calc, approvals status, source citations, exceptions. Then the QBO handoff plan
   (per-line `qbo_create_sandbox_bill.py` commands + `qbo_create_dev_fee_test.py` command),
   all shown DRY RUN.
8. Log `draw_check` events per check + a packet event. Wait for Ben — nothing posts from this prompt.
