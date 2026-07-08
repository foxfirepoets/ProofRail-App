# IMPLEMENTATION_ROADMAP — 30-day test plan (day 0 = 2026-07-05, the build day)

## Week 1 — Foundation (much already done on day 0)
- [x] QBO Advanced sandbox setup: both realms seeded via API (day 0)
- [x] Seed verification: acceptance counts PASS both realms (day 0)
- [x] Tracking prefs (Location/Class) enabled via API (day 0)
- [x] Audit log: JSONL layer live, secrets-redacting, bank-masking (day 0)
- [ ] Ben: put `ssk_live_` SwarmSync key in `.env`; UI spot-checks (docs/QBO_ADVANCED_SETUP_SPEC.md §5)
- [ ] Gmail: create the 16 `ProofRail/*` labels; connect Gmail connector in Co-work
- [ ] Drive: create the 16-folder tree at `GOOGLE_DRIVE_SYNC_ROOT`
- [ ] First Morning Brief + first Inbox Run (draft-only) with `00_MASTER_OPERATOR_PROMPT.md`
- Gate: one real email classified, filed, logged end-to-end

## Week 2 — Intake pipeline
- [ ] Invoice intake at volume: every inbound invoice → extraction → InvoiceProof packet (local + `--send` once key present)
- [ ] Vendor bill workflow: 5–10 real invoices through packet → approval → sandbox bill
- [ ] Draw package workflow: one historical draw (fixture, Do-Not-Post) + one current-format dry run through the six checks
- [ ] Measure: invoices/wk, draws/wk, classification accuracy vs Ben's corrections
- Gate: ≥95% classification on the week's mail; zero unlogged actions

## Week 3 — Money math
- [ ] QBO sandbox handoff at volume (approval sessions with real approved items)
- [ ] Developer fee test per entity with verified OAEA bases (skip unverified — they must refuse)
- [ ] Bank/CC review: one month of real CSV through matching → packet
- [x] Commission decision — RESOLVED 2026-07-06: Mike Watson 2%, Zach Coverston 2%, Porter Christensen 1% (parent realm only); Coverston accounts 21300/60400 added. Booking still per-run owner-approved.
- Gate: dev-fee pairs tie penny-exact for every verified entity; IC mirrors net 0.00

## Week 4 — Close + hardening
- [ ] Month-end close rehearsal in sandbox (full MONTH_END_CLOSE_SPEC cycle)
- [ ] Weekly retro ×2 done; playbook edits adopted (Ben-confirmed only)
- [ ] Hardening: PR-020 drill, token-rotation check, log review, permission audit
- [ ] GO_NO_GO review (docs/GO_NO_GO.md) — decide what graduates
- Gate: close packet produced; Brutal-Truth re-audit ≥ YELLOW→GREEN on open items
