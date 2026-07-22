# DECISION REQUEST - Spec Compliance Audit (STV Integration Layer, 2026-06-30)

Two items from the audit could not be resolved by code alone. This file now records Ben-facing decisions and live verification findings as of 2026-07-01.

---

## Item 1 - Dashboard delivery mechanism (Fix 6)

**Decision (2026-07-01): Use Ben's dashboard bundle as the accepted dashboard surface.**

Ben identified the intended dashboard location as:

`C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra QB Automation\Dashboard`

That folder contains the actual dashboard artifact Ben wants to use:

1. `Gmail Command Center.html`
2. `Approvals.html`
3. `Bills.html`
4. `QuickBooks Sync.html`
5. `Proof & Audit.html`
6. `Cost Dashboard.html`
7. The remaining related STV accounting pages in the same folder.

There is **no `.env` file inside `Dashboard\`**. The dashboard bundle is therefore treated as a static/exported dashboard surface, not as the active server-side System B dashboard template.

**Audit answer:** `app/dashboard/templates/system_b.html` is no longer the final dashboard artifact. It remains a useful System B internal/operator page, but the accepted Ben-facing dashboard is the `Dashboard\` bundle above.

**Action for implementation tracking:** Port or wire live System B data into the `Dashboard\` bundle if the dashboard is expected to be live, not static. Do not create a second Ben-facing dashboard without an explicit new decision.

**Implementation update (2026-07-01):** Added `Dashboard\index.html` as the stable local entrypoint for Ben's accepted dashboard bundle. Added `docs\index.html` as the stable GitHub Pages entrypoint for the published dashboard copy. The generated dashboard pages were not rewritten.

---

## Item 2 - System A deployment verification (Fix 7)

**Answer / decision (2026-07-01): Resolved for the deployed System A callback surface, with live Railway evidence.**

The original audit statement that "System A has no repository anywhere on this machine" is no longer true. System A's local source is visible at:

`C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra Gmail Automation\Stage 2 - Live Gmail Automation\`

Local source evidence shows the main System A integration pieces were ported into the Gmail Automation codebase:

1. `src/integration/outbox_writer.py` implements the System A `integration_outbox` writer and creates `bill_intent` payloads for System B.
2. `src/integration/outbox_sender.py` implements the delivery job equivalent, posting pending rows to `AIHUB_BASE_URL + /intents/bill` with retry/dead-row handling.
3. `src/integration/callback_handler.py` implements `POST /integration/bill-synced` and advances `payment_request_tracker.current_status`.
4. `src/main.py` calls `write_bill_intent(...)` and `send_pending_outbox(...)` for vendor-invoice emails.

Live Railway evidence from 2026-07-01:

1. Railway project `exemplary-tenderness` is reachable.
2. System A service `exemplary-tenderness` is online at `https://exemplary-tenderness-production.up.railway.app`.
3. System A `/health` returns 200 with Supabase connected and SwarmSync reachable.
4. System A latest listed deployment is `SUCCESS` at 2026-06-30 18:22:42 MDT.
5. System A Railway variables include the required A-to-B handoff names: `AIHUB_BASE_URL`, `AIHUB_OUTBOX_TOKEN`, `SYSTEM_A_CALLBACK_TOKEN`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`.
6. System B service `ai-accounting-hub` is online at `https://ai-accounting-hub-production.up.railway.app`.
7. System B `/health` returns 200.
8. System B OpenAPI exposes `/intents/bill`, `/approvals/{workflow_id}`, `/approve`, `/approve/{workflow_id}`, and `/callbacks/bill-synced`.
9. System B latest successful listed deployment is 2026-06-30 18:42:33 MDT, but Railway also shows a later failed deploy on 2026-07-01 11:53:12 MDT. Current live health is still 200, so the prior successful deployment appears to be serving.
10. System B code now resolves the System A callback URL from `SYSTEM_A_URL` or Railway's generated `RAILWAY_SERVICE_EXEMPLARY_TENDERNESS_URL`, preventing a silent callback no-op when only Railway's peer-service host variable is present.
11. System A was redeployed to Railway from the local Gmail Automation service on 2026-07-01. Deployment `8f9a6db1-39c7-4066-946e-80e446315dd1` succeeded at 12:26:53 MDT.
12. After redeploy, System A live OpenAPI exposes `/integration/bill-synced`.
13. A live unauthenticated probe to `/integration/bill-synced` returns 401, confirming the route exists and fails closed without the bearer token.

Remaining deployment gaps:

1. ~~I did not verify the live System A Supabase schema in this pass...~~ **RESOLVED 2026-07-01.** `integration_outbox` exists live on `ejxrbxoncsgglrqvjulr` (RLS enabled), confirmed via direct query. At verification time it already held 5 real rows, including genuine (non-synthetic) classified emails — not just prior smoke tests.
2. I did not find a System A `approval_signal.py` equivalent in the Gmail Automation local source, but Item 2 action #4 below resolves that as not MVP-required.
3. **NEW FINDING 2026-07-01 — real bug found and fixed:** `src/integration/outbox_sender.py` delivered `bill_intent` rows to System B successfully (`integration_outbox.status='delivered'`, matching `bills` rows created with `status='verified'` in System B) but **never wrote System B's returned `workflow_id`/`bill_id` back onto `payment_request_tracker`** — `aihub_workflow_id`/`aihub_bill_id`/`aihub_status` sat `NULL` forever on every delivered row, even ones from genuine live email traffic (`"Re: White Horse - Connect to Mike Watson"`, `"Fwd: New payment request from LEGGETT CLEMONS CRAN"`). The correct pattern already existed as a documented reference implementation in the System B repo (`app/integration/outbox_delivery_job.py::_update_tracker_workflow_id`, `aihub_status='active'`) but was never ported into System A's real sender. **Fixed:** added `_write_tracker_response()` to `outbox_sender.py`, called on every successful `bill_intent` delivery; added 2 new tests (9 total in `test_integration_aihub.py`, full suite 209/209 passing); backfilled the 4 pre-existing delivered rows' tracker fields; deployed to Railway (`exemplary-tenderness`, deployment `84831aad...`, confirmed healthy).
4. **Fresh live proof collected 2026-07-01, post-fix:** a real, newly-sent email (`rainking6693@gmail.com` → `stone@summaterraventures.com`, subject "DO NOT PAY - Live tracker write-back verification test invoice", with a synthetic $18.42 test invoice PDF attached — not a real vendor invoice) was picked up by the live GAS poller within ~10 minutes, classified, written to `integration_outbox`, delivered to System B, and created `bills.id=5ca70d67-427a-4de6-bb2f-9fba6a9a8e1b` (`amount=18.42`, `status='verified'`, real `invoiceproof_bundle_id`). `payment_request_tracker.id=e2296e86-...` correctly shows `aihub_workflow_id='bill-intent-e2296e86-...'`, `aihub_bill_id='5ca70d67-...'`, `aihub_status='active'` — populated automatically, proving the fix works live, not just under unit-test mocks.

**DoD tracking decision:**

- DoD #1, System A sends bill intents to System B: **RESOLVED 2026-07-01 — fully proven with fresh, live, end-to-end evidence (see finding #4 above). No longer conditional.**
- DoD #9, System B callback advances System A tracker: **callback route is live and auth-protected in production (confirmed prior pass); the *tracker linkage* half of this (aihub_workflow_id/aihub_bill_id/aihub_status) is now also proven live (finding #4). Still open: an authenticated `/integration/bill-synced` callback has not yet been fired against a real tracker row to prove `current_status` itself advances (e.g. to "Booked / Ready to Book in QB") — that remains the one final gap for full DoD #9 sign-off.**

---

## Item 2, action #4 - Approval signal decision

**Decision (2026-07-01): Do not require the missing System A `approval_signal.py` path for MVP. The System B approval surfaces replace it for the production accounting commit boundary.**

Reason:

1. System B is the accounting system of record and owns the irreversible approval/commit boundary.
2. Live System B exposes both the API approval path, `POST /approvals/{workflow_id}`, and the operator approval UI, `GET /approve` / `POST /approve/{workflow_id}`.
3. The System A codebase explicitly says no automated approvals; Mike/Aubrey actions must be human-initiated.
4. Treating email-detected approval language as a production approval signal is higher risk than requiring Ben to approve inside System B.

**Architecture answer:** System A may continue to detect Mike approval language and store it as supporting evidence, but it should not automatically approve accounting execution for MVP. Ben's System B approval action is the authoritative human approval signal.

**Spec impact:** Any DoD condition that specifically requires "System A detects Mike approval email and fires `POST /approvals/{workflow_id}`" should be changed from MVP-required to future/optional. It should not block MVP sign-off once the System B manual approval UI/API is verified end-to-end.

**Still required:** Fix or verify the System B-to-System A callback path separately. Replacing `approval_signal.py` does **not** replace the need for System A to receive bill-synced callbacks and advance tracker status after System B/QB completion.
