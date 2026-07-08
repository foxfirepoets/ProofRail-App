# GO_NO_GO — decision gates for what graduates when

## QBO sandbox is READY when (status: **READY as of 2026-07-05**)
All acceptance counts pass in both realms · BS by Location renders · a coded bill and the
dev-fee pair post and tie · duplicate/dimension guards refuse correctly · audit log captures
every write. (All verified on build day — see QBO_SANDBOX_TEST_PLAN.md.)

## Co-work-only is ENOUGH while
volumes stay ≤ ~50 invoices + ~10 draws/week · Ben approves everything · workflows are
Gmail/Drive/packet-shaped · state fits in folders + JSONL. Signals it's NOT enough: missed
hourly runs matter, multi-day state gets lost between sessions, Ben spends >30 min/day pasting.

## Helper scripts are REQUIRED for (already true)
anything touching QBO (only scripts write) · anything needing determinism (fee math, dedup,
counts) · anything needing an unforgeable log. Co-work never free-hands a QBO write — ever.

## A small dashboard becomes JUSTIFIED when
the approval queue exceeds what an email/chat brief can carry (~20+ items/day) · Ben wants
queue state without opening Co-work · exceptions age past a week because nobody sees them ·
month two, if bridge metrics (spec P0) show sustained volume. Until then: Cowork IS the UI.

## Live production QBO can be CONSIDERED only when ALL of
30 consecutive days of clean sandbox operation (proof pass rate ≥95%, zero realm-mix, zero
unlogged writes) · CPA (Ricks & Co) sign-off on COA + dimensional design · commission structure
resolved in writing · opening balances migrated via obgen F5 with G5 tie-out to the penny +
proof · owner go in writing · production OAuth set up with fully disjoint credentials · 30-day
100%-human-approval period after cutover. **Nothing in this test build may be pointed at
production — the tooling physically refuses.**

## Rightworks / QB Enterprise return to scope when
legacy-file extraction starts (obgen EXTRACT runs inside the Rightworks-hosted desktop via
QODBC against the open .qbw) — that is bridge/migration work (spec F5/P0), owned by `qb-master`
tooling, NOT this QBO test build. Until then: out of scope, and any Desktop/Enterprise/Web
Connector requirement appearing in this build is a scope error to reject.
