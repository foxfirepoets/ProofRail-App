# AUDIT_LOG_SPEC — JSONL is the source of truth; the Sheet is a convenience

## Files (append-only, never edited, never deleted; mirrored daily to Drive `11_Audit_Logs`)

| File | Written by | Content |
|---|---|---|
| `logs/qbo_seed_YYYYMMDD.jsonl` | every QBO script | token refreshes, company checks, create attempts/results, seed/verify summaries, gap fixes, preference changes |
| `logs/cowork_audit_YYYYMMDD.jsonl` | `append_audit_log.py` (Co-work + Ben) | workflow events: intake, classification, extraction, proof verdicts, approvals, handoffs, exceptions, close events |
| `logs/invoice_ledger.jsonl` | `build_invoiceproof_packet.py` | one line per scanned invoice (dedup memory) |

## Event schema (`cowork_audit`; enforced by `append_audit_log.py`)

Required: `ts` (UTC ISO, auto) · `actor` (cowork/ben/script) · `event_type` ·
`source_ref` (**every event cites its source**: `gmail:<msgid>`, `drive:<path>`, `local:<file>`) ·
`summary`.
Contextual: `classification` · `sender` · `attachment` · `extracted` (via `--json`) ·
`invoiceproof_verdict` (PASS/FLAG/FAIL) · `recommendation` · `approval`
(approved/rejected/escalated) · `approver` · `qbo_request_id` · `qbo_result` · `final_status` ·
`extra` (free JSON).

Event types (canonical): `intake_classified` `attachment_saved` `invoice_extracted`
`invoiceproof_packet` `draw_check` `approval` `qbo_handoff` `create_attempt` `create_ok`
`create_error` `posting_verified` `exception_opened` `exception_cleared` (note REQUIRED)
`bank_change_verification` `daily_summary` `close_step` `retro_note`.

## Safety invariants (enforced in code)

- `redact()` strips every known secret and token-shaped string before a line hits disk.
- Bank account/routing shapes are masked to `****last4` automatically.
- Append-only: no code path rewrites or deletes a log line.
- One event per line, machine-parseable, sorted by time by construction.

## Chain-of-proof for irreversible events (optional now, standard later)

Local JSONL logs every event. For irreversible actions (QBO writes, draw sends, close packets),
additionally seal a proof via SwarmSync VerifyAPI: `POST https://api.swarmsync.ai/api/verify`
(`source_type:"workflow_event"` or `task:"audit_proof"`) → store returned `proof_id` +
`chain_hash` in the event's `extra`. Verify anytime with `GET /api/proof/:id/verify`
(recomputes the per-org sha256 chain; `signed_hash_chain` when signing keys are set).
Note: SwarmSync exposes no JSONL-append API — the local log is primary; SwarmSync seals it.

## Google Sheet summary (optional, human-only)

A daily job MAY mirror headline fields (ts, event_type, summary, verdict, approval,
final_status) to a Sheet for skimming. The Sheet is never authoritative, never edited by hand
as "truth," and disagreements resolve to the JSONL, always.
