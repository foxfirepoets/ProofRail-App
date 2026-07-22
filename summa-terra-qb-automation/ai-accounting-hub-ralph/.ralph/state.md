# Ralph State

Current chunk: — (all chunks complete)
Last completed: CHUNK_8_SCALE (Wave 6)
Status: BUILD_COMPLETE — 8/8 chunks; full suite 160 passed/6 skipped; live Supabase 165/1.

## Wave plan (dependency-ordered)
- Wave 0: CHUNK_1_INFRA — DONE (commit cb75f01); live migration APPLIED to Supabase
- Wave 1: CHUNK_2_TRANSPORT ‖ CHUNK_4_AUDIT — DONE (commit e5d9fac, parallel)
- Wave 2: CHUNK_3_CANONICAL — DONE (commit b2f617c); live DB resolved & verified
- Wave 3: CHUNK_5_WORKFLOW — NEXT (requires CHUNK_3 + CHUNK_4, both done)
- Wave 4: CHUNK_6_VERIFY (requires 2,4,5)
- Wave 5: CHUNK_7_PAYMENTS (atomic; requires 4,5,6)
- Wave 6: CHUNK_8_SCALE (requires 7)

## Live DB (RESOLVED 2026-06-26)
- Migration 20260626_1200 applied to Supabase fdnwlcomuddzmluvbylg via Management API (PAT).
- .env DATABASE_URL = verified session pooler aws-1-us-west-2.pooler.supabase.com:5432.
- Full suite: 80 passed / 0 skipped against the live DB.

## Owner-gated items
- None outstanding. (QBWC live-poll proof on a real Rightworks box remains a future open spike, not blocking the build.)

## Instructions for ralph
Update this file after every task. Never delete history — append below.
Ralph starts in PLANNING mode (PROMPT.md == PROMPT_plan.md). Build is being driven directly
by the truth-fix-loop orchestrator in dependency waves (see Wave plan above).
