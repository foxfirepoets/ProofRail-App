# BRUTAL_TRUTH_AUDIT — 2026-07-05 (build day). No credit for intentions; only for evidence.

## What is PROVEN (live evidence, today)

Seeding executed against both sandboxes: 475+ creates, acceptance counts PASS both realms
(A 139/18/5/69/53/64 · B 109+1/17/1/3), cross-realm bleed NONE. A coded vendor bill (Id 145)
and the 5% dev-fee pair (A Bill 146 == B Invoice 145 == $15,307.03) posted and tie. Duplicate
bill refused. Historical doc hard-stopped. Location/Class tracking prefs enabled via API after
being caught OFF. Secrets scan of every created file: clean.

## What is UNDER-SPECIFIED (real gaps, not cosmetic)

1. **Commission structure** — three conflicting signals (COA reserves Watson 2%/Christensen 1%;
   worksheet pays Zach 3%; user prompt says "Mike/Porter"). Correctly gated to owner, but the
   gate has no deadline — it will silently stay unresolved unless Ben rules.
2. **OAEA fee bases** — ~10 entities have no verified fee clause. The engine refuses them
   (good), but that means dev-fee coverage is partial until the registry work happens.
3. **Auto-send whitelist** — defined as "empty until Ben adds names in writing"; the adding
   process (where, what format) is one sentence, not a procedure.
4. **Gmail/Drive side** — specs and prompts exist; ZERO live runs. Label creation, connector
   auth, Drive tree creation are all still manual firsts for tomorrow.
5. **Extraction accuracy** — the draw six-checks are specified, but no current-format draw PDF
   has been parsed in this build. Confidence scoring is a spec clause, not tested code.

## What can FAIL (ranked by likelihood × damage)

| Risk | Reality check |
|---|---|
| QBO silently drops data when a preference is off | HAPPENED TODAY (DepartmentRef). Fixed + now checked, but assume other prefs (e.g., "warn when unassigned", Projects toggle) still bite — they're not API-readable/settable and remain manual UI checks |
| CSV design errors | HAPPENED TODAY (dup AcctNum 30134; accum-dep subtype; desc >100 chars). All caught by verification — the pattern "QBO validates late, verify everything" is proven necessary |
| Refresh-token rot | Intuit rotates on every refresh; tooling persists rotations, but if Ben re-auths in another tool, .env tokens die silently → PR-011 halt. Detection: token_refresh_failed in log + morning brief |
| Sandbox reset/expiry | Intuit reclaims idle sandboxes; realm IDs then dangle. Mitigation: re-seed is cheap and idempotent (proven), but nobody is watching for it — add to Morning Brief? deferred |
| Co-work session drift | Prompts are law on paper; a session that skips append_audit_log leaves no trace of the skip. The JSONL can prove what happened, not what didn't. Mitigation: heartbeat + retro comparisons — partially specified |
| InvoiceProof outage | Fail-closed implemented and tested locally (FLAG on unreachable). Cost: intake slows to human speed — acceptable |
| BS-by-Location expectation gap | QBO renders columns only for locations WITH data — the runbook's "one column per entity, all zeros" birth certificate is structurally impossible on an empty realm via API. Documented; verify script checks render+columns-as-data-posts instead |

## QBO sandbox risks: sample data pollution (88/37 extra accounts etc.) — verification matches
by name so counts are honest, but reports will show sample noise under "Not Specified" until
someone inactivates the sample records in the UI (deliberately NOT automated — no deletes).

## Co-work risks: the operator model assumes Ben actually pastes the prompts. No prompt = no
run = silent gap. The heartbeat rule (Morning Brief must scream about silent intake) is the
only backstop, and it lives in a prompt too. This is the architecture's honest weak point —
acceptable for a test, not for production.

## Gmail/Drive risks: connector scopes must be read+compose+labels only (never delete) — not
yet verified against the actual connector config. Drive tree does not exist yet.

## Accounting risks: capitalize-vs-expense, fee recognition timing, commission treatment are
all CPA judgment — correctly fenced as options-not-decisions everywhere. Detail-type
translations (and today's OtherFixedAssets fallback on Accumulated Depreciation, and EJH-TBD
renumbered to 30144) need Ricks' blessing — flagged in manual checks.

## Security: secrets clean in files; logs redact + mask (verified live: ****0054). Residual:
.env sits in plaintext on this desktop; .qbo_tokens.json likewise. Standard for a test rig;
unacceptable for production (vault later). No git repo here, so no commit-leak vector today.

## Must NOT be automated yet: payments (never) · commission accruals (unresolved) ·
auto-send (empty whitelist) · production writes (no path exists) · opening balances (obgen F5
owns it) · sample-data cleanup (manual UI decision) · bank-detail changes (out-of-band forever).

## VERDICT: **GREEN for tomorrow's sandbox test operation** — the QBO layer is proven with
live postings and honest verification. **YELLOW overall** until (a) one real Gmail/Drive
Inbox Run completes end-to-end, (b) SwarmSync key lands and one live scan runs, (c) Ben rules
on commissions. Nothing RED: every unproven path is gated, logged, or refused by construction.
