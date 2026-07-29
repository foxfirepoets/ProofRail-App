import assert from "node:assert/strict";
import test from "node:test";
import { GoogleDriveEvidenceAdapter, GoogleGmailEvidenceAdapter } from "../src/payment-ops/imports/index.js";
import { PaymentOpsController } from "../src/payment-ops/controller.js";
import { PaymentOpsService } from "../src/payment-ops/service.js";

test("Gmail and Drive adapters reject caller-only provenance", async () => {
  const gmail = new GoogleGmailEvidenceAdapter({
    availability: async () => ({ configured: true }),
    listMessages: async () => ({ status: "READY", records: [{ messageId: "m1", threadId: "t1", internalDate: "2026-07-21T12:00:00Z" }] }),
  });
  const drive = new GoogleDriveEvidenceAdapter({
    availability: async () => ({ configured: true }),
    listFiles: async () => ({ status: "READY", records: [{ fileId: "f1", version: "v1", modifiedTime: "2026-07-21T12:00:00Z", providerReference: "caller-only", fingerprint: "caller-only" }] }),
  });
  assert.equal((await gmail.importEvidence({})).status, "REJECTED");
  assert.equal((await drive.importEvidence({})).status, "REJECTED");
});

test("controller fails closed when no verified authentication provider is configured", async () => {
  const controller = new PaymentOpsController(new PaymentOpsService(), undefined);
  await assert.rejects(
    () => controller.create({ description: "x", legalEntity: "STV", method: "ACH", idempotencyKey: "k" }, "Bearer anything"),
    (error: unknown) => (error as { status?: number }).status === 503,
  );
});

test("approved mutation requires a configured principal policy in the durable boundary", async () => {
  const service = new PaymentOpsService(undefined, true, undefined);
  assert.throws(
    () => service.requestApproval("missing", { approved: true, approver: "Mike" }, "Mike"),
    (error: unknown) => (error as { code?: string }).code === "AUTHENTICATION_REQUIRED",
  );
});
