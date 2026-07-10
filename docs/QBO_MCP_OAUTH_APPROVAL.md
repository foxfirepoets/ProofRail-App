# QBO MCP OAuth Approval — what Ben needs to do before real QBO posting is allowed

**Status as of 2026-07-09: QBO live wiring is STILL PAUSED — `container.ts` still uses
`FakeQboClient`, unchanged.** What changed today: the callback route this doc calls "does not
exist in the deployed app yet" now exists in the repo (not yet deployed/exercised — see below).
`RealQboClient` (`src/proofrail/qbo.ts`) is code-complete — OAuth refresh, sandbox guard, Class/
Location/Customer/Item resolution, dedupe, and (new) a rotation-persistence callback — but is
**not approved for real posting** until the acceptance tests in section 4 pass. Until then,
**`scripts/*.py` remains the live source of truth** for any real QBO write; the MCP path is not
to be trusted for real postings.

## 0. Implementation status (2026-07-09)

Ben registered the redirect URI as `https://proofrail-mcp.onrender.com/auth/qbo/callback`. Built
against that URL, in this repo, not yet deployed or exercised against real Intuit sandbox
companies:

- `src/api/mcp-server.ts` — added `GET /auth/qbo/start?realm=A|B` (redirects to Intuit's
  consent page, builds the redirect_uri from the same `baseUrl(req)` helper the existing
  Cowork-facing OAuth shim uses, so it resolves to the registered URL in production) and
  `GET /auth/qbo/callback` (exchanges the code, verifies `realmId` against `QBO_REALM_A`/
  `QBO_REALM_B` before storing anything, writes to `proofrail_qbo_token_store`, never echoes a
  token value in its response). Both routes respond `501` with a plain message instead of
  crashing the MCP server if `QBO_CLIENT_ID`/`QBO_CLIENT_SECRET`/`PROOFRAIL_DATABASE_URL`/the
  relevant `QBO_REALM_*` aren't set yet.
- `src/proofrail/qbo-token-store.ts` — new, narrowly-scoped module (deliberately separate from
  `PostgresProofRailRepository`, which owns business data, not auth infra) reading/writing the
  **already-provisioned** `proofrail_qbo_token_store` table (confirmed present 2026-07-09 in the
  `fdnwlcomuddzmluvbylg` Supabase project — columns `realm` (PK, 'A'/'B'), `realm_id`,
  `refresh_token`, `access_token`, `access_expires_at`, `updated_at`). No migration was needed.
- `src/proofrail/qbo.ts` — `RealQboClient` now takes an optional `onRefreshTokenRotated`
  callback, invoked every time Intuit rotates the refresh token inside `token()`. Wire it to
  `QboTokenStore.persistRotation` when this client is eventually constructed for real — this is
  what makes acceptance test 2 ("token rotation survives a restart") pass instead of silently
  losing the rotated token to memory on the next deploy/restart.
- `.env.example` — documented the Render-app env vars from section 3 below in a clearly-labeled
  section, distinct from the work-machine's `QB_*` vars. Confirmed `QBO_REALM_A_REFRESH_TOKEN`/
  `QBO_REALM_B_REFRESH_TOKEN` are correctly NOT env vars (the callback route writes them to
  Supabase directly) and added `PROOFRAIL_DATABASE_URL` + `SWARMSYNC_VERIFY_API_KEY`, which were
  missing from `.env.example` even though the code already requires/uses them.
- `container.ts` was **not touched** — still wires `FakeQboClient`. Flipping it to
  `RealQboClient` requires all seven acceptance tests in section 4 AND Ben's explicit go-ahead,
  neither of which has happened.

**What Ben still needs to do** (section 2 below, now literally clickable instead of hand-built):
confirm `QBO_CLIENT_ID`/`QBO_CLIENT_SECRET`/`QBO_REALM_A`/`QBO_REALM_B`/`PROOFRAIL_DATABASE_URL`
are set on the Render service, confirm the redirect URI is registered in the Intuit app's Keys &
OAuth settings, deploy, then visit `https://proofrail-mcp.onrender.com/auth/qbo/start?realm=A`
and `?realm=B` once each, logging into the correct sandbox company each time.

## 1. Why a SEPARATE OAuth grant — not reuse of the local script's token

Intuit **rotates the refresh token on every single refresh**. The work-machine's `scripts/*.py`
pipeline already holds a live, actively-used refresh token for both sandbox realms
(`QB_PROJECT_REFRESH_TOKEN`, `QB_PARENT_REFRESH_TOKEN` in `.env`, per `docs/OWNER_UPDATES_2026-07-06.md`'s
"Single writer, always" rule). If the Render-hosted MCP app authenticated using that **same**
refresh-token value:

- The first refresh from *either* side invalidates the token the *other* side is holding.
- Whichever side refreshes next gets a 401 (`invalid_grant`) and halts — this is exactly the
  failure `OWNER_UPDATES_2026-07-06.md` warns about, and it would break the currently-working,
  real Python pipeline that Cowork depends on today.
- There is no way to "share" one refresh token safely across two independent processes that each
  refresh on their own schedule. Intuit's rotation model assumes exactly one holder.

The fix is not a code change — it's a **second, independent authorization**: the same registered
Intuit developer app (same Client ID/Secret) can issue a second, separate refresh token via a
second consent flow. Two independent refresh tokens against the same realm do not conflict with
each other; only *sharing one token value* across two refreshers does.

## 2. Exact OAuth steps for Ben to perform

These produce a **second** refresh token per realm, used only by the Render app — the existing
`scripts/*.py` `.env` values are never touched.

1. Go to **developer.intuit.com** → the existing registered app (same one `QB_APP_ID`/`QB_CLIENT_ID`
   in `.env` already reference — no new app registration needed).
2. Under that app's **Keys & OAuth** settings, confirm the **Redirect URI** list includes:
   `https://proofrail-mcp.onrender.com/auth/qbo/callback` — **this route does not exist in the
   deployed app yet** (`src/api/mcp-server.ts` only implements the Cowork-facing `/authorize` +
   `/oauth/token` OAuth shim for *Cowork's* connection to the MCP server — that is a completely
   different OAuth flow from *this app's* connection to Intuit/QBO. A new callback route needs to
   be added to the app before step 3 can complete; flag this back to whoever does the build work).
3. For **each realm** (A = partnership/projects, B = parent/corporate), complete Intuit's
   Authorization Code flow in a browser:
   - Visit `https://appcenter.intuit.com/connect/oauth2?client_id=<QB_CLIENT_ID>&redirect_uri=<callback>&response_type=code&scope=com.intuit.quickbooks.accounting&state=<random>`
   - Log in as the user connected to the **sandbox** company for that realm and approve.
   - Intuit redirects to the callback with `code` + `realmId` — the callback route exchanges `code`
     for an access + refresh token pair (`POST https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`,
     `grant_type=authorization_code`).
4. Confirm the returned `realmId` matches the expected sandbox realm ID already in `.env`
   (`QB_PROJECT_REALM_ID` / `QB_PARENT_REALM_ID`) — if it doesn't match, the wrong company was
   authorized; redo against the correct one.
5. Store the resulting refresh tokens **only** in the MCP app's own storage (see env var checklist
   below) — never write them into the work machine's `.env`/`.qbo_tokens.json`, and never write the
   work machine's existing tokens into the MCP app's config.

## 3. Exact env var checklist for QBO on the MCP app (Render)

None of these are set yet (confirmed — only `PROOFRAIL_MCP_KEY` and `SWARMSYNC_API_KEY` exist on
the Render service today). All of these are **separate** from the work-machine's `.env` QBO vars
of the same conceptual purpose — same Client ID/Secret is fine to reuse, tokens are not.

| Var | Purpose | Reuse from work-machine `.env`? |
|---|---|---|
| `QBO_CLIENT_ID` | Intuit app Client ID | Yes — same registered app, safe to reuse (`QB_CLIENT_ID`) |
| `QBO_CLIENT_SECRET` | Intuit app Client Secret | Yes — same registered app, safe to reuse (`QB_CLIENT_SECRET`) |
| `QBO_REALM_A` | Partnership/projects sandbox realm ID | Yes — same realm, safe to reuse (`QB_PROJECT_REALM_ID`) |
| `QBO_REALM_B` | Parent/corporate sandbox realm ID | Yes — same realm, safe to reuse (`QB_PARENT_REALM_ID`) |
| `QBO_REALM_A_NAME` | Expected company name, Realm A (sandbox-guard check) | Yes (`QB_PROJECT_NAME`) |
| `QBO_REALM_B_NAME` | Expected company name, Realm B (sandbox-guard check) | Yes (`QB_PARENT_NAME`) |
| `QBO_REALM_A_REFRESH_TOKEN` | **NEW, separate** refresh token from step 2's OAuth flow | **No — must be new**, from the MCP app's own consent flow |
| `QBO_REALM_B_REFRESH_TOKEN` | **NEW, separate** refresh token from step 2's OAuth flow | **No — must be new** |
| `QBO_MINORVERSION` | Pinned Intuit minorversion | Yes (`75`, matches `qbo_common.py`'s default) |
| `QBO_BASE_URL` | Must be `https://sandbox-quickbooks.api.intuit.com/v3` | Fixed value — `RealQboClient` already refuses to start against anything else |

Storage note: once these refresh tokens exist, they should live in `proofrail_qbo_token_store`
(the Supabase table already created for this — see `PostgresProofRailRepository`), not as static
Render env vars, since Intuit will rotate them on every refresh and a static env var can't be
updated by the running app. The two `_REFRESH_TOKEN` rows above are the **initial seed values**;
the app must write rotated tokens back to `proofrail_qbo_token_store`, mirroring what
`scripts/qbo_common.py`'s `_persist_rotated_refresh_token` already does for the file-based store.

## 4. Acceptance tests required before the MCP app is allowed to post real QBO bills

All of the following must pass, in this order, before `container.ts` is changed from
`FakeQboClient` to `RealQboClient`:

1. **Callback route exists and completes a real OAuth exchange** — `/auth/qbo/start` +
   `/auth/qbo/callback` implemented 2026-07-09 (see section 0 above) but **not yet deployed or
   manually exercised against real Intuit sandbox companies** — this test is not yet passed, only
   unblocked. Still needed: deploy, confirm env vars are set, visit `/auth/qbo/start?realm=A` and
   `?realm=B` once each, confirm tokens land in `proofrail_qbo_token_store`.
2. **Token rotation survives a restart** — force a token refresh, restart the Render service,
   confirm the next call still authenticates (proves the rotated token was actually persisted, not
   just held in memory).
3. **Sandbox guard test** — point `QBO_BASE_URL` at anything other than
   `sandbox-quickbooks.api.intuit.com` and confirm `RealQboClient`'s constructor throws immediately
   (already true today — this is a regression test, not new work).
4. **Company-name guard test** — temporarily mismatch `QBO_REALM_A_NAME`/`QBO_REALM_B_NAME` against
   the real sandbox company name and confirm `assertCompany()` halts the write (already implemented
   — write the test).
5. **Class-mapping fail-closed test against a live sandbox** — attempt to post a bill for an
   (entity, project, item, vendor) combination with **no** `proofrail_class_mapping` row and
   confirm PR-043 halts before any QBO call is made (unit-tested already; needs one live-sandbox
   run too).
6. **The parity test** (already written, `test/proofrail.swarmsync-parity.test.ts` pattern extended
   to QBO): post the **same** test bill through both `scripts/qbo_create_sandbox_bill.py
   --execute-sandbox` and the MCP `approve` tool, and confirm **both** produce a real QBO bill with
   matching `DocNumber`/`Amount`/`Location`/`Class`/`Customer`/`Item` — this is the concrete proof
   that the MCP path matches the known-good Python path before any live operation switches over, as
   required.
7. **No production realm reachable** — confirm `QBO_BASE_URL`/`QBO_REALM_A`/`QBO_REALM_B` cannot
   resolve to anything outside the two sandbox companies (same guarantee `qbo_common.py` already
   gives the Python path).

Only after all seven pass, and only with Ben's explicit go-ahead, should `container.ts` be changed
to use `RealQboClient`. Until then, `FakeQboClient` stays wired, and any `approve`/`send_draw`/
`approve_fees` call through the MCP app should be treated as a no-op for real accounting purposes —
route real invoice/draw approvals through `scripts/*.py` as today.
