import fs from "node:fs";

const base = process.argv[2] ?? "https://proofrail-mcp.onrender.com";
const env = Object.fromEntries(
  fs
    .readFileSync(".env", "utf8")
    .split(/\r?\n/)
    .filter((line) => /^\s*[^#][^=]+=/.test(line))
    .map((line) => {
      const i = line.indexOf("=");
      return [line.slice(0, i).trim(), line.slice(i + 1).trim().replace(/^"|"$/g, "")];
    }),
);

const tokenResponse = await fetch(`${base}/oauth/token`, {
  method: "POST",
  body: new URLSearchParams({
    grant_type: "client_credentials",
    client_id: env.PROOFRAIL_OAUTH_CLIENT_ID || "proofrail-cowork",
    client_secret: env.PROOFRAIL_MCP_KEY,
  }),
});
const token = await tokenResponse.json();

const protectedResourceResponse = await fetch(`${base}/.well-known/oauth-protected-resource/mcp`);
const protectedResource = await protectedResourceResponse.json();

const headers = {
  Authorization: `Bearer ${token.access_token}`,
  Accept: "application/json, text/event-stream",
  "Content-Type": "application/json",
};

const initResponse = await fetch(`${base}/mcp`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "codex-e2e", version: "0.1" },
    },
  }),
});
const initText = await initResponse.text();
const sessionId = initResponse.headers.get("mcp-session-id");

const output = {
  tokenStatus: tokenResponse.status,
  tokenType: token.token_type,
  protectedResourceStatus: protectedResourceResponse.status,
  protectedResource: protectedResource.resource,
  initStatus: initResponse.status,
  sessionPresent: Boolean(sessionId),
  initPreview: initText.slice(0, 220),
};

function parseMcpPayload(text) {
  const eventLine = text
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice("data: ".length))
    .join("");
  return eventLine ? JSON.parse(eventLine) : JSON.parse(text);
}

if (sessionId) {
  const listResponse = await fetch(`${base}/mcp`, {
    method: "POST",
    headers: { ...headers, "mcp-session-id": sessionId },
    body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }),
  });
  const listText = await listResponse.text();
  const tools = Array.from(listText.matchAll(/"name":"([^"]+)/g)).map((match) => match[1]);
  Object.assign(output, {
    listStatus: listResponse.status,
    listContentType: listResponse.headers.get("content-type"),
    toolCount: tools.length,
    tools,
  });

  const gateResponse = await fetch(`${base}/mcp`, {
    method: "POST",
    headers: { ...headers, "mcp-session-id": sessionId },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: "get_gate_status", arguments: {} },
    }),
  });
  const gateRaw = await gateResponse.text();
  const gatePayload = parseMcpPayload(gateRaw);
  const gateText = gatePayload.result?.content?.[0]?.text;
  Object.assign(output, {
    gateStatus: gateResponse.status,
    gateResult: gateText ? JSON.parse(gateText) : gatePayload,
  });
}

console.log(JSON.stringify(output, null, 2));
