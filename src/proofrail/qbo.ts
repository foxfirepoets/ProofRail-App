import { createHash } from "node:crypto";
import { ProofRailError } from "./errors.js";

export interface QboBillRequest {
  vendor: string;
  amount: number;
  entity: string;
  project: string;
  item: string;
  requestId: string;
  payload: unknown;
}

export interface QboFeePairRequest {
  feeRunId: string;
  entity: string;
  period: string;
  amount: number;
  requestId: string;
}

export interface QboFeePairResult {
  invoiceTxnId?: string;
  billTxnId?: string;
  failed?: true;
  voided?: boolean;
}

export interface QboClient {
  createBill(request: QboBillRequest): Promise<{ qboTxnId: string; duplicate?: boolean }>;
  postFeePair(request: QboFeePairRequest): Promise<QboFeePairResult>;
}

/** Satisfied by ProofRailRepository.resolveQboClass - narrowed here so qbo.ts doesn't depend on the whole repository interface. */
export interface ClassResolver {
  resolveQboClass(input: { entity?: string; project?: string; item?: string; vendor?: string; context?: string }): Promise<string | undefined>;
}

export function deterministicRequestId(parts: string[]): string {
  return createHash("sha1").update(parts.join("|")).digest("hex").slice(0, 36);
}

/** "Madison Park:Vertical" -> "Vertical". Returns undefined if there's no ":phase" suffix - never guesses a phase. */
export function derivePhaseFromProject(project: string): string | undefined {
  const idx = project.lastIndexOf(":");
  if (idx === -1 || idx === project.length - 1) return undefined;
  return project.slice(idx + 1).trim();
}

/**
 * Real QBO sandbox client - OAuth + HTTP mechanics ported 1:1 from the verified, currently-working
 * scripts/qbo_common.py + scripts/qbo_create_sandbox_bill.py (Realm class, sandbox guard, deterministic
 * RequestId, name-based entity lookups, DocNumber+Vendor dedupe).
 *
 * NOT wired into container.ts yet - two blockers, both owner decisions, not code problems:
 *
 * 1. SINGLE-WRITER OAUTH COLLISION (see docs/OWNER_UPDATES_2026-07-06.md "Single writer, always"):
 *    Intuit rotates the refresh token on every refresh. The work-machine's scripts/*.py pipeline
 *    already holds a live refresh token for these two sandbox realms in .env/.qbo_tokens.json. If
 *    this Render-hosted client refreshed using the SAME refresh token value, it would rotate the
 *    token out from under the work machine (and vice versa) - both sides halt on the next call
 *    (PR-011). This client MUST authenticate with its OWN separate OAuth grant (Ben completes a
 *    fresh Intuit consent flow for this app - same registered app is fine, just a distinct
 *    authorize+token exchange) and store that token separately (e.g. Supabase, once repository.ts
 *    is real - see Task #5). Never copy the work machine's current refresh token into this app's env.
 *
 * 2. CLASS DIMENSION: RESOLVED (2026-07-08, Ben's directive) via a required, fail-closed
 *    ClassResolver - see below. The MCP tool contract (submit_intake/approve) still never collects
 *    an explicit Class from Cowork; instead Class is looked up from `proofrail_class_mapping`
 *    (entity/project/item/vendor/context -> QBO Class name) at post time. No matching row = halt
 *    the post (PR-043), never guess, never post without Class. The mapping TABLE exists
 *    (see postgres-repository.ts resolveQboClass) but is NOT YET SEEDED with real rows - that's
 *    real business data (which project:phase maps to which QBO Class) that must come from the
 *    actual QBO Advanced Class list (qbo Source Files/8_Classes_REALM_A_API_SEED.csv /
 *    9_Classes_REALM_B_API_SEED.csv) via Ben or the proofrail-coding-rules skill, not invented here.
 *
 * Until blocker #1 (OAuth) is resolved, container.ts keeps using FakeQboClient regardless of how
 * complete this class is. Blocker #2 is now a data-population task, not a code blocker.
 */
export class RealQboClient implements QboClient {
  private readonly clientId: string;
  private readonly clientSecret: string;
  private readonly realmId: string;
  private readonly expectedCompanyName: string;
  private readonly minorVersion: string;
  private readonly baseUrl: string;
  private readonly classResolver: ClassResolver;
  private readonly onRefreshTokenRotated?: (newRefreshToken: string, newAccessToken: string, accessExpiresAt: Date) => Promise<void> | void;
  private refreshToken: string;
  private accessToken: string | undefined;
  private accessExpiresAt = 0;

  constructor(options: {
    clientId: string;
    clientSecret: string;
    realmId: string;
    refreshToken: string;
    expectedCompanyName: string;
    classResolver: ClassResolver;
    minorVersion?: string;
    baseUrl?: string;
    /**
     * Called every time Intuit rotates the refresh token (i.e. on every successful token()
     * call - Intuit issues a new refresh_token on every refresh in its current model). Wire
     * this to QboTokenStore.persistRotation so a rotation surviving only in memory doesn't
     * silently break the NEXT refresh after a process restart (see docs/QBO_MCP_OAUTH_APPROVAL.md
     * acceptance test 2). Errors thrown by this callback propagate out of token() - a failed
     * persist should fail the call, not silently continue on an unpersisted token.
     */
    onRefreshTokenRotated?: (newRefreshToken: string, newAccessToken: string, accessExpiresAt: Date) => Promise<void> | void;
  }) {
    this.clientId = options.clientId;
    this.clientSecret = options.clientSecret;
    this.realmId = options.realmId;
    this.refreshToken = options.refreshToken;
    this.expectedCompanyName = options.expectedCompanyName;
    this.classResolver = options.classResolver;
    this.onRefreshTokenRotated = options.onRefreshTokenRotated;
    this.minorVersion = options.minorVersion ?? "75";
    this.baseUrl = options.baseUrl ?? "https://sandbox-quickbooks.api.intuit.com/v3";
    // Sandbox guard (qbo_common.py's guard_sandbox): no production mode exists in this client.
    if (!this.baseUrl.includes("sandbox-quickbooks.api.intuit.com")) {
      throw new Error("RealQboClient refuses to start against a non-sandbox host. There is no production mode.");
    }
  }

  private async token(): Promise<string> {
    if (this.accessToken && Date.now() < this.accessExpiresAt) return this.accessToken;
    const basic = Buffer.from(`${this.clientId}:${this.clientSecret}`).toString("base64");
    const response = await fetch("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", {
      method: "POST",
      headers: {
        Authorization: `Basic ${basic}`,
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: this.refreshToken }),
    });
    if (!response.ok) {
      throw new Error(`QBO token refresh failed: HTTP ${response.status} - ${await response.text()}`);
    }
    const tok = (await response.json()) as { access_token: string; expires_in: number; refresh_token?: string };
    this.accessToken = tok.access_token;
    this.accessExpiresAt = Date.now() + (tok.expires_in - 120) * 1000;
    // Intuit rotates the refresh token on every refresh - persist the new one (caller must supply
    // durable storage; see blocker #1 above). Losing this rotation breaks the NEXT refresh, so this
    // is not optional once wired to a real repository.
    if (tok.refresh_token && tok.refresh_token !== this.refreshToken) {
      this.refreshToken = tok.refresh_token;
      if (this.onRefreshTokenRotated) {
        await this.onRefreshTokenRotated(this.refreshToken, this.accessToken, new Date(this.accessExpiresAt));
      }
    }
    return this.accessToken;
  }

  private async request<T>(method: string, path: string, params?: Record<string, string>, body?: unknown): Promise<T> {
    const query = new URLSearchParams({ minorversion: this.minorVersion, ...params });
    const url = `${this.baseUrl}/company/${this.realmId}/${path}?${query.toString()}`;
    const response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${await this.token()}`,
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      throw new Error(`QBO ${method} ${path} failed: HTTP ${response.status} - ${await response.text()}`);
    }
    return (await response.json()) as T;
  }

  private async query(q: string): Promise<Record<string, unknown>[]> {
    const entity = q.match(/FROM\s+(\w+)/i)?.[1] ?? "";
    const resp = await this.request<{ QueryResponse?: Record<string, unknown[]> }>("GET", "query", { query: q });
    return (resp.QueryResponse?.[entity] as Record<string, unknown>[] | undefined) ?? [];
  }

  private async findOneByName(entity: string, name: string, field = "Name"): Promise<{ Id: string } | undefined> {
    const safe = name.replace(/'/g, "\\'");
    const rows = await this.query(`SELECT * FROM ${entity} WHERE ${field} = '${safe}'`);
    return rows[0] as { Id: string } | undefined;
  }

  /** Read-only sanity check before any write - refuses to post to the wrong sandbox company. */
  async assertCompany(): Promise<void> {
    // The companyinfo endpoint nests the entity under "CompanyInfo" - unlike query results (which
    // nest under QueryResponse.<Entity>), this is NOT a flat { CompanyName } response. Confirmed
    // against the live sandbox (2026-07-10): reading info.CompanyName directly was always
    // undefined, so this guard was silently mismatching on the CORRECT company too, not just
    // wrong ones - it would have blocked every real write, not just caught bad ones.
    const info = await this.request<{ CompanyInfo: { CompanyName: string } }>("GET", `companyinfo/${this.realmId}`);
    const companyName = info.CompanyInfo?.CompanyName;
    if (companyName !== this.expectedCompanyName) {
      throw new Error(
        `QBO company name mismatch: got '${companyName}', expected '${this.expectedCompanyName}'. Halting writes.`,
      );
    }
  }

  async createBill(request: QboBillRequest): Promise<{ qboTxnId: string; duplicate?: boolean }> {
    assertNoPaymentEntity(request.entity);
    await this.assertCompany();

    const parsed = request.payload as { invoice_no?: string; invoice_date?: string } | undefined;
    const docNumber = (parsed?.invoice_no ?? request.requestId).slice(0, 21);

    // Fail-closed Class resolution (Ben's directive, 2026-07-08) - resolved BEFORE any other QBO
    // lookup so a missing mapping halts fast, before this line ever touches the sandbox.
    // Class in Realm A is a cost PHASE (COWORK_START_HERE.md dimensional law: "Class = cost
    // phase"), not an entity/vendor-specific thing - real seed data confirms exactly 5 phases
    // (qbo Source Files/8_Classes_REALM_A_API_SEED.csv: Acquisition/Sitework/Vertical/
    // Disposition/Operations), matching proofrail-coding-rules' project:phase convention
    // ({Project}:{Acquisition|Sitework|Vertical|Disposition} / :Operations). The phase is the
    // suffix of `project` after the last ":" - derive it and match on `context`, not on the full
    // project string (which would need one row per exact project, an unbounded list we don't have).
    const phase = derivePhaseFromProject(request.project);
    const qboClassName = await this.classResolver.resolveQboClass({
      entity: request.entity,
      project: request.project,
      item: request.item,
      vendor: request.vendor,
      context: phase,
    });
    if (!qboClassName) {
      throw new ProofRailError(
        "PR-043",
        `No Class mapping resolves for (entity=${request.entity}, project=${request.project}, phase=${phase ?? "UNPARSEABLE"}, item=${request.item}, vendor=${request.vendor}). Every QBO bill line requires Location + Class + Customer/Project + Item - ProofRail never guesses a Class or posts without one.`,
        400,
      );
    }

    const [vendor, item, department, customer, qboClass] = await Promise.all([
      this.findOneByName("Vendor", request.vendor, "DisplayName"),
      this.findOneByName("Item", request.item, "Name"),
      this.findOneByName("Department", request.entity, "Name"),
      this.findOneByName("Customer", request.project, "FullyQualifiedName"),
      this.findOneByName("Class", qboClassName, "Name"),
    ]);
    for (const [label, ref, name] of [
      ["Vendor", vendor, request.vendor],
      ["Item", item, request.item],
      ["Department", department, request.entity],
      ["Customer", customer, request.project],
      ["Class", qboClass, qboClassName],
    ] as const) {
      if (!ref) {
        throw new ProofRailError("PR-043", `${label} '${name}' not found in QBO. ProofRail never guesses.`, 400);
      }
    }

    const dupes = await this.query(`SELECT * FROM Bill WHERE DocNumber = '${docNumber.replace(/'/g, "\\'")}'`);
    const existingDupe = dupes.find((b) => (b as { VendorRef?: { value?: string } }).VendorRef?.value === vendor!.Id);
    if (existingDupe) {
      return { qboTxnId: (existingDupe as { Id: string }).Id, duplicate: true };
    }

    const response = await this.request<{ Bill?: { Id: string } } & { Id?: string }>("POST", "bill", { requestid: request.requestId }, {
      VendorRef: { value: vendor!.Id },
      TxnDate: parsed?.invoice_date ?? new Date().toISOString().slice(0, 10),
      DocNumber: docNumber,
      DepartmentRef: { value: department!.Id },
      Line: [{
        DetailType: "ItemBasedExpenseLineDetail",
        Amount: Math.round(request.amount * 100) / 100,
        ItemBasedExpenseLineDetail: {
          ItemRef: { value: item!.Id },
          Qty: 1,
          UnitPrice: Math.round(request.amount * 100) / 100,
          CustomerRef: { value: customer!.Id },
          ClassRef: { value: qboClass!.Id },
          BillableStatus: "NotBillable",
        },
      }],
    });
    // POST create responses nest the entity under its own name (e.g. { "Bill": {...} }), same as
    // companyinfo nests under "CompanyInfo" - confirmed against the live sandbox (2026-07-10): reading
    // response.Id directly was always undefined even though the bill posted correctly, silently
    // dropping qboTxnId (breaks audit-trail linkage even though the write itself succeeded).
    const bill = response.Bill ?? response;
    if (!bill.Id) {
      throw new Error(`QBO bill create response had no Id (response: ${JSON.stringify(response)})`);
    }
    return { qboTxnId: bill.Id };
  }

  async postFeePair(): Promise<QboFeePairResult> {
    // Fee-pair posting (mirrored Invoice/Bill across realms A and B, pair-atomic per PR-020) has no
    // ported reference implementation yet - scripts/*.py doesn't have a fee-pair script to port from
    // (fees are spec'd in SPEC_proofrail_v2_0_CONSOLIDATED.md F4 but not yet built anywhere real).
    // Fail closed rather than fake a mirrored pair.
    throw new Error("RealQboClient.postFeePair is not implemented - no verified real fee-pair posting exists to port from yet.");
  }
}

export class FakeQboClient implements QboClient {
  public failNextFeePair = false;
  private readonly bills = new Map<string, string>();

  async createBill(request: QboBillRequest): Promise<{ qboTxnId: string; duplicate?: boolean }> {
    const existing = this.bills.get(request.requestId);
    if (existing) {
      return { qboTxnId: existing, duplicate: true };
    }
    const qboTxnId = `bill_${this.bills.size + 1}`;
    this.bills.set(request.requestId, qboTxnId);
    return { qboTxnId };
  }

  async postFeePair(request: QboFeePairRequest): Promise<QboFeePairResult> {
    if (this.failNextFeePair) {
      this.failNextFeePair = false;
      return { billTxnId: `bill_${request.feeRunId}`, failed: true, voided: true };
    }
    return {
      invoiceTxnId: `invoice_${request.feeRunId}`,
      billTxnId: `bill_${request.feeRunId}`,
    };
  }
}

export function assertNoPaymentEntity(entityName: string): void {
  if (/billpayment|payment|transfer|charge/i.test(entityName)) {
    throw new ProofRailError("PR-043", "Payment and transfer entities are outside ProofRail's money boundary.", 400);
  }
}
