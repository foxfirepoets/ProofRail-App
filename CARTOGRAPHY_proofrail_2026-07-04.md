# Architecture Cartographer Report — ProofRail (pre-code artifact estate)

**Audited:** 2026-07-04 · **Auditor:** architecture-cartographer v1.1.2 · **Scope note:** no application code exists yet; the "repository" is the design-artifact estate in `/mnt/user-data/outputs` + 2 project files + 4 Cowork skills + obgen CLI. All findings cite actual files (tree walked, greps run). Findings about future runtime are marked DESIGN.

## Executive Summary

ProofRail is a proof-backed Adaptive-clone (AP intake → proof gate → QBO sync, nightly audits, draws, four STV CM fee streams) with Cowork as cognition and a Netlify/Render/Supabase/Trigger.dev app as physics. **Most important finding:** the estate carries three generations of superseded truth (v2/v3 IIFs, pre-STV-CM fee language, VPS-era runtime text in 5 docs) that will poison an implementer who reads the wrong file. **Top recommendation:** hand off ONLY the consolidated SPEC v2.0 + the current-truth manifest below; superseded files stay as history, never as instruction.

## Project Map

|Component|Path|Status|Purpose|
|-|-|-|-|
|Consolidated spec (NEW)|`SPEC\_proofrail\_v2\_0\_CONSOLIDATED.md`|**CURRENT — the only doc Cowork reads**|full system, all amendments merged|
|Prisma schema|`proofrail/prisma/schema.prisma`|**CURRENT** (C2 deltas applied, `prisma@6 validate` ✓)|17 models, 10 enums — state machines as types|
|MCP contracts|`proofrail/mcp/tool-contracts.ts`|**CURRENT** (`tsc --strict` ✓)|11 tools, the Cowork↔ProofRail seam|
|Build brief|`proofrail/CLAUDE.md`|CURRENT (updated this pass)|invariants + build order for Claude Code|
|COA v4 (4 IIFs)|`\*\_v4.iif`|**CURRENT** (name-length CI ✓, 17+16 classes)|QBO seeding source for Location/Class/Item design|
|Cowork skills ×4|`cowork-skills/\*/SKILL.md`|**CURRENT** (frontmatter ✓)|operator / coding-rules / drawsheets / oaea-registry|
|obgen CLI|`obgen/run.py`, `config/`, `mappings/`|CURRENT w/ 1 refactor (below)|one-time seeding, gates G1–G7|
|ADP|`architecture-decision-packet-...md`|HISTORICAL — §3 runtime + §7.4 fee logic superseded|governance record|
|SPEC v1.0 + v1.1/1.2/1.3|4 files|HISTORICAL — merged into v2.0|amendment chain|

## Integration Forensics (DESIGN — verified against contracts/schema, not runtime)

|Integration|Where wired|Verdict|
|-|-|-|
|QBO v3 ×2 realms|`tool-contracts.ts` (approve→sync), spec F1–F5; RequestId idempotency in `schema.prisma:BillDraft.requestId @unique`|Keep|
|SwarmSync Verify/Invoice/Audit-Proof|`ProofStamp` type in contracts; `ProofRef` model; fail-closed PR-003|Keep|
|Gmail|Cowork-exclusive (v1.2 single-writer law); `EmailItem.gmailMsgId @unique`|Keep|
|Trigger.dev v4|8 tasks specced (v1.2 B2 + v1.3 C2 adds `monthly-accounting-fee`, `pm-fee-on-GOI`)|Keep|
|Stripe / RBAC / payments|grep: zero references by design|Keep-out (Non-Scope)|

## Deadweight / Supersession Ledger (grep-grounded)

|Item|Evidence|Verdict|
|-|-|-|
|`\*\_v2.iif`, `\*\_v3.iif` (8 files)|v3 still contains `IC - STV`/`IC - STDG`/`IC - Lykos` fee vendors (grep: 2 hits) — pre-STV-CM law|**Remove from handoff** (archive)|
|`README\_v2/\_v3\_Build\_Notes.md`|describe v2/v3 fee matrix|Remove from handoff|
|VPS language|grep "VPS" hits in ADP, SPEC v1.0, v1.1, `SPEC\_obgen\_...v1.md`, `obgen/run.py` docstring|Superseded by v1.2 §B1/B5; v2.0 spec states runtime once, correctly|
|`obgen/run.py` "VPS" + gates duplication|ADP §12 flagged: nightly GateRunner must import shared `gates.py`, not re-implement|**Refactor** → task P2-3 in spec|
|`SPEC\_obgen\_and\_architecture\_v1.md`|IIF emit path superseded by QBO-API emit (v1.2 B5)|Historical; G1–G7 + mapping-CSV doctrine carried into v2.0 §7|
|Old zips (`obgen\_skeleton.zip`, `claude\_code\_bundle.zip`, skills v2/v3 zips)|pre-delta contents|Remove from handoff; `proofrail\_handoff\_v2.zip` replaces all|

## Risk Register (top 5, carried + new)

1. **Stale-artifact poisoning** — implementer reads v3 IIF or v1.0 fee matrix → posts fees to wrong payee. Mitigation: manifest above + v2.0 spec §0 "reading order".
2. G9 cutover slip — unchanged; sandbox-first build (spec P1).
3. OAEA drift — fee law changed once in 2 days; mitigation now structural: `stv-oaea-registry` skill + `EntityRegistry.oaeaEffective`.
4. Unverified fee clauses ×12 entities — rows stay unborn (engine refuses) until skill-run; spec P1 task.
5. Member-vendor double-pay — `MemberVendor` model + drawsheets check #6; needs Exhibit-A ingestion (spec P3).

## Recommended Target Architecture

**Keep:** Cowork=cognition / ProofRail=physics / MCP=seam (v1.2 §B1 — verified consistent across contracts, schema, skills). **Consolidate:** 5 spec documents → `SPEC\_proofrail\_v2\_0\_CONSOLIDATED.md` (done). **Refactor:** extract `obgen` gates → shared package consumed by Trigger.dev `nightly-gates`. **Remove:** nothing deleted; superseded files excluded from handoff bundle. **Add tests for:** the 6 P0 test-first targets in `proofrail/CLAUDE.md` (state table, money\_lock 423, registry-sourced fees, idempotency ×2, pair atomicity).

## Coder Task Plan

→ Externalized as SPEC v2.0 §10 (phases P1–P6 with per-phase validation commands and binary acceptance) — single source, not duplicated here.

## Validation Checklist

* \[x] Structure mapped from actual tree (find run, 35 files)
* \[x] Schema models cited (`proofrail/prisma/schema.prisma`, validated)
* \[x] Contracts cited (`proofrail/mcp/tool-contracts.ts`, strict-clean)
* \[x] Supersessions grep-grounded ("VPS", IC-vendor greps shown)
* \[x] Dead/stale identified with evidence; zero unverified Removes
* \[x] Risk register with citations
* \[x] Coder plan exists (spec §10)
* \[BLOCKED: no runtime] routes/env/CI checks — nothing deployed yet; all runtime items are DESIGN

## Open Questions → carried into SPEC v2.0 §12 (six verifications, none blocking)

