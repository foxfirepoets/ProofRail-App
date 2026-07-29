import { DriveFileRecord, GmailMessageRecord } from "./contracts.js";

export function gmailMessageDedupeKey(record: GmailMessageRecord): string {
  return `gmail:message:${record.messageId}`;
}

export function gmailThreadDedupeKey(record: GmailMessageRecord): string {
  return `gmail:thread:${record.threadId}`;
}

export function driveVersionDedupeKey(record: DriveFileRecord): string {
  return `drive:file:${record.fileId}:version:${record.version}`;
}

export function dedupeGmailMessages(records: GmailMessageRecord[]): { records: GmailMessageRecord[]; skipped: number } {
  const seenMessages = new Set<string>();
  const unique: GmailMessageRecord[] = [];
  let skipped = 0;
  for (const record of records) {
    const key = gmailMessageDedupeKey(record);
    if (!record.messageId || !record.threadId || seenMessages.has(key)) {
      skipped += 1;
      continue;
    }
    seenMessages.add(key);
    unique.push(record);
  }
  return { records: unique, skipped };
}

export function dedupeDriveVersions(records: DriveFileRecord[]): { records: DriveFileRecord[]; skipped: number } {
  const seenVersions = new Set<string>();
  const unique: DriveFileRecord[] = [];
  let skipped = 0;
  for (const record of records) {
    const key = record.fileId && record.version ? driveVersionDedupeKey(record) : "";
    if (!key || seenVersions.has(key)) {
      skipped += 1;
      continue;
    }
    seenVersions.add(key);
    unique.push(record);
  }
  return { records: unique, skipped };
}
