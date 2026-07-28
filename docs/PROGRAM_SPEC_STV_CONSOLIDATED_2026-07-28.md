# STV Consolidated Program Spec — Three Tracks, One Umbrella

**Date:** 2026-07-28
**Owner going forward:** this repo (`Co-Work QB Summa Terra`, GitHub `foxfirepoets/ProofRail-App`, branch `main`). Per Ben's explicit instruction, execution of all three tracks below collapses into this repo — the CLAUDE.md language treating `Summa Terra QB Automation` and `Summa Terra Gmail Automation` as separate specs-only repos is superseded by this document for anything actionable; those repos become read-only archives except where Track 1 says otherwise.
**Method:** built per the `automation-spec-grandmaster` doctrine (bottleneck-first, tool-preference ladder, failure-path-before-happy-path, FOSS-over-paid, simplicity audit) — applied per-track below rather than as a separate pass, because most of the "build" here already exists; the job is inventory, correction, and sequencing, not greenfield design.

---

## 0. Executive Summary & Dependency Map

Three things have been running as separate efforts. They are now one program:

- **Track 1 — Project organization.** Get the scattered docs/specs/memory into one place with one owner, so Tracks 2 and 3 stop tripping over stale duplicates.
- **Track 2 — QB entries/reconciliation (the human/operator side).** The recurring bank-catch-up workflow just proven end-to-end this session (33-row STV catch-up sheet, 4 parallel research agents against Drive/Gmail). This is QuickBooks **Desktop Enterprise (QBE)** — the live books of record — not QBO.
- **Track 3 — ProofRail (the target automation).** The Gmail→QBO automation app in `src/`. This is QuickBooks **Online (QBO) Advanced**, sandbox-only, a different system from Track 2's QBE.

```
Track 1 (org hygiene)
   │  prerequisite: one place to look, one memory file, no duplicate specs
   ▼
Track 2 (QBE catch-up/reconciliation) ──── interim bridge ────▶ Track 3 (ProofRail/QBO automation)
   │  proves the workflow, the failure modes, the CPA-routing pattern,     │  eventually replaces Track 2's
   │  and the account-classification logic by hand + agents               │  manual/agent research loop with
   │                                                                       │  a repeatable pipeline once the
   │                                                                       │  QBE→QBO migration completes
   ▼                                                                       ▼
Both converge only after SPEC_QBW_TO_QBO_MIGRATION.md executes — until then they are
two real, separate ledgers (QBE = production books, QBO = sandbox) and must not be conflated.
```

**The single most important fact this spec corrects:** QBE (Track 2) and QBO (Track 3) are not the same system, not the same migration state, and not on the same timeline. QBE has a built, tested, cert-gated posting service (0 of 14 entities have certs granted — Ben-at-keyboard blocker). QBO/ProofRail has a live `RealQboClient` for Realm A only, with Realm B, VerifyAPI, and AuditProof still stubbed. Conflating "QB posting is real" across both systems is the exact mistake this spec exists to prevent.

---

## TRACK 1 — Project Organization / Consolidation

### A. Automation Name
STV Repo & Memory Consolidation

### B. Plain-English Summary
Right now, "where do I look for the answer" has three possible correct answers depending on which repo you're standing in. This track makes there be one answer: this repo. Old repos stay on disk as read-only history, not as competing sources of truth.

### C. Current Manual Workflow (as it stands today)
- `Co-Work QB Summa Terra` (this repo) — the code, the live MEMORY.md, most current specs, `docs/final_issue_resolution/` (today's catch-up work).
- `Summa Terra QB Automation` — a **separate, still-active** repo with its own `IMPLEMENTATION_PLAN.md`, `ArchitectureGovernor.md`, `FinalSpec.md`, `OPEN_DECISIONS_spec_audit_2026-06-30.md`, an `ai-accounting-hub-ralph/` build, and a redirect-stub `MEMORY.md`. Per this repo's own CLAUDE.md it's supposed to stay "specs/planning/deliverables only" — but `IMPLEMENTATION_PLAN.md` and `ArchitectureGovernor.md` there look like living planning docs that could drift out of sync with this repo's `docs/PROGRAM_SPEC_*` going forward.
- `Summa Terra Gmail Automation` — the original Gmail-automation build: `STV_Gmail_AccountingOS_MASTER_SPEC_v1.0.md`, `Loop Spec` stages 1-3, `Stage 1/2 Deliverables`, and **a live `credentials.json` and OAuth token-refresh scripts sitting in the repo** — a real secrets-hygiene issue, not just clutter.
- **Bottleneck:** not volume, it's *authority confusion* — an agent or session in the wrong repo will confidently produce a plan that contradicts this repo's current state, and nobody notices until two plans disagree. This already happened once (memory redirected three times: per-project → QB Automation repo → this repo).
- **Baseline [assumed]:** no formal count kept; qualitatively, this is the 3rd memory relocation in the project's history.

### D. Future Automated Workflow
Not really "automated" — this is a one-time triage + a standing rule, not a recurring job.
1. Triage `Summa Terra QB Automation`: anything still load-bearing (open decisions, active `ai-accounting-hub-ralph` build) gets a pointer doc in this repo's `docs/` linking back; anything superseded gets a one-line "ARCHIVED — see X" stub, mirroring what MEMORY.md already did for that repo.
2. Triage `Summa Terra Gmail Automation`: **rotate/revoke the exposed `credentials.json` and refresh tokens immediately** (independent of any doc triage — this is a live secret sitting in a repo that may not even be private). Then apply the same archive-stub treatment; its Gmail-automation content is superseded by this repo's `cowork_prompts/` + `GMAIL_AUTOMATION_SPEC.md` + the Cowork skills.
3. Update `CLAUDE.md`'s "canonical location" section to state plainly: this repo owns execution; the other two are archives with pointer stubs.
4. Update the `/summa-terra` skill's snapshot date and Track-3 status (see Track 3, item 1 of the punch list) — it currently understates how real `RealQboClient` is.

### E. Trigger
One-time manual pass, not recurring. (No cron/schedule needed — this is hygiene, not a pipeline.)

### F. Inputs
The three repos' current file trees (already inventoried above — no further discovery needed).

### G. Outputs
- Updated CLAUDE.md canonical-location section (this repo).
- Archive-stub `MEMORY.md`/`README.md` in the two satellite repos (pattern already proven — QB Automation repo already has one).
- Rotated credentials for the Gmail Automation repo's exposed `credentials.json`.
- Corrected `/summa-terra` skill snapshot.

### H. Systems Involved
Local filesystem / git only. No external system integration in this track.

### I. Recommended Architecture
**Tool-preference ladder: bottom rung, manual.** This is a one-time file/doc reorganization — no config, no glue, no hosted automation, no code, no agent needed for the *decision* (though an agent can execute the mechanical archive-stub writing once the triage decision is made by a human). Recommending anything heavier (a script that "watches" for drift across repos) would be solving a problem that doesn't recur often enough to justify it.

### J. Open-Source / Low-Cost Alternatives
N/A — no paid tool candidate exists for this track.

### K. Data Mapping
N/A — no data transformation, just doc relocation/stubbing.

### L. Approval Gates
- **Ben must approve before any file in `Summa Terra QB Automation` is archived/stubbed** — some of its content (`ai-accounting-hub-ralph/`, `OPEN_DECISIONS_spec_audit_2026-06-30.md`) may still be actively referenced.
- **Credential rotation is not gated on approval — do it immediately** regardless of doc-triage timing; a live secret in a repo is a standing risk every day it's not rotated.

### M. Error Handling
| Risk | Detection | Response |
|---|---|---|
| Archiving something still in active use | Ben's review gate (above) | Don't stub without explicit sign-off per repo |
| Credential rotation breaks a currently-working Gmail automation | Test the automation immediately after rotation | Have the old token available to roll back for the rotation window only |

### N. Security / Permissions
The credential exposure IS the security finding for this track — see D.2. No other permissions concerns; this track doesn't touch production data.

### O. Logging / Audit Trail
A single dated note in this repo's MEMORY.md recording what was archived, where, and why (matching the existing pattern for the two prior memory relocations).

### P. Admin Controls
N/A — one-time task, nothing to pause/resume.

### Q. Testing Plan
Manual verification only: confirm the stub docs in the two satellite repos actually redirect correctly, and confirm the rotated Gmail credentials still let the Gmail automation authenticate.

### R. Rollout Plan
Single pass, no phased rollout needed. Gate: Ben's sign-off on what's safe to archive (L above).

### S. Simplicity Audit
Removed from consideration: any kind of automated "repo drift checker" or dashboard — this doesn't happen often enough to earn tooling. Removed: touching `ai-accounting-hub-ralph/` or any in-progress build inside the QB Automation repo — out of scope for a hygiene pass.

### T. Final Build Checklist
- [ ] Credential rotation done for Gmail Automation repo
- [ ] Archive stub written in `Summa Terra QB Automation`'s README/MEMORY (beyond what already exists)
- [ ] Archive stub written in `Summa Terra Gmail Automation`
- [ ] CLAUDE.md canonical-location section updated
- [ ] `/summa-terra` skill snapshot date + Track-3 status corrected

### U. Done Looks Like
A fresh Claude session opened in *any* of the three repo folders, given no other context, reads that repo's top-level doc and is redirected to this repo within one file read. Falsifiable by literally testing it.

### V. AI Coder Implementation Prompt
> Read `Summa Terra QB Automation`'s and `Summa Terra Gmail Automation`'s top-level files. Do NOT delete anything. Rotate the OAuth credentials in `Summa Terra Gmail Automation/credentials.json` and its refresh-token scripts (generate new ones, revoke the old grant in Google Cloud Console) and confirm the Gmail automation still authenticates afterward. Then write a short `README_ARCHIVED.md` at each repo's root stating: this repo is archived, execution lives at `Co-Work QB Summa Terra`, and list which of its own subfolders (if any) are still independently active per Ben's review. Do not touch `ai-accounting-hub-ralph/` or `OPEN_DECISIONS_spec_audit_2026-06-30.md` without Ben's explicit line-item approval.

### W. Cost & Payback
Effort: ~1-2 hours of an agent's time plus Ben's 10-minute review gate. Payback: avoids a repeat of the "which memory file is real" confusion that has already happened multiple times — not quantifiable in dollars, but it's the reason this program-level spec was needed in the first place.

### X. Runbook Stub
Maintainer: Ben. **Pause:** N/A, one-time task. **Manual fallback:** if a satellite repo's stub is ever wrong or missing, the rule is simply "this repo (`Co-Work QB Summa Terra`) wins on any conflict" — no tooling required to fall back to that rule. **Restart:** re-run the triage prompt (Section V) any time a new satellite repo is discovered.

---

## TRACK 2 — QB Entries / Reconciliation Pipeline (QBE, human/operator side)

### A. Automation Name
STV Catch-Up & Reconciliation Research Pipeline

### B. Plain-English Summary
Every month, bank transactions land in STV's QuickBooks Desktop Enterprise files that don't have an obvious account to code them to — Adam used to just know, from memory and his own working notes. Now that he's gone, someone (Ben, or Ben directing Claude) has to reconstruct that knowledge from scratch: read the invoice, check the email thread, check the loan document, and only then pick the account. This track turns today's one-off version of that (33 rows, done by hand + 4 parallel research agents) into a repeatable process that runs every time new uncoded transactions show up — without pretending a computer can make the judgment calls that are actually CPA-level (capitalize vs. expense) or Ben-level (does this look like fraud, is this really unbooked, or did Adam already handle it under a different description).

### C. Current Manual Workflow
1. A bank export or QBE reconciliation surfaces rows with no coding (`UNCODED - do not post`) or a partial/ambiguous coding (`SPLIT REQUIRED`, `Multiple`).
2. Someone builds a question sheet (this session: `BEN_CATCHUP_QUESTIONS_ALL_ENTITIES_2026-07-27.xlsx`, 33 rows / 8 entities, `By Entity Summary` tab, yellow-column convention).
3. For each row, research means: check Adam's own prior coding for the identical recurring item (strongest signal), search mounted Google Drive letters for invoices/statements (`G:`=dallin@, `J:`=adam@, `K:`=patrick@, `L:`=stone@ — **letters are not stable, always verify by content**), search Gmail (bound to stone@ only — cannot open adam@'s or patrick@'s actual mailboxes, only their Drive), do arithmetic verification (does the proposed split sum to the bank amount to the penny), and flag anything that looks like it needs a CPA capitalize-vs-expense call rather than a bookkeeping answer.
4. **Bottleneck:** the research step. Each of today's 4 parallel agents took ~230-320K tokens and 12-18 minutes for one entity's handful of rows — this is genuinely hard, evidence-heavy work, not clerical lookup. Splitting by entity and running in parallel is what made 33 rows tractable in one session instead of a multi-day task.
5. **Baseline [measured, this session]:** 33 rows, ~35 minutes wall-clock using 4 parallel agents (vs. an estimated 3-4x longer sequentially), ~1M tokens total research cost. 28 of 33 rows reached CONFIRMED/LIKELY; 2 stayed genuinely unresolved (no document exists); 3 surfaced findings bigger than the original question (an unbooked $16.1M refinance, an already-posted transaction that would have been double-posted, three misdated entries that would have shifted income across period boundaries).

### D. Future Automated Workflow
This should **not** become a fully automated posting pipeline — Track 3 (ProofRail) already exists for eventual automation, and QBE is production data with no error budget. The realistic target state:
1. **Detection stays semi-manual, deterministically triggered**: whoever runs the monthly QBE reconciliation (per `stv-monthly-close` skill cadence) exports the same `UNCODED`/`SPLIT REQUIRED` question-sheet format used this session — that format is now proven, keep it as the standard intake.
2. **Research fans out to parallel agents by entity**, exactly as done this session — this is the load-bearing pattern to formalize, not replace. Each agent gets: entity name, the specific uncoded rows, the drive-letter mapping (re-verified by content, not assumed), and instructions to cite a real source or say "not found," never guess.
3. **A deterministic double-post check runs before any BenAnswer gets treated as ready-to-post**: query the live QBE register for the account/date range in question. (This was done manually this session and caught a real risk — Seq 248 was already posted. Automate this lookup specifically; it's the one step in this workflow that's actually deterministic and doesn't need agent judgment.)
4. **CPA policy questions get routed, not answered**: any row whose correct treatment depends on a capitalization-cutoff or accounting-policy call (placed-in-service, capitalize-vs-expense) goes into a separate, small "Ask Ricks & Company" list — never gets a BenAnswer that pretends to resolve it.
5. Ben reviews and approves (as just happened) — this human gate does not go away, ever, per this repo's Law ("no proof, no completion"; QBE posting additionally requires the certificate-grant + smoke-test gate documented in Track 3's readiness board).

### E. Trigger
Monthly close cadence (per `stv-monthly-close` skill) surfaces new uncoded/split rows; also ad hoc when Ben notices a gap.

### F. Inputs
QBE bank reconciliation exports, mounted Google Drive (4 letters, STV entity docs), Gmail (stone@ only), prior QBE coding history (the strongest single evidence source — check it first, every time).

### G. Outputs
The question-sheet workbook with `BenAnswer_*` columns filled + confidence + source citation; a short "Ask Ricks & Company" list; a short "still genuinely open, need a document" list (never silently guessed).

### H. Systems Involved
Google Drive (mounted local drive letters + Drive API), Gmail (MCP connector, stone@ only), QBE (via the existing QODBC/`qbe_com_bridge.ps1` read path — read-only for this track), Google Sheets/Excel for the question sheet itself.

### I. Recommended Architecture
**Tool-preference ladder: agent-driven research, deterministic everything else.** The classification research genuinely requires judgment across unstructured documents (invoices, emails, loan notes) — this is the correct, non-overbuilt use of agents per the doctrine (AI only where judgment over unstructured data is truly required). The double-post check and the sheet-filling mechanics are NOT judgment calls — those should be a script (Python, using the existing `openpyxl` pattern proven this session) reading the live QBE register, not another agent call. Recommending a permanent multi-agent system that runs unattended would be over-automating a monthly-cadence, CPA-adjacent task where a wrong guess costs real money — keep the human gate.

### J. Open-Source / Low-Cost Alternatives
No paid tool involved — Drive/Gmail access is via existing Google Workspace APIs already in use; QBE access is via the existing QODBC bridge already built. Nothing to substitute here.

### K. Data Mapping
`Seq → BenAnswer_AccountOrSplit, BenAnswer_Notes, Status` — as proven this session in `BEN_CATCHUP_QUESTIONS_ALL_ENTITIES_2026-07-27.xlsx`. Validation rule: `BenAnswer_AccountOrSplit` must never be filled without either (a) a cited source (file path or Gmail msg ID) or (b) an explicit "UNCERTAIN/no document found" flag — no silent guesses, ever (this was enforced manually this session; formalize it as a stated rule for future agents).

### L. Approval Gates
- Ben approves every `BenAnswer_*` before it's treated as postable (already the working pattern).
- Any row touching a CPA capitalization/policy question routes to Ricks & Company — never gets a Ben-level or agent-level answer.
- Posting itself requires the QBE certificate-grant + smoke-test gate (see Track 3 readiness board) — this track produces *coding decisions*, not *postings*.

### M. Error Handling
| Risk | Detection | Response |
|---|---|---|
| Double-posting an already-booked transaction | Query live QBE register before treating a row as postable | Flag as "coding-correction only," do not re-post (caught manually this session on Seq 248 — make this check standard, not a one-off catch) |
| Misdated entries shifting income across periods | Compare bank-clear date vs. rec-sheet date | Flag any mismatch explicitly (caught on 3 STDG rows this session) |
| Agent guesses instead of citing a source | Require explicit CONFIRMED/LIKELY/UNCERTAIN + citation in every agent prompt (already done this session) | Reject any answer with no citation; re-research or leave open |
| Drive-letter mapping stale | Verify by content, never assume the letter (this session's own memory already warns of this — it shifted twice before) | Re-verify at the start of every research pass |

### N. Security / Permissions
Read-only Drive/Gmail access; no write scopes needed for research. QBE posting (separate from this track) already has its own cert-gated, narrowly-scoped write path per Track 3's readiness board.

### O. Logging / Audit Trail
The filled question sheet itself is the audit trail (source citations inline). No additional logging system needed at this scale.

### P. Admin Controls
N/A at this scale — a spreadsheet with a Status column is the entire admin surface, and that's appropriately lean for a monthly-cadence, human-gated process.

### Q. Testing Plan
No formal test suite needed — the "test" is the Ben-approval gate itself, applied every cycle. If this workflow ever gets wrapped in code (e.g., the double-post-check script), that script gets a normal unit test against a known register snapshot.

### R. Rollout Plan
Already rolled out and proven this session. Next cycle: repeat the same pattern (question-sheet intake → parallel agent research by entity → double-post check script → Ben approval) at the next monthly close; treat any deviation from this session's confidence/citation discipline as a regression.

### S. Simplicity Audit
Removed from consideration: a permanent "reconciliation dashboard," a database of past answers (the existing QBE register + prior coding history already serves as institutional memory — a new database would duplicate it), and full automation of the posting step (blocked by design — QBE is production data, and the cert-gate/human-approval requirement is intentional, not a temporary limitation to engineer around).

### T. Final Build Checklist
- [ ] Formalize the "cite-or-flag" rule as a standing agent-prompt template for future research passes (this spec documents it; a short reusable prompt snippet would help)
- [ ] Build the double-post-check script (reads live QBE register, flags any Seq already present) — the one piece of this track that's genuinely automatable
- [ ] Confirm the STDG dividend double-post risk (Seq 262/267/273/282) against the live register before those get posted
- [ ] Fix the 3 misdated STDG entries before posting
- [ ] Route the two CPA policy questions (capitalization cutoffs, property-tax treatment) to Ricks & Company

### U. Done Looks Like
Next month's catch-up sheet gets the same treatment (parallel research by entity, cited answers, double-post check run before posting) without needing this spec re-explained — falsifiable by checking whether the next cycle's sheet has the same confidence/citation columns filled the same way.

### V. AI Coder Implementation Prompt
> Build a small Python script, `scripts/qbe_double_post_check.py`, that takes a list of (entity, date, amount) tuples from a catch-up question sheet and queries the live QBE register (reuse the existing QODBC/`qbe_com_bridge.ps1` read path — do not build a new connection method) for any transaction already posted matching entity+date±3days+amount. Output: a flag column appended to the sheet, `AlreadyPosted: YES/NO/UNCERTAIN`, never silently assume NO. This is read-only — no write capability, no exceptions.

### W. Cost & Payback
Baseline `[measured]`: ~35 min wall-clock / ~1M tokens for 33 rows across 8 entities this session. Payback isn't primarily time — it's avoiding a real dollar mistake (the $1.2M double-post risk this session caught) and surfacing a $16.1M unbooked refinance that would otherwise have sat undiscovered. That alone justifies the token cost many times over; this is not a workflow to shrink for efficiency's sake.

### X. Runbook Stub
Maintainer: Ben. **Pause:** there's no running process to pause — this is invoked per monthly-close cycle. **Manual fallback:** if the parallel-agent research pattern isn't available, fall back to the pre-existing manual method (Ben or a bookkeeper researching each row by hand) — slower, same rigor required (cite sources, don't guess). **Restart:** re-run the same intake→research→check→approve cycle at the next close; nothing to "restart" in a technical sense.

---

## TRACK 3 — ProofRail (Gmail → QBO Automation)

### A. Automation Name
ProofRail — SwarmSync Invoice-Proof / Verify-API / Audit-Proof construction-finance automation

### B. Plain-English Summary
This is the actual product: an app that watches for invoices and draw requests, checks them against rules that can't be faked or skipped, and only then lets real entries get written into QuickBooks Online — with a full paper trail proving every step happened correctly. Today it's live for one narrow slice (posting/voiding transactions in one of its two QuickBooks realms, when a person or Claude Code explicitly triggers it) and stubbed everywhere else. It is NOT the same system as Track 2's QuickBooks Desktop files — this automation targets a separate, still-sandbox QuickBooks **Online** environment.

### C. Current Manual Workflow (i.e., what still requires a human today)
Per three independent, evidence-based status docs written **today** (`GMAIL_TO_QB_ENGINE_STATUS.md`, `SWARMSYNC_INTEGRATION_STATUS.md`, `QBE_LIVE_CATCHUP_STATUS.md`) plus direct code inspection this pass:

- **Gmail/Drive intake:** 6 Windows Scheduled Tasks are registered (`STV_ApprovalConsumer`, `STV_DryRunIntake`, `STV_HeartbeatMonitor`, `STV_InboxRun`, `STV_MorningBrief`, `STV_WeeklyRetro`) but **every one has silently failed to fire for 12 days** — likely `LogonType=InteractiveToken` requiring an active desktop session at the exact trigger instant. The identical command runs fine manually. **Nothing is running unattended today, and nobody noticed for 12 days because Task Scheduler's own bookkeeping looked healthy.**
- **QBO/ProofRail posting (`src/proofrail/`):** `RealQboClient` is genuinely wired (confirmed by direct read of `container.ts` this session) — Bills/Invoices/JournalEntries post/void/delete for real against **Realm A only**, via the app's own separate Intuit OAuth grant, since 2026-07-10 with Ben's explicit go-ahead. **However, `src/api/mcp-server.ts`'s own header comment is stale and contradicts this** — it still says QboClient is fake/in-memory. This is exactly the kind of doc-drift this repo's own CLAUDE.md warns about ("check container.ts for what's actually wired before trusting it") — found live, in-code, this pass.
- **Persistence:** real (`PostgresProofRailRepository`, isolated Supabase project). Not a stub.
- **Proof layer:** InvoiceProof is REAL (live-verified SwarmSync call on record). AuditProof and VerifyAPI are STUBBED — silently fall back to a locally-computed SHA-256 hash (`proof_id: "local_..."`) because no real `ssk_live_` SwarmSync key has ever been obtained, despite three documented attempts.
- **A separate, newer module, `src/payment-ops/`,** is untracked in git (never committed) and implements a *different* concern — bill/loan/insurance/subscription payment *obligations* (not draws/invoices/fees) — per `docs/SPEC_SIMPLIFIED_PAYMENT_OPS.md`. It is currently the ONLY module wired into `app.module.ts`; ProofRail's MCP tools ride on top via a direct singleton import in `mcp.controller.ts`, bypassing Nest's module system entirely. **These two modules are complementary, not competing** — the payment-ops spec explicitly designs its own Phase 3 as "move state/audit authority into ProofRail; the workbook becomes an operator view, not a competing state machine." Do not merge them prematurely; they solve different problems (recurring obligations vs. draw/fee/invoice proof workflow) and the spec already has a stated convergence point.
- **QBE (the *other* QuickBooks system, Desktop Enterprise, production data)** has its own separate, unrelated posting service: built, Kraken-audited, 22/22 tests passing, but **0 of 14 entities have the certificate grant needed for live posting** — a 10-minute Ben-at-keyboard task that's the single biggest unlock on that side. A specific HLN catch-up posting run was started and abandoned mid-flight (backup taken, nothing written) — needs Ben's confirmation before any retry.
- **Drive reorganization:** partially executed — real folder structure created and copy-verified against production Drive, but the feature flag connecting it into the live pipeline is deliberately OFF.
- **Bottleneck:** getting the scheduled tasks to actually fire unattended. Everything downstream of intake (proof, posting, gates) has *some* real wiring; intake itself is the thing that's completely non-functional today despite looking configured.

### D. Future Automated Workflow
Per this repo's CLAUDE.md build order (P1 provisioning → P2 API core + MCP → P3 Cowork playbooks + obgen seeding → P4 Trigger.dev gates/money_lock → P5 web UI → P6 cutover) — largely unchanged, but re-sequenced by what today's status docs show is actually blocking:
1. Fix the scheduled-task launch failure (swap `LogonType=InteractiveToken` for `S4U`/service-account logon, or move to a always-on host) — this is the one fix that turns "built" into "operating."
2. Get a real `ssk_live_` SwarmSync key so AuditProof/VerifyAPI stop silently falling back to local hashes — every "proof" claim this system makes today for those two products is not actually third-party-sealed.
3. Correct the stale `mcp-server.ts` header comment (or better: replace the hand-written status comment with a comment that just points to `container.ts`, so it can't drift again).
4. Decide and execute the Realm B (parent/corporate) wiring — today only Realm A posts for real.
5. Continue the QBE→QBO migration per `SPEC_QBW_TO_QBO_MIGRATION.md` — this is what eventually lets Track 2's manual/agent workflow be replaced by Track 3's automation; not there yet.

### E. Trigger
Gmail message arrival / Drive file arrival (intake) → currently scheduled-task-driven (broken, see C); MCP tool calls (approve/void/build_draw/etc.) are directly invoked by Cowork or Claude Code CLI — these work today, just not from an unattended trigger.

### F. Inputs
Gmail (via Cowork's connected MCP), Google Drive, MCP tool calls (11 frozen tools per `tool-contracts.ts`), QBO sandbox API (Realm A + Realm B).

### G. Outputs
QBO Bills/Invoices/JournalEntries (Realm A, real); InvoiceProof-scanned packets (real); AuditProof/VerifyAPI bundles (currently local-only stamps, not real third-party proof); audit-log JSONL.

### H. Systems Involved
QBO Advanced (2 sandbox realms), SwarmSync API, Supabase Postgres, Gmail/Drive (Cowork side), Windows Task Scheduler (broken), Trigger.dev (tasks exist in `src/trigger/proofrail.tasks.ts`, gate status not independently re-verified this pass — recommend the same root-cause-analyst treatment given to the other 5 status docs).

### I. Recommended Architecture
Already built at the right altitude for most of this track — a real MCP server (justified: Cowork genuinely needs agent-judgment-driven tool calls, not a fixed pipeline) plus a NestJS API plus Trigger.dev for scheduled/gated jobs. The one architecture correction: **Windows Scheduled Tasks are the wrong mechanism for a server process that needs to run unattended without an interactive desktop session** — this is a textbook case for a proper service-account logon type or, better, moving these jobs onto whatever always-on host already runs the NestJS API (Render, per this repo's stack) rather than a local Windows machine at all. Don't over-correct into a new queue/orchestration system — Trigger.dev already exists for this and is the right tier.

### J. Open-Source / Low-Cost Alternatives
SwarmSync itself is a paid, purpose-built proof API and is the correct choice here — it's not a generic problem a FOSS tool solves (cryptographic invoice-proof/audit-proof is the product's actual moat per this repo's CLAUDE.md). No substitution recommended. The scheduling layer, however, should not depend on a Windows interactive logon — that's a $0 config fix (service logon type), not a tooling purchase.

### K. Data Mapping
Per `tool-contracts.ts` (11 tools) and `schema.prisma` (EntityRegistry, GcCodeMap, MemberVendor) — already fully specified; not re-derived here.

### L. Approval Gates
Already implemented per this repo's Law: RED gate → `money_lock` → 423 on `send_draw`/`approve_fees`; QUARANTINED approvals require `override_reason`. Not re-specified; verify these still pass their existing test suite as part of the punch list below rather than re-designing them.

### M. Error Handling
The single biggest gap found this pass: **silent failure with no alerting.** The scheduled tasks have been failing for 12 days with zero notification — Task Scheduler's own success-looking bookkeeping actively hid the failure. Per the doctrine ("failure path before happy path," "an automation that fails silently is worse than the manual process"): any fix here must include a heartbeat/alert that fires if the intake job hasn't produced a log line in N hours, not just a fix to the trigger mechanism itself.

### N. Security / Permissions
`PROOFRAIL_MCP_KEY` fail-closed on server start (verified in code this pass — good). Realm A OAuth grant is separate from the work-machine's Python scripts' tokens (also verified, good — this separation is a real safeguard, not just a comment). No changes recommended here beyond fixing the SwarmSync key gap in C/D above.

### O. Logging / Audit Trail
Append-only JSONL per this repo's Law — already implemented for the parts that are real. Add: the heartbeat/alert log named in M above.

### P. Admin Controls
Existing MCP tools (`get_gate_status`, `list_queue`, etc.) already provide admin visibility for what's wired. No new controls needed for what already works; the scheduled-task fix needs a way to *see* that a trigger fired (currently invisible per the intake status doc).

### Q. Testing Plan
The existing acceptance-test suite (per `QBO_MCP_OAUTH_APPROVAL.md` §4, 7 tests, already passed live) covers the QboClient real-wiring. Recommend the same root-cause-analyst-style independent status audit be re-run in ~30 days on all 5 areas (intake, SwarmSync, QBE, Plaid, Drive) — these drift fast and the "verified 2026-07-28" docs found this pass were themselves catching drift from even more recent claims.

### R. Rollout Plan
Already mid-rollout, phased per this repo's own build order (P1-P6). Gate criteria unchanged from CLAUDE.md; the correction is sequencing — fix intake (P item above) before investing further in P5 (web UI), since an app with no working unattended trigger has no live data to show a UI anyway.

### S. Simplicity Audit
Nothing to cut here — if anything, this track has the opposite problem (real components mistaken for stubs and vice versa, because status comments drifted). The simplicity win is **removing stale status comments as a source of truth** — replace narrative "what's real" comments in code with a single doc that's the only place status lives (this document + the dated status docs), and keep code comments to WHY, not WHAT'S-CURRENTLY-TRUE (which rots).

### T. Final Build Checklist
- [ ] Fix scheduled-task logon type or move intake off local Windows Task Scheduler entirely
- [ ] Add heartbeat/alert for intake silent-failure detection
- [ ] Obtain a real SwarmSync `ssk_live_` key (3 prior attempts failed — needs escalation, not a 4th identical attempt)
- [ ] Correct `mcp-server.ts`'s stale header comment
- [ ] Decide Realm B wiring timeline
- [ ] Ben: grant QBE certificates (0 of 14) + run the $1 wash smoke test
- [ ] Ben: confirm the abandoned HLN catch-up posting run before any retry
- [ ] Ben: approve the Plaid top-10 connection list (Wave 4 held on this)

### U. Done Looks Like
`logs/scheduler/` (or its Render equivalent) shows a fresh log line from an unattended trigger within the last 24 hours, with no human having manually invoked it. Falsifiable — either the log line exists with a timestamp inside the trigger window, or it doesn't.

### V. AI Coder Implementation Prompt
> Investigate why the 6 Windows Scheduled Tasks (`STV_ApprovalConsumer`, `STV_DryRunIntake`, `STV_HeartbeatMonitor`, `STV_InboxRun`, `STV_MorningBrief`, `STV_WeeklyRetro`) silently fail to launch (suspected: `LogonType=InteractiveToken` requiring an active desktop session). Fix by changing the logon type to a service-compatible option, OR recommend and scope moving these jobs to run on the same host already serving the NestJS API (Render) instead of a local Windows machine. Whichever fix you implement, add a heartbeat check that alerts (email/Slack/log-monitor, whichever this repo already has wired) if no successful run has been logged in 25 hours. Do not touch `mcp-server.ts`'s business logic — only correct its stale header comment to stop asserting QboClient is fake when `container.ts` shows it is real.

### W. Cost & Payback
Not newly costed here — this track's build cost is sunk; the punch list above is completion/correction, not new build. The clearest payback: the scheduled-task fix alone converts 12+ days of silent non-operation into an actually-running system, which is the entire point of the automation existing.

### X. Runbook Stub
Maintainer: whoever holds the Render/infra keys (currently Ben). **Pause:** disable the relevant Windows Scheduled Task or Render cron entry. **Manual fallback:** every MCP tool this system exposes can still be invoked directly by Cowork or Claude Code CLI — the "automation" pausing does not remove the manual path, it just stops the unattended trigger. **Restart:** re-enable the task/cron entry; confirm via the heartbeat log (once built) that it actually fired, not just that Task Scheduler's UI says it's scheduled.

---

## Program-Level Prioritized Punch List (ranked by what unblocks the most other work)

1. **Fix the ProofRail intake scheduler (Track 3).** Nothing downstream — Gmail-to-QB automation, the eventual replacement for Track 2's manual workflow — matters if intake never fires. 12 days silent failure, zero alerting. Highest leverage item in the whole program.
2. **Rotate the exposed Gmail-automation credentials (Track 1).** A live secret sitting in a repo is a compounding risk every day it's not fixed; costs almost nothing to do now.
3. **Ben grants the 0-of-14 QBE certificates + runs the $1 wash smoke test (Track 3/QBE side).** A 10-minute task that unblocks the entire production QuickBooks Desktop posting path — the highest-leverage 10 minutes available to Ben personally.
4. **Confirm/retry the abandoned HLN catch-up posting run (Track 2/QBE).** A real backup exists, nothing was written, but it needs Ben's explicit confirmation before any retry — don't let this sit ambiguous.
5. **Run the double-post-check script against the live QBE register for the 4 STDG dividend rows (Seq 262/267/273/282) before posting anything from today's approved sheet.** Directly protects against a real duplicate-posting mistake identified this session.
6. **Escalate the SwarmSync `ssk_live_` key request (Track 3).** Three failed attempts means the fourth identical attempt won't work either — this needs a different approach (direct contact with SwarmSync, not just retrying the same request).
7. **Correct the `/summa-terra` skill snapshot and the `mcp-server.ts` stale comment (Track 1 + Track 3).** Both are "the map says X, the territory says Y" problems — cheap to fix, expensive to leave (every future session inherits the wrong picture).
8. **Route the two CPA policy questions to Ricks & Company (Track 2): placed-in-service capitalization cutoff for HLN/Union Station, and property-tax capitalize-vs-expense policy.** Not urgent in dollars, but every month it's undecided is another month of inconsistent treatment accumulating.
9. **Triage and archive-stub the two satellite repos (Track 1).** Lower urgency than the above because it's a confusion risk, not an active-failure risk — but do it before the next new session starts in the wrong repo.
10. **Ben approves the Plaid top-10 connection list (Track 3).** Wave 4 is held on this single decision.
