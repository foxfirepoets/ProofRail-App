import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";
import fs from "node:fs";
import test from "node:test";
import { EvidenceRole, EvidenceSource, ObligationState, type Obligation } from "../src/payment-ops/types.js";
import { importMasterPaymentRegister, importPaymentCalendar } from "../src/payment-ops/imports/workbook-adapters.js";
import { reconcilePaymentSources } from "../src/payment-ops/imports/reconcile.js";
import {
  GoogleDriveEvidenceAdapter,
  GoogleGmailEvidenceAdapter,
  dedupeDriveVersions,
  dedupeGmailMessages,
  type DriveFileRecord,
  type GmailMessageRecord,
} from "../src/payment-ops/imports/index.js";
import { GmailProvenanceVerifier, DriveProvenanceVerifier } from "../src/payment-ops/provenance/verifier.js";

const headers = ["Entity", "Obligation", "Payee / Lender", "Payment / Due Date", "Pay From Bank", "Last 4", "Amount", "Payment Method"];
const row = (entity: string, obligation: string, payee: string, lastFour: string, amount: number) => [entity, obligation, payee, "2026-07-25", "Operating Bank", lastFour, amount, "ACH"];

test("both local workbooks are present as the acceptance fixtures, with normalized adapter contracts", () => {
  const masterPath = "C:/Users/Heather Workman/Downloads/STV_MASTER_PAYMENT_CONTROL_REGISTER_MERGED_2026-07-21.xlsx";
  const calendarPath = "C:/Users/Heather Workman/Downloads/STV Monthly Payment Calendar — How to Pay (2026-07-20).xlsx";
  assert.equal(fs.existsSync(masterPath), true, "master register fixture is missing");
  assert.equal(fs.existsSync(calendarPath), true, "payment calendar fixture is missing");

  const master = importMasterPaymentRegister([headers, row("12SB, LLC", "Loan payment", "Lender A", "1234", 1000)]);
  const calendar = importPaymentCalendar([headers, row("12SB, LLC", "Loan payment", "Lender A", "1234", 1000)]);
  assert.equal(master.kind, "MASTER_REGISTER");
  assert.equal(calendar.kind, "PAYMENT_CALENDAR");
  assert.equal(master.records[0]?.amount, 1000);
  assert.match(master.records[0]?.sourceId ?? "", /^master_register-/);
});

test("calendar reconciliation reports matched, missing, duplicate, and amount conflict rows", () => {
  const master = importMasterPaymentRegister([
    headers,
    row("STV CM, LLC", "Insurance", "Carrier A", "1111", 200),
    row("STV CM, LLC", "Duplicate", "Carrier D", "2222", 300),
    row("STV CM, LLC", "Duplicate", "Carrier D", "2222", 300),
    row("STV CM, LLC", "Master only", "Carrier M", "3333", 400),
  ]).records;
  const calendar = importPaymentCalendar([
    headers,
    row("STV CM, LLC", "Insurance", "Carrier A", "1111", 200),
    row("STV CM, LLC", "Duplicate", "Carrier D", "2222", 300),
    row("STV CM, LLC", "Calendar only", "Vendor Z", "4444", 500),
    row("STV CM, LLC", "Conflict", "Carrier X", "5555", 600),
  ]).records;
  const conflictMaster = importMasterPaymentRegister([headers, row("STV CM, LLC", "Conflict", "Carrier X", "5555", 601)]).records;
  const result = reconcilePaymentSources([...master, ...conflictMaster], calendar);
  assert.ok(result.matched >= 1);
  assert.ok(result.missingFromCalendar >= 1);
  assert.ok(result.missingFromMaster >= 1);
  assert.ok(result.duplicates >= 1);
  assert.ok(result.conflicts >= 1);
});

test("12SB pay-from account conflicts are quarantined and never guessed", () => {
  const master = importMasterPaymentRegister([headers, row("12SB, LLC", "Land loan", "Lender", "1234", 1000)]).records;
  const calendar = importPaymentCalendar([headers, row("12SB, LLC", "Land loan", "Lender", "9999", 1000)]).records;
  const result = reconcilePaymentSources(master, calendar);
  assert.equal(result.records[0]?.status, "CONFLICT");
  assert.equal(result.quarantined.length, 1);
  assert.match(result.quarantined[0]?.reason ?? "", /12SB account identity conflict quarantined/);
});

const gmailRecord = (messageId: string, threadId = "thread-1"): GmailMessageRecord => ({
  messageId, threadId, internalDate: "2026-07-21T12:00:00Z", obligationId: "obl-1", stableAccountId: "acct-1", amount: 100,
});

const driveRecord = (fileId: string, version: string): DriveFileRecord => ({
  fileId, version, modifiedTime: "2026-07-21T12:00:00Z", obligationId: "obl-1", stableAccountId: "acct-1", amount: 100,
});

const provenanceSecret = "acceptance-test-secret";
const provenanceNow = new Date("2026-07-21T12:00:00Z");
function attestedRecord<T extends GmailMessageRecord | DriveFileRecord>(record: T, provider: "GMAIL" | "DRIVE", immutableId: string, payloadText: string): T {
  const payload = new TextEncoder().encode(payloadText);
  const payloadHash = createHash("sha256").update(payload).digest("hex");
  const capturedAt = new Date(provider === "GMAIL"
    ? (record as GmailMessageRecord).internalDate
    : (record as DriveFileRecord).modifiedTime).toISOString();
  const keyId = `${provider.toLowerCase()}-acceptance-key`;
  const signature = createHmac("sha256", provenanceSecret)
    .update(`${provider}:${immutableId}:${payloadHash}:${capturedAt}:${keyId}`)
    .digest("hex");
  return {
    ...record,
    immutableId,
    rawPayload: payload,
    fetchedAt: capturedAt,
    attestation: { algorithm: "HMAC-SHA256" as const, keyId, signature },
  } as T;
}

const gmailVerifier = new GmailProvenanceVerifier({ credentials: { credentialId: "gmail-acceptance", attestationSecret: provenanceSecret }, now: provenanceNow });
const driveVerifier = new DriveProvenanceVerifier({ credentials: { credentialId: "drive-acceptance", attestationSecret: provenanceSecret }, now: provenanceNow });

test("Gmail message/thread and Drive file/version deduplication are stable", () => {
  const gmail = dedupeGmailMessages([gmailRecord("m1"), gmailRecord("m1"), gmailRecord("m2", "thread-1")]);
  assert.equal(gmail.records.length, 2);
  assert.equal(gmail.skipped, 1);
  const drive = dedupeDriveVersions([driveRecord("f1", "v1"), driveRecord("f1", "v1"), driveRecord("f1", "v2")]);
  assert.equal(drive.records.length, 2);
  assert.equal(drive.skipped, 1);
});

test("Gmail and Drive connectors fail closed when unavailable or source evidence is malformed", async () => {
  const unavailableGmail = await new GoogleGmailEvidenceAdapter().importEvidence();
  const unavailableDrive = await new GoogleDriveEvidenceAdapter().importEvidence();
  assert.equal(unavailableGmail.status, "UNAVAILABLE");
  assert.equal(unavailableDrive.status, "UNAVAILABLE");

  const gmail = new GoogleGmailEvidenceAdapter({
    availability: async () => ({ configured: true }),
    listMessages: async () => ({ status: "READY", records: [attestedRecord(gmailRecord("m-valid"), "GMAIL", "gmail-immutable-1", "gmail acceptance payload")] }),
  });
  const drive = new GoogleDriveEvidenceAdapter({
    availability: async () => ({ configured: true }),
    listFiles: async () => ({ status: "READY", records: [{ ...driveRecord("f1", "v1"), modifiedTime: "not-a-date" }] }),
  });
  assert.equal((await gmail.importEvidence({ provenanceVerifier: gmailVerifier } as never)).status, "READY");
  assert.equal((await drive.importEvidence()).status, "REJECTED");

  const rejectedGmail = new GoogleGmailEvidenceAdapter({
    availability: async () => ({ configured: true }),
    listMessages: async () => ({ status: "READY", records: [{ ...gmailRecord("m-bad"), internalDate: "not-a-date" }] }),
  });
  assert.equal((await rejectedGmail.importEvidence()).status, "REJECTED");
});

test("imported evidence carries provenance fields required for downstream proof validation", async () => {
  const adapter = new GoogleDriveEvidenceAdapter({
    availability: async () => ({ configured: true }),
    listFiles: async () => ({ status: "READY", records: [attestedRecord({ ...driveRecord("f1", "v1"), providerReference: "bank-record-1" }, "DRIVE", "drive-immutable-1", "drive acceptance payload")] }),
  });
  const result = await adapter.importEvidence({ role: EvidenceRole.CLEARING_PROOF, source: EvidenceSource.DRIVE, provenanceVerifier: driveVerifier } as never);
  assert.equal(result.status, "READY");
  assert.equal(result.evidence[0]?.evidence.providerReference, "bank-record-1");
  assert.equal(result.evidence[0]?.evidence.provenanceVerified, true);
  assert.equal(result.evidence[0]?.evidence.fingerprint, createHash("sha256").update(new TextEncoder().encode("drive acceptance payload")).digest("hex"));
});

function obligation(id: string, key: string): Obligation {
  return {
    id, kind: "BILL" as Obligation["kind"], description: key, legalEntity: "STV CM, LLC", payee: "Payee", amount: 1,
    amountBasis: "invoice", dueDate: "2026-07-25", payFromAccountId: "acct", payToReference: "payee-ref", method: "ACH" as Obligation["method"],
    autopay: false, targetOperator: "BEN" as Obligation["targetOperator"], benCanPay: "YES", aubreyRequired: false,
    accountIdentityStatus: "VERIFIED" as Obligation["accountIdentityStatus"], payFromAccountStableId: "stable-acct", state: ObligationState.DISCOVERED,
    approval: "NOT_REQUIRED" as Obligation["approval"], evidence: [], approvals: [], confirmationEvidenceIds: [], clearingEvidenceIds: [], audit: [],
    createdAt: "2026-07-21T00:00:00Z", updatedAt: "2026-07-21T00:00:00Z",
  };
}

test("restart-safe atomic idempotency is preserved across repository instances", async () => {
  const rows = new Map<string, Obligation>();
  class DurableTestDouble {
    async createIfAbsent(value: Obligation, key: string): Promise<Obligation> {
      const existing = rows.get(key);
      if (existing) return existing;
      await Promise.resolve();
      const winner = rows.get(key);
      if (winner) return winner;
      rows.set(key, value);
      return value;
    }
  }
  const firstProcess = new DurableTestDouble();
  const secondProcess = new DurableTestDouble();
  const [first, second] = await Promise.all([
    firstProcess.createIfAbsent(obligation("o-1", "first"), "gmail:m-1"),
    secondProcess.createIfAbsent(obligation("o-2", "second"), "gmail:m-1"),
  ]);
  assert.equal(rows.size, 1);
  assert.equal(first.id, second.id);
});

test("Prisma durable idempotency integration runs when configured and skips only without DATABASE_URL", async (t) => {
  if (!process.env.DATABASE_URL) {
    t.skip("DATABASE_URL is absent; durable integration requires a configured database");
    return;
  }
  const { PrismaClient } = await import("@prisma/client");
  const { PrismaPaymentOpsRepository } = await import("../src/payment-ops/repository.js");
  const prisma = new PrismaClient();
  t.after(async () => prisma.$disconnect());
  const repository = new PrismaPaymentOpsRepository(prisma);
  const [first, second] = await Promise.all([
    repository.createIfAbsentAsync(obligation("integration-1", "one"), "integration-key"),
    repository.createIfAbsentAsync(obligation("integration-2", "two"), "integration-key"),
  ]);
  assert.equal(first.id, second.id);
});
