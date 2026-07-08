> **ARCHIVED 2026-07-08.** This was `proofrail/CLAUDE.md`. Its content is now superseded by the
> root `CLAUDE.md` (which has the corrected "In this bundle" paths and the "Source of truth — TWO
> TRACKS" section). Kept here for history only — do not edit or treat as live instruction.

# CLAUDE.md — ProofRail (read before writing any code)

## What this is
Adaptive-clone construction-finance app for STV on QBO, plus the moat Adaptive lacks:
SwarmSync Invoice-Proof / Verify-API / Audit-Proof at every material action.
Cowork = cognition (email, parsing, approvals-by-chat). This app = physics
(state machines, proofs, QBO writes, nightly gates). MCP = the seam.

## Source of truth
This directory (`proofrail/`) describes the TARGET architecture for the future app — not what
Cowork operates today. For what's actually live and binding right now, read `../CLAUDE.md`'s
"Source of truth — TWO TRACKS" section first: today's real pipeline is `../docs/OWNER_UPDATES_2026-07-06.md`
+ `../docs/*_SPEC.md` + `../scripts/*.py`, not this directory.

Within the target-architecture track: SPEC_proofrail_v2_0_CONSOLIDATED.md — THE spec (merges
v1.0-v1.3). Anything below v4/v2.0 is history, not instruction (see CARTOGRAPHY supersession
ledger). As of 2026-07-08, the actual runtime code lives in `../src/` (not `proofrail/mcp/` —
that's the frozen tool-contract design doc, not the deployed server); `../src/proofrail/container.ts`
is the single place that shows what's real vs stubbed right now.

## Stack (copy SwarmSync patterns exactly — see swarmsync-ai skill)
Next.js 14 (Netlify) · NestJS ESM w/ .js import suffixes (Render) · Prisma 6 legacy mode +
Supabase Postgres (NEW isolated project) · Trigger.dev v4 tasks · MCP module per SwarmSync
mcp/ + mcp-builder skill. No Stripe. No RBAC (solo operator v1).

## In this bundle
- prisma/schema.prisma   — v2, C2 deltas applied, prisma@6 validate clean. Enums ARE the
  state machines; EntityRegistry carries the law; GcCodeMap + MemberVendor included.
- mcp/tool-contracts.ts  — strict-TS-clean. 11 tools; the only door Cowork gets.
- ../cowork-skills/      — 4 domain skills: operator / coding-rules / drawsheets /
  oaea-registry. Cowork also installs 4 instrument skills: gmail, pdf-mastery,
  google-workspace, google-sheets-mastermind (domain decides, instruments execute).
- ../COA_*_v4.iif        — QBO dimensional design (17 partnership classes, 15 STV CM parent).
- ../obgen/              — seeding CLI (re-target emit to QBO API; import shared gates pkg).

## Non-negotiables (each has an acceptance test — see spec DoD + A8/B6)
1. Fail closed: no proof ⇒ no completion. No bypass flag exists anywhere.
2. Money boundary: NEVER create BillPayment/transfer. Bills/Invoices/JEs only.
3. Fee law: 4 streams (DEV_CM 5% x entity feeBase / DRAW / ACCOUNTING / PM), all payee
   STV CM, LLC per 7-2-2026 OAEAs. NO EntityRegistry row (born only via stv-oaea-registry
   skill + migration) = NO fee, any stream. 12SB's base EXCLUDES land — test it.
4. RED gate ⇒ money_lock ⇒ 423 on send_draw/approve_fees middleware.
5. Idempotency: gmailMsgId + BillDraft.requestId unique — double-fire = one write.
6. State guards server-side on every MCP mutation (cognition can't outrun physics).
7. QUARANTINED approvals require override_reason; surfaced in nightly Audit-Proof bundle.
8. Gmail is Cowork's; QBO is this app's. Neither crosses.

## Build order (spec v1.2 §B7)
P1 provisioning → P2 API core + MCP module (the seam first) → P3 Cowork playbooks +
obgen seeding → P4 Trigger.dev gates/money_lock → P5 web UI + draws + F6 + fees → P6 cutover.
Web UI is LAST on purpose: Cowork is the UI until the pipeline earns a dashboard.

## Test-first targets (write these before implementation)
- state-machine transition table (every illegal transition → 409)
- money_lock middleware (RED ⇒ 423 on exactly the money routes)
- registry-sourced fees: no row -> refused (all 4 streams); 12SB land-inclusive base -> refused
- submit_intake idempotency (same gmail_msg_id ×3 ⇒ 1 intake)
- fee pair atomicity (mock realm-A failure ⇒ realm-B void ⇒ FAILED)
