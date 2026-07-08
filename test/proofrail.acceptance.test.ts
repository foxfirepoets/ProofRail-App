import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { FakeQboClient } from "../src/proofrail/qbo.js";
import { LocalProofClient } from "../src/proofrail/proof.js";
import { InMemoryProofRailRepository } from "../src/proofrail/repository.js";
import { ProofRailService } from "../src/proofrail/service.js";

function harness() {
  const repo = new InMemoryProofRailRepository();
  const qbo = new FakeQboClient();
  const service = new ProofRailService(repo, new LocalProofClient(), qbo);
  return { repo, qbo, service };
}

function intake(gmailMsgId = "msg-1") {
  return {
    email_meta: { gmail_msg_id: gmailMsgId, sender: "vendor@example.com", subject: "Invoice", received_at: new Date().toISOString() },
    parsed_invoice: {
      vendor: "GC - Concord Homes Utah",
      invoice_no: "INV-1",
      invoice_date: "2026-07-07",
      total: 123.45,
      lines: [{ description: "Concrete", item: "003 Concrete", amount: 123.45 }],
    },
    suggested_coding: { entity: "Madison", project: "Madison Park:Vertical", item: "003 Concrete", confidence: 0.98 },
    attachments: [{ sha256: "abc", filename: "invoice.pdf", storage_uri: "supabase://invoice.pdf" }],
  };
}

describe("ProofRail highest-risk acceptance laws", () => {
  it("submit_intake is idempotent by gmail message id", async () => {
    const { repo, service } = harness();
    const first = await service.submitIntake(intake("same-msg")) as { intake_id: string; status: string };
    const second = await service.submitIntake(intake("same-msg")) as { intake_id: string };
    const third = await service.submitIntake(intake("same-msg")) as { intake_id: string };

    assert.equal(first.status, "PENDING_APPROVAL");
    assert.equal(second.intake_id, first.intake_id);
    assert.equal(third.intake_id, first.intake_id);
    assert.equal(await repo.countIntakes(), 1);
  });

  it("illegal approval transition returns STATE_409", async () => {
    const { service } = harness();
    const submitted = await service.submitIntake(intake("state-msg")) as { intake_id: string };
    await service.approve({ intake_id: submitted.intake_id });

    await assert.rejects(
      () => service.approve({ intake_id: submitted.intake_id }),
      (error: any) => error.code === "STATE_409" && error.status === 409,
    );
  });

  it("QUARANTINED approval requires an override reason", async () => {
    const { service } = harness();
    const submitted = await service.submitIntake({
      ...intake("quarantine-msg"),
      suggested_coding: { entity: "Madison", project: "Madison Park:Vertical", item: "003 Concrete", confidence: 0.2 },
    }) as { intake_id: string };

    await assert.rejects(
      () => service.approve({ intake_id: submitted.intake_id }),
      (error: any) => error.code === "PR-002",
    );
  });

  it("RED gate money_lock blocks send_draw and approve_fees with 423", async () => {
    const { repo, service } = harness();
    await service.saveGateRun("RED", [{ gate: "G-A", pass: false, summary: "Injected RED" }]);
    await repo.saveDraw({ id: "draw-1", project: "Madison", period: "2026-07", lender: "Arixa", status: "PROOFED" });

    await assert.rejects(
      () => service.sendDraw({ draw_id: "draw-1", confirm: true }),
      (error: any) => error.code === "LOCKED_423" && error.status === 423,
    );
    await assert.rejects(
      () => service.approveFees({ fee_run_ids: [] }),
      (error: any) => error.code === "LOCKED_423" && error.status === 423,
    );
  });

  it("registry-sourced fees refuse entities without fee law and 12SB land-inclusive bases", async () => {
    const { repo, service } = harness();
    await repo.saveEntityRegistry({ entity: "12SB", locationA: "01 12SB Hunters Landing", feeRate: 0.05, feePayee: "STV CM, LLC", feeBase: "5% of project cost including land" });
    await repo.saveEntityRegistry({ entity: "Madison", locationA: "04 Madison Park", feeRate: 0.05, feePayee: "STV CM, LLC", feeBase: "5% of approved development cost excluding land" });

    const result = await service.runFees({ period: "2026-07" }) as { fee_runs: unknown[]; skipped: { entity: string; reason: string }[] };

    assert.deepEqual(result.skipped, [{ entity: "12SB", reason: "NO_FEE_OAEA" }]);
    assert.equal(result.fee_runs.length, 1);
  });

  it("fee pair failure records PR-020-style FAILED row with voided compensation", async () => {
    const { repo, qbo, service } = harness();
    await service.saveGateRun("GREEN", [{ gate: "G-A", pass: true, summary: "Fresh GREEN" }]);
    const feeRun = await repo.saveFeeRun({
      id: "fee-1",
      stream: "DEV_CM",
      period: "2026-07",
      entity: "Madison",
      base: 1000,
      rate: 0.05,
      payee: "STV CM, LLC",
      status: "PENDING_APPROVAL",
    });
    qbo.failNextFeePair = true;

    const result = await service.approveFees({ fee_run_ids: [feeRun.id] }) as { failed: { fee_run_id: string; error: string; voided: boolean }[] };
    const saved = await repo.findFeeRun("fee-1");

    assert.deepEqual(result.failed, [{ fee_run_id: "fee-1", error: "PR-020", voided: true }]);
    assert.equal(saved?.status, "FAILED");
  });
});
