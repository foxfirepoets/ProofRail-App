/**
 * ProofRail MCP — Tool Contracts v1.2.0
 * The seam: Cowork (cognition) drives ProofRail (physics) ONLY through these tools.
 * Spec: SPEC v1.2 §B3. Pattern: SwarmSync mcp/ module + mcp-builder skill.
 *
 * Three laws, enforced server-side (never trust the caller — even when the caller is Claude):
 *  1. STATE GUARD  — every mutation validates the state machine; illegal transition → 409.
 *  2. MONEY LOCK   — latest GateRun RED → send_draw / run_fees / post mutations → 423.
 *  3. AUDIT        — every mutating call writes McpAuditLog before returning.
 *
 * Error model (all tools):
 *  { error: { code: 'PR-0xx' | 'STATE_409' | 'LOCKED_423' | 'NOT_FOUND_404', message, detail? } }
 *  PR-002 flag-without-override · PR-003 proof service down (fail closed) ·
 *  PR-010 QBO throttle (retry queued) · PR-020 fee pair partial (voided) ·
 *  PR-043 unknown project/cost-code (never guess)
 */

// ───────────────────────── shared types ─────────────────────────

export type IntakeStatus =
  | 'RECEIVED' | 'PARSED' | 'PROOFING' | 'PROOF_PASS' | 'QUARANTINED'
  | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'SYNCING' | 'SYNCED' | 'PROOFED';

export interface ProofStamp {
  proof_id: string;      // SwarmSync ProofRecord id
  chain_hash: string;
  verify_url: string;    // GET /api/proof/:id/verify — anyone can check, no trust required
  product: 'INVOICE_PROOF' | 'VERIFY_API' | 'AUDIT_PROOF';
}

export interface ParsedInvoice {
  vendor: string;                 // raw as seen; server canonicalizes via Vendor.aliases
  invoice_no: string;
  invoice_date: string;           // ISO
  total: number;
  lines: { description: string; item?: string; amount: number }[];
  bank?: { acct_last4?: string; routing_last4?: string }; // Invoice-Proof BEC baseline
}

// ───────────────────────── 1. submit_intake ─────────────────────────
/** Cowork's hand-off after Inbox Run parses an invoice. Idempotent on email_meta.gmail_msg_id.
 *  Server pipeline (synchronous through the gate): create intake → PROOFING →
 *  Invoice-Proof POST /api/verify → PROOF_PASS→PENDING_APPROVAL | FLAG→QUARANTINED.
 *  Proof service unreachable → QUARANTINED with PR-003 (fail closed — no bypass exists). */
export interface SubmitIntakeInput {
  email_meta: { gmail_msg_id: string; sender: string; subject: string; received_at: string };
  parsed_invoice: ParsedInvoice;
  suggested_coding?: { entity: string; project: string; item: string; confidence: number };
  attachments: { sha256: string; filename: string; storage_uri: string }[];
}
export interface SubmitIntakeResult {
  intake_id: string;
  status: Extract<IntakeStatus, 'PENDING_APPROVAL' | 'QUARANTINED'>;
  proof: ProofStamp;                    // the Invoice-Proof run — even FLAGs are proofed
  flags?: string[];                     // e.g. ['DUPLICATE_SUSPECT','BANK_CHANGE','LINE_MATH']
  duplicate_of?: string;                // intake_id if dup detected
}

// ───────────────────────── 2. list_queue ─────────────────────────
export interface ListQueueInput {
  status?: IntakeStatus[];              // default ['PENDING_APPROVAL','QUARANTINED']
  entity?: string;
  limit?: number;                       // default 25
}
export interface ListQueueResult {
  items: {
    intake_id: string; vendor: string; amount: number; invoice_no: string;
    coding: { entity?: string; project?: string; item?: string };
    status: IntakeStatus; flags: string[]; proof: ProofStamp; age_hours: number;
  }[];
  quarantined_count: number;
  money_lock: boolean;                  // surfaced everywhere — no surprises at act time
}

// ───────────────────────── 3. approve / 4. reject ─────────────────────────
/** Guards: intake must be PENDING_APPROVAL or QUARANTINED. QUARANTINED requires
 *  override_reason (≥20 chars) — recorded, surfaced in tonight's Audit-Proof bundle.
 *  On approve: → APPROVED → SYNCING → QBO POST /bill (RequestId idempotent) → SYNCED
 *  → Verify-API workflow_event → PROOFED. Returns only after SYNCED or queued-retry. */
export interface ApproveInput {
  intake_id: string;
  coding_final?: { entity: string; project: string; item: string }; // Ben's correction wins
  override_reason?: string;             // REQUIRED iff QUARANTINED (else PR-002)
}
export interface ApproveResult {
  intake_id: string;
  status: Extract<IntakeStatus, 'SYNCED' | 'PROOFED' | 'SYNCING'>; // SYNCING = QBO throttled, queued
  qbo_txn_id?: string;
  proof?: ProofStamp;                   // the workflow_event proof of the write
}
export interface RejectInput  { intake_id: string; reason: string; }
export interface RejectResult { intake_id: string; status: 'REJECTED'; }

// ───────────────────────── 5. get_gate_status ─────────────────────────
/** Morning Brief's first call. Read-only, always available. */
export interface GetGateStatusResult {
  run_date: string;
  verdict: 'GREEN' | 'RED';
  money_lock: boolean;
  green_streak_days: number;
  results: { gate: 'G-A'|'G-B'|'G-C'|'G-D'|'G-E'|'G-F'; pass: boolean; summary: string }[];
  bundle_proof: ProofStamp;             // Audit-Proof bundle — GREEN or RED, always bundled
}

// ───────────────────────── 6. reconcile_draw_sheet (F6 — the leak detector) ─────────────────────────
/** GC pay-app arrives → Cowork extracts, server reconciles against QBO committed costs,
 *  prior draws, and schedule of values. The 12SB 5% markup catch, as a machine check. */
export interface ReconcileDrawSheetInput {
  project: string;
  gc: string;
  period: string;
  sheet_storage_uri: string;
  extracted_lines: { cost_code?: string; description: string; this_period: number;
                     total_to_date: number; retainage?: number }[];
}
export interface ReconcileDrawSheetResult {
  reconcile_id: string;
  verdict: 'PASS' | 'FLAG';
  variance: {
    line: string;
    billed: number;
    basis: number;                      // sub-invoice support found in QBO
    prior_draws: number;
    delta: number;
    flag?: 'MARKUP' | 'DUPLICATE_BILLING' | 'RETAINAGE_MATH' | 'NO_BASIS';
  }[];
  proof: ProofStamp;                    // document proof — lender-shareable
}

// ───────────────────────── 7. build_draw / 8. send_draw ─────────────────────────
/** build: refuses if last GREEN gate >24h old (stale-GL rule) — PR-030 detail in error.
 *  send: IRREVERSIBLE. Guards: status=PROOFED, money_lock=false (else 423). */
export interface BuildDrawInput  { project: string; period: string; lender: string; }
export interface BuildDrawResult {
  draw_id: string;
  status: 'ASSEMBLED' | 'DRAFT';
  gaps?: string[];                      // missing budget lines / estimates — blocks assembly
  bva_summary: { budget: number; committed: number; actual: number; this_draw: number };
  pdf_uri?: string;
  chain_hash?: string;                  // printed in the package footer
}
export interface SendDrawInput  { draw_id: string; confirm: true; }  // literal true — no default sends
export interface SendDrawResult { draw_id: string; status: 'SENT'; sent_at: string; proof: ProofStamp; }

// ───────────────────────── 9. run_fees ─────────────────────────
/** Computes the OAEA matrix for a period. NEVER posts — returns PENDING_APPROVAL rows;
 *  posting happens via approve_fees after Ben reviews. 12SB & Summa Elite appear ONLY
 *  in skipped[] with reason 'NO_FEE_OAEA' — their exclusion is code, tested, not config. */
export interface RunFeesInput { period: string; }
export interface RunFeesResult {
  fee_runs: { fee_run_id: string; entity: string; base: number; rate: number;
              fee: number; payee: string; status: 'PENDING_APPROVAL' }[];
  skipped: { entity: string; reason: 'NO_FEE_OAEA' | 'NO_ACTIVITY' }[];
  money_lock: boolean;                  // if true, approve_fees will 423 — told up front
}
export interface ApproveFeesInput  { fee_run_ids: string[]; }
export interface ApproveFeesResult {
  posted: { fee_run_id: string; invoice_txn_id: string; bill_txn_id: string; proof: ProofStamp }[];
  failed: { fee_run_id: string; error: 'PR-020'; voided: boolean }[]; // pair-atomic or voided
}

// ───────────────────────── 10. lookup_coding ─────────────────────────
/** Cowork's memory prosthetic while parsing: history-informed coding suggestion.
 *  Read-only. Returns matrix context so Cowork never proposes a fee item on 12SB. */
export interface LookupCodingInput { vendor: string; description?: string; amount?: number; }
export interface LookupCodingResult {
  canonical_vendor?: string;
  suggestions: { entity: string; project: string; item: string;
                 confidence: number; based_on: 'HISTORY' | 'VENDOR_DEFAULT' | 'RULE' }[];
  entity_notes?: string[];              // e.g. '12SB: NO developer fee (OAEA)'
  bank_baseline?: { acct_last4: string }; // for Cowork to spot a change before submit
}

// ───────────────────────── 12. void_transaction ─────────────────────────
/** Ben's directive, 2026-07-10. VOID, not hard delete - zeroes the transaction but keeps it in
 *  QBO's history/audit trail (standard accounting practice). Scoped to the same money boundary
 *  as everything else here: Bill, Invoice, JournalEntry only, never BillPayment/Payment/Deposit/
 *  Check. Money-lock gated (423 on a RED gate, same as send_draw/approve_fees) and requires
 *  literal confirm:true plus a reason (>=10 chars) - no default sends, no unexplained voids. */
export interface VoidTransactionInput {
  entity_type: 'Bill' | 'Invoice' | 'JournalEntry';
  qbo_txn_id: string;
  reason: string;             // required, >= 10 chars - why this transaction is being voided
  confirm: true;               // literal true - no default voids
}
export interface VoidTransactionResult {
  entity_type: 'Bill' | 'Invoice' | 'JournalEntry';
  qbo_txn_id: string;
  operation: 'void' | 'delete';  // QBO only supports true void for Invoice; Bill/JournalEntry get a hard delete
  voided: true;
  proof: ProofStamp;
}

// ───────────────────────── registration ─────────────────────────
export const PROOFRAIL_TOOLS = [
  'submit_intake', 'list_queue', 'approve', 'reject', 'get_gate_status',
  'reconcile_draw_sheet', 'build_draw', 'send_draw', 'run_fees', 'approve_fees',
  'lookup_coding', 'void_transaction',
] as const;
// Auth: Authorization: Bearer sk_proofrail_...  (org-scoped, SwarmSync key pattern)
// Mutating tools: submit_intake, approve, reject, send_draw, run_fees→approve_fees, void_transaction.
// Every mutation → McpAuditLog row BEFORE response. Read tools are unlogged and cheap.
