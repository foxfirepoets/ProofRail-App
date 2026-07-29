import { randomUUID } from "node:crypto";
import { PaymentOpsError } from "./errors.js";
import { InMemoryPaymentOpsRepository, PaymentOpsRepository } from "./repository.js";
import {
  AccountIdentityStatus, ApprovalLog, ApprovalStatus, AuditEntry, CreateObligationInput,
  EvidenceRef, EvidenceRole, EvidenceSource, NonBillOutflow, NonBillOutflowType,
  Obligation, ObligationKind, ObligationState, OperatorTarget, PaymentOpsResult, VerifyInput, AuthenticatedPrincipal,
} from "./types.js";

export const PAYMENT_OPS_APPROVER_PRINCIPAL = "Mike";

const transitions: Record<ObligationState, ObligationState[]> = {
  [ObligationState.DISCOVERED]: [ObligationState.VERIFIED],
  [ObligationState.VERIFIED]: [ObligationState.APPROVAL_NEEDED, ObligationState.APPROVED],
  [ObligationState.APPROVAL_NEEDED]: [ObligationState.APPROVED],
  [ObligationState.APPROVED]: [ObligationState.READY_FOR_EXECUTION],
  [ObligationState.READY_FOR_EXECUTION]: [ObligationState.SCHEDULED],
  [ObligationState.SCHEDULED]: [ObligationState.PAID_PENDING_CLEARING],
  [ObligationState.PAID_PENDING_CLEARING]: [ObligationState.CLEARED],
  [ObligationState.CLEARED]: [ObligationState.RECONCILED],
  [ObligationState.RECONCILED]: [],
};

type DurablePaymentOpsRepository = PaymentOpsRepository & {
  getAsync(id: string): Promise<Obligation | undefined>;
  listAsync(): Promise<Obligation[]>;
  findByIdempotencyKeyAsync(key: string): Promise<Obligation | undefined>;
  createIfAbsentAsync(obligation: Obligation, idempotencyKey: string): Promise<Obligation>;
  saveAsync(obligation: Obligation): Promise<Obligation>;
  saveNonBillOutflowAsync(outflow: NonBillOutflow): Promise<NonBillOutflow>;
  listNonBillOutflowsAsync(): Promise<NonBillOutflow[]>;
};

export class PaymentOpsService {
  /** The default exists only for legacy unit tests; Nest production wiring injects the durable adapter. */
  constructor(public readonly repository: PaymentOpsRepository = new InMemoryPaymentOpsRepository(), private readonly trustedMutationBoundary = false, private readonly approverPolicy = trustedMutationBoundary ? process.env.PAYMENT_OPS_APPROVER_ID?.trim() : PAYMENT_OPS_APPROVER_PRINCIPAL) {}

  private durable(): DurablePaymentOpsRepository {
    const repository = this.repository as PaymentOpsRepository & Partial<DurablePaymentOpsRepository>;
    if (typeof repository.getAsync !== "function" || typeof repository.saveAsync !== "function") {
      throw new PaymentOpsError("DURABLE_REPOSITORY_REQUIRED", "Production payment operations require the durable Prisma repository", 503);
    }
    return repository as DurablePaymentOpsRepository;
  }

  private async durableCall<T>(operation: (repository: DurablePaymentOpsRepository) => Promise<T>): Promise<T> {
    try {
      return await operation(this.durable());
    } catch (error) {
      if (error instanceof PaymentOpsError) throw error;
      throw new PaymentOpsError("DURABLE_REPOSITORY_UNAVAILABLE", "The durable payment-ops repository is unavailable; no mutation was completed", 503);
    }
  }

  async createAsync(input: CreateObligationInput, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    if (!input.idempotencyKey?.trim()) throw new PaymentOpsError("IDEMPOTENCY_KEY_REQUIRED", "Create requires an idempotencyKey", 409, ["idempotencyKey"]);
    const existing = await this.durableCall((repository) => repository.findByIdempotencyKeyAsync(input.idempotencyKey));
    if (existing) return this.resultFrom(existing, existing.audit.at(-1)?.id ?? "idempotent-replay");
    const principal = this.requirePrincipal(actor);
    const created = new PaymentOpsService(new InMemoryPaymentOpsRepository(), true, this.approverPolicy).create(input, principal.id).obligation;
    const durable = await this.durableCall((repository) => repository.createIfAbsentAsync(created, input.idempotencyKey));
    return this.resultFrom(durable, durable.audit.at(-1)?.id ?? "created");
  }

  async listAsync(): Promise<Obligation[]> { return this.durableCall((repository) => repository.listAsync()); }
  async getAsync(id: string): Promise<Obligation> {
    const obligation = await this.durableCall((repository) => repository.getAsync(id));
    if (!obligation) throw new PaymentOpsError("NOT_FOUND", `Obligation ${id} was not found`, 404);
    return obligation;
  }

  async verifyAsync(id: string, input: VerifyInput, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.verify(id, input, principal.id));
  }
  async requestApprovalAsync(id: string, input: { approver?: string; approved?: boolean; requestDraftId?: string; replyThreadId?: string; scope?: string; standing?: boolean; evidence?: EvidenceRef[] }, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.requestApproval(id, { ...input, approver: principal.id }, principal.id));
  }
  async markUnavailableAsync(id: string, reason: string, actor: AuthenticatedPrincipal, fallbackTaskRef?: string): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.markUnavailable(id, reason, principal.id, fallbackTaskRef));
  }
  async markScheduledAsync(id: string, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.markScheduled(id, principal.id));
  }
  async markPaidAsync(id: string, evidence: EvidenceRef, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.markPaid(id, evidence, principal.id));
  }
  async clearAsync(id: string, evidence: EvidenceRef, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.clear(id, evidence, principal.id));
  }
  async reconcileAsync(id: string, evidence: EvidenceRef, actor: AuthenticatedPrincipal): Promise<PaymentOpsResult> {
    const principal = this.requirePrincipal(actor);
    return this.mutateAsync(id, (service) => service.reconcile(id, evidence, principal.id));
  }
  async createNonBillAsync(input: { type: NonBillOutflowType; sourceEntity: string; destination: string; amount: number; date: string; approval?: ApprovalStatus; evidence?: EvidenceRef[] }): Promise<NonBillOutflow> {
    const outflow = new PaymentOpsService(new InMemoryPaymentOpsRepository()).createNonBill(input);
    return this.durableCall((repository) => repository.saveNonBillOutflowAsync(outflow));
  }
  async listNonBillAsync(): Promise<NonBillOutflow[]> { return this.durableCall((repository) => repository.listNonBillOutflowsAsync()); }

  private async mutateAsync(id: string, operation: (service: PaymentOpsService) => PaymentOpsResult): Promise<PaymentOpsResult> {
    const current = await this.durableCall((repository) => repository.getAsync(id));
    if (!current) throw new PaymentOpsError("NOT_FOUND", `Obligation ${id} was not found`, 404);
    const memory = new InMemoryPaymentOpsRepository();
    memory.save(structuredClone(current));
    const result = operation(new PaymentOpsService(memory, this.trustedMutationBoundary, this.approverPolicy));
    const saved = await this.durableCall((repository) => repository.saveAsync(result.obligation));
    return this.resultFrom(saved, result.auditId);
  }

  private resultFrom(obligation: Obligation, auditId: string): PaymentOpsResult {
    return { obligation, auditId, missingGates: this.gates(obligation) };
  }

  create(input: CreateObligationInput, actor = "system"): PaymentOpsResult {
    if (!input.idempotencyKey?.trim()) throw new PaymentOpsError("IDEMPOTENCY_KEY_REQUIRED", "Create requires an idempotencyKey", 409, ["idempotencyKey"]);
    const existing = this.repository.findByIdempotencyKey(input.idempotencyKey);
    if (existing) return this.result(existing, existing.audit.at(-1)?.id ?? "idempotent-replay");
    const now = new Date().toISOString();
    const obligation: Obligation = {
      id: randomUUID(), kind: input.kind ?? ObligationKind.OTHER, description: input.description,
      legalEntity: input.legalEntity, payee: input.payee ?? "", amount: input.amount ?? 0,
      amountBasis: input.amountBasis ?? "", dueDate: input.dueDate ?? "",
      payFromAccountId: input.payFromAccountId ?? "", payToReference: input.payToReference ?? "",
      method: input.method, autopay: input.autopay ?? false, targetOperator: input.targetOperator ?? (input.autopay ? OperatorTarget.AUTO : OperatorTarget.BEN),
      benCanPay: input.benCanPay ?? "UNKNOWN", aubreyRequired: false,
      accountIdentityStatus: input.accountIdentityStatus ?? AccountIdentityStatus.MISSING,
      payFromAccountStableId: input.payFromAccountStableId ?? "",
      state: ObligationState.DISCOVERED,
      approval: input.autopay ? ApprovalStatus.NOT_REQUIRED : ApprovalStatus.PENDING,
      evidence: input.evidence ?? [], approvals: [], confirmationEvidenceIds: [], clearingEvidenceIds: [],
      audit: [], createdAt: now, updatedAt: now,
    };
    this.repository.createIfAbsent(obligation, input.idempotencyKey);
    const auditId = this.audit(obligation, actor, ObligationState.DISCOVERED, ObligationState.DISCOVERED, []);
    return this.result(obligation, auditId);
  }

  list(): Obligation[] { return this.repository.list(); }
  get(id: string): Obligation { return this.require(id); }

  verify(id: string, input: VerifyInput, actor = "system"): PaymentOpsResult {
    const obligation = this.require(id);
    this.assertState(obligation, ObligationState.DISCOVERED);
    const missing = this.missingVerification(input);
    if (missing.length) throw new PaymentOpsError("NEEDS_VERIFICATION", "Verification is incomplete", 409, missing);
    const accountEvidence = (input.evidence ?? []).find((e) => e.role === EvidenceRole.ACCOUNT_IDENTITY);
    const accountEvidenceSet = (input.evidence ?? []).filter((e) => e.role === EvidenceRole.ACCOUNT_IDENTITY);
    const identityConflict = accountEvidenceSet.some((e) =>
      e.accountId !== input.payFromAccountId ||
      e.stableAccountId !== input.payFromAccountStableId ||
      !this.authoritativeAccountSource(e.source) ||
      e.accountLegalOwner !== accountEvidence?.accountLegalOwner ||
      e.accountInstitution !== accountEvidence?.accountInstitution ||
      e.accountType !== accountEvidence?.accountType ||
      e.providerReference !== accountEvidence?.providerReference ||
      e.fingerprint !== accountEvidence?.fingerprint,
    ) || new Set(accountEvidenceSet.map((e) => `${e.accountId}:${e.stableAccountId}`)).size > 1;
    if (!accountEvidence || !this.validEvidence(accountEvidence, {
      allowedSources: [EvidenceSource.DRIVE, EvidenceSource.STATEMENT, EvidenceSource.BANK_FEED, EvidenceSource.WORKBOOK],
      obligationId: id,
      accountId: input.payFromAccountId,
      stableAccountId: input.payFromAccountStableId,
      requireAmount: false,
      requireTransactionDate: false,
      requireProviderMetadata: true,
      requireVerifiedProvenance: this.trustedMutationBoundary,
      requireAccountIdentityMetadata: true,
    }) || identityConflict || !input.payFromAccountStableId) {
      throw new PaymentOpsError("ACCOUNT_IDENTITY_EVIDENCE_REQUIRED", "Verification requires evidence-backed stable pay-from account identity", 409, ["accountIdentityEvidence", "payFromAccountStableId"]);
    }
    obligation.payee = input.payee;
    obligation.amount = input.amount;
    obligation.dueDate = input.dueDate;
    obligation.payFromAccountId = input.payFromAccountId;
    obligation.accountIdentityStatus = input.accountIdentityStatus;
    obligation.payFromAccountStableId = input.payFromAccountStableId;
    obligation.payToReference = input.payToReference;
    obligation.amountBasis = input.amountBasis;
    obligation.evidence = [...obligation.evidence, ...(input.evidence ?? [])];
    obligation.updatedAt = new Date().toISOString();
    const evidenceIds = input.evidence?.map((e) => e.id) ?? [];
    const verifiedAuditId = this.transition(obligation, ObligationState.VERIFIED, actor, evidenceIds);
    obligation.approval = obligation.autopay ? ApprovalStatus.NOT_REQUIRED : ApprovalStatus.PENDING;
    if (!obligation.autopay) return this.result(obligation, verifiedAuditId);
    const approvedAuditId = this.transition(obligation, ObligationState.APPROVED, actor, evidenceIds);
    return this.result(obligation, approvedAuditId);
  }

  requestApproval(id: string, input: { approver?: string; approved?: boolean; requestDraftId?: string; replyThreadId?: string; scope?: string; standing?: boolean; evidence?: EvidenceRef[] }, actor = "system"): PaymentOpsResult {
    this.assertActor(actor);
    if (!input.approver?.trim() || typeof input.approved !== "boolean") throw new PaymentOpsError("APPROVAL_CONTEXT_REQUIRED", "Approval requires an explicit approver and approved boolean", 409, ["approver", "approved"]);
    if (input.approver.trim() !== actor.trim()) throw new PaymentOpsError("APPROVER_ACTOR_MISMATCH", "Approval actor must match the authenticated approver", 403, ["approver"]);
    const approvalEvidence = (input.evidence ?? []).some((e) => this.validEvidence(e, {
      allowedSources: [EvidenceSource.GMAIL, EvidenceSource.DRIVE, EvidenceSource.CALENDAR, EvidenceSource.WORKBOOK],
      role: EvidenceRole.APPROVAL,
      requireAmount: false,
      requireTransactionDate: false,
      requireProviderMetadata: false,
    }));
    if (!approvalEvidence && !input.requestDraftId?.trim() && !input.replyThreadId?.trim()) throw new PaymentOpsError("APPROVAL_EVIDENCE_REQUIRED", "Approval requires approval evidence, requestDraftId, or replyThreadId", 409, ["approvalEvidence"]);
    const obligation = this.require(id);
    if (obligation.state === ObligationState.VERIFIED) this.transition(obligation, ObligationState.APPROVAL_NEEDED, actor, input.evidence?.map((e) => e.id) ?? []);
    this.assertState(obligation, ObligationState.APPROVAL_NEEDED);
    const approval: ApprovalLog = { id: randomUUID(), obligationId: id, approver: input.approver.trim(), status: input.approved ? ApprovalStatus.APPROVED : ApprovalStatus.PENDING, requestDraftId: input.requestDraftId, replyThreadId: input.replyThreadId, timestamp: new Date().toISOString(), scope: input.scope ?? "transaction", standing: input.standing ?? false };
    obligation.approvals.push(approval);
    obligation.evidence.push(...(input.evidence ?? []));
    if (!input.approved) { obligation.approval = ApprovalStatus.PENDING; return this.result(obligation, approval.id); }
    obligation.approval = ApprovalStatus.APPROVED;
    const auditId = this.transition(obligation, ObligationState.APPROVED, actor, input.evidence?.map((e) => e.id) ?? []);
    return this.result(obligation, auditId);
  }

  markUnavailable(id: string, reason: string, actor = "system", fallbackTaskRef?: string): PaymentOpsResult {
    if (!reason?.trim()) throw new PaymentOpsError("AUBREY_REASON_REQUIRED", "Fallback requires an explicit reason", 409, ["aubreyReason"]);
    const obligation = this.require(id);
    if (![ObligationState.DISCOVERED, ObligationState.VERIFIED, ObligationState.APPROVAL_NEEDED, ObligationState.APPROVED, ObligationState.READY_FOR_EXECUTION].includes(obligation.state)) throw new PaymentOpsError("FALLBACK_TOO_LATE", "Aubrey fallback is only allowed before scheduling", 409, ["state"]);
    if (!fallbackTaskRef?.trim()) throw new PaymentOpsError("AUBREY_TASK_REF_REQUIRED", "Fallback requires a draft or task reference", 409, ["fallbackTaskRef"]);
    obligation.targetOperator = OperatorTarget.AUBREY; obligation.aubreyRequired = true; obligation.aubreyReason = reason.trim(); obligation.fallbackTaskRef = fallbackTaskRef.trim(); obligation.updatedAt = new Date().toISOString();
    return this.result(obligation, this.audit(obligation, actor, obligation.state, obligation.state, []));
  }

  markScheduled(id: string, actor = "system"): PaymentOpsResult {
    const obligation = this.require(id);
    if (obligation.state === ObligationState.APPROVED) this.transition(obligation, ObligationState.READY_FOR_EXECUTION, actor, []);
    return this.moveExecutable(id, ObligationState.SCHEDULED, actor);
  }

  markPaid(id: string, confirmation: EvidenceRef, actor = "system"): PaymentOpsResult {
    const obligation = this.require(id); this.assertState(obligation, ObligationState.SCHEDULED);
    if (!this.validEvidence(confirmation, {
      allowedSources: [EvidenceSource.BANK_FEED, EvidenceSource.STATEMENT],
      role: EvidenceRole.PAYMENT_CONFIRMATION,
      obligationId: id,
      accountId: obligation.payFromAccountId,
      stableAccountId: obligation.payFromAccountStableId,
      amount: obligation.amount,
      requireAmount: true,
      requireTransactionDate: true,
      requireProviderMetadata: true,
      requireVerifiedProvenance: this.trustedMutationBoundary,
    })) throw new PaymentOpsError("CONFIRMATION_REQUIRED", "Payment confirmation evidence must be complete, linked, and amount-matched", 409, ["confirmation"]);
    obligation.evidence.push(confirmation); obligation.confirmationEvidenceIds.push(confirmation.id);
    const auditId = this.transition(obligation, ObligationState.PAID_PENDING_CLEARING, actor, [confirmation.id]); return this.result(obligation, auditId);
  }

  clear(id: string, evidence: EvidenceRef, actor = "system"): PaymentOpsResult {
    const obligation = this.require(id);
    if (!this.validEvidence(evidence, {
      allowedSources: [EvidenceSource.BANK_FEED, EvidenceSource.STATEMENT],
      role: EvidenceRole.CLEARING_PROOF,
      obligationId: id,
      accountId: obligation.payFromAccountId,
      stableAccountId: obligation.payFromAccountStableId,
      amount: obligation.amount,
      requireAmount: true,
      requireTransactionDate: true,
      requireProviderMetadata: true,
      requireVerifiedProvenance: this.trustedMutationBoundary,
    })) throw new PaymentOpsError("BANK_EVIDENCE_REQUIRED", "Bank clearing evidence must be complete, bank-sourced, linked, and amount-matched", 409, ["clearingEvidence"]);
    this.assertState(obligation, ObligationState.PAID_PENDING_CLEARING);
    obligation.evidence.push(evidence); obligation.clearingEvidenceIds.push(evidence.id);
    const auditId = this.transition(obligation, ObligationState.CLEARED, actor, [evidence.id]); return this.result(obligation, auditId);
  }

  reconcile(id: string, evidence: EvidenceRef, actor = "system"): PaymentOpsResult {
    const obligation = this.require(id); this.assertState(obligation, ObligationState.CLEARED);
    if (!this.validEvidence(evidence, {
      allowedSources: [EvidenceSource.BANK_FEED, EvidenceSource.STATEMENT],
      role: EvidenceRole.RECONCILIATION,
      obligationId: id,
      accountId: obligation.payFromAccountId,
      stableAccountId: obligation.payFromAccountStableId,
      amount: obligation.amount,
      requireAmount: true,
      requireTransactionDate: true,
      requireProviderMetadata: true,
    })) throw new PaymentOpsError("RECONCILIATION_PROOF_REQUIRED", "Reconciliation evidence must be complete, linked, and amount-matched", 409, ["reconciliationEvidence"]);
    obligation.evidence.push(evidence);
    const auditId = this.transition(obligation, ObligationState.RECONCILED, actor, [evidence.id]); return this.result(obligation, auditId);
  }

  createNonBill(input: { type: NonBillOutflowType; sourceEntity: string; destination: string; amount: number; date: string; approval?: ApprovalStatus; evidence?: EvidenceRef[] }): NonBillOutflow {
    if (!input.sourceEntity || !input.destination || !Number.isFinite(input.amount) || input.amount <= 0 || !input.date) throw new PaymentOpsError("INVALID_NON_BILL_OUTFLOW", "Non-bill outflow requires source, destination, amount, and date", 422);
    return this.repository.saveNonBillOutflow({ id: randomUUID(), ...input, approval: input.approval ?? ApprovalStatus.PENDING, evidence: input.evidence ?? [], reconciled: false, createdAt: new Date().toISOString() });
  }
  listNonBill(): NonBillOutflow[] { return this.repository.listNonBillOutflows(); }

  private moveExecutable(id: string, next: ObligationState, actor: string): PaymentOpsResult {
    const obligation = this.require(id); this.assertState(obligation, ObligationState.READY_FOR_EXECUTION);
    if (obligation.accountIdentityStatus !== AccountIdentityStatus.VERIFIED || !obligation.payFromAccountStableId || !obligation.payee || obligation.amount <= 0 || !obligation.amountBasis || !obligation.dueDate || !obligation.payToReference || (!obligation.autopay && obligation.benCanPay === "UNKNOWN") || (!obligation.autopay && obligation.approval !== ApprovalStatus.APPROVED)) throw new PaymentOpsError("EXECUTION_GATES_BLOCKED", "Obligation is not executable", 409, this.gates(obligation));
    const auditId = this.transition(obligation, next, actor, []); return this.result(obligation, auditId);
  }
  private missingVerification(input: VerifyInput): string[] { return [!input.payee && "payee", !(input.amount > 0) && "amount", !input.amountBasis?.trim() && "amountBasis", !input.dueDate && "dueDate", !input.payFromAccountId && "payFromAccountId", !input.payFromAccountStableId && "payFromAccountStableId", !input.payToReference && "payToReference", input.accountIdentityStatus !== AccountIdentityStatus.VERIFIED && "accountIdentity"].filter((x): x is string => Boolean(x)); }
  private gates(o: Obligation): string[] { return [o.accountIdentityStatus !== AccountIdentityStatus.VERIFIED && "accountIdentity", !o.payFromAccountStableId && "payFromAccountStableId", !o.payee && "payee", !(o.amount > 0) && "amount", !o.amountBasis && "amountBasis", !o.dueDate && "dueDate", !o.payToReference && "payToReference", !o.autopay && o.approval !== ApprovalStatus.APPROVED && "approval", !o.autopay && o.benCanPay === "UNKNOWN" && "benCanPay"].filter((x): x is string => Boolean(x)); }
  private authoritativeAccountSource(source: EvidenceSource): boolean { return [EvidenceSource.DRIVE, EvidenceSource.STATEMENT, EvidenceSource.BANK_FEED, EvidenceSource.WORKBOOK].includes(source); }
  private validEvidence(evidence: EvidenceRef | undefined, options: {
    allowedSources: EvidenceSource[];
    role?: EvidenceRole;
    obligationId?: string;
    accountId?: string;
    stableAccountId?: string;
    amount?: number;
    requireAmount: boolean;
    requireTransactionDate?: boolean;
    requireProviderMetadata?: boolean;
    requireVerifiedProvenance?: boolean;
    requireAccountIdentityMetadata?: boolean;
  }): boolean {
    const transactionDateValid = !options.requireTransactionDate || Boolean(evidence?.transactionDate?.trim() && !Number.isNaN(Date.parse(evidence.transactionDate)));
    const linkageValid = (!options.obligationId || evidence?.obligationId === options.obligationId) &&
      (!options.accountId || evidence?.accountId === options.accountId) &&
      (!options.stableAccountId || evidence?.stableAccountId === options.stableAccountId);
    const providerMetadataValid = !options.requireProviderMetadata || (this.trustedMutationBoundary
      ? Boolean(evidence?.providerReference?.trim() && evidence?.fingerprint?.trim())
      : Boolean(evidence?.providerReference?.trim() || evidence?.fingerprint?.trim()));
    const trustedProvenanceValid = !options.requireVerifiedProvenance || Boolean(
      evidence?.provenanceVerified === true && evidence.provenanceCredentialId?.trim() && evidence.provenancePayloadHash?.trim() && evidence.providerImmutableId?.trim() && evidence.hash === evidence.provenancePayloadHash && evidence.fingerprint === evidence.provenancePayloadHash,
    );
    const accountIdentityMetadataValid = !options.requireAccountIdentityMetadata || Boolean(
      evidence?.accountId?.trim() && evidence.stableAccountId?.trim() && evidence.accountLegalOwner?.trim() &&
      evidence.accountInstitution?.trim() && evidence.accountType?.trim(),
    );
    if (!evidence || !evidence.id?.trim() || !evidence.sourceId?.trim() || !evidence.capturedAt?.trim() || Number.isNaN(Date.parse(evidence.capturedAt)) || !options.allowedSources.includes(evidence.source) || (options.role && evidence.role !== options.role) || !linkageValid || !transactionDateValid || !providerMetadataValid || !trustedProvenanceValid || !accountIdentityMetadataValid) return false;
    if (options.requireAmount && (!Number.isFinite(evidence.amount) || Math.abs((evidence.amount as number) - (options.amount as number)) > 0.01)) return false;
    return true;
  }
  private assertActor(actor: string): void {
    if (!actor?.trim() || !this.approverPolicy || actor !== this.approverPolicy) throw new PaymentOpsError("AUTHENTICATION_REQUIRED", "The authenticated principal is not authorized", 401);
  }
  private requirePrincipal(actor: AuthenticatedPrincipal): AuthenticatedPrincipal {
    if (!actor || actor.verified !== true || !actor.id?.trim() || !actor.issuer?.trim() || !Array.isArray(actor.roles) || !actor.roles.includes("payment-ops")) throw new PaymentOpsError("AUTHENTICATION_REQUIRED", "A server-verified payment-ops principal is required", 401);
    return actor;
  }
  private assertState(o: Obligation, expected: ObligationState): void { if (o.state !== expected) throw new PaymentOpsError("INVALID_STATE", `Expected ${expected}; found ${o.state}`, 409, [expected]); }
  private transition(o: Obligation, next: ObligationState, actor: string, evidenceIds: string[]): string { if (!transitions[o.state].includes(next)) throw new PaymentOpsError("INVALID_STATE_TRANSITION", `Cannot transition ${o.state} to ${next}`, 409, [next]); const id = this.audit(o, actor, o.state, next, evidenceIds); o.state = next; o.updatedAt = new Date().toISOString(); return id; }
  private audit(o: Obligation, actor: string, before: ObligationState, after: ObligationState, evidenceIds: string[]): string { const entry: AuditEntry = { id: randomUUID(), actor, at: new Date().toISOString(), before, after, evidenceIds }; o.audit.push(entry); return entry.id; }
  private require(id: string): Obligation { const o = this.repository.get(id); if (!o) throw new PaymentOpsError("NOT_FOUND", `Obligation ${id} was not found`, 404); return o; }
  private result(obligation: Obligation, auditId: string): PaymentOpsResult { this.repository.save(obligation); return { obligation, auditId, missingGates: this.gates(obligation) }; }
}
