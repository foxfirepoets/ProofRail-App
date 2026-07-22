#!/usr/bin/env node
//
// Remote (Streamable HTTP) MCP server for Gmail + Calendar, deployable to
// Render so Cowork's "Add custom connector" (which only accepts a remote MCP
// URL, never a local stdio process) can reach it. Revived from the original
// stdio-only version 2026-07-22 - see git history for that version if the
// local/stdio mode is ever needed again.
//
// Auth model, copied deliberately from proofrail-mcp's proven working pattern
// (src/api/mcp-server.ts in this same repo) rather than reinvented: Cowork's
// connector screen only offers a URL field plus optional OAuth Client ID/
// Secret - no bare API-key field - and its "Connect" button drives a full
// OAuth Authorization Code flow (browser redirect to /authorize), not just a
// token POST. So this server implements both grants (authorization_code and
// client_credentials) plus the RFC 8414/9728 discovery documents MCP clients
// look for. Every grant just issues GMAIL_MCP_KEY itself as the access token,
// so the bearer check on /mcp needs no separate token store. Single-tenant:
// there is exactly one operator (Ben) and one pre-registered client, so
// /authorize auto-approves - there's no second party whose consent would
// mean anything here.
//
// Per-account Google credentials are NOT interactive here (no browser on a
// headless Render instance). They come from GMAIL_REFRESH_TOKEN_<EMAIL> env
// vars (see GAuthService.envVarNameForEmail) for every account listed in
// .accounts.json, obtained once via the existing gmail_skill/google-workspace
// manual-consent flow on the work machine and pasted into Render's env vars.

import * as dotenv from 'dotenv';
dotenv.config();

import { createHash, randomUUID } from 'crypto';
import express, { NextFunction, Request, Response } from 'express';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { ListToolsRequestSchema, CallToolRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { GmailTools } from './tools/gmail.js';
import { CalendarTools } from './tools/calendar.js';
import { GAuthService } from './services/gauth.js';

const logger = {
  info: (msg: string) => console.log(`[INFO] ${msg}`),
  warn: (msg: string) => console.warn(`[WARN] ${msg}`),
  error: (msg: string, error?: Error) => {
    console.error(`[ERROR] ${msg}`);
    if (error?.stack) console.error(error.stack);
  }
};

const PORT = Number(process.env.PORT ?? 8788);
const MCP_KEY = process.env.GMAIL_MCP_KEY;
if (!MCP_KEY || MCP_KEY.length < 32) {
  throw new Error('GMAIL_MCP_KEY must be set (>=32 chars) - refusing to start unauthenticated.');
}

interface ServerConfig {
  gauthFile: string;
  accountsFile: string;
  credentialsDir: string;
}

const config: ServerConfig = {
  gauthFile: process.env.GAUTH_FILE ?? './.gauth.json',
  accountsFile: process.env.ACCOUNTS_FILE ?? './.accounts.json',
  credentialsDir: process.env.CREDENTIALS_DIR ?? '.'
};

// -- one shared GAuthService + tool set, built once at boot; per-call
// account switching is just picking which stored/env credential to load. --
async function buildToolset() {
  const gauth = new GAuthService(config);
  await gauth.initialize();

  const accounts = await gauth.getAccountInfo();
  if (accounts.length === 0) {
    logger.warn('No accounts in .accounts.json - every tool call will fail until one is added.');
  }
  for (const account of accounts) {
    const envVar = GAuthService.envVarNameForEmail(account.email);
    if (!process.env[envVar]) {
      logger.warn(`No ${envVar} set - ${account.email} will 401/403 until it's provisioned.`);
    }
  }

  return {
    gauth,
    accounts,
    gmail: new GmailTools(gauth),
    calendar: new CalendarTools(gauth)
  };
}

async function ensureAccountReady(gauth: GAuthService, accounts: Awaited<ReturnType<GAuthService['getAccountInfo']>>, userId: string) {
  if (!accounts.some((a) => a.email === userId)) {
    throw new Error(`Account for email: ${userId} not registered in .accounts.json`);
  }
  const creds = await gauth.getStoredCredentials(userId);
  if (!creds) {
    throw new Error(
      `No credentials available for ${userId}. Set ${GAuthService.envVarNameForEmail(userId)} ` +
      `(a Google refresh token for this account) in the server's environment.`
    );
  }
}

function buildMcpServer(toolset: Awaited<ReturnType<typeof buildToolset>>): Server {
  const server = new Server(
    { name: 'mcp-gmail', version: '2.0.0' },
    { capabilities: { tools: {} } }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [...toolset.gmail.getTools(), ...toolset.calendar.getTools()]
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    try {
      if (typeof args !== 'object' || args === null) {
        return {
          isError: true,
          content: [{ type: 'text', text: JSON.stringify({ error: 'arguments must be dictionary', success: false }, null, 2) }]
        };
      }

      if (name === 'gmail_list_accounts' || name === 'calendar_list_accounts') {
        const result = name.startsWith('gmail_')
          ? await toolset.gmail.handleTool(name, args)
          : await toolset.calendar.handleTool(name, args);
        return { content: result };
      }

      const userId = (args as Record<string, unknown>).user_id;
      if (!userId || typeof userId !== 'string') {
        return {
          isError: true,
          content: [{ type: 'text', text: JSON.stringify({ error: 'user_id argument is missing in dictionary', success: false }, null, 2) }]
        };
      }

      try {
        await ensureAccountReady(toolset.gauth, toolset.accounts, userId);
      } catch (error) {
        return {
          isError: true,
          content: [{ type: 'text', text: JSON.stringify({ error: `OAuth2 setup failed: ${(error as Error).message}`, success: false }, null, 2) }]
        };
      }

      const result = name.startsWith('gmail_')
        ? await toolset.gmail.handleTool(name, args)
        : name.startsWith('calendar_')
          ? await toolset.calendar.handleTool(name, args)
          : (() => { throw new Error(`Unknown tool: ${name}`); })();

      return { content: await result };
    } catch (error) {
      logger.error(`Error handling tool ${name}:`, error as Error);
      return {
        isError: true,
        content: [{ type: 'text', text: JSON.stringify({ error: `Tool execution failed: ${(error as Error).message}`, success: false }, null, 2) }]
      };
    }
  });

  return server;
}

// -- Cowork-facing OAuth2 shim (see file header comment) --
const OAUTH_CLIENT_ID = process.env.GMAIL_MCP_OAUTH_CLIENT_ID ?? 'gmail-mcp-cowork';
const OAUTH_CLIENT_SECRET = MCP_KEY;

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
  if (configured) return configured.replace(/\/$/, '');
  const proto = req.header('x-forwarded-proto') ?? req.protocol;
  return `${proto}://${req.header('host')}`;
}

function resourceUrl(req: Request): string {
  return `${baseUrl(req)}/mcp`;
}

function requireBearerAuth(req: Request, res: Response, next: NextFunction): void {
  const header = req.header('authorization') ?? '';
  const presented = header.replace(/^Bearer\s+/i, '');
  if (!presented || presented !== MCP_KEY) {
    res
      .status(401)
      .set('WWW-Authenticate', `Bearer resource_metadata="${baseUrl(req)}/.well-known/oauth-protected-resource/mcp"`)
      .json({ error: { code: 'UNAUTHORIZED', message: 'Missing or invalid bearer token.' } });
    return;
  }
  next();
}

function isInitializeRequest(body: unknown): boolean {
  const msg = body as { method?: string } | Array<{ method?: string }>;
  if (Array.isArray(msg)) return msg.some((m) => m?.method === 'initialize');
  return msg?.method === 'initialize';
}

interface Session {
  server: Server;
  transport: StreamableHTTPServerTransport;
}

async function main() {
  const toolset = await buildToolset();

  const app = express();
  app.use(express.json());
  app.use(express.urlencoded({ extended: false })); // OAuth token requests are form-encoded per RFC 6749

  app.get('/healthz', (_req, res) => res.json({ ok: true, service: 'gmail-mcp', accounts: toolset.accounts.map((a) => a.email) }));

  const protectedResourceMetadata = (req: Request, res: Response) => {
    const base = baseUrl(req);
    res.json({ resource: resourceUrl(req), authorization_servers: [base] });
  };
  app.get('/.well-known/oauth-protected-resource', protectedResourceMetadata);
  app.get('/.well-known/oauth-protected-resource/mcp', protectedResourceMetadata);

  app.get('/.well-known/oauth-authorization-server', (req, res) => {
    const base = baseUrl(req);
    res.json({
      issuer: base,
      authorization_endpoint: `${base}/authorize`,
      token_endpoint: `${base}/oauth/token`,
      grant_types_supported: ['authorization_code', 'client_credentials'],
      response_types_supported: ['code'],
      token_endpoint_auth_methods_supported: ['client_secret_post', 'client_secret_basic'],
      code_challenge_methods_supported: ['S256', 'plain']
    });
  });

  app.get('/authorize', (req, res) => {
    const { response_type, client_id, redirect_uri, state, code_challenge, code_challenge_method } =
      req.query as Record<string, string | undefined>;

    if (response_type !== 'code' || !redirect_uri) {
      res.status(400).send("invalid_request: response_type must be 'code' and redirect_uri is required");
      return;
    }
    if (client_id !== OAUTH_CLIENT_ID) {
      res.status(401).send('invalid_client: unknown client_id');
      return;
    }

    const code = randomUUID();
    authCodes.set(code, {
      clientId: client_id,
      redirectUri: redirect_uri,
      codeChallenge: code_challenge,
      codeChallengeMethod: code_challenge_method,
      expiresAt: Date.now() + 5 * 60_000
    });

    const redirect = new URL(redirect_uri);
    redirect.searchParams.set('code', code);
    if (state) redirect.searchParams.set('state', state);
    res.redirect(302, redirect.toString());
  });

  app.post('/oauth/token', (req, res) => {
    const body = req.body as Record<string, string | undefined>;
    let clientId = body.client_id;
    let clientSecret = body.client_secret;

    const authHeader = req.header('authorization') ?? '';
    if (authHeader.startsWith('Basic ')) {
      const decoded = Buffer.from(authHeader.slice(6), 'base64').toString('utf8');
      const sep = decoded.indexOf(':');
      if (sep >= 0) {
        clientId = decodeURIComponent(decoded.slice(0, sep));
        clientSecret = decodeURIComponent(decoded.slice(sep + 1));
      }
    }

    if (body.grant_type === 'authorization_code') {
      const code = body.code;
      const entry = code ? authCodes.get(code) : undefined;
      if (!entry || entry.expiresAt < Date.now()) {
        res.status(400).json({ error: 'invalid_grant' });
        return;
      }
      authCodes.delete(code!);

      if (entry.clientId !== (clientId ?? OAUTH_CLIENT_ID) || (clientId && clientSecret !== OAUTH_CLIENT_SECRET)) {
        res.status(401).json({ error: 'invalid_client' });
        return;
      }
      if (body.redirect_uri && body.redirect_uri !== entry.redirectUri) {
        res.status(400).json({ error: 'invalid_grant', error_description: 'redirect_uri mismatch' });
        return;
      }
      if (entry.codeChallenge) {
        const verifier = body.code_verifier ?? '';
        const computed =
          entry.codeChallengeMethod === 'plain' ? verifier : createHash('sha256').update(verifier).digest('base64url');
        if (computed !== entry.codeChallenge) {
          res.status(400).json({ error: 'invalid_grant', error_description: 'PKCE verification failed' });
          return;
        }
      }

      res.json({ access_token: MCP_KEY, token_type: 'Bearer', expires_in: 3600 });
      return;
    }

    if (body.grant_type === 'client_credentials') {
      if (clientId !== OAUTH_CLIENT_ID || clientSecret !== OAUTH_CLIENT_SECRET) {
        res.status(401).json({ error: 'invalid_client' });
        return;
      }
      res.json({ access_token: MCP_KEY, token_type: 'Bearer', expires_in: 3600 });
      return;
    }

    res.status(400).json({ error: 'unsupported_grant_type' });
  });

  // Stateful Streamable HTTP: one session per Cowork connection (initialize),
  // then many tools/list + tools/call requests keyed by mcp-session-id.
  const sessions = new Map<string, Session>();

  app.get('/mcp', requireBearerAuth, (_req, res) => {
    res.status(405).set('Allow', 'POST, DELETE').json({ error: { code: 'METHOD_NOT_ALLOWED', message: 'Use POST /mcp for Streamable HTTP requests.' } });
  });

  app.post('/mcp', requireBearerAuth, async (req, res) => {
    const existingSessionId = req.header('mcp-session-id');
    let session = existingSessionId ? sessions.get(existingSessionId) : undefined;

    if (!session) {
      if (!isInitializeRequest(req.body)) {
        res.status(400).json({ jsonrpc: '2.0', error: { code: -32000, message: 'Bad Request: no session; first request must be initialize' }, id: null });
        return;
      }
      const server = buildMcpServer(toolset);
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (sessionId) => {
          sessions.set(sessionId, { server, transport });
        }
      });
      transport.onclose = () => {
        if (transport.sessionId) sessions.delete(transport.sessionId);
      };
      await server.connect(transport);
      session = { server, transport };
    }

    await session.transport.handleRequest(req, res, req.body);
  });

  app.delete('/mcp', requireBearerAuth, async (req, res) => {
    const sessionId = req.header('mcp-session-id');
    const session = sessionId ? sessions.get(sessionId) : undefined;
    if (!session) {
      res.status(404).json({ error: { code: 'NOT_FOUND_404', message: 'Unknown session.' } });
      return;
    }
    await session.transport.handleRequest(req, res);
  });

  app.listen(PORT, () => {
    logger.info(`Gmail MCP server listening on :${PORT} (POST/DELETE /mcp, GET /healthz)`);
    logger.info(`Accounts: ${toolset.accounts.map((a) => a.email).join(', ') || '(none registered)'}`);
  });
}

main().catch((error) => {
  logger.error('Fatal error starting server:', error as Error);
  process.exit(1);
});
