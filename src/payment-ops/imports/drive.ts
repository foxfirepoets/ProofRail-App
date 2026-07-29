import { createHash } from "node:crypto";
import { EvidenceRole, EvidenceSource } from "../types.js";
import { DriveConnector, DriveFileRecord, EvidenceImportOptions, EvidenceImportResult, ImportResult, invalidCapturedAt } from "./contracts.js";
import { dedupeDriveVersions, driveVersionDedupeKey } from "./dedupe.js";
import { TrustedProvenanceVerifier } from "../provenance/verifier.js";
import { TrustedEvidenceRecord } from "../provenance/types.js";

type AttestedDriveRecord = DriveFileRecord & { rawPayload?: Uint8Array; fetchedAt?: string; attestation?: TrustedEvidenceRecord["attestation"]; immutableId?: string };

export class GoogleDriveEvidenceAdapter {
  public constructor(private readonly connector?: DriveConnector) {}

  public async importEvidence(options: Partial<EvidenceImportOptions> = {}): Promise<EvidenceImportResult> {
    if (!this.connector) return unavailable("Drive connector is not configured");
    const availability = await this.connector.availability();
    if (!availability.configured) return unavailable(availability.reason ?? "Drive credentials or connector are unavailable");

    const result: ImportResult<DriveFileRecord> = await this.connector.listFiles({});
    if (result.status !== "READY") return { status: result.status, evidence: [], skippedDuplicates: 0, reason: result.reason };

    const deduped = dedupeDriveVersions(result.records);
    const evidence = [];
    const verifier = (options as Partial<EvidenceImportOptions> & { provenanceVerifier?: TrustedProvenanceVerifier }).provenanceVerifier;
    if (!verifier) return rejected("A trusted Drive provenance verifier is required");
    for (const record of deduped.records as AttestedDriveRecord[]) {
      if (invalidCapturedAt(record.modifiedTime)) return rejected("Drive file is missing a valid modifiedTime");
      const sourceId = driveVersionDedupeKey(record);
      if (!(record.rawPayload instanceof Uint8Array) || !record.fetchedAt || !record.attestation) return rejected("Drive record lacks a provider attestation payload");
      const verified = await verifier.verify({ provider: "DRIVE", immutableId: record.immutableId ?? record.fileId, capturedAt: record.modifiedTime, fetchedAt: record.fetchedAt, payload: record.rawPayload, providerReference: record.providerReference ?? record.fileId, attestation: record.attestation, metadata: { obligationId: record.obligationId, accountId: record.accountId, stableAccountId: record.stableAccountId, amount: record.amount } });
      if (verified.status !== "VERIFIED") return rejected(verified.reason);
      evidence.push({ sourceRecordId: record.fileId, dedupeKey: sourceId, evidence: verified.value.evidence });
    }
    return { status: "READY", evidence, skippedDuplicates: deduped.skipped };
  }
}

function stableEvidenceId(value: string): string {
  return `evidence:${createHash("sha256").update(value).digest("hex")}`;
}

function unavailable(reason: string): EvidenceImportResult {
  return { status: "UNAVAILABLE", evidence: [], skippedDuplicates: 0, reason };
}

function rejected(reason: string): EvidenceImportResult {
  return { status: "REJECTED", evidence: [], skippedDuplicates: 0, reason };
}
