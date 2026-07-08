import { FakeQboClient } from "./qbo.js";
import { SwarmSyncProofClient } from "./proof.js";
import { PostgresProofRailRepository } from "./postgres-repository.js";
import { ProofRailService } from "./service.js";

// InvoiceProof and VerifyAPI/AuditProof are now real (SwarmSyncProofClient) - see proof.ts doc
// comment for the auth-key nuance (VerifyAPI/AuditProof fall back to a local stamp until
// SWARMSYNC_VERIFY_API_KEY is set). Persistence is now real (PostgresProofRailRepository, lean
// proofrail_*-prefixed schema in the "Summa Terra Co-Work Automation" Supabase project) - see
// CLAUDE.md/OWNER_UPDATES for why QboClient is still FakeQboClient: real QBO posting stays PAUSED
// per Ben's 2026-07-08 directive until he completes a separate OAuth grant (single-writer
// collision risk with the work-machine's scripts/*.py pipeline) - do not flip this to
// RealQboClient without that approval.
export const proofRailRepository = new PostgresProofRailRepository();
export const proofRailProofClient = new SwarmSyncProofClient();
export const proofRailQboClient = new FakeQboClient();
export const proofRailService = new ProofRailService(
  proofRailRepository,
  proofRailProofClient,
  proofRailQboClient,
);
