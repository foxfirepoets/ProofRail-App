# CLAUDE.md — ProofRail (read before writing any code)

## What this is
Adaptive-clone construction-finance app for STV on QBO, plus the moat Adaptive lacks:
SwarmSync Invoice-Proof / Verify-API / Audit-Proof at every material action.
Cowork = cognition (email, parsing, approvals-by-chat). This app = physics
(state machines, proofs, QBO writes, nightly gates). MCP = the seam.

## Source of truth — TWO TRACKS, do not conflate them
1. **What Cowork actually operates today (live, real, binding):** `docs/OWNER_UPDATES_2026-07-06.md`
   (overrides everything below it) + `docs/*_SPEC.md` + `scripts/*.py` + `cowork_prompts/*.md` +
   `COWORK_START_HERE.md`. This is the local-scripts pipeline: real SwarmSync InvoiceProof calls
   (`scripts/build_invoiceproof_packet.py --send`), real QBO sandbox writes (`scripts/qbo_*.py`),
   real audit logs (`logs/*.jsonl`). Follow this track for any change to what Cowork does hour-to-hour.
2. **Target architecture for the future app (not yet live):** SPEC_proofrail_v2_0_CONSOLIDATED.md
   (merges v1.0-v1.3; anything below v4/v2.0 is history — see CARTOGRAPHY supersession ledger) +
   this file + `prisma/schema.prisma` + `mcp/tool-contracts.ts`. This describes the Next.js/NestJS/MCP
   app scaffolded in `src/` and deployed to Render. As of 2026-07-08 its QboClient, ProofClient (for
   VerifyAPI/AuditProof), and repository are still fake/local stubs (`src/proofrail/container.ts`) —
   InvoiceProof was reintegrated to call the real SwarmSync API (`SwarmSyncProofClient`), but QBO
   writes and persistence are not real yet. Do not treat a tool call succeeding through this app's
   MCP connector as proof that anything reached real QBO — check `container.ts` for what's actually
   wired before trusting it.

**Which track wins on conflict:** track 1 is authoritative for present-day operator behavior. Track 2
is authoritative for what the future app should eventually do. If they disagree about *how something
works right now*, track 1 is correct.

## Stack (copy SwarmSync patterns exactly — see swarmsync-ai skill)
Next.js 14 (Netlify) · NestJS ESM w/ .js import suffixes (Render) · Prisma 6 legacy mode +
Supabase Postgres (NEW isolated project) · Trigger.dev v4 tasks · MCP module per SwarmSync
mcp/ + mcp-builder skill. No Stripe. No RBAC (solo operator v1).

## In this bundle
(Paths below are relative to this repo root — corrected 2026-07-08 after architecture-cartographer
found the original paths assumed a different folder layout, per-package `proofrail/`, that no
longer matches how this repo is actually laid out. `proofrail/prisma/` and `proofrail/mcp/` were
byte-identical duplicates of the root copies below and have been archived to `archive/proofrail/`.)
- `schema.prisma` (repo root) — v2, C2 deltas applied, prisma@6 validate clean. Enums ARE the
  state machines; EntityRegistry carries the law; GcCodeMap + MemberVendor included. This is the
  copy `package.json`'s `prisma:validate` script actually uses — treat it as canonical.
- `tool-contracts.ts` (repo root) — strict-TS-clean. 11 tools; the frozen design reference for
  what Cowork gets. (The actual deployed MCP server defines these tools inline via zod in
  `src/api/mcp-server.ts` — this file is documentation, not imported code.)
- `cowork-skills/` (repo root subdirectory, not a sibling) — 4 domain skills: operator /
  coding-rules / drawsheets / oaea-registry. Cowork also installs 4 instrument skills: gmail,
  pdf-mastery, google-workspace, google-sheets-mastermind (domain decides, instruments execute).
- `COA_*_v4.iif` — QBO dimensional design (17 partnership classes, 15 STV CM parent). Confirm
  current location before relying on this path; not verified in the 2026-07-08 cartographer pass.
- `obgen/` (repo root subdirectory) — seeding CLI (re-target emit to QBO API; import shared gates
  pkg). Also the verified reuse source for the QBB→QBO migration pipeline (see
  `docs/SPEC_QBB_TO_QBO_MIGRATION.md`).

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

## Cowork operator notes (learned this session — don't re-derive)
- Gmail attachment downloads: the connected Gmail MCP has no `download_attachment`/`get_attachment`
  tool, and Cowork's "Add custom connector" only accepts a *remote* MCP server URL — it cannot spawn
  a local stdio server, so a self-hosted Gmail MCP (e.g. j3k0/mcp-google-workspace) CANNOT be wired
  into Cowork. Don't attempt that again. Instead: use Claude-in-Chrome, open the Gmail message, click
  the attachment's "Add to Drive" button, then pull the file from Drive via the Drive connector
  (search_files / download_file_content). This is the standing method for saving invoice/draw PDFs
  out of Gmail into the `01_Email_Attachments` pipeline folder.
- A `gmail-mcp-server/` folder exists in this repo from the abandoned local-MCP attempt (built,
  authenticated as stone@summaterraventures.com, but unusable by Cowork). Harmless to leave; not on
  the critical path.

## Communication rules (Ben, 2026-07-08)
- ALL emails Claude sends on Ben's behalf: CC Mike@summaterraventures.com, every time, no exceptions.
- Any higher-level item the president should know about (material exceptions, fee/commission
  decisions, gate RED status, anything Ben would escalate): ALSO CC porter@summaterraventures.com.

## Test-first targets (write these before implementation)
- state-machine transition table (every illegal transition → 409)
- money_lock middleware (RED ⇒ 423 on exactly the money routes)
- registry-sourced fees: no row -> refused (all 4 streams); 12SB land-inclusive base -> refused
- submit_intake idempotency (same gmail_msg_id ×3 ⇒ 1 intake)
- fee pair atomicity (mock realm-A failure ⇒ realm-B void ⇒ FAILED)
