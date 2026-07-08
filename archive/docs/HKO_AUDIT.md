# HKO_AUDIT — hidden risks, killer objections, operational failure points (2026-07-05)

## Hidden risks (things nobody asked about)

1. **The .env had duplicate `QB_NAME`/`QB_ID` keys** — the parser takes last-wins and the
   realm scripts key off the unambiguous `QB_PARENT_/QB_PROJECT_` names, so it's inert — but a
   future tool parsing .env naively could grab the wrong realm. Recommend deleting the
   ambiguous duplicate keys.
2. **Deterministic RequestId reuse after content change**: retrying the "same" create after
   editing its payload reuses the RequestId within Intuit's dedup window — QBO may return the
   ORIGINAL result and silently ignore the edit. Mitigated in fix-scripts by suffixing the key
   (`|fixgap`, `|nosub`); operators editing amounts must change the DocNumber. Documented here
   because it WILL bite someone eventually.
3. **`ClassRef` persisted even while class tracking was OFF** (observed today) — meaning QBO
   accepts and stores dimension data it isn't enforcing. Verification must therefore always
   read back what posted (we do) rather than trust the write succeeded semantically.
4. **Sample-data name collisions are silent skips** — 'Insurance' matched sample data and
   would have shipped with the wrong number if verification hadn't compared AcctNum. Any future
   CSV row whose name collides with sample data inherits the sample record. The verify script's
   AcctNum check is the only tripwire; it doesn't compare Type/SubType — LOW risk, noted.
5. **Windows console mangles UTF-8** (— became ?) — cosmetic, but JSONL uses ensure_ascii=false;
   logs are fine (verified), console output only.

## Killer objections, answered or conceded

- *"An LLM is your operator — it will eventually not follow a prompt."* Conceded. Defense in
  depth: everything irreversible sits behind scripts that themselves enforce the rules
  (sandbox guard, execute flag, PR-043 refusal, dedup, no payment surface). The prompts are the
  cognition; the scripts are the physics. A disobedient session can waste time; it cannot move
  money, touch production, or post unlogged.
- *"You seeded from CSVs that contained errors."* True — and the system caught all three
  (dup number, invalid subtype, name collision) via API validation + count verification, fixed
  them with documented deviations, and flagged owner review. That's the designed behavior.
- *"The two realms could still be economically mixed by a bad coding decision."* The canary
  checks (commission accounts only in B, GC vendors only in A) catch structural bleed; a
  wrong-but-valid coding needs the human approval gate — which is why nothing posts without Ben.
- *"AuditProof isn't what the prompt assumed."* Correct — verified against the SwarmSync repo:
  no JSONL-append API exists; AuditProof rides `POST /api/verify` (`task:"audit_proof"`).
  The design therefore keeps local JSONL as truth and uses SwarmSync to SEAL events. The spec
  docs say exactly this; no imaginary endpoints were specified.

## Operational failure points

| Point | Failure | Backstop |
|---|---|---|
| Ben stops pasting prompts | pipeline silently idles | heartbeat rule in Morning Brief; weekly retro measures volumes — weakest link, accepted for test |
| Token rotation race (two tools sharing one refresh token) | PR-011 halt | .env is single-writer today; document "don't re-auth elsewhere" |
| Sandbox reclaimed by Intuit | 401s everywhere | re-seed proven cheap; company-name check makes it unmistakable |
| Partial dev-fee pair | A posted, B failed | atomic-or-nothing ordering + PR-020 compensating instruction (tested in code path, not force-tested live) |
| Approval recorded but command edited before run | posting ≠ approved packet | approval event captures the packet path; session prompt requires DRY RUN display before execute — human eyes gate |

## QBO API issues encountered (all resolved, all documented)

DepartmentRef silently dropped when TrackDepartments=false → Preferences API fix ·
top-level AccumulatedDepreciation subtype rejected (6000) → OtherFixedAssets fallback ·
Account.Description >100 chars rejected (2050) · DocNumber >21 chars rejected (2050) ·
duplicate AcctNum rejected as generic 2010 · Bill/Invoice updates need full object, not sparse ·
BS-by-Location renders columns only where data exists.

## Approval risks: FLAG-override requires a reason (enforced by prompt + logged); but nothing
technically stops Ben approving a FAIL — except the scripts won't be handed a command for FAIL
items (packets stop at quarantine). Residual: Ben hand-running a script for a quarantined item
— possible, logged, his prerogative as owner.

## Proof/audit risks: local JSONL is append-only by convention, not cryptographically —
tampering is possible on this box. SwarmSync sealing (chain hash + optional Ed25519) is the
answer and is specified but not yet live (needs the ssk_live_ key). Until then the audit trail
is honest but not tamper-EVIDENT. Acceptable for sandbox test; required before production.

## FINAL VERDICT: **GREEN for the sandbox test build** (scope: two sandboxes, no money, no
production, everything gated/logged; QBO layer live-proven today). **YELLOW on the same three
items as the Brutal Truth audit** (first live Inbox Run, live SwarmSync scan, commission
ruling) — none of which block starting tomorrow.
