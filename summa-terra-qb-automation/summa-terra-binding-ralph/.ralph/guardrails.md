# Guardrails — Known Risks and Scope Exclusions

ralph: before taking any action, scan this file. If your action matches a SIGN, stop and report.

## Pre-Loaded Risks (from the binding spec §7/§9/§14 + project CLAUDE.md)

### SIGN: commission/income/due-from account loaded into a partnership file
The split is enforced at file level (the CSVs are already split into `*_Partnership.csv` / `*_Parent.csv`).
`parent_only` accounts (`12200, 21100, 21200, 40200, 40300, 40400, 60200, 60300, 70100, 70200`) and parent
`fee_role` cost codes (`dev_inc_5_parent, ceo_2_parent, pres_1_parent`) and `EXEC —` vendors must NEVER land in
a `role='partnership'` company. `FEE-DEV` / `dev_5_partnership` IS allowed in the partnership.
Mitigation: CHUNK_5 split-at-file-level assertion must fail loudly; loaders reject by role.

### SIGN: companies.role given a blanket DEFAULT
`ADD COLUMN role ... DEFAULT 'partnership'` silently mis-tags the existing parent row → loader then rejects the
parent's own accounts. Mitigation: add nullable, backfill explicitly, then `SET NOT NULL` (binding spec §13).

### SIGN: cost code with no resolvable account ("orphan")
Items reference accounts by NAME ("CIP - Hard Costs"); every one must resolve to a loaded `accounts.number`.
Mitigation: fail the load naming the unresolved item; 0 orphans is an acceptance criterion.

### SIGN: draw cost code mapped outside the CIP buckets
Every `kind='draw'` cost code maps to `15200` or `15300` only (verified: 0 draw codes use 15100/15400).
Mitigation: bucket invariant enforced at load and re-checked in CHUNK_5.

### SIGN: non-idempotent load
A second bootstrap run must report 0 inserts/0 updates. Mitigation: UPSERT on the UNIQUE keys; diff-count test.

### SIGN: reshaping the QB CSVs
The CSVs are QB-upload-ready and are the source of truth. The loader MIRRORS them 1:1 — never renames columns,
re-buckets accounts, or "improves" the lists. `068 Construction Profit` is a GC cost line, NOT the developer fee.

### SIGN: writing to the wrong Supabase project
Canonical store = Supabase `fdnwlcomuddzmluvbylg` via `DATABASE_URL`. Use the `supabase-aihub` MCP only —
NEVER the `supabase` MCP (that is SwarmSync's prod). Never run DDL against any other project.

## Scope Exclusions — Do Not Build

- DO NOT BUILD the Draw-Package fee engine here (binding spec §5.3) — this scaffold is migration + catalog
  loader ONLY. The fee engine is a later, separate build.
- DO NOT BUILD any QBWC write-back, qbXML mapping, or QB-side automation in this scaffold.
- DO NOT modify the QB Summa Terra source files or the prior build's 8 chunks (extend, reuse — never rewrite).
- DO NOT add an inbound listener to any Rightworks box. (Project hard rule.)

## Standing Guardrails (always active)

- DO NOT add pip dependencies without updating TARGET_REPO/requirements.txt + this file. (None expected — stdlib
  `csv` + existing SQLAlchemy cover the loader.)
- DO NOT skip the validation gate (`ruff check . && mypy app && pytest -q` in TARGET_REPO), even for trivial changes.
- DO NOT commit with --no-verify. DO NOT `git add -A` — stage only files the task changed.
- DO NOT generate code for a future chunk's domain. DO NOT modify files outside the current task's scope.
- DO NOT hard-code secrets; never log raw bank fields or proof secrets; store bank fingerprints, not raw details.
- DO NOT write application code into this binding workspace — all code goes into TARGET_REPO.

## Accumulation Instructions

When ralph encounters a new failure pattern, append below.

### Learned: (none yet)

### Learned: size VARCHAR columns to the real data, not the spec's guess
cost_codes.code must fit 'RETAINAGE-HELD'(14)/'FEE-DEV-INC'(11) -> VARCHAR(20); fee_role must fit
'dev_5_partnership'(17) -> VARCHAR(24); cost_codes.name is the QB item Description (~74) -> VARCHAR(128).
Measure max field lengths from the CSV fixtures before sizing. (CHUNK_3 backpressure.)
