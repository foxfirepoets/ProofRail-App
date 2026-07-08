import { createHash } from "node:crypto";
import type { ProofStamp, SubmitIntakeInput } from "./types.js";

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

/**
 * Real SwarmSync client - both InvoiceProof and VerifyAPI/AuditProof are now real, ported from
 * the actual swarmsync source repo (C:\...\Github\swarmsync), not invented:
 *
 * - InvoiceProof: `POST /invoice-proof/scan` (apps/api/src/modules/invoice-proof/invoice-proof.controller.ts).
 *   AUTH CORRECTION vs docs/INVOICEPROOF_ROUTING_SPEC.md: that doc claims `ssk_live_` for this
 *   endpoint - wrong. The controller uses the base JwtAuthGuard (route is @Public(), scan itself
 *   accepts unauthenticated calls too), and the real service-account credential format is an
 *   `sa_`-prefixed key via `Authorization: Bearer sa_...` or `X-Api-Key` (jwt-auth.guard.ts:113-116,
 *   ServiceAccountsService.validateApiKey). SWARMSYNC_API_KEY in .env is already `sa_`-prefixed, so
 *   this client's existing Bearer usage is correct by coincidence - flagging the doc bug for a
 *   future fix to INVOICEPROOF_ROUTING_SPEC.md, not a code bug here.
 *
 * - VerifyAPI + AuditProof: SAME real endpoint, `POST /api/verify`
 *   (apps/api/src/modules/verification/verify-api.controller.ts:2171). They are NOT two separate
 *   products at the wire level - discriminated by `source_type` (required enum: api_output |
 *   agent_activity | audit_proof | document | workflow_event | software_delivery) and, for audit
 *   bundles specifically, `task: "audit_proof"` (triggers the additional Conduit dispatch,
 *   verify-api.controller.ts:3341-3366). Auth is a DIFFERENT credential than InvoiceProof: an
 *   `ssk_live_`-prefixed key via `Authorization: Bearer` or `X-API-Key`
 *   (verify-api-auth.guard.ts:17-73, SwarmScoreApiKey.keyHash lookup, status must be ACTIVE).
 *   No `ssk_live_` key exists anywhere in .env as of 2026-07-08 - only the InvoiceProof `sa_` key
 *   is present. Until SWARMSYNC_VERIFY_API_KEY is set, these two methods fail over to the same
 *   honest local chain-hash stamp as before (never silently pretend to be real without the key).
 */
export class SwarmSyncProofClient implements ProofClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly verifyApiKey: string | undefined;

  constructor(options?: { baseUrl?: string; apiKey?: string; verifyApiKey?: string }) {
    this.baseUrl = options?.baseUrl ?? process.env.SWARMSYNC_BASE_URL ?? "https://api.swarmsync.ai";
    const apiKey = options?.apiKey ?? process.env.SWARMSYNC_API_KEY;
    if (!apiKey) {
      // Fail closed: constructing a proof client for a money-adjacent system with no key
      // configured is a bug, not a convenience (CLAUDE.md non-negotiable #1 - no bypass flag).
      throw new Error(
        "SWARMSYNC_API_KEY is not set. This is the same key already used by " +
          "scripts/build_invoiceproof_packet.py --send; reuse it (do not mint a second key) so both " +
          "code paths hit the same SwarmSync org/quota.",
      );
    }
    this.apiKey = apiKey;
    // Optional on purpose - VerifyAPI/AuditProof use a different (ssk_live_) key that doesn't
    // exist yet. Falls back to the local stamp below when absent - see class doc comment.
    this.verifyApiKey = options?.verifyApiKey ?? process.env.SWARMSYNC_VERIFY_API_KEY;
  }

  async verifyInvoice(input: unknown): Promise<{ verdict: "PASS" | "FLAG"; flags: string[]; proof: ProofStamp }> {
    const invoice = this.toSwarmSyncInvoice(input as SubmitIntakeInput);

    const response = await fetch(`${this.baseUrl}/invoice-proof/scan`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ invoices: [invoice] }),
      signal: AbortSignal.timeout(60_000),
    });

    if (!response.ok) {
      // Let the caller's existing PR-003 fail-closed catch handle this (ProofRailService.submitIntake).
      throw new Error(`SwarmSync invoice-proof/scan failed: HTTP ${response.status} - ${await response.text()}`);
    }

    const scan = (await response.json()) as {
      scanId?: string;
      riskLevel?: string;
      findings?: { severity: string; pattern: string; detail: string }[];
    };

    // RISK_TO_VERDICT per docs/INVOICEPROOF_ROUTING_SPEC.md: LOW->PASS, MEDIUM->FLAG, HIGH/CRITICAL->FAIL.
    // KNOWN GAP: this app's ProofClient/IntakeStatus type system has no FAIL state distinct from FLAG
    // (see types.ts IntakeStatus - only QUARANTINED exists, and QUARANTINED IS approvable with an
    // override_reason). The real script's FAIL is meant to be "never approvable as-is" - stricter than
    // QUARANTINED. Until IntakeStatus gets a real FAIL/BLOCKED state, HIGH/CRITICAL is mapped to FLAG
    // here (same bucket as MEDIUM) rather than silently under-reporting risk as PASS. Flagged as a
    // follow-up: promote HIGH/CRITICAL to a hard-blocked state once product/schema work lands.
    const riskLevel = (scan.riskLevel ?? "MEDIUM").toUpperCase();
    const verdict: "PASS" | "FLAG" = riskLevel === "LOW" ? "PASS" : "FLAG";
    const flags = (scan.findings ?? []).map((f) => f.pattern);

    return {
      verdict,
      flags,
      proof: {
        proof_id: scan.scanId ?? "",
        chain_hash: scan.scanId ?? "",
        verify_url: `${this.baseUrl}/api/proof/${scan.scanId}/verify`,
        product: "INVOICE_PROOF",
      },
    };
  }

  async recordWorkflowEvent(input: unknown): Promise<ProofStamp> {
    if (!this.verifyApiKey) return this.localStamp("VERIFY_API", input);
    return this.callVerifyApi("VERIFY_API", "workflow_event", input);
  }

  async recordAuditBundle(input: unknown): Promise<ProofStamp> {
    if (!this.verifyApiKey) return this.localStamp("AUDIT_PROOF", input);
    return this.callVerifyApi("AUDIT_PROOF", "audit_proof", input);
  }

  private async callVerifyApi(
    product: ProofStamp["product"],
    sourceType: "workflow_event" | "audit_proof",
    input: unknown,
  ): Promise<ProofStamp> {
    const body: Record<string, unknown> = { source_type: sourceType, output: input };
    if (sourceType === "audit_proof") body.task = "audit_proof"; // triggers the Conduit dispatch leg

    const response = await fetch(`${this.baseUrl}/api/verify`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.verifyApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60_000),
    });

    if (!response.ok) {
      // No PR-003-style catch wraps recordWorkflowEvent/recordAuditBundle callers today (unlike
      // verifyInvoice) - throwing here will surface as an unhandled rejection until service.ts
      // adds one. Flagged, not silently swallowed: better to fail loudly than fall back to a fake
      // "real" proof.
      throw new Error(`SwarmSync /api/verify failed: HTTP ${response.status} - ${await response.text()}`);
    }

    const result = (await response.json()) as { proof_id?: string; chain_hash?: string };
    return {
      proof_id: result.proof_id ?? "",
      chain_hash: result.chain_hash ?? "",
      verify_url: `${this.baseUrl}/api/proof/${result.proof_id}/verify`,
      product,
    };
  }

  private toSwarmSyncInvoice(input: SubmitIntakeInput) {
    const invoice = input.parsed_invoice;
    const lineItemsTotal = invoice.lines.reduce((sum, line) => sum + line.amount, 0);
    return {
      vendor: invoice.vendor,
      invoiceNo: invoice.invoice_no,
      amount: invoice.total,
      lineItemsTotal,
      // Money-boundary policy (COWORK_START_HERE.md #11.3): this app only ever receives last-4
      // masked bank digits, never a full routing number, so BEC bank-change detection here is
      // necessarily lower-fidelity than scripts/build_invoiceproof_packet.py's full-routing compare.
      bankRouting: invoice.bank?.routing_last4,
    };
  }

  /** Same local chain-hash approach LocalProofClient used - see class doc comment for why. */
  private localStamp(product: ProofStamp["product"], input: unknown): ProofStamp {
    const payload = JSON.stringify(input);
    const chainHash = createHash("sha256").update(`${product}:${payload}`).digest("hex");
    return {
      proof_id: `local_${chainHash.slice(0, 16)}`,
      chain_hash: chainHash,
      verify_url: `/api/proof/local_${chainHash.slice(0, 16)}/verify`,
      product,
    };
  }
}
