import { FakeQboClient } from "./qbo.js";
import { LocalProofClient } from "./proof.js";
import { InMemoryProofRailRepository } from "./repository.js";
import { ProofRailService } from "./service.js";

export const proofRailRepository = new InMemoryProofRailRepository();
export const proofRailProofClient = new LocalProofClient();
export const proofRailQboClient = new FakeQboClient();
export const proofRailService = new ProofRailService(
  proofRailRepository,
  proofRailProofClient,
  proofRailQboClient,
);
