import { createHash } from "node:crypto";
import { EvidenceRole, EvidenceSource } from "../types.js";
import {
  EvidenceImportOptions,
  EvidenceImportResult,
  GmailConnector,
  GmailMessageRecord,
  ImportResult,
  invalidCapturedAt,
} from "./contracts.js";
import { dedupeGmailMessages, gmailMessageDedupeKey, gmailThreadDedupeKey } from "./dedupe.js";
import { TrustedProvenanceVerifier } from "../provenance/verifier.js";
import { TrustedEvidenceRecord } from "../provenance/types.js";

type AttestedGmailRecord = GmailMessageRecord & { rawPayload?: Uint8Array; fetchedAt?: string; attestation?: TrustedEvidenceRecord["attestation"]; immutableId?: string };

export class GoogleGmailEvidenceAdapter {
  public constructor(private readonly connector?: GmailConnector) {}

  public async importEvidence(options: Partial<EvidenceImportOptions> = {}): Promise<EvidenceImportResult> {
    if (!this.connector) return unavailable("Gmail connector is not configured");
    const availability = await this.connector.availability();
    if (!availability.configured) return unavailable(availability.reason ?? "Gmail credentials or connector are unavailable");

    const result: ImportResult<GmailMessageRecord> = await this.connector.listMessages({});
    if (result.status !== "READY") return { status: result.status, evidence: [], skippedDuplicates: 0, reason: result.reason };

    const deduped = dedupeGmailMessages(result.records);
    const evidence = [];
    const verifier = (options as Partial<EvidenceImportOptions> & { provenanceVerifier?: TrustedProvenanceVerifier }).provenanceVerifier;
    if (!verifier) return rejected("A trusted Gmail provenance verifier is required");
    for (const record of deduped.records as AttestedGmailRecord[]) {
      if (invalidCapturedAt(record.internalDate)) return rejected("Gmail message is missing a valid internalDate");
      if (!(record.rawPayload instanceof Uint8Array) || !record.fetchedAt || !record.attestation) return rejected("Gmail record lacks a provider attestation payload");
      const verified = await verifier.verify({ provider: "GMAIL", immutableId: record.immutableId ?? record.messageId, capturedAt: record.internalDate, fetchedAt: record.fetchedAt, payload: record.rawPayload, providerReference: record.providerReference ?? gmailThreadDedupeKey(record), attestation: record.attestation, metadata: { obligationId: record.obligationId, accountId: record.accountId, stableAccountId: record.stableAccountId, amount: record.amount } });
      if (verified.status !== "VERIFIED") return rejected(verified.reason);
      evidence.push({ sourceRecordId: record.messageId, dedupeKey: gmailMessageDedupeKey(record), evidence: verified.value.evidence });
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
