# Merged in from `foxfirepoets/Summa-Terra-QB-Automation` — 2026-07-22

This subfolder is the full content of the (now-deprecated) `Summa Terra QB Automation` repo,
merged in so there is one universal-truth repo instead of two. 792 files, byte-for-byte copies
(git-tracked files via `git ls-files`, plus untracked-but-not-gitignored files via
`git status --untracked-files=all`) — nothing was cherry-picked or rewritten.

**Why this repo was chosen as the merge target, not the other way around:** this repo
(`ProofRail-App` / `Co-Work QB Summa Terra`) is where the real, live, proven pipeline lives —
the QuickBooks Desktop posting engine (`../scripts/qbe_*.py`), the deployed MCP servers
(`../src/api/mcp-server.ts`, `../gmail-mcp-server/`), and the canonical STV memory
(`../MEMORY.md`, moved here the same day). `Summa Terra QB Automation` was comparatively a
specs/planning repo, including a separate future-app build (`ai-accounting-hub-ralph/`, `summa-
terra-binding-ralph/`) that its own CLAUDE.md explicitly called "not yet live." The living thing
became the trunk.

**What's in here** (original top-level structure preserved as-is):
- `01_Specs_and_Briefings/` through `06_Legal_Hunters_Union_Costs/` — specs, data, deliverables,
  catch-up work, QB build spec, legal/cost documentation (incl. Hunter's Landing draw history PDFs)
- `SPEC.md`, `SPEC_SUMMA_TERRA_BINDING.md`, `ArchitectureGovernor.md`, `FinalSpec.md`,
  `ARCHITECTURE_DECISION.md` and other root-level spec/architecture docs
- `ai-accounting-hub-ralph/` — the separate future-app ralph-loop build workspace (Next.js/NestJS/
  Prisma/Supabase target architecture, per its own docs not yet live)
- `summa-terra-binding-ralph/` — a smaller related ralph workspace
- `docs/`, `Dashboard/`, `memory/`, `.agents/`, `.claude/` — supporting content from the original repo
- `MEMORY_ARCHIVED_2026-07-22.md` — the STV memory file's full history prior to its move (the live
  version is now `../MEMORY.md` at this repo's root)
- Assorted `_tmp_*` scratch files from the original repo, preserved as-is

**Excluded on purpose** (gitignored in the source repo, never copied): `.env`/`.env.*` (except
`.env.example`), `credentials.json`, `*.key`/`*.pem`, `node_modules/`, Python venvs
(`.venv/`, `.venv-311/`), `__pycache__/`, build caches. None of that is source — regenerate it
locally per the original repo's own setup docs if this workspace is ever actually run.

**The original repo is not deleted** — `foxfirepoets/Summa-Terra-QB-Automation` still exists on
GitHub, now marked deprecated at its own repo root, pointing back here.
