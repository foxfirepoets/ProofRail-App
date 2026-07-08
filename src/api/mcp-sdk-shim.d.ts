/**
 * Ambient shim for @modelcontextprotocol/sdk deep-import subpaths.
 *
 * Why this file exists: the installed @modelcontextprotocol/sdk (checked: 1.29.0, the latest
 * on npm as of 2026-07-08) ships ZERO .d.ts files anywhere under dist/ in this environment -
 * confirmed with `find node_modules/@modelcontextprotocol/sdk/dist -iname '*.d.ts' | wc -l` = 0.
 * The runtime .js files are present and correct (verified against source), so this is a types-only
 * gap, not a broken install. Before deploying this for real, re-run that same find command in your
 * deploy environment; if it returns >0 there, delete this shim file - the real types are better.
 */
declare module "@modelcontextprotocol/sdk/server/mcp.js" {
  export interface McpServerInfo {
    name: string;
    version: string;
  }
  export interface McpServerOptions {
    capabilities?: { tools?: Record<string, unknown> };
  }
  export interface RegisteredToolConfig {
    description?: string;
    inputSchema?: unknown;
  }
  export interface ToolCallResult {
    isError?: boolean;
    content: { type: "text"; text: string }[];
  }
  export class McpServer {
    constructor(serverInfo: McpServerInfo, options?: McpServerOptions);
    registerTool(
      name: string,
      config: RegisteredToolConfig,
      handler: (args: unknown) => Promise<ToolCallResult>,
    ): void;
    connect(transport: unknown): Promise<void>;
    close(): Promise<void> | void;
  }
}

declare module "@modelcontextprotocol/sdk/server/streamableHttp.js" {
  import type { IncomingMessage, ServerResponse } from "node:http";

  export interface StreamableHTTPServerTransportOptions {
    sessionIdGenerator?: () => string;
    onsessioninitialized?: (sessionId: string) => void | Promise<void>;
  }
  export class StreamableHTTPServerTransport {
    constructor(options?: StreamableHTTPServerTransportOptions);
    readonly sessionId: string | undefined;
    onclose: (() => void) | undefined;
    handleRequest(req: IncomingMessage, res: ServerResponse, parsedBody?: unknown): Promise<void>;
    close(): Promise<void> | void;
  }
}
