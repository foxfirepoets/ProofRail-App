# QB Summa Terra — preserved authority docs (point-in-time snapshot)

These are **version-controlled copies** of the QuickBooks-side source-of-truth docs that
otherwise live OUTSIDE this repo at `C:\Users\Administrator\Desktop\QB Summa Terra\`. They were
edited in place during the fee-structure reconciliation; preserving them here stops the domain
authority from drifting or getting lost.

**Authority precedence is unchanged:** the live docs under `QB Summa Terra\` remain canonical;
this folder is the auditable snapshot. The AI-layer binding (`SPEC_SUMMA_TERRA_BINDING.md`)
consumes these — it never redesigns them.

## Snapshot contents

| File | Source |
|------|--------|
| `SPEC.md` | `QB Summa Terra/SPEC.md` (v2.2.0) |
| `Chart_of_Accounts.md` | `QB Summa Terra/Chart_of_Accounts.md` |
| `Cost_Codes_and_Items.md` | `QB Summa Terra/Cost_Codes_and_Items.md` |
| `Month_End_Checklist.md` | `QB Summa Terra/Month_End_Checklist.md` |
| `IMPORT_GUIDE.md` | `QB Summa Terra/Import_Files/IMPORT_GUIDE.md` (CSV/IIF import schema) |

Snapshot date: 2026-06-27. Integrity: `MANIFEST.sha256` (verify with `sha256sum -c MANIFEST.sha256`).

## Refreshing the snapshot

When the QB-side docs change, re-copy and regenerate the manifest so drift is detectable:

```bash
SRC="/c/Users/Administrator/Desktop/QB Summa Terra"
cp "$SRC"/{SPEC,Chart_of_Accounts,Cost_Codes_and_Items,Month_End_Checklist}.md docs/qb-summa-terra/
cp "$SRC/Import_Files/IMPORT_GUIDE.md" docs/qb-summa-terra/
( cd docs/qb-summa-terra && sha256sum *.md > MANIFEST.sha256 )
git add docs/qb-summa-terra && git commit -m "docs: refresh QB Summa Terra authority snapshot"
```

To detect drift without refreshing, diff the live docs against this snapshot; any mismatch means
the canonical authority moved and the binding/engine must be re-reconciled.
