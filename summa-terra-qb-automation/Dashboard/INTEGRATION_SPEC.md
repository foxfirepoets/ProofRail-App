# SPEC — Summa Terra AI Accounting Hub Dashboard: Live-Data Integration

```
Spec Title:  Dashboard Live-Data Integration (Gmail + QB Hub → 14 pages)
Version:     1.0.0
Author:      STV automation build
Last Updated: 2026-07-02
Status:      Ready for Build
Timeline:    ~1 week (1 pass via orchestrated build + audit)
Confidence:  ~90% (template-engine re-render hook to confirm per page during build)
Next Steps:  Build via output-to-orchestrator → hko-truth-audit → push
```

---

## 1. Executive Summary

The Summa Terra "AI Accounting Hub" dashboard is 14 self-contained HTML pages that today render **hardcoded mock arrays** (e.g. `kpis = [{label:'Bills mirrored', value:'1,284'}]`). This spec wires every page to **live data** from the two automations already in production: the **Gmail Automation** (Supabase `ejxrbxoncsgglrqvjulr`) and the **AI Accounting Hub / QuickBooks** system (Supabase `fdnwlcomuddzmluvbylg`). The dashboards become a real operating view — Ben's single pane over email intake, approvals, bills, draws, fees, proofs, and QuickBooks sync — instead of a static mockup. The build is client-side only, reads through **anon keys protected by row-level security (RLS)**, and never embeds a secret in the HTML. Primary user: Ben (Accounting Manager). Success = every page shows real rows from the correct project, degrading gracefully when empty or offline.

## 2. Scope Definition & Non-Scope

**In scope**
- Replace the static `renderVals()` data in all 14 pages with live Supabase reads, preserving each template's exact data shape.
- A small shared data layer (`assets/stv-data.js` or inline equivalent) providing a Supabase client per project + typed fetch helpers + loading/error handling.
- A Supabase migration per project enabling RLS + **anon SELECT** on exactly the tables read.
- Loading (skeletons already exist), empty, and error states per widget.
- `QuickBooks Sync` page also reads the live QBWC endpoint health (`/health`).

**Out of scope (WON'T-BUILD, v1)**
- Any **write** from the dashboard (no inserts/updates/deletes). Read-only.
- A new backend / API server. (Existing FastAPI services are not modified here.)
- Auth / login / per-user access control on the dashboard.
- Realtime subscriptions / websockets (v1 is fetch-on-load + manual refresh).
- Rewriting the bundler/template engine. We hook into it, not replace it.
- Cross-tenant multi-company switching UI beyond what pages already show.

**Dependencies**
- Live Supabase projects `ejxrbxoncsgglrqvjulr` (A) and `fdnwlcomuddzmluvbylg` (B), populated by the running automations.
- Supabase JS v2 (CDN) or the PostgREST REST endpoint with the anon key.

## 3. Business Context & Acceptance Criteria

**Goal:** give Ben a truthful, live operating dashboard so the automations' state (emails classified, drafts pending, bills approved, draws/fees, proofs, QB sync) is visible without opening Supabase or QuickBooks.

**Success metric:** 14/14 pages render live rows from the correct project; 0 pages show mock numbers; 0 secrets in client HTML.

**Acceptance criteria (per page — each names a concrete failing observation to disprove):**
- [ ] **Cost Dashboard** (landing) shows real cross-system KPIs (e.g. real bill count from B and real inbox/classification count from A) — NOT `1,284`.
- [ ] **Bills** lists real `bills` rows (id, vendor, amount, status) from B; count matches `select count(*) from bills`.
- [ ] **Approvals** shows real pending approvals: `payment_request_tracker` (A, `approval_status`) + `bills` where `status='approved'` (B).
- [ ] **Vendors** lists real `vendors` (+ `vendor_candidates`) from B.
- [ ] **Cost Codes** lists real `cost_codes`/`accounts`/`classes` from B.
- [ ] **Draw Packages** lists real `draw_packages` + `draw_lines` from B.
- [ ] **Developer Fees** shows real `fee_entries` (B) and `fee_opportunities`/`developer_fee_email_events` (A).
- [ ] **Intercompany** shows real `intercompany_links` + `v_intercompany_net` from B.
- [ ] **Proof & Audit** shows real `proof_bundles`+`audit_rows` (B) and `proof_results` (A).
- [ ] **QuickBooks Sync** shows real `bills.qb_txn_id/qb_synced_at/qb_sync_attempts/status` + `companies.qb_file_id` (B) and the live `/health` of the QBWC service.
- [ ] **Month-End Close** shows real per-company roll-ups (bills/draws/fees/proofs by status) from B.
- [ ] **Entities** lists real `companies` (+ intercompany) from B.
- [ ] **Gmail Command Center** shows real `email_messages`/`email_classifications`/`draft_queue`/`payment_request_tracker`/`task_queue`/`review_queue` from A.
- [ ] Every page: empty query → visible empty state (not a spinner forever); network/RLS error → visible error banner, no console crash.
- [ ] `grep -ri "service_role\|sb_secret" Dashboard/*.html` returns **nothing**.

**Spec status:** build-phase. If the template re-render hook differs per page, update code and note it here; don't silently diverge.

## 4. Architecture & System Integration

**Data flow**
```
Browser opens page.html
  → shared data layer creates 2 Supabase clients (A anon, B anon)
  → page.renderVals() (now async) queries the mapped table(s)
  → PostgREST applies RLS (anon SELECT allowed on whitelisted tables)
  → rows mapped to the template's expected shape ({label,value,...})
  → template engine re-renders <sc-for list="{{ kpis }}">
  → loading skeleton → data | empty state | error banner
```

**Integration points**
- Supabase A (`ejxrbxoncsgglrqvjulr`) PostgREST `/rest/v1/*` — Gmail domain.
- Supabase B (`fdnwlcomuddzmluvbylg`) PostgREST `/rest/v1/*` — accounting domain.
- QBWC service health: `GET https://ai-accounting-hub-production.up.railway.app/health` (QuickBooks Sync page only).

**New infrastructure**
- RLS policies (anon SELECT) on the read tables in both projects (Section 13). No new servers, tables, or queues.

**Ownership:** dashboard files live in `Dashboard/`; RLS migrations live in each system's repo (`.../db/` for A; Alembic/SQL for B) and are also captured here.

## 5. User Flows & Happy Path

**Actor:** Ben (no login). **Precondition:** automations have produced rows.

1. Ben opens `index.html` → redirect to `Cost Dashboard.html`.
2. Page load: skeletons show; shared layer fires the page's queries against A and/or B.
3. Rows return; KPIs/tables/lists populate with live values; "last updated" stamp set.
4. Ben clicks a nav link (e.g. Bills) → that page loads and queries B `bills`.
5. Ben clicks Refresh (if present) → re-runs the page's queries.

**Alternate paths**
- *Empty table:* query returns `[]` → widget shows "No records yet" empty state.
- *Network/RLS failure:* fetch throws or returns 401/403 → widget shows red "Couldn't load — check connection/RLS" banner; other widgets on the page still render.
- *Partial:* one of several widgets fails → only that widget shows its error; page does not blank out.

## 6. Data Models & Schema (source-of-truth matrix)

Read-only. Shapes are the template's existing tokens; transforms map DB → token.

| Page | Widget/token | Project | Table(s) | Key columns | Transform |
|---|---|---|---|---|---|
| Cost Dashboard | KPIs | A+B | email_messages, email_classifications (A); bills, draw_packages, fee_entries (B) | counts, status | count/group roll-up |
| Bills | list/kpis | B | bills, vendors, companies | id, vendor_id→name, amount, status, qb_txn_id | join vendor name; format $ |
| Approvals | queue | A+B | payment_request_tracker (A), bills (B) | approval_status, status | union of pending items |
| Vendors | list | B | vendors, vendor_candidates | name, qb_list_id, swarmscore, status | merge confirmed+candidate |
| Cost Codes | list | B | cost_codes, accounts, classes | code, name, maps_to_account, kind | join account name |
| Draw Packages | list | B | draw_packages, draw_lines | draw_number, package_total, status | header + line count/sum |
| Developer Fees | list/kpis | B+A | fee_entries, draw_packages (B); fee_opportunities, developer_fee_email_events (A) | fee_role, percent, amount, status | policy split view |
| Intercompany | net table | B | intercompany_links, v_intercompany_net | partnership/parent, amount, net | net per pair |
| Proof & Audit | list | B+A | proof_bundles, audit_rows (B); proof_results (A) | kind, passed, created_at | chronological proofs |
| QuickBooks Sync | kpis/events/health | B + QBWC | bills (qb_txn_id, qb_synced_at, qb_sync_attempts, status), companies (qb_file_id); /health | synced vs pending vs exception | sync roll-up + live health |
| Month-End Close | per-company | B | bills, draw_packages, fee_entries, proof_bundles | company_id, status | group by company×status |
| Entities | list | B | companies, intercompany_links | legal_name, entity_type, role, qb_file_id | entity cards |
| Gmail Command Center | inbox/stages/people/feed | A | email_messages, email_classifications, draft_queue, payment_request_tracker, task_queue, review_queue, gmail_thread_index, sender_profiles, automation_audit_log | status, workflow_type, urgency | stage funnel + feed |

**Validation:** every query is `select <cols> ... limit N order by created_at desc`; no `*` on wide tables where a column list is cheap; no writes.

## 7. Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| anon SELECT not permitted (RLS missing) | PostgREST 401/permission → widget error banner "read not permitted"; log to console.warn; DO NOT fall back to a service key. |
| Network offline / fetch throws | catch → error banner; retry on next manual Refresh. |
| Empty result `[]` | render empty state, not skeleton, not error. |
| Column renamed/missing | map defensively (`row.x ?? '—'`); never throw in the mapper. |
| QBWC `/health` down | QuickBooks Sync shows health chip "unreachable" (amber), other widgets still load from B. |
| Large table | `.limit()` (e.g. 200 rows for lists, aggregates via count) to bound payload/latency. |
| Two clients, wrong project | each page imports the correct client (A vs B) per the matrix; a page must never query the wrong project. |
| Mixed A+B widget fails one side | render the side that succeeded; error only the failed side. |

**Consistency note:** Section 2 says read-only; Section 6/7/13 contain only SELECT + RLS SELECT policies — consistent. Section 9 says anon+RLS, no secrets; Section 7 forbids service-key fallback — consistent.

## 8. Performance & Scalability

- Page interactive < 1.5s on broadband; each query < 400ms p95 (bounded by `.limit`).
- Lists capped (e.g. 200 rows) with "showing N of M" where M = count.
- No N+1: prefer a single query per widget; resolve names via embedded selects (`vendors(name)`) or a small lookup map fetched once.
- Data volumes are small (hundreds–low-thousands of rows); no caching layer needed in v1.

## 9. Security & Compliance

- **Keys:** only the **anon** (or publishable) key appears in client HTML. Service-role/`sb_secret_*` keys are **forbidden** in `Dashboard/*`.
- **RLS:** every read table has RLS **enabled** with an explicit `anon SELECT` policy scoped to that table. No table is world-readable by accident; enabling RLS without a policy denies all, so policies are additive and reviewed.
- **No writes:** anon role gets SELECT only; no INSERT/UPDATE/DELETE policies added.
- **PII:** email bodies are already stored as `body_preview` (truncated) in A; dashboards display preview/subject/sender only.
- **Audit:** read access is not logged per-view in v1 (no backend). Acceptable for an internal single-user dashboard.
- **Transport:** Supabase is HTTPS only.

## 10. Testing Strategy

- **Static check:** `grep -ri "service_role\|sb_secret\|SERVICE_ROLE" Dashboard/*.html` → empty (secret-leak gate).
- **Per-page smoke:** open each page; confirm live rows (compare a KPI to a direct `select count(*)`), empty state (point at an empty table), and error state (temporarily use a bad key locally).
- **RLS test:** with the anon key, `curl '<proj>.supabase.co/rest/v1/<table>?select=*&limit=1' -H "apikey: <anon>"` returns rows for whitelisted tables and 401/empty for non-whitelisted.
- **Shape test:** each `renderVals()` returns the same keys the template binds (`kpis[].label/value`, etc.) — verified by the page rendering without `undefined`.
- **Truth audit:** hko-truth-audit across config→schema→query→UI (Section 17 downstream).

## 11. Deployment & Rollout

- Dashboards are static files opened locally by Ben (or served from any static host). "Deploy" = save files + apply the two RLS migrations.
- **Order:** (1) apply RLS migrations on A and B (so anon reads work); (2) update the 14 pages; (3) open each page to verify.
- **Rollback:** revert the HTML files (git); RLS policies can be dropped (`drop policy`) with no data impact. No blue-green needed (static).

## 12. API Documentation (data access contracts)

All access is Supabase PostgREST with header `apikey: <ANON>` + `Authorization: Bearer <ANON>`.
- `GET /rest/v1/<table>?select=<cols>&order=created_at.desc&limit=<n>` → 200 `[rows]`.
- Aggregates: `GET /rest/v1/<table>?select=count` (with `Prefer: count=exact`) or client-side count on a bounded fetch.
- Embedded joins: `GET /rest/v1/bills?select=id,amount,status,vendors(name)` (FK embed).
- QBWC health: `GET https://ai-accounting-hub-production.up.railway.app/health` → `{status, version}`.
- Errors: 401 (RLS/anon denied), 404 (bad table), network throw → per Section 7.

## 13. Database Migrations (RLS)

Two migrations (one per project). Each **enables RLS** and adds an **anon SELECT** policy for the exact tables read. Template (repeat per table):

```sql
-- PROJECT A (ejxrbxoncsgglrqvjulr): dashboard read tables
alter table public.email_messages enable row level security;
create policy "dash anon read" on public.email_messages for select to anon using (true);
-- repeat for: email_classifications, draft_queue, payment_request_tracker,
--   payment_approval_events, fee_opportunities, developer_fee_email_events,
--   proof_results, review_queue, task_queue, gmail_thread_index,
--   sender_profiles, automation_audit_log

-- PROJECT B (fdnwlcomuddzmluvbylg): dashboard read tables
alter table public.bills enable row level security;
create policy "dash anon read" on public.bills for select to anon using (true);
-- repeat for: bill_lines, vendors, vendor_candidates, companies, accounts,
--   classes, cost_codes, draw_packages, draw_lines, fee_entries,
--   intercompany_links, proof_bundles, audit_rows, work_items
-- (v_intercompany_net is a view; grant select to anon)
grant select on public.v_intercompany_net to anon;
```

**DOWN:** `drop policy "dash anon read" on public.<table>;` per table (RLS stays enabled or `disable` if it was off before — record prior state).

**Validation:** anon `curl` returns rows for each listed table and is denied for any non-listed table.

## 14. Known Limitations & Future Work

- v1 is read-only + fetch-on-load; no realtime. Future: Supabase realtime for live tiles.
- No per-user auth; anyone with the file + anon key + network can read whitelisted tables. Acceptable internal-only; future: Supabase Auth + per-role RLS if hosted publicly.
- Cross-system joins (A↔B) are done client-side (two fetches) since they're separate projects. Future: a read API that federates.
- Month-End Close aggregates are computed client-side; future: DB views for heavier roll-ups.

## 15. Glossary

- **System A / Gmail Automation:** Supabase `ejxrbxoncsgglrqvjulr`; email intake, classification, drafts, payment tracker, fee opportunities, proofs (`proof_results`).
- **System B / AI Accounting Hub:** Supabase `fdnwlcomuddzmluvbylg`; canonical bills, vendors, cost codes, draws, fees, intercompany, proofs (`proof_bundles`), QB sync.
- **renderVals():** each page's method returning the arrays bound to template tokens; the integration seam.
- **anon key / RLS:** public Supabase key whose access is governed by row-level-security policies; safe for client use.
- **QBWC:** QuickBooks Web Connector; System B's outbound sync channel (health surfaced on the QuickBooks Sync page).

## 16. Monitoring, Metrics & Observability

- Client-side only: each page shows a "last updated" timestamp and a per-widget status (ok/empty/error).
- No server telemetry in v1. QuickBooks Sync surfaces the QBWC `/health` as the one live external signal.
- Manual verification via the Section 10 smoke tests after each deploy.

## 17. Alternative Designs Considered

- **Through the FastAPI backends** (add read endpoints): keeps DB server-side, but requires new endpoints for many tables and a running server for the dashboard to work. Rejected for v1 — heavier, and the dashboards are static/local. (Chosen: anon+RLS direct reads.)
- **Service key in local-only HTML:** fastest, but embeds a full-access secret; unacceptable risk if a file ever leaves the machine. Rejected.
- **Rebuild pages in a framework (React app w/ Supabase):** cleaner long-term but throws away the existing bundled pages and is far larger. Rejected for v1; the seam (`renderVals()`) makes in-place wiring cheap.

**Rationale:** anon+RLS direct reads deliver live data with zero new infrastructure, no secrets in the client, and minimal change surface (swap `renderVals()` bodies + add RLS).

## 18. Final Build Checklist

- [ ] Shared data layer: 2 anon clients (A, B) + `fetchRows`, `fetchCount`, `fetchHealth`, error/empty handling.
- [ ] Reverse-engineer the render/re-render hook (make `renderVals()` async or add a data-load + re-render call) — confirm on one page, then apply to all.
- [ ] Wire each of the 14 pages per the Section 6 matrix; preserve token shapes.
- [ ] Loading (existing skeleton), empty, and error states per widget.
- [ ] QuickBooks Sync reads `/health`.
- [ ] RLS migrations applied on A and B; anon curl verifies allow/deny.
- [ ] Secret-leak grep is empty.
- [ ] Per-page acceptance criteria (Section 3) all pass.
- [ ] hko-truth-audit run; findings fixed.
- [ ] Committed + pushed to `foxfirepoets/Summa-Terra-QB-Automation`.

## Consistency Check Results

- ✓ Scope (read-only) ↔ Migrations (SELECT-only RLS) ↔ Security (anon SELECT, no writes): consistent.
- ✓ Security (no secrets/service key) ↔ Error handling (no service-key fallback): consistent.
- ✓ Per-page acceptance (real rows) ↔ Data matrix (explicit table/columns): consistent.
- ✓ Performance (`.limit`) ↔ Error handling (empty/large) ↔ Data models (bounded queries): consistent.

**Status: 0 contradictions — Ready for Build.**
