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
import { randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { ProofRailError } from "../proofrail/errors.js";
import { proofRailService } from "../proofrail/container.js";

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

  return server;
}

function requireBearerAuth(req: Request, res: Response, next: NextFunction): void {
  const header = req.header("authorization") ?? "";
  const presented = header.replace(/^Bearer\s+/i, "");
  if (!presented || presented !== MCP_KEY) {
    res.status(401).json({ error: { code: "UNAUTHORIZED", message: "Missing or invalid bearer token." } });
    return;
  }
  next();
}

interface Session {
  server: McpServer;
  transport: StreamableHTTPServerTransport;
}

function isInitializeRequest(body: unknown): boolean {
  const msg = body as { method?: string } | Array<{ method?: string }>;
  if (Array.isArray(msg)) {
    return msg.some((m) => m?.method === "initialize");
  }
  return msg?.method === "initialize";
}

export function startMcpServer(): void {
  const app = express();
  app.use(express.json());

  app.get("/healthz", (_req, res) => res.json({ ok: true, service: "proofrail-mcp" }));

  // Streamable HTTP transport, STATEFUL mode: Cowork opens one session (initialize) and then
  // makes many tools/list + tools/call requests against it, so the transport (and the McpServer
  // wrapping it) must persist across requests, keyed by the mcp-session-id header the SDK issues
  // on initialize. This is the reference pattern from the MCP SDK docs for Streamable HTTP.
  const sessions = new Map<string, Session>();

  app.post("/mcp", requireBearerAuth, async (req, res) => {
    const existingSessionId = req.header("mcp-session-id");
    let session = existingSessionId ? sessions.get(existingSessionId) : undefined;

    if (!session) {
      if (!isInitializeRequest(req.body)) {
        res.status(400).json({
          jsonrpc: "2.0",
          error: { code: -32000, message: "Bad Request: no session; first request must be initialize" },
          id: null,
        });
        return;
      }
      const server = buildServer();
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (sessionId) => {
          sessions.set(sessionId, { server, transport });
        },
      });
      transport.onclose = () => {
        if (transport.sessionId) sessions.delete(transport.sessionId);
      };
      await server.connect(transport);
      session = { server, transport };
    }

    await session.transport.handleRequest(req, res, req.body);
  });

  app.delete("/mcp", requireBearerAuth, async (req, res) => {
    const sessionId = req.header("mcp-session-id");
    const session = sessionId ? sessions.get(sessionId) : undefined;
    if (!session) {
      res.status(404).json({ error: { code: "NOT_FOUND_404", message: "Unknown session." } });
      return;
    }
    await session.transport.handleRequest(req, res);
  });

  app.listen(PORT, () => {
    // eslint-disable-next-line no-console
    console.log(`ProofRail MCP server listening on :${PORT} (POST/DELETE /mcp, GET /healthz)`);
  });
}

startMcpServer();
