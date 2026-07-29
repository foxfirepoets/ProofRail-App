import { createHash } from "node:crypto";
import { PrismaClient } from "@prisma/client";
import { Obligation, NonBillOutflow } from "./types.js";

export interface PaymentOpsRepository {
  save(obligation: Obligation): Obligation;
  createIfAbsent(obligation: Obligation, idempotencyKey: string): Obligation;
  get(id: string): Obligation | undefined;
  list(): Obligation[];
  findByIdempotencyKey(key: string): Obligation | undefined;
  saveNonBillOutflow(outflow: NonBillOutflow): NonBillOutflow;
  listNonBillOutflows(): NonBillOutflow[];
}

export class InMemoryPaymentOpsRepository implements PaymentOpsRepository {
  private readonly obligations = new Map<string, Obligation>();
  private readonly idempotency = new Map<string, string>();
  private readonly outflows = new Map<string, NonBillOutflow>();

  save(obligation: Obligation): Obligation {
    this.obligations.set(obligation.id, obligation);
    return obligation;
  }

  createIfAbsent(obligation: Obligation, idempotencyKey: string): Obligation {
    const existing = this.findByIdempotencyKey(idempotencyKey);
    if (existing) return existing;
    this.save(obligation);
    this.rememberIdempotency(idempotencyKey, obligation.id);
    return obligation;
  }

  get(id: string): Obligation | undefined { return this.obligations.get(id); }
  list(): Obligation[] { return [...this.obligations.values()]; }
  findByIdempotencyKey(key: string): Obligation | undefined {
    const id = this.idempotency.get(key);
    return id ? this.get(id) : undefined;
  }
  rememberIdempotency(key: string, id: string): void { this.idempotency.set(key, id); }
  saveNonBillOutflow(outflow: NonBillOutflow): NonBillOutflow {
    this.outflows.set(outflow.id, outflow);
    return outflow;
  }
  listNonBillOutflows(): NonBillOutflow[] { return [...this.outflows.values()]; }
}

type PaymentOpsPrismaClient = Pick<PrismaClient, "paymentObligation" | "paymentNonBillOutflow">;
type JsonPayload = unknown;

/** Durable adapter. There is intentionally no implicit in-memory fallback. */
export class PrismaPaymentOpsRepository implements PaymentOpsRepository {
  constructor(private readonly prisma: PaymentOpsPrismaClient = new PrismaClient()) {}

  save(obligation: Obligation): Obligation {
    throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use saveAsync with Prisma");
  }

  async saveAsync(obligation: Obligation): Promise<Obligation> {
    await this.prisma.paymentObligation.upsert({
      where: { id: obligation.id },
      create: this.toRow(obligation),
      update: { state: obligation.state, payload: obligation as unknown as JsonPayload },
    });
    return obligation;
  }

  createIfAbsent(obligation: Obligation, idempotencyKey: string): Obligation {
    throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use createIfAbsentAsync with Prisma");
  }

  async createIfAbsentAsync(obligation: Obligation, idempotencyKey: string): Promise<Obligation> {
    try {
      const row = await this.prisma.paymentObligation.create({ data: this.toRow(obligation, idempotencyKey) });
      return this.fromRow(row);
    } catch (error) {
      if (isUniqueConstraintError(error)) {
        const existing = await this.prisma.paymentObligation.findUnique({ where: { idempotencyKey } });
        if (existing) return this.fromRow(existing);
      }
      throw error;
    }
  }

  get(id: string): Obligation | undefined { throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use getAsync with Prisma"); }
  async getAsync(id: string): Promise<Obligation | undefined> {
    const row = await this.prisma.paymentObligation.findUnique({ where: { id } });
    return row ? this.fromRow(row) : undefined;
  }
  list(): Obligation[] { throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use listAsync with Prisma"); }
  async listAsync(): Promise<Obligation[]> {
    const rows = await this.prisma.paymentObligation.findMany({ orderBy: { updatedAt: "desc" } });
    return rows.map((row: { payload: JsonPayload }) => this.fromRow(row));
  }
  findByIdempotencyKey(key: string): Obligation | undefined { throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use findByIdempotencyKeyAsync with Prisma"); }
  async findByIdempotencyKeyAsync(key: string): Promise<Obligation | undefined> {
    const row = await this.prisma.paymentObligation.findUnique({ where: { idempotencyKey: key } });
    return row ? this.fromRow(row) : undefined;
  }
  saveNonBillOutflow(outflow: NonBillOutflow): NonBillOutflow { throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use saveNonBillOutflowAsync with Prisma"); }
  async saveNonBillOutflowAsync(outflow: NonBillOutflow): Promise<NonBillOutflow> {
    await this.prisma.paymentNonBillOutflow.upsert({ where: { id: outflow.id }, create: { id: outflow.id, payload: outflow as unknown as JsonPayload }, update: { payload: outflow as unknown as JsonPayload } });
    return outflow;
  }
  listNonBillOutflows(): NonBillOutflow[] { throw new Error("DURABLE_REPOSITORY_ASYNC_REQUIRED: use listNonBillOutflowsAsync with Prisma"); }
  async listNonBillOutflowsAsync(): Promise<NonBillOutflow[]> {
    const rows = await this.prisma.paymentNonBillOutflow.findMany({ orderBy: { createdAt: "desc" } });
    return rows.map((row: { payload: JsonPayload }) => row.payload as NonBillOutflow);
  }

  private toRow(obligation: Obligation, idempotencyKey = obligation.id): { id: string; idempotencyKey: string; sourceDedupKey: string | null; state: string; payload: JsonPayload } {
    return { id: obligation.id, idempotencyKey, sourceDedupKey: this.sourceDedupKey(obligation), state: obligation.state, payload: obligation as unknown as JsonPayload };
  }
  private sourceDedupKey(obligation: Obligation): string | null {
    const ids = obligation.evidence.map((e) => `${e.source}:${e.sourceId}`).sort();
    return ids.length ? createHash("sha256").update(ids.join("|"), "utf8").digest("hex") : null;
  }
  private fromRow(row: { payload: JsonPayload }): Obligation { return row.payload as Obligation; }
}

function isUniqueConstraintError(error: unknown): error is { code: string } {
  return typeof error === "object" && error !== null && "code" in error && (error as { code?: unknown }).code === "P2002";
}
