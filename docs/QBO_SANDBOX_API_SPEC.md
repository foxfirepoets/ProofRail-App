# QBO_SANDBOX_API_SPEC — the sandbox API layer (implemented in `scripts/qbo_common.py`)

## Environment & realm separation

- Base URL: `https://sandbox-quickbooks.api.intuit.com/v3` — **hard guard**: every script exits
  unless `QB_ENV=sandbox` AND the URL host is exactly the sandbox host. **There is no production
  mode and none can be enabled by env var.**
- Realm A (projects) = `QB_PROJECT_REALM_ID` = 9341457403104290 · Realm B (parent) =
  `QB_PARENT_REALM_ID` = 9341457403104051. Every call embeds its realm ID in the URL; every
  audit line carries the realm key; before any write the script fetches CompanyInfo and refuses
  if `CompanyName` ≠ the expected sandbox name (read-only sanity check, Safety Rule 10).
- App: "STV Automation" (`QB_APP_ID=489286d2-b0c5-41b8-a59d-9430c1f4eef3`), scope
  `com.intuit.quickbooks.accounting`.

## OAuth refresh-token handling

- Token endpoint: `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`, Basic auth
  `client_id:client_secret`, `grant_type=refresh_token`.
- Access tokens cached in `.qbo_tokens.json` (never committed, never printed), refreshed 2 min
  before expiry, and re-refreshed once automatically on a 401.
- **Intuit rotates refresh tokens** — every refresh persists the newest refresh token back to
  `.env` automatically. Never reuse a stale one.
- Verify OAuth specifics against current Intuit docs before hardening further — endpoints and
  TTLs drift over time.

## minorversion strategy

Every call pins `minorversion` (env `QBO_MINORVERSION`, default 75). Bump deliberately after
testing, never implicitly.

## Entity operations (all idempotent, all audit-logged)

| Operation | API | Script |
|---|---|---|
| Account create/lookup | `POST /account`, lookup by FullyQualifiedName via query | `qbo_seed_accounts.py` (colon names → ParentRef+SubAccount; AccountSubType fallback on validation fault) |
| Location create/lookup | **`POST /department`** (UI "Location" = API `Department`) | `qbo_seed_locations_departments.py` |
| Class create | `POST /class` | `qbo_seed_classes.py` |
| Customer/Project create | `POST /customer` (`ParentRef`+`Job:true` for sub-customers) | `qbo_seed_customers_projects.py` |
| Vendor lookup/create | `POST /vendor`, lookup by DisplayName | `qbo_seed_vendors.py` |
| Item lookup/create | `POST /item` (Type=Service, `ExpenseAccountRef` for purchase-side cost codes) | `qbo_seed_items.py` |
| Bill create | `POST /bill` — ItemBasedExpenseLine with **ItemRef + ClassRef + CustomerRef** and header **DepartmentRef**; refuses if any ref missing (PR-043) | `qbo_create_sandbox_bill.py` |
| Invoice create | `POST /invoice` — SalesItemLine + DepartmentRef + ClassRef (Realm B dev-fee income side) | `qbo_create_dev_fee_test.py` |
| Journal entry | **only if needed** — native forms preferred; JEs bypass AP/AR subledgers. Not implemented; add only with CPA sign-off | — |
| Reports | `GET /reports/BalanceSheet?summarize_column_by=Departments` | `qbo_read_report_by_location.py`, verify script |
| Query | `GET /query?query=SELECT … STARTPOSITION n MAXRESULTS 1000` (paginated) | `qbo_common.query_all` |

## Idempotency (three layers)

1. **Name lookup before create** — existing records are skipped and logged "exists".
2. **Deterministic RequestId** on every POST: `sha1(realmId|entity|naturalKey)[:36]` as
   `?requestid=` — an identical retry returns the original result instead of double-creating
   (PR-012: duplicate RequestId = success).
3. **Local ledger dedup** for bills (DocNumber+Vendor refused if already present).

## Error handling & throttling

- 401 → one forced token refresh, then retry once; still failing → halt (PR-011).
- 429/5xx → exponential backoff honoring `Retry-After`, max 5 tries (PR-010).
- Row-level failures are logged and the batch continues; the summary lists every failed row.
- Write throttle 0.25s/request (~240/min, ~50% of Intuit's per-realm budget).
- Error code 6240 (duplicate name) is logged as a collision warning, not fatal.

## Audit logging

Every create attempt/success/error, token refresh, company check, and verification run appends
one redacted JSONL line to `logs/qbo_seed_YYYYMMDD.jsonl` (append-only). Redaction strips every
known secret value plus anything token-shaped before the line hits disk.

## Rollback / cleanup strategy

- **The tooling never deletes** — there is no delete/void code path.
- A bad single record: void/inactivate manually in the QBO UI, then note it in the audit log
  (manual override protocol — overrides never bypass the log).
- A partial dev-fee pair (Realm A posted, Realm B failed): the script prints and logs the
  PR-020 compensating action — void the Realm A bill manually in the UI.
- A truly poisoned sandbox: Intuit Developer Portal → delete and recreate the sandbox company,
  update the realm ID in `.env`, re-run the seed (it is idempotent and fast). This is the
  nuclear option and is fine — it's a sandbox.

## No production writes — enforcement inventory

1. URL host allowlist (exact sandbox host match) · 2. `QB_ENV=sandbox` assert ·
3. realm IDs must be the two configured sandbox IDs · 4. CompanyName check before writes ·
5. writes require the `--execute-sandbox` flag (DRY_RUN env cannot enable writes) ·
6. no BillPayment/transfer/charge code exists anywhere in `scripts/`.
