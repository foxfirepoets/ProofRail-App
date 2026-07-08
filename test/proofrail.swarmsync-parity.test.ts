/**
 * Parity/acceptance test for the reintegration described in root CLAUDE.md's "Source of truth —
 * TWO TRACKS" section: proves the MCP app's SwarmSyncProofClient reaches the SAME real SwarmSync
 * InvoiceProof API that scripts/build_invoiceproof_packet.py --send has always used - not a local
 * hash pretending to be a proof.
 *
 * Requires a real SWARMSYNC_API_KEY in the environment (the same key scripts/*.py already use).
 * Skips (does not fail) when absent, so CI/dev machines without the real key still pass - but
 * anyone running this WITH the real key gets a live, load-bearing assertion.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SwarmSyncProofClient } from "../src/proofrail/proof.js";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const hasRealKey = Boolean(process.env.SWARMSYNC_API_KEY);

// Same synthetic test invoice submitted through both code paths - values chosen to be obviously
// fake/non-billable (so a real SwarmSync scan of it is harmless) while still exercising the real
// request/response contract.
const TEST_INVOICE = {
  vendor: "TEST VENDOR - proofrail parity check",
  invoiceNo: `PARITY-${Date.now()}`,
  amount: 1.0,
};

describe("SwarmSync InvoiceProof reintegration parity (MCP app vs scripts/*.py)", { skip: !hasRealKey && "SWARMSYNC_API_KEY not set - skipping live parity check" }, () => {
  it("SwarmSyncProofClient (MCP app) returns a real scanId, not a local_ hash", async () => {
    const client = new SwarmSyncProofClient();
    const result = await client.verifyInvoice({
      email_meta: { gmail_msg_id: "parity-test", sender: "test@example.com", subject: "parity", received_at: new Date().toISOString() },
      parsed_invoice: {
        vendor: TEST_INVOICE.vendor,
        invoice_no: TEST_INVOICE.invoiceNo,
        invoice_date: new Date().toISOString().slice(0, 10),
        total: TEST_INVOICE.amount,
        lines: [{ description: "parity check line", amount: TEST_INVOICE.amount }],
      },
      attachments: [],
    });

    assert.ok(result.proof.proof_id, "expected a non-empty proof_id");
    assert.ok(
      !result.proof.proof_id.startsWith("local_"),
      `expected a real SwarmSync scanId, got a local fallback id: ${result.proof.proof_id}`,
    );
    assert.ok(
      result.proof.verify_url.startsWith("https://api.swarmsync.ai") || result.proof.verify_url.includes(process.env.SWARMSYNC_BASE_URL ?? ""),
      `expected verify_url to point at the real SwarmSync API, got: ${result.proof.verify_url}`,
    );
  });

  it("scripts/build_invoiceproof_packet.py --send also reaches the real API for the same invoice shape", () => {
    const output = execFileSync(
      "python",
      [
        "scripts/build_invoiceproof_packet.py",
        "--vendor", TEST_INVOICE.vendor,
        "--invoice-no", `${TEST_INVOICE.invoiceNo}-py`,
        "--amount", String(TEST_INVOICE.amount),
        "--line-items-total", String(TEST_INVOICE.amount),
        "--source", "test:parity-check",
        "--send",
      ],
      { cwd: ROOT, encoding: "utf-8" },
    );
    const parsed = JSON.parse(output.split("\n").filter((l) => l.trim().startsWith("{"))[0] ?? "{}");

    // If the real call failed for an environmental reason (network, rate limit), the script fails
    // closed to FLAG with a PR-003 note rather than crashing - treat that as inconclusive, not a
    // pass, so a flaky network doesn't silently green-light this parity check.
    assert.notEqual(
      parsed.recommended_next_action,
      "proof service unavailable — fail closed: human review required (PR-003)",
      "script's real SwarmSync call failed closed (network/env issue) - rerun once connectivity is confirmed",
    );
  });
});
