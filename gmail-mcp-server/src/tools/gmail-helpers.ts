import { Buffer } from 'buffer';
import { randomUUID } from 'crypto';
import fs from 'fs';
import os from 'os';
import * as path from 'path';
import { marked } from 'marked';

export function decodeBase64Data(fileData: string): Buffer {
  const standardBase64Data = fileData.replace(/-/g, '+').replace(/_/g, '/');
  const padding = '='.repeat((4 - standardBase64Data.length % 4) % 4);
  return Buffer.from(standardBase64Data + padding, 'base64');
}

function getAttachmentsBaseDir(): string {
  const fromEnv = process.env.GMAIL_ATTACHMENTS_DIR;
  const baseDir = fromEnv && fromEnv.length > 0
    ? path.resolve(fromEnv)
    : path.join(os.homedir(), '.mcp-gsuite', 'attachments');
  fs.mkdirSync(baseDir, { recursive: true });
  return baseDir;
}

/**
 * Resolves a caller-supplied attachment filename against the configured
 * attachments base directory (GMAIL_ATTACHMENTS_DIR, defaulting to
 * ~/.mcp-gsuite/attachments). Absolute paths, traversal, NUL bytes and
 * symlink escapes are rejected.
 */
export function resolveAttachmentPath(filePath: string): string {
  if (typeof filePath !== 'string' || filePath.length === 0 || filePath.includes('\0')) {
    throw new Error('Invalid save path');
  }
  if (path.isAbsolute(filePath)) {
    throw new Error(
      `Absolute save paths are not allowed; provide a relative path under GMAIL_ATTACHMENTS_DIR (got: ${filePath})`
    );
  }
  const baseDir = getAttachmentsBaseDir();
  const resolved = path.resolve(baseDir, filePath);
  if (resolved !== baseDir && !resolved.startsWith(baseDir + path.sep)) {
    throw new Error(`Save path escapes attachments directory: ${filePath}`);
  }
  const parent = path.dirname(resolved);
  fs.mkdirSync(parent, { recursive: true });
  const realBase = fs.realpathSync(baseDir);
  const realParent = fs.realpathSync(parent);
  if (realParent !== realBase && !realParent.startsWith(realBase + path.sep)) {
    throw new Error(`Save path escapes attachments directory via symlink: ${filePath}`);
  }
  return resolved;
}

interface MessageHeaderLike {
  name?: string | null;
  value?: string | null;
}

export interface DraftMessageLike {
  id?: string | null;
  threadId?: string | null;
  internalDate?: string | null;
  snippet?: string | null;
  payload?: {
    headers?: MessageHeaderLike[] | null;
  } | null;
}

export interface DraftEntry {
  draft_id: string;
  message_id: string | null;
  threadId?: string | null;
  internalDate?: string | null;
  snippet?: string | null;
  headers?: Record<string, string>;
}

export type EmailBodyType = 'plain' | 'html' | 'markdown';

export interface RenderedEmailBody {
  contentType: 'text/plain' | 'text/html';
  body: string;
}

/**
 * Renders the agent-supplied body into the MIME body + Content-Type the
 * Gmail API should see. 'plain' is passthrough (current behavior),
 * 'html' is passthrough as text/html, 'markdown' is rendered to HTML
 * via marked. Defaults to 'plain' when the input is omitted/unknown so
 * existing callers see no behavior change.
 */
export function renderEmailBody(body: string, bodyType: EmailBodyType | string | undefined): RenderedEmailBody {
  switch (bodyType) {
    case 'html':
      return { contentType: 'text/html', body };
    case 'markdown':
      return { contentType: 'text/html', body: marked.parse(body, { async: false }) as string };
    case 'plain':
    default:
      return { contentType: 'text/plain', body };
  }
}

export interface AttachmentInput {
  /** Display filename, e.g. "invoice.pdf". Never used as a filesystem path. */
  filename: string;
  /** File content, base64 or base64url encoded (both accepted). */
  content_base64: string;
  /** Defaults to application/octet-stream if omitted. */
  mime_type?: string;
}

export interface RawMessageHeaders {
  to?: string;
  cc?: string;
  subject: string;
  inReplyTo?: string;
  references?: string;
}

const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024; // Gmail's own combined-attachment cap

/** Re-encodes base64 or base64url input as standard, padded base64 (RFC 2045). */
function toStandardBase64(data: string): string {
  const std = data.replace(/-/g, '+').replace(/_/g, '/');
  const padding = '='.repeat((4 - (std.length % 4)) % 4);
  return std + padding;
}

/** RFC 2045 requires base64 body lines wrapped at 76 chars. */
function wrapBase64(b64: string): string {
  const out: string[] = [];
  for (let i = 0; i < b64.length; i += 76) out.push(b64.slice(i, i + 76));
  return out.join('\r\n');
}

/** Header values (filenames, subjects) must not carry CR/LF or bare quotes. */
function sanitizeHeaderValue(value: string): string {
  return value.replace(/[\r\n"]/g, '');
}

/**
 * Builds a full RFC 2822 message (plain body, optionally multipart/mixed with
 * attachments) and returns it base64url-encoded, ready for Gmail API's
 * `raw` field. Caller is responsible for sanitizing `headers` values that
 * come from outside this module (this function only sanitizes attachment
 * filenames, which are always caller-supplied).
 */
export function buildRawMessage(
  headers: RawMessageHeaders,
  body: RenderedEmailBody,
  attachments?: AttachmentInput[]
): string {
  const lines: string[] = [];
  if (headers.to) lines.push(`To: ${headers.to}`);
  if (headers.cc) lines.push(`Cc: ${headers.cc}`);
  if (headers.inReplyTo) lines.push(`In-Reply-To: ${headers.inReplyTo}`);
  if (headers.references) lines.push(`References: ${headers.references}`);
  lines.push(`Subject: ${headers.subject}`);
  lines.push('MIME-Version: 1.0');

  if (!attachments || attachments.length === 0) {
    lines.push(`Content-Type: ${body.contentType}; charset="UTF-8"`);
    lines.push('', body.body);
    return Buffer.from(lines.join('\r\n'), 'utf-8').toString('base64url');
  }

  let totalBytes = 0;
  const encoded = attachments.map((att) => {
    if (!att.filename || !att.content_base64) {
      throw new Error('Each attachment needs filename and content_base64');
    }
    const std = toStandardBase64(att.content_base64);
    const bytes = Buffer.from(std, 'base64');
    totalBytes += bytes.length;
    if (totalBytes > MAX_ATTACHMENT_BYTES) {
      throw new Error(
        `Attachments exceed Gmail's 25MB combined limit (got ${(totalBytes / 1024 / 1024).toFixed(1)}MB so far)`
      );
    }
    return { filename: sanitizeHeaderValue(att.filename), mimeType: att.mime_type || 'application/octet-stream', b64: wrapBase64(bytes.toString('base64')) };
  });

  const boundary = `----=_gmail_mcp_${randomUUID().replace(/-/g, '')}`;
  lines.push(`Content-Type: multipart/mixed; boundary="${boundary}"`);
  lines.push('', `--${boundary}`);
  lines.push(`Content-Type: ${body.contentType}; charset="UTF-8"`);
  lines.push('', body.body, '');

  for (const att of encoded) {
    lines.push(`--${boundary}`);
    lines.push(`Content-Type: ${att.mimeType}; name="${att.filename}"`);
    lines.push('Content-Transfer-Encoding: base64');
    lines.push(`Content-Disposition: attachment; filename="${att.filename}"`);
    lines.push('', att.b64, '');
  }
  lines.push(`--${boundary}--`);

  return Buffer.from(lines.join('\r\n'), 'utf-8').toString('base64url');
}

/**
 * Shapes a single (draft, message) pair into the public response entry
 * for gmail_list_drafts. Headers are lowercased; entries with no
 * underlying message return a minimal { draft_id, message_id: null }.
 */
export function formatDraftEntry(draftId: string, message: DraftMessageLike | null | undefined): DraftEntry {
  if (!message || !message.id) {
    return { draft_id: draftId, message_id: null };
  }
  const headers: Record<string, string> = {};
  message.payload?.headers?.forEach(h => {
    if (h.name && h.value) headers[h.name.toLowerCase()] = h.value;
  });
  return {
    draft_id: draftId,
    message_id: message.id,
    threadId: message.threadId,
    internalDate: message.internalDate,
    snippet: message.snippet,
    headers,
  };
}
