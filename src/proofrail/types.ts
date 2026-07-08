export type IntakeStatus =
  | "RECEIVED"
  | "PARSED"
  | "PROOFING"
  | "PROOF_PASS"
  | "QUARANTINED"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "SYNCING"
  | "SYNCED"
  | "PROOFED";

export type GateVerdict = "GREEN" | "RED";
export type DrawStatus = "DRAFT" | "ASSEMBLED" | "PROOFED" | "SENT" | "FUNDED";
export type FeeStatus = "COMPUTED" | "PENDING_APPROVAL" | "POSTED" | "PROOFED" | "FAILED";
export type FeeStream = "DEV_CM" | "DRAW" | "ACCOUNTING" | "PM";

export interface ProofStamp {
  proof_id: string;
  chain_hash: string;
  verify_url: string;
  product: "INVOICE_PROOF" | "VERIFY_API" | "AUDIT_PROOF";
}

export interface ParsedInvoice {
  vendor: string;
  invoice_no: string;
  invoice_date: string;
  total: number;
  lines: { description: string; item?: string; amount: number }[];
  bank?: { acct_last4?: string; routing_last4?: string };
}

export interface SubmitIntakeInput {
  email_meta: { gmail_msg_id: string; sender: string; subject: string; received_at: string };
  parsed_invoice: ParsedInvoice;
  suggested_coding?: { entity: string; project: string; item: string; confidence: number };
  attachments: { sha256: string; filename: string; storage_uri: string }[];
}

export interface ApproveInput {
  intake_id: string;
  coding_final?: { entity: string; project: string; item: string };
  override_reason?: string;
}

export interface FeeRunRecord {
  id: string;
  stream: FeeStream;
  period: string;
  entity: string;
  base: number;
  rate: number;
  payee: string;
  status: FeeStatus;
  invoiceTxnId?: string;
  billTxnId?: string;
  proof?: ProofStamp;
}

export interface EntityRegistryRecord {
  entity: string;
  locationA: string;
  feeRate?: number | null;
  feePayee?: string | null;
  feeBase?: string | null;
  oaeaDocUrl?: string | null;
  drawFee?: number | null;
  acctFeeCapMo?: number | null;
  pmFeeRate?: number | null;
}

export interface IntakeRecord {
  id: string;
  gmailMsgId: string;
  vendorRaw: string;
  parsed: ParsedInvoice;
  amount: number;
  entity?: string;
  project?: string;
  item?: string;
  status: IntakeStatus;
  quarantineReason?: string;
  overrideReason?: string;
  qboTxnId?: string;
  requestId?: string;
  proof?: ProofStamp;
  flags?: string[];
  createdAt: Date;
}

export interface GateRunRecord {
  id: string;
  runDate: Date;
  verdict: GateVerdict;
  moneyLock: boolean;
  results: { gate: string; pass: boolean; summary: string }[];
  bundleProof?: ProofStamp;
}

export interface DrawRecord {
  id: string;
  project: string;
  period: string;
  lender: string;
  status: DrawStatus;
  chainHash?: string;
  sentAt?: Date;
  proof?: ProofStamp;
}

export interface AuditRecord {
  tool: string;
  input: unknown;
  result: unknown;
  actorKey: string;
}

export interface DrawReconcileLine {
  cost_code?: string;
  description: string;
  this_period: number;
  total_to_date: number;
  retainage?: number;
}

export interface ReconcileDrawSheetInput {
  project: string;
  gc: string;
  period: string;
  sheet_storage_uri: string;
  extracted_lines: DrawReconcileLine[];
}

export interface DrawReconcileVariance {
  line: string;
  billed: number;
  basis: number;
  prior_draws: number;
  delta: number;
  flag?: "MARKUP" | "DUPLICATE_BILLING" | "RETAINAGE_MATH" | "NO_BASIS";
}

export interface DrawReconcileRecord {
  id: string;
  project: string;
  gc: string;
  period: string;
  verdict: "PASS" | "FLAG";
  variance: DrawReconcileVariance[];
  proof?: ProofStamp;
}

export interface LookupCodingInput {
  vendor: string;
  description?: string;
  amount?: number;
}

export interface LookupCodingSuggestion {
  entity: string;
  project: string;
  item: string;
  confidence: number;
  based_on: "HISTORY" | "VENDOR_DEFAULT" | "RULE";
}

export interface VendorHistoryRecord {
  vendorCanonical: string;
  aliases: string[];
  entity: string;
  project: string;
  item: string;
  lastAmount?: number;
  bankAcctLast4?: string;
}
