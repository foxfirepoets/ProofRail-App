# archive/ — do not touch, history only

Everything under this folder was moved here on 2026-07-08 after an architecture-cartographer
sweep confirmed zero live references from either the real operating pipeline (`scripts/*.py`,
`docs/*_SPEC.md`) or the scaffolded app (`src/`). Nothing here is deleted — just out of the way.

| Item | Why archived |
|---|---|
| `proofrail/prisma/schema.prisma`, `proofrail/mcp/tool-contracts.ts`, `proofrail/CLAUDE.md` | Byte-identical duplicates of the root `schema.prisma`/`tool-contracts.ts`; root copies are canonical (`package.json`'s `prisma:validate` uses them). `proofrail/CLAUDE.md`'s content is now in root `CLAUDE.md`. |
| `qbo_setup_pack/` | Byte-identical duplicate of `qbo Source Files/`, which is the one every `scripts/qbo_seed_*.py` actually reads. |
| `gmail-mcp-server/` | Abandoned local-MCP attempt — documented in root `CLAUDE.md` as unusable by Cowork (Cowork's "Add custom connector" can't spawn a local stdio server). Contains real OAuth credential files (`.gauth.json`, `.oauth2.*.json`) — still gitignored at this new path, do not remove that `.gitignore` coverage. |
| `SPEC_proofrail_v1_3_amendment.md`, `CARTOGRAPHY_proofrail_2026-07-04.md`, `sag-coverage-proofrail-2026-07-04.md` | Superseded drafts — `SPEC_proofrail_v2_0_CONSOLIDATED.md` explicitly states it merges and supersedes v1.0-v1.3. |
| `docs/GO_NO_GO.md`, `docs/BRUTAL_TRUTH_AUDIT.md`, `docs/HKO_AUDIT.md` | Point-in-time audit snapshots with zero inbound references from any live doc or script. |

Source: architecture-cartographer report, 2026-07-08 (see conversation history / `.claude/cbv/` if retained).
