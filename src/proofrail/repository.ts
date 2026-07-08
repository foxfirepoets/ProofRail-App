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

export interface ProofRailRepository {
  findIntakeByGmailMsgId(gmailMsgId: string): Promise<IntakeRecord | undefined>;
  findIntakeById(id: string): Promise<IntakeRecord | undefined>;
  saveIntake(record: IntakeRecord): Promise<IntakeRecord>;
  countIntakes(): Promise<number>;
  listIntakes(filter: { status?: IntakeStatus[]; entity?: string; limit?: number }): Promise<IntakeRecord[]>;
  latestGateRun(): Promise<GateRunRecord | undefined>;
  saveGateRun(record: GateRunRecord): Promise<GateRunRecord>;
  findDraw(id: string): Promise<DrawRecord | undefined>;
  saveDraw(record: DrawRecord): Promise<DrawRecord>;
  listEntityRegistry(): Promise<EntityRegistryRecord[]>;
  saveEntityRegistry(record: EntityRegistryRecord): Promise<EntityRegistryRecord>;
  findFeeRun(id: string): Promise<FeeRunRecord | undefined>;
  findFeeRunByUnique(period: string, entity: string, stream: string): Promise<FeeRunRecord | undefined>;
  saveFeeRun(record: FeeRunRecord): Promise<FeeRunRecord>;
  saveDrawReconcile(record: DrawReconcileRecord): Promise<DrawReconcileRecord>;
  findVendorHistory(vendorRaw: string): Promise<VendorHistoryRecord | undefined>;
  seedVendorHistory(records: VendorHistoryRecord[]): Promise<void>;
  audit(record: AuditRecord): Promise<void>;
  auditCount(): Promise<number>;
}

export class InMemoryProofRailRepository implements ProofRailRepository {
  private readonly intakes = new Map<string, IntakeRecord>();
  private readonly intakeByGmail = new Map<string, string>();
  private readonly gates: GateRunRecord[] = [];
  private readonly draws = new Map<string, DrawRecord>();
  private readonly registries = new Map<string, EntityRegistryRecord>();
  private readonly feeRuns = new Map<string, FeeRunRecord>();
  private readonly drawReconciles = new Map<string, DrawReconcileRecord>();
  private readonly vendorHistory = new Map<string, VendorHistoryRecord>();
  private readonly audits: AuditRecord[] = [];

  async findIntakeByGmailMsgId(gmailMsgId: string): Promise<IntakeRecord | undefined> {
    const id = this.intakeByGmail.get(gmailMsgId);
    return id ? this.intakes.get(id) : undefined;
  }

  async findIntakeById(id: string): Promise<IntakeRecord | undefined> {
    return this.intakes.get(id);
  }

  async saveIntake(record: IntakeRecord): Promise<IntakeRecord> {
    this.intakes.set(record.id, record);
    this.intakeByGmail.set(record.gmailMsgId, record.id);
    return record;
  }

  async countIntakes(): Promise<number> {
    return this.intakes.size;
  }

  async listIntakes(filter: { status?: IntakeStatus[]; entity?: string; limit?: number }): Promise<IntakeRecord[]> {
    const statuses = filter.status ?? (["PENDING_APPROVAL", "QUARANTINED"] as IntakeStatus[]);
    const limit = filter.limit ?? 25;
    return [...this.intakes.values()]
      .filter((r) => statuses.includes(r.status))
      .filter((r) => !filter.entity || r.entity === filter.entity)
      .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
      .slice(0, limit);
  }

  async latestGateRun(): Promise<GateRunRecord | undefined> {
    return [...this.gates].sort((a, b) => b.runDate.getTime() - a.runDate.getTime())[0];
  }

  async saveGateRun(record: GateRunRecord): Promise<GateRunRecord> {
    this.gates.push(record);
    return record;
  }

  async findDraw(id: string): Promise<DrawRecord | undefined> {
    return this.draws.get(id);
  }

  async saveDraw(record: DrawRecord): Promise<DrawRecord> {
    this.draws.set(record.id, record);
    return record;
  }

  async listEntityRegistry(): Promise<EntityRegistryRecord[]> {
    return [...this.registries.values()];
  }

  async saveEntityRegistry(record: EntityRegistryRecord): Promise<EntityRegistryRecord> {
    this.registries.set(record.entity, record);
    return record;
  }

  async findFeeRun(id: string): Promise<FeeRunRecord | undefined> {
    return this.feeRuns.get(id);
  }

  async findFeeRunByUnique(period: string, entity: string, stream: string): Promise<FeeRunRecord | undefined> {
    return [...this.feeRuns.values()].find((run) => (
      run.period === period && run.entity === entity && run.stream === stream
    ));
  }

  async saveFeeRun(record: FeeRunRecord): Promise<FeeRunRecord> {
    this.feeRuns.set(record.id, record);
    return record;
  }

  async saveDrawReconcile(record: DrawReconcileRecord): Promise<DrawReconcileRecord> {
    this.drawReconciles.set(record.id, record);
    return record;
  }

  async findVendorHistory(vendorRaw: string): Promise<VendorHistoryRecord | undefined> {
    const needle = vendorRaw.trim().toLowerCase();
    return [...this.vendorHistory.values()].find(
      (v) => v.vendorCanonical.toLowerCase() === needle || v.aliases.some((a) => a.toLowerCase() === needle),
    );
  }

  async seedVendorHistory(records: VendorHistoryRecord[]): Promise<void> {
    for (const record of records) {
      this.vendorHistory.set(record.vendorCanonical, record);
    }
  }

  async audit(record: AuditRecord): Promise<void> {
    this.audits.push(record);
  }

  async auditCount(): Promise<number> {
    return this.audits.length;
  }
}
