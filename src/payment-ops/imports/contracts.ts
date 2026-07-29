import { EvidenceRef, EvidenceRole, EvidenceSource } from "../types.js";

export interface GoogleConnectorAvailability {
  configured: boolean;
  reason?: string;
}

export interface ImportUnavailable {
  status: "UNAVAILABLE";
  records: [];
  reason: string;
}

export interface ImportRejected {
  status: "REJECTED";
  records: [];
  reason: string;
}

export interface ImportReady<T> {
  status: "READY";
  records: T[];
}

export type ImportResult<T> = ImportReady<T> | ImportUnavailable | ImportRejected;

export interface ImportedEvidence {
  evidence: EvidenceRef;
  sourceRecordId: string;
  dedupeKey: string;
}

export interface EvidenceImportResult {
  status: "READY" | "UNAVAILABLE" | "REJECTED";
  evidence: ImportedEvidence[];
  skippedDuplicates: number;
  reason?: string;
}

export interface GmailMessageRecord {
  messageId: string;
  threadId: string;
  internalDate: string;
  subject?: string;
  from?: string;
  providerReference?: string;
  fingerprint?: string;
  obligationId?: string;
  accountId?: string;
  stableAccountId?: string;
  amount?: number;
  role?: EvidenceRole;
}

export interface GmailConnector {
  availability(): Promise<GoogleConnectorAvailability>;
  listMessages(input: { query?: string; pageToken?: string }): Promise<ImportResult<GmailMessageRecord>>;
}

export interface DriveFileRecord {
  fileId: string;
  version: string;
  modifiedTime: string;
  name?: string;
  mimeType?: string;
  providerReference?: string;
  fingerprint?: string;
  obligationId?: string;
  accountId?: string;
  stableAccountId?: string;
  amount?: number;
  role?: EvidenceRole;
}

export interface DriveConnector {
  availability(): Promise<GoogleConnectorAvailability>;
  listFiles(input: { query?: string; pageToken?: string }): Promise<ImportResult<DriveFileRecord>>;
}

export interface EvidenceImportOptions {
  role: EvidenceRole;
  source: EvidenceSource.GMAIL | EvidenceSource.DRIVE;
}

export function invalidCapturedAt(value: string): boolean {
  return !value || Number.isNaN(Date.parse(value));
}
