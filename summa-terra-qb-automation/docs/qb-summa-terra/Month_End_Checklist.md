# Month-End Close Checklist — Real Estate Development Partnerships (Deliverable 13)

Companion to `SPEC.md` §16.2. Run **per entity file**, then the **portfolio roll-up** in the master reporting
file. Target: **≤ 3 business days per entity**, **≤ 7 business days portfolio**. Do the steps in order — later
steps depend on earlier ones. The ★ step is the headline control that stops developer-fee leakage.

## A. Reconciliations (do first)
- [ ] **Bank reconciliations** — every operating, loan-funding, reserve, escrow account reconciled to statement.
- [ ] **Credit card reconciliations** — all cards reconciled; clearing account at $0.
- [ ] **Loan reconciliations** — `Construction Loan Payable` ties to lender statement; interest/fees recorded.
- [ ] **Intercompany reconciliation** — every `Due To — X` equals the matching `Due From — X` on the other
      file. **Portfolio net must be $0.** Do not proceed past close with a non-zero net.

## B. ★ Developer-fee review (the control)
**Trigger reminder:** a draw is fee-eligible only after **construction-manager + Mike Watson approval** —
not on the GC's first submission.

**In a PARTNERSHIP file (per entity) — the 5% only:**
- [ ] Run **Approved Draw Register** — list every approved **draw package** this period (by Draw #).
- [ ] Run the **Partnership Draw vs. Developer Fee Reconciliation** — verifies the **5% only**: confirm
      **every approved draw package** links to its **5% Developer Fee** entry (`FEE-DEV` → `15500`/`60100`
      Dr, `21000 Due-To Summa Terra` Cr) on the **package total**. This report must show **no commission lines**.
- [ ] **Any approved draw without its 5% fee** → generate it now, or **log a written exception**
      (reason + approver) in **Missed Fee Exceptions**. **No silent gaps.**
- [ ] Confirm **no commission accounts** (`60200/60300/21100/21200`) carry a balance here — commissions are
      **parent-only**. Any balance = posting error; reverse.
- [ ] Reverse/adjust the 5% for any **denied or revised** draw; document.
- [ ] Review **Outstanding Developer Fee (Due-To Summa Terra)** — confirm it ties to the parent's Due-From.

**In the PARENT file (Summa Terra) — income + commissions:**
- [ ] Confirm each approved draw's **5% Developer Fee Income + Due-From** is booked (mirrors the partnership).
- [ ] Run the **Parent Commission Register** — verifies **Mike 2% + Porter 1%**: confirm the
      **2% (Watson, `60200`/`21100`) + 1% (Christensen, `60300`/`21200`) commission** accruals are booked on
      the **same draw total** (`COMM-<Draw#>`); investigate any 5% income lacking its commissions.
- [ ] Review **Outstanding Executive Commissions** (payables to Watson/Christensen) — action payments.

## C. Project cost & coding cleanup
- [ ] **Project Cost Detail** review — costs land on the right Customer:Job / Item / Class.
- [ ] **Missing Customer/Job** report → recode every cost transaction lacking a project.
- [ ] **Missing Class** report → recode every transaction lacking a phase class.
- [ ] **Missing Item/Cost Code** report → recode every cost lacking an Item.
- [ ] **Uncategorized Transactions** report → zero out the Uncategorized account.
- [ ] **Capitalize vs. expense** check — CIP additions are correctly capitalized (via Item), not expensed.
- [ ] **Budget vs. Actual** (Estimate vs. Actual by Item) — review variances; flag overruns.

## D. Subledger & balance review
- [ ] **AP Aging** — review; nothing stuck/duplicated; vendor bank-change controls respected.
- [ ] **AR Aging** — review draw/fee billings and collections.
- [ ] **Unapplied payments** — apply or resolve.
- [ ] **Old uncleared checks** — investigate/void as needed.
- [ ] **Capital account review** — contributions/distributions posted to the right partner; capital rolls.
- [ ] **Draw review** — all period draws recorded with Draw # custom field; loan funding tied out.

## E. Lock & report
- [ ] **Set/advance the closing-date password** to lock the period (prior-period edits require re-auth).
- [ ] Review **Audit Trail – changed transactions** for any prior-period edits.
- [ ] Produce the **financial-statement package**:
      - [ ] Partnership Balance Sheet
      - [ ] Partnership P&L
      - [ ] (Parent file) Parent Company P&L + fee income/commission payables
- [ ] Confirm all reports ran from the **memorized "STV Monthly Pack"** (no rebuilt filters).

## F. Portfolio roll-up (master reporting file)
- [ ] Import/refresh each entity trial balance (or run Combined Reports).
- [ ] Run the **Cross-book Draw Fee/Commission Reconciliation** — verifies **all three fees exist in the
      correct books**: for each approved Draw #, the partnership carries its **5% only** and the parent carries
      the **5% income + 2% Watson + 1% Christensen** — never a commission on a partnership. (Counts the
      mirrored 5% **once**: distinct charge = 8%, not 13%.)
- [ ] Confirm **intercompany eliminates / nets to $0** across the portfolio.
- [ ] Produce the **Consolidated Management Report** (Class = entity) for owners.
- [ ] Produce **Monthly Management Fee Summary** + **Executive Commission Summary**.

---

### Close sign-off
| Item | Value |
|------|-------|
| Entity / file | __________________ |
| Period | __________________ |
| Approved draws this period | _____  → fees verified? ☐ |
| Exceptions logged | _____ |
| Intercompany net | $______ (must be $0) |
| Closed & locked by | __________________  Date: ________ |
| Reviewed by | __________________  Date: ________ |
