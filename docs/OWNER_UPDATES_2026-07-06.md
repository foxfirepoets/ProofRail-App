# OWNER UPDATES — 2026-07-06 (authoritative; overrides older wording anywhere else)

Read this alongside `COWORK_START_HERE.md`. Where any other doc or prompt disagrees with the
items below, **this file wins** — the others were written before these owner rulings.

## 0. Where this runs (deployment) — ONE machine, Claude Co-work runs it front-to-back

**Everything operational runs on the Summa Terra work computer, driven by Claude Co-work — not on
any VPS, not on another computer, and not by hand.** Co-work does the whole pipeline end-to-end on
this one machine: Gmail automation (scan / classify / label / download), the Morning Brief, the
hourly Inbox Runs, invoice + draw coding, InvoiceProof routing, preparing QBO transactions AND
posting the approved ones to the QBO Advanced sandbox via the local `scripts/*.py`, the nightly
Audit-Proof gates, and the Weekly Retro. **QBO is QuickBooks *Online* — reached by cloud API from
this computer; it needs no VPS.** The build machine it was authored on is **not** part of the
operating setup.

**The only human touch is APPROVAL, never execution.** Money postings, FLAG overrides, and vendor
bank-change verification wait for Ben; Co-work never free-hands a QBO write and never moves money.
But every non-approval step — reading, coding, drafting, filing, posting-once-approved, logging —
is Co-work's, on this machine. Nothing is handed to a person to "run," and nothing is handed to
another computer.

**The ONE step that is NOT on this computer** is the one-time HISTORICAL EXTRACT from the legacy
QuickBooks **Desktop** Enterprise files (the obgen migration read, via QODBC). Those `.qbw` files
live on the Rightworks host, so that single data-pull reads them there — it is one-time migration
work, not ongoing automation, and it stops touching Rightworks the moment opening balances land in
QBO. If QuickBooks Desktop is made reachable from this machine, even that step runs here too.
Everything else is 100% on this computer. *(Triggering: Ben kicks off a stage by pasting its
prompt; for hands-off scheduling, Windows Task Scheduler can fire the stages — the WORK is always
Co-work's, on this machine, either way.)*

- **`.env` (real QBO keys) and `.qbo_tokens.json` live ONLY on the work machine.** They stay
  local and gitignored; never copy them anywhere else, never commit them.
- **Single writer, always.** Intuit rotates the refresh token on every refresh, and the tooling
  saves the rotated token back to `.qbo_tokens.json`/`.env`. If a second machine ever refreshes
  the same token, it rotates out from under the first and both break (PR-011 halt). So exactly
  one machine may ever run these scripts against these sandboxes — the work machine. Do not run
  them from the original build machine again; retire/delete its copy of `.env`,
  `.qbo_tokens.json`, and `logs/` so no live credentials or business data are left behind on it.
- Paths in these docs are relative to the project folder, so the package is portable — just drop
  the whole folder on the work machine and run from there.

## 1. The two sandbox companies were RENAMED (realm IDs unchanged)

| Realm | Role | Live QBO company name (now) | Realm ID | Was |
|---|---|---|---|---|
| A | Partnership / Projects | **Partnerships Summa Terra Ventures Sandbox** | 9341457403104290 | "Advanced Sandbox Company US 0e8d" |
| B | Parent / Corporate | **Parent- Summa Terra Ventures Sandbox** | 9341457403104051 | "Advanced Sandbox Company US ee68" |

The write scripts refuse to post unless the live company name matches the expected name in
`.env`. The expected names are now set via `QB_PROJECT_NAME` (Realm A) and `QB_PARENT_NAME`
(Realm B). **If either company is renamed again, update those two `.env` keys to match, or every
write will halt** with "CompanyName … Halting writes for this realm." (That halt is the safety
guard working, not a bug.)

## 2. Commission structure — RESOLVED and BUILT (parent realm B only)

Ben's ruling 2026-07-06. This **supersedes** the earlier "unresolved / Zach 3%" language:
Zach is **2%**, not 3%.

| Recipient | Rate | Payable account | Expense account | Status |
|---|---|---|---|---|
| Mike Watson | 2% | `Comm Payable - Watson (2%)` 21100 | `CEO Commission Expense (2%)` 60200 | pre-existing |
| Zach Coverston | 2% | `Comm Payable - Coverston (2%)` 21300 | `Commission Expense - Coverston (2%)` 60400 | **added 2026-07-06** |
| Porter Christensen | 1% | `Comm Payable - Christensen (1%)` 21200 | `Pres Commission Expense (1%)` 60300 | pre-existing |

- All three account pairs now EXIST in Realm B (added via `scripts/qbo_add_commission_coverston.py
  --execute-sandbox`, audit-logged). Verified present in B, absent in A.
- **Accounts existing ≠ commissions booked. NOTHING is booked automatically.** Each commission
  posting is a separate owner-approved action (Ben approves the packet + `--execute-sandbox`),
  coded to class **90 Parent Overhead**.
- **The partnership realm (A) must NEVER book any commission** — Watson, Coverston, Christensen,
  or anyone. The accounts don't exist in A by design; the verify script asserts their absence.
- The dev-fee flow (`qbo_create_dev_fee_test.py`) still has **no commission code path** — booking
  a commission is always a deliberate, separate, approved step.

## 3. Open follow-ups (not blockers; flag to Ben before the relevant action)

- **Coverston vendor:** if commissions are paid via a Bill to a member-vendor, Realm B currently
  has EXEC vendors only for Watson and Christensen. A vendor for **Zach Coverston** would need to
  be added before a Bill-based commission payment. (Not needed if commissions post via journal
  entry to the payable account.)
- **Commission timing/base:** the rates are set; the *when* (per draw vs monthly) and the *base*
  (which fee figure the % applies to) still follow Ben's instruction per posting — confirm in
  writing at the first real commission run.

## 4. Note on the future ProofRail app (informational — not this test build)

A separate review of the ProofRail app repo (partially captured in `From Original plan/` here;
the full app repo lives separately from this operating package) found that the `stv-oaea-registry`
skill extracts governance fields — executive member,
authorized signatory, loan guarantor, named GC, fee-timing — that have **no columns** in the
`EntityRegistry` Prisma model. That reviewer correctly parked them in a `governance_extracted:`
block instead of inventing registry columns. **Decision rule for Ben:** persist a field in
`EntityRegistry` (via a schema migration) only if the automated engine must READ it to compute
or block a money decision; keep pure reference/approval fields in the governance block. Under
that rule, executive/signatory/guarantor are governance reference (leave them in the block);
**named GC and fee-timing** are the two to scrutinize — promote them to the schema only if the
draw/fee engine selects behavior per entity from them. None of this affects the completed QBO
sandbox test build; it's a design choice for when the app is actually built.
