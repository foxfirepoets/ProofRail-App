# HKO Truth Audit - STV Gmail/QB Integration Fixes

Date: 2026-07-01

## Scope

- Code path: `ai-accounting-hub-ralph/`
- Task docs: `OPEN_DECISIONS_spec_audit_2026-06-30.md`, `spec-compliance-audit-stv-integration-layer-2026-06-30.md`, `IMPLEMENTATION_PLAN.md`
- Live surfaces checked: System A Railway and System B Railway
- Mode: Full repo integration audit with reduced HK/OTA automation because the HKO supporting skill-call tool is not exposed in this Codex session.

## Findings

No unresolved Critical or High findings remain in the modified System B repo surface.

Resolved during this run:

1. **[HIGH] System B callback could silently no-op in Railway.**
   - Evidence before fix: System B code only read `SYSTEM_A_URL`, while live Railway exposed the peer service URL as `RAILWAY_SERVICE_EXEMPLARY_TENDERNESS_URL`.
   - Fix: `ai-accounting-hub-ralph/app/integration/intents_router.py:1487` now calls `_system_a_url_from_env()`.
   - Fix: `ai-accounting-hub-ralph/app/integration/intents_router.py:1512` normalizes either `SYSTEM_A_URL` or Railway's generated service host.
   - Test: `ai-accounting-hub-ralph/tests/test_intents_bill.py:422` and `ai-accounting-hub-ralph/tests/test_intents_bill.py:433`.

2. **[HIGH] System A live deployment did not expose `/integration/bill-synced`.**
   - Evidence before fix: live OpenAPI listed `/classify`, `/health`, and `/verify/*`, but not `/integration/bill-synced`.
   - Fix: redeployed System A Railway service `exemplary-tenderness`.
   - Deployment proof: Railway deployment `8f9a6db1-39c7-4066-946e-80e446315dd1` succeeded on 2026-07-01 at 12:26:53 MDT.
   - Live proof: System A OpenAPI now lists `/integration/bill-synced`.
   - Live auth proof: unauthenticated POST to `/integration/bill-synced` returns 401, so the route exists and fails closed.
   - Recorded in `OPEN_DECISIONS_spec_audit_2026-06-30.md:63`.

3. **[MEDIUM] Accepted dashboard had no stable entrypoint.**
   - Fix: `Dashboard/index.html` redirects to the accepted local dashboard bundle.
   - Fix: `docs/index.html` redirects to the published dashboard copy.
   - Recorded in `OPEN_DECISIONS_spec_audit_2026-06-30.md:31`.

4. **[HIGH] System B Railway build was failing on Railpack/mise Python attestations.**
   - Evidence before fix: Railway failed during Python 3.11.9 install with `No GitHub artifact attestations found`.
   - Fix: `ai-accounting-hub-ralph/Dockerfile` provides a Docker-based production build.
   - Fix: `ai-accounting-hub-ralph/railway.toml` tells Railway to use the Dockerfile and health-check `/health`.
   - Fix: `ai-accounting-hub-ralph/.dockerignore` removes `.venv`, caches, logs, and secrets from the upload context.
   - Deployment proof: Railway deployment `b83f3d94-e6d9-487b-ad82-7a9ef57a366c` succeeded on 2026-07-01 at 13:01:59 MDT.
   - Live proof: System B `/health` returned 200 and `/openapi.json` exposed `/approve`, `/approvals/{workflow_id}`, `/intents/bill`, and `/callbacks/bill-synced`.

5. **[HIGH] Live Gmail classify returned 200 while Supabase blocked tracker/outbox/proof writes.**
   - Evidence before fix: System A logs showed permission denied for `payment_request_tracker`, `integration_outbox`, and `proof_results`; System B had no `/intents/bill` hit for the first smoke test.
   - Fix: live Gmail Supabase migration `20260701_live_integration_permissions.sql` added/normalized `integration_outbox`, added missing proof columns, and granted service-role table/RLS access.
   - Fix: System A `src/verify/verify_router.py` now includes `proof_type="invoice"` when writing VerifyAPI proof cache rows.
   - Test: Gmail Automation `pytest tests/test_integration_aihub.py tests/test_verify_api.py -q` passed, 27 passed.
   - Deployment proof: System A Railway deployment `e63efd12-c2d5-44a4-a084-a90d4339ff93` succeeded on 2026-07-01 at 13:12:58 MDT.
   - Live proof: final harmless `DO NOT PAY` classifier smoke test returned `classified`, `Vendor Invoice / Bill`, tracker `4a6636f2-b217-42e5-aff5-d8d28222a46d`, proof `8af443d3-22a1-41c5-a323-ac3cb31d6e6c`.
   - Live handoff proof: System B HTTP logs show `POST /intents/bill 201` at 2026-07-01 13:14:20 MDT.

## Task Status Table

| Task | Status | Evidence |
|---|---|---|
| System B callback URL resolution | implemented | `ai-accounting-hub-ralph/app/integration/intents_router.py:1512` |
| System B callback fallback tests | implemented | `ai-accounting-hub-ralph/tests/test_intents_bill.py:422`, `:433` |
| System A callback route live | implemented | Railway deployment `8f9a6db1-39c7-4066-946e-80e446315dd1`; live OpenAPI includes `/integration/bill-synced` |
| Callback auth fail-closed | implemented | Live unauthenticated probe returns 401 |
| System B Railway deployment | implemented | Railway deployment `b83f3d94-e6d9-487b-ad82-7a9ef57a366c`; live `/health` 200 |
| Live Gmail classify to System B handoff | implemented | Tracker `4a6636f2-b217-42e5-aff5-d8d28222a46d`; System B `/intents/bill` 201 |
| Gmail Supabase write permissions | fixed live | `20260701_live_integration_permissions.sql`; final smoke test had no tracker/outbox permission errors |
| Ben dashboard entrypoint | implemented | `Dashboard/index.html`, `docs/index.html` |
| HKO audit | completed with reduced HK/OTA tooling | This file |
| Full local validation | passed | `ruff check .`, `mypy app`, `pytest -q` all exited 0 |

## Verification Summary

- `pytest tests/test_intents_bill.py tests/test_integration_e2e.py -q`: passed, 27 passed / 1 skipped.
- `pytest tests/test_integration_aihub.py -q` in Gmail Automation: passed, 8 passed.
- `ruff check .` in `ai-accounting-hub-ralph`: passed.
- `mypy app` in `ai-accounting-hub-ralph`: passed.
- `pytest -q` in `ai-accounting-hub-ralph`: passed.
- System A `/health`: 200, Supabase connected, SwarmSync reachable.
- System A `/openapi.json`: includes `/integration/bill-synced`.
- System A `/integration/bill-synced` without auth: 401.
- System B Railway Docker deployment `b83f3d94-e6d9-487b-ad82-7a9ef57a366c`: success.
- System B `/health`: 200, `{"status":"ok","version":"0.1.0"}`.
- System B `/openapi.json`: includes `/approve`, `/approvals/{workflow_id}`, `/intents/bill`, `/callbacks/bill-synced`.
- Gmail Automation `pytest tests/test_integration_aihub.py tests/test_verify_api.py -q`: passed, 27 passed.
- System A Railway deployment `e63efd12-c2d5-44a4-a084-a90d4339ff93`: success.
- Final live smoke test: System A `/classify` returned `classified` for a harmless `DO NOT PAY` vendor invoice test, and System B logged `POST /intents/bill 201`.

## Residual Risks

1. The final Gmail smoke test used a synthetic `DO NOT PAY` classifier payload against the live endpoint, not a real message pulled by the Google Apps Script poller from a Gmail inbox. GAS poller trigger proof remains the next operational test.
2. The smoke test stopped at System B intent creation. It did not approve, book to QuickBooks, or exercise the irreversible QB commit boundary, by design.
3. The dashboard bundle is still mostly static/generated HTML. The entrypoint is fixed, but fully live data wiring remains a separate product task unless the static bundle is accepted as the dashboard artifact.

## Verdict

Passed with operational caveats.

The repo-level integration fixes are implemented, locally verified, deployed, and smoke-tested against both live Railway services. System A now classifies a guarded vendor-invoice payload, writes the tracker/outbox path without permission errors, and hands the bill intent to System B, which returns 201. The remaining work is Gmail poller/live-inbox proof and human-approval/QB boundary testing, not the System A/System B API integration itself.
