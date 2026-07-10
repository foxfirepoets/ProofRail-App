import { RealQboClient, type ClassResolver } from "./qbo.js";
import { SwarmSyncProofClient } from "./proof.js";
import { PostgresProofRailRepository } from "./postgres-repository.js";
import { ProofRailService } from "./service.js";
import { QboTokenStore } from "./qbo-token-store.js";
import { requiredEnv } from "../env.js";

// InvoiceProof and VerifyAPI/AuditProof are real (SwarmSyncProofClient) - see proof.ts doc
// comment for the auth-key nuance (VerifyAPI/AuditProof fall back to a local stamp until
// SWARMSYNC_VERIFY_API_KEY is set). Persistence is real (PostgresProofRailRepository, lean
// proofrail_*-prefixed schema in the "Summa Terra Co-Work Automation" Supabase project).
//
// QboClient is REAL as of 2026-07-10 (Ben's explicit go-ahead, after all 7 acceptance tests in
// docs/QBO_MCP_OAUTH_APPROVAL.md section 4 passed live against the sandbox - including a live
// parity check against the known-good Python path, plus the void_transaction capability, added
// same day - see git log for both). Bills/Invoices/JournalEntries now post/void/delete for real
// against Realm A (partnership/projects) when approve/void_transaction is called through this
// MCP server, from either Cowork or Claude Code CLI - this is no longer a no-op. Uses this app's
// OWN separate Intuit OAuth grant (proofrail_qbo_token_store), never the work-machine's
// scripts/*.py tokens - see QBO_MCP_OAUTH_APPROVAL.md section 1 for why that separation matters.
export const proofRailRepository = new PostgresProofRailRepository();
export const proofRailProofClient = new SwarmSyncProofClient();

const classResolver: ClassResolver = { resolveQboClass: (input) => proofRailRepository.resolveQboClass(input) };

const qboTokenStore = new QboTokenStore();
const realmAToken = await qboTokenStore.get("A");
if (!realmAToken) {
  throw new Error(
    "No stored QBO token for realm A in proofrail_qbo_token_store. Visit /auth/qbo/start?realm=A " +
      "to complete the OAuth consent before this service can start with a real QboClient.",
  );
}

export const proofRailQboClient = new RealQboClient({
  clientId: requiredEnv("QBO_CLIENT_ID"),
  clientSecret: requiredEnv("QBO_CLIENT_SECRET"),
  realmId: requiredEnv("QBO_REALM_A"),
  refreshToken: realmAToken.refreshToken,
  expectedCompanyName: requiredEnv("QBO_REALM_A_NAME"),
  classResolver,
  minorVersion: process.env.QBO_MINORVERSION,
  baseUrl: process.env.QBO_BASE_URL,
  onRefreshTokenRotated: (newRefreshToken, newAccessToken, accessExpiresAt) =>
    qboTokenStore.persistRotation("A", newRefreshToken, newAccessToken, accessExpiresAt),
});

export const proofRailService = new ProofRailService(
  proofRailRepository,
  proofRailProofClient,
  proofRailQboClient,
);
