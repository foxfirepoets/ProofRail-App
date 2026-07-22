---
name: fee-split-correction-2026-07-09
description: Correct 3-way internal split of the 5% STV developer/CM fee (Zach 2% / Mike Watson 2% / Porter 1%) — supersedes older 2-way split language
metadata:
  type: project
---

The 5% developer/CM fee assessed on STV project draws is split internally three ways, not two:
Zach Coverston 2%, Mike Watson 2%, Porter Christensen 1% (sums to the full 5% — no residual
held back for STVE on this split).

**Why:** the "Development Fee Tracking Worksheet" (Google Sheet id
`1qxg79-N6UgTPSng3ZofCS5-WhjL5cPBAr9q7NmeyJtQ`) only tracks two named columns — "Zach's Cut
(2%)" and "Porter's Cut (1%)" — leaving 2% unaccounted in that sheet. The
`proofrail-coding-rules` skill (v2) separately described the split as "CEO 2% (Watson) /
Pres 1% (Christensen)," a different 2-person breakdown. Ben confirmed on 2026-07-09 the real
split is three people: Zach Coverston 2%, Mike Watson 2%, Porter Christensen 1%. Both prior
sources were each partially right and partially stale/incomplete.

**How to apply:** when reconciling or documenting the STV CM developer fee split (in
entities.yaml comments, ProofRail fee-engine logic, or the proofrail-coding-rules skill),
use this 3-way Zach/Watson/Christensen (2%/2%/1%) breakdown as current truth. Flag to Ben if
the Development Fee Tracking Worksheet itself doesn't have a column for Mike Watson's 2% —
that sheet may need a column added, or Watson's cut may be tracked elsewhere untraced yet.
This split is a parent-side bonus allocation *out of* the 5% fee — not a separate project
cost stream and not itself gated by [[stv-oaea-registry]] rows.
