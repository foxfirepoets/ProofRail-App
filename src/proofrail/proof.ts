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
 * Real SwarmSync client. InvoiceProof is real and empirically verified working end-to-end
 * (live test, 2026-07-08: `sa_...` key -> HTTP 200 from POST /invoice-proof/scan with real
 * findings). VerifyAPI/AuditProof's wire contract (POST /api/verify, source_type-discriminated)
 * is also real and ported from the actual swarmsync source, but the auth story needed two rounds
 * of static analysis AND a live test to get right - record it plainly so nobody re-guesses:
 *
 * Round 1 (static read of verify-api-auth.guard.ts only): concluded VerifyAPI needs a dedicated
 * `ssk_live_` SwarmScore key, `sa_` wouldn't work.
 * Round 2 (static read of key-issuance code, prompted by Ben's dashboard screenshot showing the
 * "VerifyAPI" button issuing an `sa_` key): concluded the guard falls through to accept `sa_` too,
 * so one key should serve all three products.
 * Round 3 (LIVE TEST, 2026-07-08): round 2 was WRONG. The exact same `sa_` key that returns
 * HTTP 200 from /invoice-proof/scan returns HTTP 401 "Invalid API key" from /api/verify. Static
 * code reading missed something real at runtime (scoping, entitlement lookup, or a guard version
 * mismatch) - trust the live result over the code trace.
 *
 * Conclusion: VerifyAPI/AuditProof genuinely need a dedicated `ssk_live_` key that this account
 * has not yet obtained. The SwarmSync dashboard's general "API Keys" page (Agent Market /
 * VerifyAPI / Routing buttons) does NOT issue this format - "VerifyAPI" there is a UI label only
 * and creates the same `sa_` service-account type as "Agent Market". A genuine `ssk_live_` key
 * must come from wherever the dedicated SwarmScore product setup lives (not yet located - ask
 * SwarmSync support or look for a "SwarmScore" section distinct from the general API Keys page).
 * A `sk-ss-...` ("Routing"/model-routing) key is a different product entirely and does not
 * authenticate to /api/verify OR /invoice-proof/scan - never put one in SWARMSYNC_VERIFYAPI_KEY.
 *
 * Until a real `ssk_live_` key exists, recordWorkflowEvent/recordAuditBundle fall back to the
 * same honest local chain-hash stamp as before - never silently pretend to be real without it.
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
    const verifyOverride = options?.verifyApiKey ?? process.env.SWARMSYNC_VERIFYAPI_KEY;
    if (verifyOverride && !verifyOverride.startsWith("ssk_live_")) {
      // Empirically confirmed 2026-07-08: sa_ keys get a real HTTP 401 from /api/verify, so don't
      // accept a non-ssk_live_ value here and silently call an endpoint that will just fail.
      throw new Error(
        `SWARMSYNC_VERIFYAPI_KEY is set but doesn't start with ssk_live_ - it looks like a key from ` +
          `the wrong product (e.g. a Routing/model-routing 'sk-ss-...' key). That will not ` +
          `authenticate to /api/verify (confirmed by live test) - remove it or replace it with a ` +
          `real ssk_live_ SwarmScore key.`,
      );
    }
    this.verifyApiKey = verifyOverride;
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
        Authorization: `Bearer ${this.verifyApiKey!}`,
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
