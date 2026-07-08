import { createHash } from "node:crypto";
import type { ProofStamp } from "./types.js";

export interface ProofClient {
  verifyInvoice(input: unknown): Promise<{ verdict: "PASS" | "FLAG"; flags: string[]; proof: ProofStamp }>;
  recordWorkflowEvent(input: unknown): Promise<ProofStamp>;
  recordAuditBundle(input: unknown): Promise<ProofStamp>;
}

export class LocalProofClient implements ProofClient {
  async verifyInvoice(input: unknown): Promise<{ verdict: "PASS" | "FLAG"; flags: string[]; proof: ProofStamp }> {
    const payload = JSON.stringify(input);
    const flags = payload.includes("BANK_CHANGE") ? ["BANK_CHANGE"] : [];
    return {
      verdict: flags.length ? "FLAG" : "PASS",
      flags,
      proof: this.stamp("INVOICE_PROOF", payload),
    };
  }

  async recordWorkflowEvent(input: unknown): Promise<ProofStamp> {
    return this.stamp("VERIFY_API", JSON.stringify(input));
  }

  async recordAuditBundle(input: unknown): Promise<ProofStamp> {
    return this.stamp("AUDIT_PROOF", JSON.stringify(input));
  }

  private stamp(product: ProofStamp["product"], payload: string): ProofStamp {
    const chainHash = createHash("sha256").update(`${product}:${payload}`).digest("hex");
    return {
      proof_id: `local_${chainHash.slice(0, 16)}`,
      chain_hash: chainHash,
      verify_url: `/api/proof/local_${chainHash.slice(0, 16)}/verify`,
      product,
    };
  }
}
