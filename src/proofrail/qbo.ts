import { createHash } from "node:crypto";
import { ProofRailError } from "./errors.js";

export interface QboBillRequest {
  vendor: string;
  amount: number;
  entity: string;
  project: string;
  item: string;
  requestId: string;
  payload: unknown;
}

export interface QboFeePairRequest {
  feeRunId: string;
  entity: string;
  period: string;
  amount: number;
  requestId: string;
}

export interface QboFeePairResult {
  invoiceTxnId?: string;
  billTxnId?: string;
  failed?: true;
  voided?: boolean;
}

export interface QboClient {
  createBill(request: QboBillRequest): Promise<{ qboTxnId: string; duplicate?: boolean }>;
  postFeePair(request: QboFeePairRequest): Promise<QboFeePairResult>;
}

export function deterministicRequestId(parts: string[]): string {
  return createHash("sha1").update(parts.join("|")).digest("hex").slice(0, 36);
}

export class FakeQboClient implements QboClient {
  public failNextFeePair = false;
  private readonly bills = new Map<string, string>();

  async createBill(request: QboBillRequest): Promise<{ qboTxnId: string; duplicate?: boolean }> {
    const existing = this.bills.get(request.requestId);
    if (existing) {
      return { qboTxnId: existing, duplicate: true };
    }
    const qboTxnId = `bill_${this.bills.size + 1}`;
    this.bills.set(request.requestId, qboTxnId);
    return { qboTxnId };
  }

  async postFeePair(request: QboFeePairRequest): Promise<QboFeePairResult> {
    if (this.failNextFeePair) {
      this.failNextFeePair = false;
      return { billTxnId: `bill_${request.feeRunId}`, failed: true, voided: true };
    }
    return {
      invoiceTxnId: `invoice_${request.feeRunId}`,
      billTxnId: `bill_${request.feeRunId}`,
    };
  }
}

export function assertNoPaymentEntity(entityName: string): void {
  if (/billpayment|payment|transfer|charge/i.test(entityName)) {
    throw new ProofRailError("PR-043", "Payment and transfer entities are outside ProofRail's money boundary.", 400);
  }
}
