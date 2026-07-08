import { createHash, randomUUID } from "node:crypto";
import { moneyLocked, notFound, ProofRailError, stateConflict } from "./errors.js";
import { deterministicRequestId, type QboClient } from "./qbo.js";
import type { ProofClient } from "./proof.js";
import type { ProofRailRepository } from "./repository.js";
import type {
  ApproveInput,
  DrawReconcileVariance,
  DrawRecord,
  FeeRunRecord,
  FeeStream,
  GateRunRecord,
  IntakeRecord,
  IntakeStatus,
  LookupCodingInput,
  LookupCodingSuggestion,
  ReconcileDrawSheetInput,
  SubmitIntakeInput,
  ProofStamp,
} from "./types.js";

const APPROVABLE = new Set(["PENDING_APPROVAL", "QUARANTINED"]);
const NO_DEV_FEE = new Set(["12SB", "SUMMA ELITE"]);

export class ProofRailService {
  constructor(
    private readonly repo: ProofRailRepository,
    private readonly proof: ProofClient,
    private readonly qbo: QboClient,
  ) {}

  async submitIntake(input: SubmitIntakeInput, actorKey = "local"): Promise<unknown> {
    const existing = await this.repo.findIntakeByGmailMsgId(input.email_meta.gmail_msg_id);
    if (existing) {
      const result = this.intakeResult(existing, existing.proof, []);
      await this.audit("submit_intake", input, result, actorKey);
      return result;
    }

    let proofResult: Awaited<ReturnType<ProofClient["verifyInvoice"]>>;
    try {
      proofResult = await this.proof.verifyInvoice(input);
    } catch (error) {
      proofResult = {
        verdict: "FLAG",
        flags: ["PR-003"],
        proof: this.localFailureProof("INVOICE_PROOF", input),
      };
    }

    const lowConfidence = (input.suggested_coding?.confidence ?? 1) < 0.8;
    const status = proofResult.verdict === "PASS" && !lowConfidence ? "PENDING_APPROVAL" : "QUARANTINED";
    const intake: IntakeRecord = {
      id: randomUUID(),
      gmailMsgId: input.email_meta.gmail_msg_id,
      vendorRaw: input.parsed_invoice.vendor,
      parsed: input.parsed_invoice,
      amount: input.parsed_invoice.total,
      entity: input.suggested_coding?.entity,
      project: input.suggested_coding?.project,
      item: input.suggested_coding?.item,
      status,
      quarantineReason: status === "QUARANTINED" ? [...proofResult.flags, lowConfidence ? "LOW_CONFIDENCE" : ""].filter(Boolean).join(",") : undefined,
      proof: proofResult.proof,
      flags: proofResult.flags,
      createdAt: new Date(),
    };
    await this.repo.saveIntake(intake);
    const result = this.intakeResult(intake, proofResult.proof, proofResult.flags);
    await this.audit("submit_intake", input, result, actorKey);
    return result;
  }

  async approve(input: ApproveInput, actorKey = "local"): Promise<unknown> {
    const intake = await this.requiredIntake(input.intake_id);
    if (!APPROVABLE.has(intake.status)) {
      throw stateConflict("Intake is not approvable.", { intake_id: intake.id, status: intake.status });
    }
    if (intake.status === "QUARANTINED" && (!input.override_reason || input.override_reason.trim().length < 20)) {
      throw new ProofRailError("PR-002", "QUARANTINED approvals require an override_reason of at least 20 characters.", 400);
    }

    const coding = input.coding_final ?? this.requiredCoding(intake);
    const requestId = deterministicRequestId([intake.gmailMsgId, intake.vendorRaw, intake.parsed.invoice_no, String(intake.amount)]);
    intake.status = "SYNCING";
    intake.entity = coding.entity;
    intake.project = coding.project;
    intake.item = coding.item;
    intake.requestId = requestId;
    intake.overrideReason = input.override_reason;
    await this.repo.saveIntake(intake);

    const bill = await this.qbo.createBill({
      vendor: intake.vendorRaw,
      amount: intake.amount,
      entity: coding.entity,
      project: coding.project,
      item: coding.item,
      requestId,
      payload: intake.parsed,
    });
    const proof = await this.proof.recordWorkflowEvent({ kind: "qbo_bill", intake_id: intake.id, requestId, qboTxnId: bill.qboTxnId });
    intake.status = "PROOFED";
    intake.qboTxnId = bill.qboTxnId;
    intake.proof = proof;
    await this.repo.saveIntake(intake);
    const result = { intake_id: intake.id, status: intake.status, qbo_txn_id: bill.qboTxnId, proof };
    await this.audit("approve", input, result, actorKey);
    return result;
  }

  async reject(input: { intake_id: string; reason: string }, actorKey = "local"): Promise<unknown> {
    const intake = await this.requiredIntake(input.intake_id);
    if (!APPROVABLE.has(intake.status)) {
      throw stateConflict("Intake is not rejectable.", { intake_id: intake.id, status: intake.status });
    }
    intake.status = "REJECTED";
    await this.repo.saveIntake(intake);
    const result = { intake_id: intake.id, status: "REJECTED" };
    await this.audit("reject", input, result, actorKey);
    return result;
  }

  async listQueue(input: { status?: IntakeStatus[]; entity?: string; limit?: number }): Promise<unknown> {
    const items = await this.repo.listIntakes(input);
    const all = await this.repo.listIntakes({ status: ["QUARANTINED"], limit: 10_000 });
    const latest = await this.repo.latestGateRun();
    const now = Date.now();
    return {
      items: items.map((r) => ({
        intake_id: r.id,
        vendor: r.vendorRaw,
        amount: r.amount,
        invoice_no: r.parsed.invoice_no,
        coding: { entity: r.entity, project: r.project, item: r.item },
        status: r.status,
        flags: r.flags ?? [],
        proof: r.proof,
        age_hours: Math.round(((now - r.createdAt.getTime()) / 3_600_000) * 10) / 10,
      })),
      quarantined_count: all.length,
      money_lock: latest?.moneyLock ?? true,
    };
  }

  /** F6 — reconcile_draw_sheet. Real, checkable math today: line-arithmetic tie-out and a
   *  retainage-math sanity check. Cost-basis-vs-QBO-committed comparison (MARKUP/NO_BASIS
   *  detection) needs the QBO-committed-costs read wired up (P5) — until then those two flag
   *  types are never emitted, per PR-043 (never guess; a missing basis is FLAGged as NO_BASIS
   *  only when we can actually prove there's no basis, not by default). */
  async reconcileDrawSheet(input: ReconcileDrawSheetInput, actorKey = "local"): Promise<unknown> {
    const variance: DrawReconcileVariance[] = [];
    let anyFlag = false;

    for (const line of input.extracted_lines) {
      const retainageExpected = Math.round((line.total_to_date - line.this_period) * 10000) / 10000;
      const billed = line.this_period;
      const basis = line.total_to_date;
      const delta = Math.round((billed - (basis - (line.retainage ?? 0)) ) * 100) / 100;

      let flag: DrawReconcileVariance["flag"] | undefined;
      if (line.retainage !== undefined && Math.abs(line.retainage) > Math.abs(basis) * 0.15 + 0.01) {
        // retainage larger than 15% of total-to-date is outside every known STV GC rate (Concord 5% / Elite 10%)
        flag = "RETAINAGE_MATH";
      }
      if (flag) anyFlag = true;

      variance.push({
        line: line.cost_code ? `${line.cost_code} ${line.description}` : line.description,
        billed,
        basis,
        prior_draws: Math.round((basis - billed) * 100) / 100,
        delta,
        flag,
      });
      void retainageExpected;
    }

    const record = {
      id: randomUUID(),
      project: input.project,
      gc: input.gc,
      period: input.period,
      verdict: (anyFlag ? "FLAG" : "PASS") as "PASS" | "FLAG",
      variance,
      proof: await this.proof.recordWorkflowEvent({ kind: "draw_reconcile", input }),
    };
    await this.repo.saveDrawReconcile(record);
    const result = { reconcile_id: record.id, verdict: record.verdict, variance: record.variance, proof: record.proof };
    await this.audit("reconcile_draw_sheet", input, result, actorKey);
    return result;
  }

  /** lookup_coding — read-only memory prosthetic. Looks up prior (entity, project, item) coding
   *  by vendor from VendorHistory (seeded via seedVendorHistory — populate from obgen's historical
   *  extract or from approved intakes over time). Returns entity_notes for the known no-fee
   *  entities so Cowork never proposes a FEE-DEV item on 12SB / Summa Elite. */
  async lookupCoding(input: LookupCodingInput): Promise<unknown> {
    const history = await this.repo.findVendorHistory(input.vendor);
    const suggestions: LookupCodingSuggestion[] = [];
    if (history) {
      suggestions.push({
        entity: history.entity,
        project: history.project,
        item: history.item,
        confidence: 0.9,
        based_on: "HISTORY",
      });
    }
    const entityNotes: string[] = [];
    for (const entity of NO_DEV_FEE) {
      entityNotes.push(`${entity}: NO developer fee (OAEA)`);
    }
    return {
      canonical_vendor: history?.vendorCanonical,
      suggestions,
      entity_notes: entityNotes,
      bank_baseline: history?.bankAcctLast4 ? { acct_last4: history.bankAcctLast4 } : undefined,
    };
  }

  async getGateStatus(): Promise<unknown> {
    const gate = await this.repo.latestGateRun();
    if (!gate) {
      return { run_date: null, verdict: "RED", money_lock: true, green_streak_days: 0, results: [], bundle_proof: null };
    }
    return {
      run_date: gate.runDate.toISOString().slice(0, 10),
      verdict: gate.verdict,
      money_lock: gate.moneyLock,
      green_streak_days: gate.verdict === "GREEN" ? 1 : 0,
      results: gate.results,
      bundle_proof: gate.bundleProof,
    };
  }

  async saveGateRun(verdict: "GREEN" | "RED", results: GateRunRecord["results"]): Promise<GateRunRecord> {
    const bundleProof = await this.proof.recordAuditBundle({ verdict, results });
    return this.repo.saveGateRun({
      id: randomUUID(),
      runDate: new Date(),
      verdict,
      moneyLock: verdict === "RED",
      results,
      bundleProof,
    });
  }

  async buildDraw(input: { project: string; period: string; lender: string }, actorKey = "local"): Promise<unknown> {
    const latest = await this.repo.latestGateRun();
    const gateAgeMs = latest ? Date.now() - latest.runDate.getTime() : Number.POSITIVE_INFINITY;
    if (!latest || latest.verdict !== "GREEN" || gateAgeMs > 24 * 60 * 60 * 1000) {
      throw new ProofRailError("PR-030", "Cannot build draw without a fresh GREEN gate.", 423);
    }
    const draw: DrawRecord = {
      id: randomUUID(),
      project: input.project,
      period: input.period,
      lender: input.lender,
      status: "PROOFED",
      chainHash: createHash("sha256").update(JSON.stringify(input)).digest("hex"),
    };
    await this.repo.saveDraw(draw);
    const result = { draw_id: draw.id, status: "ASSEMBLED", chain_hash: draw.chainHash, bva_summary: { budget: 0, committed: 0, actual: 0, this_draw: 0 } };
    await this.audit("build_draw", input, result, actorKey);
    return result;
  }

  async sendDraw(input: { draw_id: string; confirm: true }, actorKey = "local"): Promise<unknown> {
    await this.assertMoneyOpen("send_draw");
    const draw = await this.repo.findDraw(input.draw_id);
    if (!draw) {
      throw notFound("Draw not found.", { draw_id: input.draw_id });
    }
    if (draw.status !== "PROOFED") {
      throw stateConflict("Draw must be PROOFED before send.", { draw_id: input.draw_id, status: draw.status });
    }
    draw.status = "SENT";
    draw.sentAt = new Date();
    draw.proof = await this.proof.recordWorkflowEvent({ kind: "draw_sent", draw_id: draw.id });
    await this.repo.saveDraw(draw);
    const result = { draw_id: draw.id, status: "SENT", sent_at: draw.sentAt.toISOString(), proof: draw.proof };
    await this.audit("send_draw", input, result, actorKey);
    return result;
  }

  async runFees(input: { period: string }, actorKey = "local"): Promise<unknown> {
    const registries = await this.repo.listEntityRegistry();
    const feeRuns = [];
    const skipped = [];
    for (const registry of registries) {
      const entityKey = registry.entity.toUpperCase();
      if (!registry.feeRate || !registry.feePayee || !registry.feeBase || NO_DEV_FEE.has(entityKey)) {
        skipped.push({ entity: registry.entity, reason: "NO_FEE_OAEA" });
        continue;
      }
      if (entityKey === "12SB" && /land/i.test(registry.feeBase)) {
        skipped.push({ entity: registry.entity, reason: "NO_FEE_OAEA" });
        continue;
      }
      const existing = await this.repo.findFeeRunByUnique(input.period, registry.entity, "DEV_CM");
      const run: FeeRunRecord = existing ?? {
        id: randomUUID(),
        stream: "DEV_CM",
        period: input.period,
        entity: registry.entity,
        base: 0,
        rate: registry.feeRate,
        payee: registry.feePayee,
        status: "PENDING_APPROVAL",
      };
      await this.repo.saveFeeRun(run);
      feeRuns.push({ fee_run_id: run.id, entity: run.entity, base: run.base, rate: run.rate, fee: run.base * run.rate, payee: run.payee, status: "PENDING_APPROVAL" });
    }
    const latest = await this.repo.latestGateRun();
    const result = { fee_runs: feeRuns, skipped, money_lock: latest?.moneyLock ?? true };
    await this.audit("run_fees", input, result, actorKey);
    return result;
  }

  async approveFees(input: { fee_run_ids: string[] }, actorKey = "local"): Promise<unknown> {
    await this.assertMoneyOpen("approve_fees");
    const posted = [];
    const failed = [];
    for (const id of input.fee_run_ids) {
      const run = await this.repo.findFeeRun(id);
      if (!run) {
        throw notFound("Fee run not found.", { fee_run_id: id });
      }
      if (run.status !== "PENDING_APPROVAL") {
        throw stateConflict("Fee run must be PENDING_APPROVAL.", { fee_run_id: id, status: run.status });
      }
      const pair = await this.qbo.postFeePair({
        feeRunId: run.id,
        entity: run.entity,
        period: run.period,
        amount: run.base * run.rate,
        requestId: deterministicRequestId([run.period, run.entity, run.stream]),
      });
      if (pair.failed) {
        run.status = "FAILED";
        run.billTxnId = pair.billTxnId;
        await this.repo.saveFeeRun(run);
        failed.push({ fee_run_id: run.id, error: "PR-020", voided: Boolean(pair.voided) });
        continue;
      }
      const proof = await this.proof.recordWorkflowEvent({ kind: "fee_pair", fee_run_id: run.id, pair });
      run.status = "POSTED";
      run.invoiceTxnId = pair.invoiceTxnId;
      run.billTxnId = pair.billTxnId;
      run.proof = proof;
      await this.repo.saveFeeRun(run);
      posted.push({ fee_run_id: run.id, invoice_txn_id: pair.invoiceTxnId, bill_txn_id: pair.billTxnId, proof });
    }
    const result = { posted, failed };
    await this.audit("approve_fees", input, result, actorKey);
    return result;
  }

  private async requiredIntake(id: string): Promise<IntakeRecord> {
    const intake = await this.repo.findIntakeById(id);
    if (!intake) {
      throw notFound("Intake not found.", { intake_id: id });
    }
    return intake;
  }

  private requiredCoding(intake: IntakeRecord): { entity: string; project: string; item: string } {
    if (!intake.entity || !intake.project || !intake.item) {
      throw new ProofRailError("PR-043", "Missing project/entity/item coding; ProofRail never guesses.", 400);
    }
    return { entity: intake.entity, project: intake.project, item: intake.item };
  }

  private async assertMoneyOpen(tool: string): Promise<void> {
    const latest = await this.repo.latestGateRun();
    if (!latest || latest.moneyLock || latest.verdict === "RED") {
      throw moneyLocked(`${tool} is locked because the latest gate is RED or missing.`, { tool, gate: latest?.id });
    }
  }

  private intakeResult(intake: IntakeRecord, proof: ProofStamp | undefined, flags: string[]): unknown {
    return {
      intake_id: intake.id,
      status: intake.status,
      proof,
      flags,
      duplicate_of: undefined,
    };
  }

  private async audit(tool: string, input: unknown, result: unknown, actorKey: string): Promise<void> {
    await this.repo.audit({
      tool,
      input,
      result,
      actorKey: this.fingerprint(actorKey),
    });
  }

  private fingerprint(actorKey: string): string {
    return createHash("sha256").update(actorKey).digest("hex").slice(0, 16);
  }

  private localFailureProof(product: ProofStamp["product"], input: unknown): ProofStamp {
    const chainHash = createHash("sha256").update(`failure:${JSON.stringify(input)}`).digest("hex");
    return {
      proof_id: `local_fail_${chainHash.slice(0, 12)}`,
      chain_hash: chainHash,
      verify_url: `/api/proof/local_fail_${chainHash.slice(0, 12)}/verify`,
      product,
    };
  }
}
