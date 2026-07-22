# Operator Handoff — AI Accounting Hub Dashboard (Accounting Work Queue)

**Mode: SHADOW. QB WRITE-BACK DISABLED.** Nothing in this dashboard writes to QuickBooks, sends
payments, or runs BillAdd. Every action changes only the canonical store (Supabase) and appends an
audit row. A red banner reading **⛔ SHADOW MODE — QB WRITE-BACK DISABLED** is pinned to the top of
every page, with the subtext *"Payments, BillAdd, and live QuickBooks write-back are disabled in this
build."*

---

## 1. How I start it and what URL I use

1. Open a terminal in `C:\Users\Administrator\Desktop\AI Accounting Hub\ai-accounting-hub-ralph`.
2. Activate the venv and start the server:
   ```
   .venv\Scripts\activate
   uvicorn app.main:app --reload --port 8000
   ```
   (Live data needs `DATABASE_URL` set in `.env` — already configured for Supabase project
   `fdnwlcomuddzmluvbylg`. The pages still render without it; the lists will just be empty.)
3. Open the dashboard at:  **http://127.0.0.1:8000/ui**

**Login / auth:** None. This is an internal, localhost-only tool — there is no login screen and no
test credentials. (Health checks, if you want them: `GET /health` and `GET /ready`.)

Every page shares one layout: the red shadow banner on top, a left nav with a **Search** box, a
**⚑ What Needs My Attention** link, the modules grouped by workflow, and a **Records** group
(Companies, Vendors, Bills, Sync Health). A green dot marks a **functional** module, a grey dot a
**pending** one.

---

## 2. The Accounting Work Queue landing (`/ui`)

`/ui` is the **Accounting Work Queue** landing page. It lists all **16 modules** grouped into 10
sections in this order: **Construction, Accounts Payable, Banking, Financing, Equity, Intercompany,
Fees, Master Data, Close, QuickBooks**. Each module is a card with:

- a **status badge** — green/**Functional** (usable now) or grey/**Pending** (placeholder), and
- a **live count** — e.g. "*N* to review", "*N* open", "*N* to fix", or "—" when a module has no
  count yet.

The counts are real reads of the canonical store: Draw Review and each work-item module show their
open ("to review") item count, Vendor Bills shows its open count, Month-End Close Exceptions shows the
number of open exceptions, and Missing-Dimensions Cleanup shows the number of items needing coding.

The same page surfaces the **"What needs my attention today"** rollup (full page at `/ui/attention` —
see §6). 15 of the 16 modules are functional; only **QuickBooks Sync / Write-back** is pending.

---

## 3. Every functional module (15 of 16)

All routes below were verified against `app/dashboard/router.py`. Draw Review and Vendor Bills have
their own bespoke routes; the other twelve functional modules share the generic `/ui/m/{key}` engine.
Month-End and Missing-Dimensions are read-only cross-module aggregations (no per-item actions).

| Module | Group | Route | What it does | Actions |
|---|---|---|---|---|
| **Draw Review** | Construction | `/ui/draws` (detail `/ui/draws/{id}`) | GC construction draw packages — parsed lines, row-confidence, amount-coverage, exceptions, the 5/2/1 fee panel, proof/audit trail | **Approve for Accounting**, **Reject**, **Mark Historical** |
| **Vendor Bills** | Accounts Payable | `/ui/vendor-bills` (detail `/ui/vendor-bills/{id}`) | Standard AP vendor bills — intake, vendor match, coding, duplicate + bank-change checks | **Intake**, **Approve**, **Reject**, **Needs-info** |
| **Non-GC Invoices** | Accounts Payable | `/ui/m/non_gc_invoices` | Non-construction invoices (services, soft costs, professional fees) | Intake, Approve, Reject, Needs-info |
| **Bank Feed Review** | Banking | `/ui/m/bank_feed` | Bank feed transactions awaiting match + categorization (bank-sensitive) | Intake, Approve, Reject, Needs-info |
| **Credit Card Charges** | Banking | `/ui/m/credit_card` | Credit card charges awaiting receipt match + coding (bank-sensitive) | Intake, Approve, Reject, Needs-info |
| **Loan Draws** | Financing | `/ui/m/loan_draws` | Construction-loan draw fundings against the lender facility | Intake, Approve, Reject, Needs-info |
| **Interest Reserve Activity** | Financing | `/ui/m/interest_reserve` | Interest reserve draws + accruals against the loan facility | Intake, Approve, Reject, Needs-info |
| **Owner/Investor Contributions** | Equity | `/ui/m/owner_contributions` | Capital contributions from owners + investors | Intake, Approve, Reject, Needs-info |
| **Distributions** | Equity | `/ui/m/distributions` | Distributions to owners + investors | Intake, Approve, Reject, Needs-info |
| **Intercompany Reimbursements** | Intercompany | `/ui/m/intercompany` | Cross-entity reimbursements + due-to/due-from settlement | Intake, Approve, Reject, Needs-info |
| **Developer Fees** | Fees | `/ui/m/developer_fees` | Developer fee billing (the live 5% calc is shown in the Draw Review fee panel) | Intake, Approve, Reject, Needs-info |
| **Management Fees** | Fees | `/ui/m/management_fees` | Recurring management fee billing across entities | Intake, Approve, Reject, Needs-info |
| **Vendor Setup / Bank Changes** | Master Data | `/ui/m/vendor_setup` | New vendor setup + vendor bank-detail change review (ATEP gate, bank-sensitive) | Intake, Approve, Reject, Needs-info |
| **Month-End Close Exceptions** | Close | `/ui/m/month_end` | Read-only rollup of every open exception blocking close (see §5) | None (links to the source item) |
| **Missing Customer:Job / Class / Item Cleanup** | Close | `/ui/m/missing_dimensions` | Read-only rollup of items missing dimensions (see §5) | None (links to the source item) |

**Records** (left nav, not modules): Companies `/ui/companies` (+ `/{id}`), Vendors `/ui/vendors`
(+ `/{id}`), Bills `/ui/bills` (+ `/{id}`, read-only synced GC bills), Sync Health `/ui/sync`.

The work-item modules each accept the same intake fields (company, title, reference, counterparty,
amount, txn date, project, Customer:Job, Class, Item, and — for bank-sensitive ones — a bank detail
that is fingerprinted, never stored raw). Intake runs three checks: **DUPLICATE** (same
company+module+reference), **MISSING_CODING** (any of Customer:Job / Class / Item absent), and
**BANK_CHANGE** (a new fingerprint differing from a prior one for the same counterparty — a warning,
not a hard exception). New items land in `needs_review`.

---

## 4. The pending module + the only remaining work

Exactly one module is **Pending**: **QuickBooks Sync / Write-back** (`qb_sync`, QuickBooks group,
`/ui/queue/qb_sync`). It opens to a "Module pending — no QB write-back" placeholder page. This is the
**single remaining non-functional module** and the only major work left: live QuickBooks Desktop
write-back (QBWC / BillAdd) against QuickBooks Enterprise on Rightworks. It stays disabled in this
shadow build — there is no QBWC write path in the codebase.

Two open spikes gate that work (both shown on the **Sync Health** page, `/ui/sync`):

1. **QBWC poll cadence** — *"pending spike #1"*: the real poll cadence + queue depth have not yet been
   measured on a Rightworks file.
2. **Rightworks persistent poller** — *"pending written approval — spike #2"*: a persistent poller is
   awaiting written Rightworks approval; there is no inbound fallback.

QBWC write-back stays disabled until both are resolved. Everything else in the dashboard is functional
today.

(Note: any functional module's `/ui/queue/{key}` URL just 307-redirects to that module's real route.
Unknown module keys return 404. Only `qb_sync` actually renders the placeholder.)

---

## 5. The two cross-cutting Close views

Both live under `/ui/m/...` but aggregate across **every** source (draws, vendor bills, and all
work-item modules). They are read-only — each row links to the source item where you actually fix it.

- **Month-End Close Exceptions** (`/ui/m/month_end`) aggregates every open exception that blocks
  close: draw packages still in `needs_review` (shown as `DRAW_NEEDS_REVIEW`), vendor bills carrying
  exceptions (`DUPLICATE_INVOICE`, `MISSING_CODING`, `VENDOR_NOT_SET_UP`), and work items carrying
  exceptions (`DUPLICATE`, `MISSING_CODING`). Each row shows source, reference, entity, exception,
  amount, and a link.
- **Missing Customer:Job / Class / Item Cleanup** (`/ui/m/missing_dimensions`) lists every vendor bill
  and work item missing one or more of Customer:Job / Class / Item, with the specific missing
  dimensions and a link to fix coding on the source.

---

## 6. Cross-entity Search and the Attention dashboard

**Search** (`/ui/search?q=...`, also the box at the top of the left nav). A read-only, parameterized
search across the canonical store. A query under 2 characters renders a friendly prompt, never an
error. Results are grouped, and each hit links to the entity's detail page. Groups: **Draws, Bills**
(GC bills), **Vendor Bills, Vendors, Invoices / Work Items, Projects, Exceptions**. It matches draw
number / project / borrower / lender / address, vendor names (trigram-indexed), invoice numbers and
PO refs, work-item titles/references/counterparties/projects, and open-exception text.

**What Needs My Attention** (`/ui/attention`, and summarized on `/ui`). A read-only cross-module
rollup of everything needing action, bucketed by urgency:

| Bucket | Urgency | What it collects |
|---|---|---|
| Open exceptions (close-blocking) | high | the Month-End exception rollup |
| Vendor bank-change warnings | high | vendor-bill + work-item `BANK_CHANGE` warnings (fingerprint-derived; raw bank fields are never read) |
| Missing coding (Customer:Job / Class / Item) | medium | the Missing-Dimensions rollup |
| Needs info / needs review | medium | every open vendor bill, work item, and draw |
| Pending approvals | low | open items carrying no exception and no warning |

Use it as your start-of-day list: work the high-urgency buckets first, click through to the source,
resolve, and the counts drop.

---

## 7. Operator how-tos

### Review a draw
1. Click **Draw Review** in the nav (or go to `/ui/draws`). You get the list with each draw's status
   (`needs_review`, `approved_for_accounting`, `rejected`, etc.) and a Historical flag.
2. Click a draw to open `/ui/draws/{id}`. The detail page shows the header (project, lender, borrower,
   draw #, total, status), **parsed lines** with row-confidence (`exact` / `reconstructed` /
   `needs_review` / `unrecoverable`), **amount coverage** (authoritative vs reconstructed total,
   unresolved delta, % coverage), **exceptions** (retainage/cost-code) and **warnings**, the **fee &
   commission panel**, and the **proof / audit trail**.

### Mark Draw #29 historical / not-for-posting
On the draw detail page, click **Mark Historical** (posts to `/ui/draws/{id}/mark-historical`). This
sets `not_for_posting = true` and `historical_example = true` on the draw's canonical flags — no
QuickBooks action. **Draw #29 (Hunter's Landing) is already a paid historical fixture**
(`not_for_posting`, `already_paid`, `historical_example`). Once a draw is historical it **can never be
approved for posting** — see the next how-to.

### Approve a current draw for accounting
On the draw detail page, click **Approve for Accounting** (posts to `/ui/draws/{id}/approve`). For a
normal current draw this transitions status to `approved_for_accounting` in the canonical store. **In
shadow mode that is the end of the line — it does NOT post to QuickBooks, run BillAdd, or move money.**
**Guard:** if the draw is historical / `not_for_posting` (e.g. Draw #29), Approve is **refused** with
an HTTP 400 and a clear message before any status change. The guard is enforced in both the approve
route (`assert_postable`) and the canonical transition (`transition_draw_status`). **Reject**
(`/ui/draws/{id}/reject`) sets status `rejected`. Both write canonical status only.

### Approve a vendor bill or a work item for accounting
On a vendor-bill detail page (`/ui/vendor-bills/{id}`) or a work-item detail page
(`/ui/m/{key}/{id}`), use **Approve** / **Reject** / **Needs-info**. Approve sets
`approved_for_accounting`, Reject sets `rejected`, Needs-info sets `needs_info`. Each writes canonical
status only and appends an audit row — no QuickBooks write-back.

### Intake a vendor bill
On `/ui/vendor-bills`, submit the intake form (posts to `/ui/vendor-bills/intake`) with company,
vendor name, invoice #, amount, due date, and coding (Customer:Job / Class / Item), plus an optional
bank detail. The system matches the vendor by normalized name; if no vendor matches it **queues a
vendor candidate** instead of creating the bill and tells you so. A matched bill runs the duplicate /
bank-change / missing-coding checks, lands in `pending_review` (or `needs_info` if it has a hard
exception), and you're redirected to its detail page.

### Intake a work item
On any work-item module list (e.g. `/ui/m/loan_draws`), submit the intake form (posts to
`/ui/m/{key}/intake`; JSON is also accepted). The item runs the duplicate / bank-change /
missing-coding checks, lands in `needs_review`, and you're redirected to its detail page.

### Resolve a vendor candidate
From a company detail page (`/ui/companies/{id}`, which lists candidates) submit the resolve form
(posts to `/ui/vendor-candidates/{id}/resolve`) choosing the real vendor. This marks the candidate
resolved and back-fills any unlinked draw lines whose payee matches the candidate, then redirects to
the vendor. Canonical-only.

### Remap a draw-line cost code
On the draw detail page, use the cost-code remap control on a line (posts to
`/ui/draw-lines/{id}/remap-cost-code`). It sets the line's cost code + item code in the canonical
store and returns you to the draw. Canonical-only.

---

## 8. Where exceptions show

- **Per draw:** the **exceptions** and **warnings** blocks on `/ui/draws/{id}` (retainage exceptions,
  cost-code gaps, and line-validation warnings) — warnings never block you the way a true exception
  does.
- **Per vendor bill / work item:** on its detail page, with hard exceptions distinguished from
  warnings. Vendor-bill exceptions are `DUPLICATE_INVOICE`, `MISSING_CODING`, `VENDOR_NOT_SET_UP`
  (warning: `VENDOR_BANK_CHANGE`). Work-item exceptions are `DUPLICATE`, `MISSING_CODING` (warning:
  `BANK_CHANGE`).
- **Across modules:** the **Month-End Close Exceptions** view (§5) and the **Attention** dashboard
  (§6).
- **Across sync runs:** the **Sync Health** page (`/ui/sync`) shows counts + AuditProof status.

---

## 9. Where the audit trail / proof shows

Every intake and every status change writes an **AIVS hash-chained audit row** (the AuditProof spine),
not a QuickBooks write. Vendor-bill rows carry `tool_name = "vendor_bills"`; work-item rows carry
`tool_name = "work_queue:{module_key}"`.

- **Per vendor bill / work item:** the detail page shows the item's **audit trail** — every intake and
  status-change row that references it, each with its action type, actor, and a truncated row hash.
- **Per draw:** `/ui/draws/{id}` shows the draw's **proof bundles** (kind, pass/fail, VCAP state,
  proof hash) plus the **fee & commission panel** — the shadow draft of the 5/2/1 split: developer fee
  **5%** (partnership owes this only), and on the parent's books 5% income + Mike Watson **2%** +
  Porter Christensen **1%**, with the correct **8% distinct-economic total** highlighted and the buggy
  **13%** naive sum labeled as never booked. Every fee entry is **SHADOW DRAFT — not posted**
  (`posted = False`, `qb_txn_id = None`).
- **Per sync run:** AuditProof status (passed bundle count) on the **Sync Health** page.

---

## 10. Shadow-mode guarantees

- Every action writes **canonical status + an audit row ONLY**.
- **NO** QuickBooks write-back, **NO** BillAdd, **NO** payments — no module imports or calls the QB /
  QBWC / BillAdd / payment path.
- Bank details are stored as **SHA-256 fingerprints**, never raw — the raw value never reaches the
  database or any log; bank-change detection compares fingerprints only.
- The shadow banner is pinned to every page as your constant confirmation.

---

**Bottom line:** Start with `uvicorn app.main:app --reload --port 8000`, open
**http://127.0.0.1:8000/ui**, no login. Work the **Attention** list, drill into any of the 15
functional modules, intake/approve/reject/needs-info or mark-historical, and read exceptions, the
proof, and the audit trail on the detail pages, Month-End, and Sync Health. Nothing posts to
QuickBooks — connecting/writing to QuickBooks Enterprise on Rightworks (the `qb_sync` module + the two
poller spikes) is the only major work that remains.
