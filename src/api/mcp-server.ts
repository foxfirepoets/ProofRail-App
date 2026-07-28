/**
 * ProofRail MCP server - the actual seam Cowork connects to.
 *
 * This is a REAL Model Context Protocol server (not a plain REST API): it speaks the
 * Streamable HTTP transport, which is what Cowork's "Add custom connector" screen requires
 * (a remote MCP server URL - no stdio/local servers, see CLAUDE.md operator notes).
 *
 * It exposes exactly the 11 tools frozen in proofrail/mcp/tool-contracts.ts, and nothing else.
 * Every tool call is forwarded to the same `proofRailService` the NestJS REST controller uses -
 * one source of truth for the state machine, money_lock, and audit log, reachable by two doors.
 *
 * Auth: Authorization: Bearer <PROOFRAIL_MCP_KEY> - checked before the MCP transport ever sees
 * the request. No key configured => server refuses to start (fail closed, not fail open).
 *
 * Status: the business logic behind these tools (service.ts) is real and tested. What's still
 * FAKE underneath: QboClient (FakeQboClient - in-memory, not the real QBO sandbox API) and
 * ProofRailRepository (InMemoryProofRailRepository - resets on restart, not Supabase/Prisma yet).
 * Swapping those two for real implementations is P1/P2 work per SPEC_proofrail_v2_0_CONSOLIDATED
 * section 10 - this file doesn't paper over that; see the README note in this repo for honest status.
 */
import express, { type NextFunction, type Request, type Response } from "express";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { ProofRailError } from "../proofrail/errors.js";
import { proofRailService } from "../proofrail/container.js";
import { QboTokenStore, type QboRealmSlot } from "../proofrail/qbo-token-store.js";

// Render (and most PaaS hosts) assign the port via $PORT and route traffic only to that port.
// PROOFRAIL_MCP_PORT stays as a local-dev override; $PORT wins when present.
const PORT = Number(process.env.PORT ?? process.env.PROOFRAIL_MCP_PORT ?? 8787);
const MCP_KEY = process.env.PROOFRAIL_MCP_KEY;

if (!MCP_KEY) {
  // Fail closed: an MCP server for a money-adjacent system with no key configured is a bug,
  // not a convenience. There is no bypass flag anywhere in this project (CLAUDE.md non-negotiable #1).
  throw new Error(
    "PROOFRAIL_MCP_KEY is not set. Generate one (e.g. `openssl rand -hex 24`, prefixed sk_proofrail_) " +
      "and set it in the environment before starting the MCP server.",
  );
}

const intakeStatusEnum = z.enum([
  "RECEIVED", "PARSED", "PROOFING", "PROOF_PASS", "QUARANTINED",
  "PENDING_APPROVAL", "APPROVED", "REJECTED", "SYNCING", "SYNCED", "PROOFED",
]);

function buildServer(): McpServer {
  const server = new McpServer({ name: "proofrail", version: "0.1.0" }, { capabilities: { tools: {} } });

  const tool = (
    name: string,
    description: string,
    shape: Parameters<McpServer["registerTool"]>[1]["inputSchema"],
    handler: (args: never) => Promise<unknown>,
  ) => {
    server.registerTool(
      name,
      { description, inputSchema: shape },
      async (args) => {
        try {
          const result = await handler(args as never);
          return { content: [{ type: "text", text: JSON.stringify(result) }] };
        } catch (error) {
          if (error instanceof ProofRailError) {
            return {
              isError: true,
              content: [{ type: "text", text: JSON.stringify({ error: { code: error.code, message: error.message, detail: error.detail } }) }],
            };
          }
          throw error;
        }
      },
    );
  };

  tool(
    "submit_intake",
    "Hand off a parsed invoice from an Inbox Run. Idempotent on gmail_msg_id. Runs Invoice-Proof synchronously; fails closed (QUARANTINED, PR-003) if the proof service is unreachable.",
    {
      email_meta: z.object({ gmail_msg_id: z.string(), sender: z.string(), subject: z.string(), received_at: z.string() }),
      parsed_invoice: z.object({
        vendor: z.string(),
        invoice_no: z.string(),
        invoice_date: z.string(),
        total: z.number(),
        lines: z.array(z.object({ description: z.string(), item: z.string().optional(), amount: z.number() })),
        bank: z.object({ acct_last4: z.string().optional(), routing_last4: z.string().optional() }).optional(),
      }),
      suggested_coding: z.object({ entity: z.string(), project: z.string(), item: z.string(), confidence: z.number() }).optional(),
      attachments: z.array(z.object({ sha256: z.string(), filename: z.string(), storage_uri: z.string() })),
    },
    (args) => proofRailService.submitIntake(args),
  );

  tool(
    "list_queue",
    "List intake items awaiting approval or quarantined, with proof and coding status.",
    {
      status: z.array(intakeStatusEnum).optional(),
      entity: z.string().optional(),
      limit: z.number().optional(),
    },
    (args) => proofRailService.listQueue(args),
  );

  tool(
    "approve",
    "Approve an intake (PENDING_APPROVAL or QUARANTINED). QUARANTINED requires override_reason >= 20 chars (PR-002). Posts the QBO bill on approval.",
    {
      intake_id: z.string(),
      coding_final: z.object({ entity: z.string(), project: z.string(), item: z.string() }).optional(),
      override_reason: z.string().optional(),
    },
    (args) => proofRailService.approve(args),
  );

  tool(
    "reject",
    "Reject an intake that is PENDING_APPROVAL or QUARANTINED.",
    { intake_id: z.string(), reason: z.string() },
    (args) => proofRailService.reject(args),
  );

  tool(
    "get_gate_status",
    "Read the latest nightly gate verdict and whether money_lock is engaged. Read-only, always available.",
    {},
    () => proofRailService.getGateStatus(),
  );

  tool(
    "reconcile_draw_sheet",
    "F6 - reconcile an extracted GC draw/pay-app against expected line arithmetic and retainage rate. Returns PASS/FLAG with a line-by-line variance table.",
    {
      project: z.string(),
      gc: z.string(),
      period: z.string(),
      sheet_storage_uri: z.string(),
      extracted_lines: z.array(z.object({
        cost_code: z.string().optional(),
        description: z.string(),
        this_period: z.number(),
        total_to_date: z.number(),
        retainage: z.number().optional(),
      })),
    },
    (args) => proofRailService.reconcileDrawSheet(args),
  );

  tool(
    "build_draw",
    "Assemble a draw package. Refuses (PR-030, 423) if the latest gate isn't GREEN and less than 24h old.",
    { project: z.string(), period: z.string(), lender: z.string() },
    (args) => proofRailService.buildDraw(args),
  );

  tool(
    "send_draw",
    "Send an assembled draw. IRREVERSIBLE. Requires status=PROOFED and confirm:true; 423s if money_lock is engaged.",
    { draw_id: z.string(), confirm: z.literal(true) },
    (args) => proofRailService.sendDraw(args),
  );

  tool(
    "run_fees",
    "Compute the fee matrix for a period from EntityRegistry. Never posts - returns PENDING_APPROVAL rows. Entities without a registry row (or 12SB/Summa Elite) appear only in skipped[].",
    { period: z.string() },
    (args) => proofRailService.runFees(args),
  );

  tool(
    "approve_fees",
    "Post approved fee runs as a mirrored Invoice/Bill pair. Pair-atomic: a partial failure voids and marks FAILED (PR-020). 423s if money_lock is engaged.",
    { fee_run_ids: z.array(z.string()) },
    (args) => proofRailService.approveFees(args),
  );

  tool(
    "lookup_coding",
    "Read-only coding lookup by vendor history, plus standing entity notes (e.g. no-developer-fee entities).",
    { vendor: z.string(), description: z.string().optional(), amount: z.number().optional() },
    (args) => proofRailService.lookupCoding(args),
  );

  tool(
    "void_transaction",
    "Remove a posted QBO Bill, Invoice, or JournalEntry. Invoice gets a true void (zeroed, stays visible in history) - QBO's API does not support void for Bill/JournalEntry, so those get a hard delete instead (still logged in QBO's own system Audit History). The response's 'operation' field always reports which one actually happened. Requires confirm:true and a reason (>=10 chars). 423s if money_lock is engaged, same as send_draw/approve_fees.",
    {
      entity_type: z.enum(["Bill", "Invoice", "JournalEntry"]),
      qbo_txn_id: z.string(),
      reason: z.string(),
      confirm: z.literal(true),
    },
    (args) => proofRailService.voidTransaction(args),
  );

  return server;
}

// OAuth2 shim: Cowork's "Add custom connector" screen only offers a plain URL field plus
// optional OAuth Client ID/Secret - there is no bare API-key field. Cowork's "Connect" button
// drives the full Authorization Code flow (browser redirect to /authorize, not just a token
// POST) - confirmed by hitting "Cannot GET /authorize" on the first attempt. So this server
// implements both grants: authorization_code (what the Connect button actually uses) and
// client_credentials (kept for any client that wants the simpler path), plus the discovery
// documents MCP clients look for (RFC 8414 authorization-server metadata, RFC 9728
// protected-resource metadata). Every grant issues PROOFRAIL_MCP_KEY itself as the access
// token, so the existing bearer check on /mcp below needs no changes.
//
// Single-tenant simplification: there's exactly one user (Ben) and one pre-registered client
// (the Client ID/Secret he pastes into Cowork's screen), so /authorize auto-approves instead of
// showing a real consent screen - there's no second party whose consent would mean anything here.
const OAUTH_CLIENT_ID = process.env.PROOFRAIL_OAUTH_CLIENT_ID ?? "proofrail-cowork";
const OAUTH_CLIENT_SECRET = MCP_KEY; // reuse the same secret Cowork puts in "OAuth Client Secret"

interface AuthCode {
  clientId: string;
  redirectUri: string;
  codeChallenge?: string;
  codeChallengeMethod?: string;
  expiresAt: number;
}
const authCodes = new Map<string, AuthCode>();

function baseUrl(req: Request): string {
  const configured = process.env.RENDER_EXTERNAL_URL ?? process.env.PUBLIC_BASE_URL;
  if (configured) return configured.replace(/\/$/, "");
  const proto = req.header("x-forwarded-proto") ?? req.protocol;
  return `${proto}://${req.header("host")}`;
}

function resourceUrl(req: Request): string {
  return `${baseUrl(req)}/mcp`;
}

function requireBearerAuth(req: Request, res: Response, next: NextFunction): void {
  const header = req.header("authorization") ?? "";
  const presented = header.replace(/^Bearer\s+/i, "");
  if (!presented || presented !== MCP_KEY) {
    res
      .status(401)
      .set("WWW-Authenticate", `Bearer resource_metadata="${baseUrl(req)}/.well-known/oauth-protected-resource/mcp"`)
      .json({ error: { code: "UNAUTHORIZED", message: "Missing or invalid bearer token." } });
    return;
  }
  next();
}

export function startMcpServer(): void {
  const app = express();
  app.use(express.json());
  app.use(express.urlencoded({ extended: false })); // OAuth token requests are form-encoded per RFC 6749

  app.get("/healthz", (_req, res) => res.json({ ok: true, service: "proofrail-mcp" }));

  // -- OAuth2 discovery + token endpoint (see comment above requireBearerAuth) --
  const protectedResourceMetadata = (req: Request, res: Response) => {
    const base = baseUrl(req);
    res.json({ resource: resourceUrl(req), authorization_servers: [base] });
  };

  app.get("/.well-known/oauth-protected-resource", protectedResourceMetadata);
  app.get("/.well-known/oauth-protected-resource/mcp", protectedResourceMetadata);

  app.get("/.well-known/oauth-authorization-server", (req, res) => {
    const base = baseUrl(req);
    res.json({
      issuer: base,
      authorization_endpoint: `${base}/authorize`,
      token_endpoint: `${base}/oauth/token`,
      grant_types_supported: ["authorization_code", "client_credentials"],
      response_types_supported: ["code"],
      token_endpoint_auth_methods_supported: ["client_secret_post", "client_secret_basic"],
      code_challenge_methods_supported: ["S256", "plain"],
    });
  });

  // Browser-facing leg of the Authorization Code flow: Cowork's "Connect" button navigates
  // the user's browser here. Single-tenant auto-approve (see comment above authCodes) -
  // straight to issuing a code and redirecting back, no login/consent form.
  app.get("/authorize", (req, res) => {
    const { response_type, client_id, redirect_uri, state, code_challenge, code_challenge_method } =
      req.query as Record<string, string | undefined>;

    if (response_type !== "code" || !redirect_uri) {
      res.status(400).send("invalid_request: response_type must be 'code' and redirect_uri is required");
      return;
    }
    if (client_id !== OAUTH_CLIENT_ID) {
      res.status(401).send("invalid_client: unknown client_id");
      return;
    }

    const code = randomUUID();
    authCodes.set(code, {
      clientId: client_id,
      redirectUri: redirect_uri,
      codeChallenge: code_challenge,
      codeChallengeMethod: code_challenge_method,
      expiresAt: Date.now() + 5 * 60_000, // 5 min, single-use, consumed in /oauth/token below
    });

    const redirect = new URL(redirect_uri);
    redirect.searchParams.set("code", code);
    if (state) redirect.searchParams.set("state", state);
    res.redirect(302, redirect.toString());
  });

  app.post("/oauth/token", (req, res) => {
    const body = req.body as Record<string, string | undefined>;
    let clientId = body.client_id;
    let clientSecret = body.client_secret;

    const authHeader = req.header("authorization") ?? "";
    if (authHeader.startsWith("Basic ")) {
      const decoded = Buffer.from(authHeader.slice(6), "base64").toString("utf8");
      const sep = decoded.indexOf(":");
      if (sep >= 0) {
        clientId = decodeURIComponent(decoded.slice(0, sep));
        clientSecret = decodeURIComponent(decoded.slice(sep + 1));
      }
    }

    if (body.grant_type === "authorization_code") {
      const code = body.code;
      const entry = code ? authCodes.get(code) : undefined;
      if (!entry || entry.expiresAt < Date.now()) {
        res.status(400).json({ error: "invalid_grant" });
        return;
      }
      authCodes.delete(code!); // single-use

      if (entry.clientId !== (clientId ?? OAUTH_CLIENT_ID) || (clientId && clientSecret !== OAUTH_CLIENT_SECRET)) {
        res.status(401).json({ error: "invalid_client" });
        return;
      }
      if (body.redirect_uri && body.redirect_uri !== entry.redirectUri) {
        res.status(400).json({ error: "invalid_grant", error_description: "redirect_uri mismatch" });
        return;
      }
      if (entry.codeChallenge) {
        const verifier = body.code_verifier ?? "";
        const computed =
          entry.codeChallengeMethod === "plain" ? verifier : createHash("sha256").update(verifier).digest("base64url");
        if (computed !== entry.codeChallenge) {
          res.status(400).json({ error: "invalid_grant", error_description: "PKCE verification failed" });
          return;
        }
      }

      res.json({ access_token: MCP_KEY, token_type: "Bearer", expires_in: 3600 });
      return;
    }

    if (body.grant_type === "client_credentials") {
      if (clientId !== OAUTH_CLIENT_ID || clientSecret !== OAUTH_CLIENT_SECRET) {
        res.status(401).json({ error: "invalid_client" });
        return;
      }
      res.json({ access_token: MCP_KEY, token_type: "Bearer", expires_in: 3600 });
      return;
    }

    res.status(400).json({ error: "unsupported_grant_type" });
  });

  // -- QBO OAuth (this app's OWN Intuit grant - NOT the Cowork-facing shim above) --
  // See docs/QBO_MCP_OAUTH_APPROVAL.md for the full rationale: Intuit rotates the refresh token
  // on every refresh, so this app must hold a SEPARATE refresh token from the work-machine's
  // scripts/*.py pipeline (never the same value) or the two halves will invalidate each other's
  // tokens on their next refresh. This section only ever reads QBO_CLIENT_ID/QBO_CLIENT_SECRET/
  // QBO_REALM_A/QBO_REALM_B from THIS process's environment and writes tokens to
  // proofrail_qbo_token_store in Supabase - it never touches the work machine's .env or
  // .qbo_tokens.json, and there is no code path here that could.
  //
  // Registered redirect URI (Ben, 2026-07-09): https://proofrail-mcp.onrender.com/auth/qbo/callback
  // - this MUST exactly match what's registered in the Intuit app's Keys & OAuth settings
  // (scheme+host+path+trailing-slash all matter). baseUrl(req) below resolves to that same value
  // in production via RENDER_EXTERNAL_URL, so the two stay in sync without hardcoding it twice.
  const QBO_CLIENT_ID = process.env.QBO_CLIENT_ID;
  const QBO_CLIENT_SECRET = process.env.QBO_CLIENT_SECRET;
  const QBO_REALM_IDS: Record<QboRealmSlot, string | undefined> = {
    A: process.env.QBO_REALM_A,
    B: process.env.QBO_REALM_B,
  };
  let qboTokenStore: QboTokenStore | undefined;
  try {
    qboTokenStore = new QboTokenStore();
  } catch {
    // PROOFRAIL_DATABASE_URL missing - QBO OAuth routes report 501 below rather than crashing
    // the whole MCP server (money-adjacent QBO posting is explicitly paused/optional per
    // CLAUDE.md; the core MCP tool surface must still start without it).
    qboTokenStore = undefined;
  }

  interface QboAuthState {
    realm: QboRealmSlot;
    redirectUri: string;
    expiresAt: number;
  }
  const qboAuthStates = new Map<string, QboAuthState>();

  function qboConfigError(): string | undefined {
    if (!QBO_CLIENT_ID || !QBO_CLIENT_SECRET) {
      return "QBO_CLIENT_ID / QBO_CLIENT_SECRET are not set on this service yet.";
    }
    if (!qboTokenStore) {
      return "PROOFRAIL_DATABASE_URL is not set on this service yet - cannot store QBO tokens.";
    }
    return undefined;
  }

  // Step 1 of 2: start a fresh Intuit consent flow for one realm. Ben visits this once per realm
  // (?realm=A for partnership/projects, ?realm=B for parent/corporate) per
  // docs/QBO_MCP_OAUTH_APPROVAL.md section 2 step 3 - this route builds that URL so it doesn't
  // have to be hand-assembled.
  app.get("/auth/qbo/start", (req, res) => {
    const configError = qboConfigError();
    if (configError) {
      res.status(501).send(`QBO OAuth not configured: ${configError}`);
      return;
    }
    const realm = (req.query.realm as string | undefined)?.toUpperCase();
    if (realm !== "A" && realm !== "B") {
      res.status(400).send("invalid_request: ?realm=A or ?realm=B is required (A = partnership/projects, B = parent/corporate).");
      return;
    }
    if (!QBO_REALM_IDS[realm]) {
      res.status(501).send(`QBO_REALM_${realm} is not set on this service yet - cannot verify the callback's realmId without it.`);
      return;
    }

    const redirectUri = `${baseUrl(req)}/auth/qbo/callback`;
    const state = randomBytes(24).toString("hex");
    qboAuthStates.set(state, { realm, redirectUri, expiresAt: Date.now() + 10 * 60_000 });

    const authorizeUrl = new URL("https://appcenter.intuit.com/connect/oauth2");
    authorizeUrl.searchParams.set("client_id", QBO_CLIENT_ID!);
    authorizeUrl.searchParams.set("redirect_uri", redirectUri);
    authorizeUrl.searchParams.set("response_type", "code");
    authorizeUrl.searchParams.set("scope", "com.intuit.quickbooks.accounting");
    authorizeUrl.searchParams.set("state", state);
    res.redirect(302, authorizeUrl.toString());
  });

  // Step 2 of 2: Intuit redirects here with `code` + `realmId` after Ben logs in and approves.
  // Exchanges the code for a refresh token, verifies realmId matches the realm this flow was
  // started for, and stores the token pair in proofrail_qbo_token_store - never in this app's
  // response, logs, or any file.
  app.get("/auth/qbo/callback", async (req, res) => {
    const configError = qboConfigError();
    if (configError) {
      res.status(501).send(`QBO OAuth not configured: ${configError}`);
      return;
    }
    const { code, realmId, state, error, error_description } = req.query as Record<string, string | undefined>;
    if (error) {
      res.status(400).send(`Intuit returned an error: ${error} - ${error_description ?? "no description"}. Nothing was stored.`);
      return;
    }
    const entry = state ? qboAuthStates.get(state) : undefined;
    if (!entry || entry.expiresAt < Date.now()) {
      res.status(400).send("invalid_state: this consent flow expired or was never started via /auth/qbo/start. Nothing was stored.");
      return;
    }
    qboAuthStates.delete(state!); // single-use
    if (!code || !realmId) {
      res.status(400).send("invalid_request: Intuit's callback is missing code or realmId. Nothing was stored.");
      return;
    }
    const expectedRealmId = QBO_REALM_IDS[entry.realm];
    if (realmId !== expectedRealmId) {
      // Doc section 2 step 4: wrong company was authorized - refuse to store, tell Ben plainly.
      res.status(400).send(
        `realmId mismatch: Intuit returned realmId ${realmId}, but QBO_REALM_${entry.realm} is configured as ` +
          `${expectedRealmId}. This means the wrong sandbox company was approved during login. Nothing was ` +
          `stored - redo /auth/qbo/start?realm=${entry.realm} and make sure to log into the correct sandbox company.`,
      );
      return;
    }

    try {
      const basic = Buffer.from(`${QBO_CLIENT_ID}:${QBO_CLIENT_SECRET}`).toString("base64");
      const tokenRes = await fetch("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", {
        method: "POST",
        headers: {
          Authorization: `Basic ${basic}`,
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: new URLSearchParams({ grant_type: "authorization_code", code, redirect_uri: entry.redirectUri }),
      });
      if (!tokenRes.ok) {
        res.status(502).send(`Intuit token exchange failed: HTTP ${tokenRes.status} - ${await tokenRes.text()}. Nothing was stored.`);
        return;
      }
      const tok = (await tokenRes.json()) as { access_token: string; refresh_token: string; expires_in: number };
      await qboTokenStore!.seed({
        realm: entry.realm,
        realmId,
        refreshToken: tok.refresh_token,
        accessToken: tok.access_token,
        accessExpiresAt: new Date(Date.now() + (tok.expires_in - 120) * 1000),
      });
      res
        .status(200)
        .type("text/plain")
        .send(
          `QBO Realm ${entry.realm} connected. realmId ${realmId} authorized and stored in ` +
            `proofrail_qbo_token_store. Tokens are not shown here or in any log. ` +
            `${entry.realm === "A" ? "Now run /auth/qbo/start?realm=B for the other realm." : "Both realms should now be connected - verify with a read from proofrail_qbo_token_store."}`,
        );
    } catch (err) {
      res.status(500).send(`QBO token exchange threw: ${err instanceof Error ? err.message : String(err)}. Nothing was stored.`);
    }
  });

  // Streamable HTTP transport, STATELESS mode (SDK reference pattern:
  // examples/server/simpleStatelessStreamableHttp.ts): no session Map. Every POST /mcp builds a
  // fresh McpServer + transport, handles that one request, and tears down on response close.
  // Nothing to lose when the process restarts (Render free-tier idle spin-down, redeploys) -
  // there is no session for a restart to invalidate, so the "no session; first request must be
  // initialize" failure this replaced can't happen anymore. Safe here because no tool carries
  // state inside the MCP session itself - it all lives in proofRailService's own repository.
  app.get("/mcp", requireBearerAuth, (_req, res) => {
    res
      .status(405)
      .set("Allow", "POST")
      .json({ error: { code: "METHOD_NOT_ALLOWED", message: "Use POST /mcp for Streamable HTTP requests." } });
  });

  app.post("/mcp", requireBearerAuth, async (req, res) => {
    const server = buildServer();
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    res.on("close", () => {
      void transport.close();
      void server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  });

  app.delete("/mcp", requireBearerAuth, (_req, res) => {
    res
      .status(405)
      .set("Allow", "POST")
      .json({ error: { code: "METHOD_NOT_ALLOWED", message: "Stateless mode has no sessions to delete." } });
  });

  app.listen(PORT, () => {
    // eslint-disable-next-line no-console
    console.log(`ProofRail MCP server listening on :${PORT} (POST/DELETE /mcp, GET /healthz)`);
  });
}

startMcpServer();
