export enum ObligationState {
  DISCOVERED = "DISCOVERED",
  VERIFIED = "VERIFIED",
  APPROVAL_NEEDED = "APPROVAL_NEEDED",
  APPROVED = "APPROVED",
  READY_FOR_EXECUTION = "READY_FOR_EXECUTION",
  SCHEDULED = "SCHEDULED",
  PAID_PENDING_CLEARING = "PAID_PENDING_CLEARING",
  CLEARED = "CLEARED",
  RECONCILED = "RECONCILED",
}

export enum ObligationKind {
  BILL = "BILL",
  LOAN = "LOAN",
  INSURANCE = "INSURANCE",
  SUBSCRIPTION = "SUBSCRIPTION",
  TAX = "TAX",
  PAYROLL = "PAYROLL",
  OTHER = "OTHER",
}

export enum PaymentMethod {
  ACH = "ACH",
  WIRE = "WIRE",
  CHECK = "CHECK",
  CARD = "CARD",
  AUTOPAY = "AUTOPAY",
  OTHER = "OTHER",
}

export enum AccountIdentityStatus {
  VERIFIED = "VERIFIED",
  CONFLICT = "CONFLICT",
  MISSING = "MISSING",
}

export enum EvidenceSource {
  GMAIL = "GMAIL",
  DRIVE = "DRIVE",
  CALENDAR = "CALENDAR",
  STATEMENT = "STATEMENT",
  BANK_FEED = "BANK_FEED",
  WORKBOOK = "WORKBOOK",
  OTHER = "OTHER",
}

export enum EvidenceRole {
  INVOICE = "INVOICE",
  ACCOUNT_IDENTITY = "ACCOUNT_IDENTITY",
  APPROVAL = "APPROVAL",
  PAYMENT_CONFIRMATION = "PAYMENT_CONFIRMATION",
  CLEARING_PROOF = "CLEARING_PROOF",
  RECONCILIATION = "RECONCILIATION",
  INSTRUCTION = "INSTRUCTION",
}

export enum ApprovalStatus {
  NOT_REQUIRED = "NOT_REQUIRED",
  PENDING = "PENDING",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
}

export enum OperatorTarget {
  BEN = "BEN",
  AUBREY = "AUBREY",
  AUTO = "AUTO",
  OTHER = "OTHER",
}

export enum NonBillOutflowType {
  CASH_CALL = "CASH_CALL",
  INTERCOMPANY_TRANSFER = "INTERCOMPANY_TRANSFER",
  DISTRIBUTION = "DISTRIBUTION",
  FEE_TRANSFER = "FEE_TRANSFER",
  OTHER = "OTHER",
}

export interface AccountIdentity {
  id: string;
  legalOwner: string;
  institution: string;
  accountType: string;
  stableAccountId?: string;
  lastFour?: string;
  accessOwner?: string;
  signerRequirement?: string;
  status: AccountIdentityStatus;
  evidenceIds: string[];
}

export interface EvidenceRef {
  id: string;
  source: EvidenceSource;
  sourceId: string;
  capturedAt: string;
  role: EvidenceRole;
  reviewer?: string;
  hash?: string;
  stableAccountId?: string;
  obligationId?: string;
  accountId?: string;
  amount?: number;
  transactionDate?: string;
  accountLegalOwner?: string;
  accountInstitution?: string;
  accountType?: string;
  providerReference?: string;
  fingerprint?: string;
  provenanceVerified?: boolean;
  provenanceCredentialId?: string;
  provenancePayloadHash?: string;
  providerImmutableId?: string;
}

export interface AuthenticatedPrincipal {
  id: string;
  roles: string[];
  verified: true;
  issuer: string;
}

export type PrincipalAuthenticator = (authorization: string | undefined) => AuthenticatedPrincipal | Promise<AuthenticatedPrincipal | undefined> | undefined;

export const PAYMENT_OPS_AUTHENTICATOR = Symbol("PAYMENT_OPS_AUTHENTICATOR");

export interface ApprovalLog {
  id: string;
  obligationId: string;
  approver: string;
  status: ApprovalStatus;
  requestDraftId?: string;
  replyThreadId?: string;
  timestamp: string;
  scope: string;
  standing: boolean;
}

export interface Obligation {
  id: string;
  kind: ObligationKind;
  description: string;
  legalEntity: string;
  payee: string;
  amount: number;
  amountBasis: string;
  dueDate: string;
  payFromAccountId: string;
  payToReference: string;
  method: PaymentMethod;
  autopay: boolean;
  targetOperator: OperatorTarget;
  benCanPay: "YES" | "NO" | "UNKNOWN";
  aubreyRequired: boolean;
  aubreyReason?: string;
  fallbackReference?: string;
  fallbackTaskRef?: string;
  accountIdentityStatus: AccountIdentityStatus;
  payFromAccountStableId: string;
  state: ObligationState;
  approval: ApprovalStatus;
  evidence: EvidenceRef[];
  approvals: ApprovalLog[];
  confirmationEvidenceIds: string[];
  clearingEvidenceIds: string[];
  audit: AuditEntry[];
  createdAt: string;
  updatedAt: string;
}

export interface NonBillOutflow {
  id: string;
  type: NonBillOutflowType;
  sourceEntity: string;
  destination: string;
  amount: number;
  date: string;
  approval: ApprovalStatus;
  evidence: EvidenceRef[];
  reconciled: boolean;
  createdAt: string;
}

export interface AuditEntry {
  id: string;
  actor: string;
  at: string;
  before: ObligationState;
  after: ObligationState;
  evidenceIds: string[];
}

export interface CreateObligationInput {
  kind?: ObligationKind;
  description: string;
  legalEntity: string;
  payee?: string;
  amount?: number;
  amountBasis?: string;
  dueDate?: string;
  payFromAccountId?: string;
  payToReference?: string;
  method: PaymentMethod;
  autopay?: boolean;
  targetOperator?: OperatorTarget;
  benCanPay?: "YES" | "NO" | "UNKNOWN";
  accountIdentityStatus?: AccountIdentityStatus;
  payFromAccountStableId?: string;
  evidence?: EvidenceRef[];
  idempotencyKey: string;
}

export interface VerifyInput {
  payee: string;
  amount: number;
  dueDate: string;
  payFromAccountId: string;
  accountIdentityStatus: AccountIdentityStatus;
  payFromAccountStableId?: string;
  payToReference: string;
  amountBasis: string;
  evidence?: EvidenceRef[];
}

export interface PaymentOpsResult {
  obligation: Obligation;
  auditId: string;
  missingGates: string[];
}
