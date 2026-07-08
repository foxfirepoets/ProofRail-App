import pg from "pg";
import type { ProofRailRepository } from "./repository.js";
import type {
  AuditRecord,
  DrawReconcileRecord,
  DrawRecord,
  EntityRegistryRecord,
  FeeRunRecord,
  GateRunRecord,
  IntakeRecord,
  IntakeStatus,
  VendorHistoryRecord,
} from "./types.js";

const { Pool } = pg;

/**
 * Real persistence, matching the LEAN runtime shape in types.ts - not the richer future
 * proofrail/prisma/schema.prisma (archived, unused by any live client per the 2026-07-08
 * architecture-cartographer pass). Tables are the `proofrail_*`-prefixed set created by the
 * `proofrail_lean_runtime_schema` migration against the "Summa Terra Co-Work Automation" Supabase
 * project (fdnwlcomuddzmluvbylg) - chosen because it already held the (unused, empty) rich-schema
 * Prisma tables from an earlier P1 provisioning pass, confirming it's the project this build was
 * always meant to use. Deliberately prefixed to avoid touching either that old empty rich schema
 * or the separate, real, populated dataset (bills/vendors/accounts/etc, Alembic-managed) also
 * living in this same database - neither belongs to this app.
 */
export class PostgresProofRailRepository implements ProofRailRepository {
  private readonly pool: pg.Pool;

  constructor(connectionString?: string) {
    const cs = connectionString ?? process.env.PROOFRAIL_DATABASE_URL;
    if (!cs) {
      throw new Error(
        "PROOFRAIL_DATABASE_URL is not set. This must point at the 'Summa Terra Co-Work " +
          "Automation' Supabase project (fdnwlcomuddzmluvbylg) - not the 'Gmail Automation' " +
          "project, which is a different live system's database.",
      );
    }
    this.pool = new Pool({ connectionString: cs, ssl: { rejectUnauthorized: false } });
  }

  async close(): Promise<void> {
    await this.pool.end();
  }

  async findIntakeByGmailMsgId(gmailMsgId: string): Promise<IntakeRecord | undefined> {
    const { rows } = await this.pool.query(`select * from proofrail_intake where gmail_msg_id = $1`, [gmailMsgId]);
    return rows[0] ? this.toIntake(rows[0]) : undefined;
  }

  async findIntakeById(id: string): Promise<IntakeRecord | undefined> {
    const { rows } = await this.pool.query(`select * from proofrail_intake where id = $1`, [id]);
    return rows[0] ? this.toIntake(rows[0]) : undefined;
  }

  async saveIntake(record: IntakeRecord): Promise<IntakeRecord> {
    await this.pool.query(
      `insert into proofrail_intake
         (id, gmail_msg_id, vendor_raw, parsed, amount, entity, project, item, status,
          quarantine_reason, override_reason, qbo_txn_id, request_id, proof, flags, created_at)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
       on conflict (id) do update set
         vendor_raw = excluded.vendor_raw, parsed = excluded.parsed, amount = excluded.amount,
         entity = excluded.entity, project = excluded.project, item = excluded.item,
         status = excluded.status, quarantine_reason = excluded.quarantine_reason,
         override_reason = excluded.override_reason, qbo_txn_id = excluded.qbo_txn_id,
         request_id = excluded.request_id, proof = excluded.proof, flags = excluded.flags`,
      [
        record.id, record.gmailMsgId, record.vendorRaw, JSON.stringify(record.parsed), record.amount,
        record.entity ?? null, record.project ?? null, record.item ?? null, record.status,
        record.quarantineReason ?? null, record.overrideReason ?? null, record.qboTxnId ?? null,
        record.requestId ?? null, record.proof ? JSON.stringify(record.proof) : null,
        record.flags ?? [], record.createdAt,
      ],
    );
    return record;
  }

  async countIntakes(): Promise<number> {
    const { rows } = await this.pool.query(`select count(*)::int as n from proofrail_intake`);
    return rows[0].n;
  }

  async listIntakes(filter: { status?: IntakeStatus[]; entity?: string; limit?: number }): Promise<IntakeRecord[]> {
    const statuses = filter.status ?? (["PENDING_APPROVAL", "QUARANTINED"] as IntakeStatus[]);
    const limit = filter.limit ?? 25;
    const { rows } = await this.pool.query(
      `select * from proofrail_intake
       where status = any($1) and ($2::text is null or entity = $2)
       order by created_at asc
       limit $3`,
      [statuses, filter.entity ?? null, limit],
    );
    return rows.map((r) => this.toIntake(r));
  }

  async latestGateRun(): Promise<GateRunRecord | undefined> {
    const { rows } = await this.pool.query(`select * from proofrail_gate_run order by run_date desc limit 1`);
    return rows[0] ? this.toGateRun(rows[0]) : undefined;
  }

  async saveGateRun(record: GateRunRecord): Promise<GateRunRecord> {
    await this.pool.query(
      `insert into proofrail_gate_run (id, run_date, verdict, money_lock, results, bundle_proof)
       values ($1,$2,$3,$4,$5,$6)
       on conflict (id) do update set
         verdict = excluded.verdict, money_lock = excluded.money_lock,
         results = excluded.results, bundle_proof = excluded.bundle_proof`,
      [
        record.id, record.runDate, record.verdict, record.moneyLock,
        JSON.stringify(record.results), record.bundleProof ? JSON.stringify(record.bundleProof) : null,
      ],
    );
    return record;
  }

  async findDraw(id: string): Promise<DrawRecord | undefined> {
    const { rows } = await this.pool.query(`select * from proofrail_draw where id = $1`, [id]);
    return rows[0] ? this.toDraw(rows[0]) : undefined;
  }

  async saveDraw(record: DrawRecord): Promise<DrawRecord> {
    await this.pool.query(
      `insert into proofrail_draw (id, project, period, lender, status, chain_hash, proof, sent_at)
       values ($1,$2,$3,$4,$5,$6,$7,$8)
       on conflict (id) do update set
         project = excluded.project, period = excluded.period, lender = excluded.lender,
         status = excluded.status, chain_hash = excluded.chain_hash, proof = excluded.proof,
         sent_at = excluded.sent_at`,
      [
        record.id, record.project, record.period, record.lender, record.status,
        record.chainHash ?? null, record.proof ? JSON.stringify(record.proof) : null,
        record.sentAt ?? null,
      ],
    );
    return record;
  }

  async listEntityRegistry(): Promise<EntityRegistryRecord[]> {
    const { rows } = await this.pool.query(`select * from proofrail_entity_registry`);
    return rows.map((r) => this.toEntityRegistry(r));
  }

  async saveEntityRegistry(record: EntityRegistryRecord): Promise<EntityRegistryRecord> {
    await this.pool.query(
      `insert into proofrail_entity_registry
         (entity, location_a, fee_rate, fee_payee, fee_base, oaea_doc_url, draw_fee, acct_fee_cap_mo, pm_fee_rate)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9)
       on conflict (entity) do update set
         location_a = excluded.location_a, fee_rate = excluded.fee_rate, fee_payee = excluded.fee_payee,
         fee_base = excluded.fee_base, oaea_doc_url = excluded.oaea_doc_url, draw_fee = excluded.draw_fee,
         acct_fee_cap_mo = excluded.acct_fee_cap_mo, pm_fee_rate = excluded.pm_fee_rate`,
      [
        record.entity, record.locationA, record.feeRate ?? null, record.feePayee ?? null,
        record.feeBase ?? null, record.oaeaDocUrl ?? null, record.drawFee ?? null,
        record.acctFeeCapMo ?? null, record.pmFeeRate ?? null,
      ],
    );
    return record;
  }

  async findFeeRun(id: string): Promise<FeeRunRecord | undefined> {
    const { rows } = await this.pool.query(`select * from proofrail_fee_run where id = $1`, [id]);
    return rows[0] ? this.toFeeRun(rows[0]) : undefined;
  }

  async findFeeRunByUnique(period: string, entity: string, stream: string): Promise<FeeRunRecord | undefined> {
    const { rows } = await this.pool.query(
      `select * from proofrail_fee_run where period = $1 and entity = $2 and stream = $3`,
      [period, entity, stream],
    );
    return rows[0] ? this.toFeeRun(rows[0]) : undefined;
  }

  async saveFeeRun(record: FeeRunRecord): Promise<FeeRunRecord> {
    await this.pool.query(
      `insert into proofrail_fee_run
         (id, stream, period, entity, base, rate, payee, invoice_txn_id, bill_txn_id, status, proof)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
       on conflict (id) do update set
         invoice_txn_id = excluded.invoice_txn_id, bill_txn_id = excluded.bill_txn_id,
         status = excluded.status, proof = excluded.proof`,
      [
        record.id, record.stream, record.period, record.entity, record.base, record.rate, record.payee,
        record.invoiceTxnId ?? null, record.billTxnId ?? null, record.status,
        record.proof ? JSON.stringify(record.proof) : null,
      ],
    );
    return record;
  }

  async saveDrawReconcile(record: DrawReconcileRecord): Promise<DrawReconcileRecord> {
    await this.pool.query(
      `insert into proofrail_draw_reconcile (id, project, gc, period, verdict, variance, proof)
       values ($1,$2,$3,$4,$5,$6,$7)
       on conflict (id) do update set
         verdict = excluded.verdict, variance = excluded.variance, proof = excluded.proof`,
      [
        record.id, record.project, record.gc, record.period, record.verdict,
        JSON.stringify(record.variance), record.proof ? JSON.stringify(record.proof) : null,
      ],
    );
    return record;
  }

  async findVendorHistory(vendorRaw: string): Promise<VendorHistoryRecord | undefined> {
    const needle = vendorRaw.trim().toLowerCase();
    const { rows } = await this.pool.query(
      `select * from proofrail_vendor_history
       where lower(vendor_canonical) = $1 or $1 = any(select lower(a) from unnest(aliases) as a)`,
      [needle],
    );
    return rows[0] ? this.toVendorHistory(rows[0]) : undefined;
  }

  async seedVendorHistory(records: VendorHistoryRecord[]): Promise<void> {
    for (const record of records) {
      await this.pool.query(
        `insert into proofrail_vendor_history (vendor_canonical, aliases, entity, project, item, last_amount, bank_last4)
         values ($1,$2,$3,$4,$5,$6,$7)
         on conflict (vendor_canonical) do update set
           aliases = excluded.aliases, entity = excluded.entity, project = excluded.project,
           item = excluded.item, last_amount = excluded.last_amount, bank_last4 = excluded.bank_last4`,
        [
          record.vendorCanonical, record.aliases, record.entity, record.project, record.item,
          record.lastAmount ?? null, record.bankAcctLast4 ?? null,
        ],
      );
    }
  }

  async audit(record: AuditRecord): Promise<void> {
    await this.pool.query(
      `insert into proofrail_audit_event (tool, input, result, actor_key) values ($1,$2,$3,$4)`,
      [record.tool, JSON.stringify(record.input), JSON.stringify(record.result), record.actorKey],
    );
  }

  async auditCount(): Promise<number> {
    const { rows } = await this.pool.query(`select count(*)::int as n from proofrail_audit_event`);
    return rows[0].n;
  }

  async resolveQboClass(input: { entity?: string; project?: string; item?: string; vendor?: string; context?: string }): Promise<string | undefined> {
    const { rows } = await this.pool.query(
      `select qbo_class from proofrail_class_mapping
       where (entity is null or entity = $1)
         and (project is null or project = $2)
         and (item is null or item = $3)
         and (vendor is null or vendor = $4)
         and (context is null or context = $5)
       order by
         (case when entity is not null then 1 else 0 end
          + case when project is not null then 1 else 0 end
          + case when item is not null then 1 else 0 end
          + case when vendor is not null then 1 else 0 end
          + case when context is not null then 1 else 0 end) desc,
         priority asc
       limit 1`,
      [input.entity ?? null, input.project ?? null, input.item ?? null, input.vendor ?? null, input.context ?? null],
    );
    return rows[0]?.qbo_class as string | undefined;
  }

  private toIntake(r: Record<string, unknown>): IntakeRecord {
    return {
      id: r.id as string,
      gmailMsgId: r.gmail_msg_id as string,
      vendorRaw: r.vendor_raw as string,
      parsed: r.parsed as IntakeRecord["parsed"],
      amount: Number(r.amount),
      entity: (r.entity as string) ?? undefined,
      project: (r.project as string) ?? undefined,
      item: (r.item as string) ?? undefined,
      status: r.status as IntakeStatus,
      quarantineReason: (r.quarantine_reason as string) ?? undefined,
      overrideReason: (r.override_reason as string) ?? undefined,
      qboTxnId: (r.qbo_txn_id as string) ?? undefined,
      requestId: (r.request_id as string) ?? undefined,
      proof: (r.proof as IntakeRecord["proof"]) ?? undefined,
      flags: (r.flags as string[]) ?? [],
      createdAt: new Date(r.created_at as string),
    };
  }

  private toGateRun(r: Record<string, unknown>): GateRunRecord {
    return {
      id: r.id as string,
      runDate: new Date(r.run_date as string),
      verdict: r.verdict as GateRunRecord["verdict"],
      moneyLock: r.money_lock as boolean,
      results: r.results as GateRunRecord["results"],
      bundleProof: (r.bundle_proof as GateRunRecord["bundleProof"]) ?? undefined,
    };
  }

  private toDraw(r: Record<string, unknown>): DrawRecord {
    return {
      id: r.id as string,
      project: r.project as string,
      period: r.period as string,
      lender: r.lender as string,
      status: r.status as DrawRecord["status"],
      chainHash: (r.chain_hash as string) ?? undefined,
      sentAt: r.sent_at ? new Date(r.sent_at as string) : undefined,
      proof: (r.proof as DrawRecord["proof"]) ?? undefined,
    };
  }

  private toEntityRegistry(r: Record<string, unknown>): EntityRegistryRecord {
    return {
      entity: r.entity as string,
      locationA: r.location_a as string,
      feeRate: r.fee_rate !== null ? Number(r.fee_rate) : null,
      feePayee: (r.fee_payee as string) ?? null,
      feeBase: (r.fee_base as string) ?? null,
      oaeaDocUrl: (r.oaea_doc_url as string) ?? null,
      drawFee: r.draw_fee !== null ? Number(r.draw_fee) : null,
      acctFeeCapMo: r.acct_fee_cap_mo !== null ? Number(r.acct_fee_cap_mo) : null,
      pmFeeRate: r.pm_fee_rate !== null ? Number(r.pm_fee_rate) : null,
    };
  }

  private toFeeRun(r: Record<string, unknown>): FeeRunRecord {
    return {
      id: r.id as string,
      stream: r.stream as FeeRunRecord["stream"],
      period: r.period as string,
      entity: r.entity as string,
      base: Number(r.base),
      rate: Number(r.rate),
      payee: r.payee as string,
      status: r.status as FeeRunRecord["status"],
      invoiceTxnId: (r.invoice_txn_id as string) ?? undefined,
      billTxnId: (r.bill_txn_id as string) ?? undefined,
      proof: (r.proof as FeeRunRecord["proof"]) ?? undefined,
    };
  }

  private toVendorHistory(r: Record<string, unknown>): VendorHistoryRecord {
    return {
      vendorCanonical: r.vendor_canonical as string,
      aliases: (r.aliases as string[]) ?? [],
      entity: r.entity as string,
      project: r.project as string,
      item: r.item as string,
      lastAmount: r.last_amount !== null ? Number(r.last_amount) : undefined,
      bankAcctLast4: (r.bank_last4 as string) ?? undefined,
    };
  }
}
