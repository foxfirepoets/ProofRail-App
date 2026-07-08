# SAG Coverage Audit — ProofRail SPEC v2.1 vs the full build plan
`sag-coverage-proofrail-2026-07-04.md` · Governor: system-architecture-governor v1.2.0 (--update mode) · Method: adversarial integration sweep, every claim grep-verified against the artifact estate

## Verdict
```
╔══════════════════════════════════════════════════════════════╗
║  READY_FOR_BUILD — re-stamped 2026-07-04                      ║
║  9 gaps found · 7 patched (SPEC v2.2) · 2 resolved by Ben:    ║
║  G-1 HLE → parent class 16 · G-2 Ensign → class 18 (COA v5)  ║
╚══════════════════════════════════════════════════════════════╝
```
Coverage is strong: all 5 workflows, 4 fee streams, 11 MCP tools, 9 skills, gates, bridge ops, and 15 of 17 integrations trace cleanly spec→schema→contracts→skills. The sweep found what completeness audits exist to find — entities with no home and truths with two homes.

## Gap register (evidence → disposition)
| # | Gap | Evidence | Severity | Disposition |
|---|---|---|---|---|
| G-1 | **HLE has no home.** Skills say "HLE = corporate-side, not realm A," but grep of all v4 IIFs returns zero HLE — an entity that cannot be booked anywhere | `grep HLE *_v4.iif` → empty | **BLOCKING** | **RESOLVED:** parent class 16 HLE — Operating Cash 10103, Land Held for Sale 13900, Member Equity 30116 (COA v5) |
| G-2 | **Ensign has no home** — yet its OAEA was refreshed 7-2-2026 and Lazarus carries $924,890 in it. Sold entities still need K-1s and final-year books | `grep Ensign *_v4.iif` → empty; OAEA folder shows 7-2-26 Ensign | **BLOCKING** | **RESOLVED:** partnership class 18 Ensign (wind-down) — bank 10118, IC pair 12518/22518, Capital:Ensign-Lazarus 30148 + parent mirrors & Investment 14034 (COA v5) |
| G-3 | **Dual entity truth.** `obgen/config/entities.yaml` and Prisma `EntityRegistry` both describe entities; no SoT rule between them | run.py:22 loads yaml; spec §4 says rows born via oaea-registry | REAL | **Patched:** yaml = extraction-config only (legacy file names, cutover); EntityRegistry = the law; any overlap field (fee, capital) lives ONLY in registry |
| G-4 | **QBO "Location" ≠ API entity name.** The API object is `Department` (labeled Location in UI); an implementer following §9.1 verbatim would hunt a nonexistent endpoint | grep Department → 0 hits anywhere | REAL | **Patched** into §9.1 |
| G-5 | **No env-var manifest.** "Implement immediately" fails at hour one without the exact env contract | grep QBO_REALM/DATABASE_URL → 1 incidental hit | REAL | **Patched:** §9.2 manifest (14 vars, per service) |
| G-6 | **Bridge ledger-of-record never named.** July close runs against WHICH books? And cutover TB date is coupled to the last bridge-closed month | grep "ledger-of-record" → 0 | REAL | **Patched:** P0 states legacy QB Desktop files remain ledger-of-record until P6; cutover TB = last bridge-closed month-end (G9 made explicit) |
| G-7 | **obgen extract locus.** QODBC only runs inside the Rightworks-hosted desktop; v1.2's "runs from Ben's machine" is true for build/emit, false for extract | run.py qodbc() requires DSN on host | REAL | **Patched** into F5 |
| G-8 | Gmail OAuth scopes + SwarmSync key rotation dropped in consolidation (existed in v1.1/v1.0) | grep scopes → absent | MINOR | **Patched** into §7 |
| G-9 | QBO bank-feed connection (≈35 accounts) + Ricks accountant-seat access absent from cutover steps; lender-portal submission (Phoenix Tide) unverified | §9.1/P6 silent | MINOR | **Patched:** §9.1 steps 11–12; portal question → §12 |

## Also swept, found covered (no action)
QBO throttle/idempotency/webhooks · SwarmSync fail-closed + tiers · Trigger.dev roster incl. `monthly-accruals` · MCP auth+state guards+audit log · PM T-12 ingestion path · payroll (non-scope, funds-check only) · payments boundary (human-forever, both skill and server law) · litigation holds · member-vendor trap · dual draw numbering · 12SB fee-base exclusion · proof economics · Camden/Rock Creek Acq split.

## New open verification (added to §12)
12SB fee **retroactivity**: the 7-2-26 OAEA authorizes the 5% going forward — whether it reaches back to already-billed construction is a litigation-adjacent call for counsel + CPA, never an engine default (engine posts prospective-only until answered).
