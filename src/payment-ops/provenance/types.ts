import { EvidenceRef, EvidenceSource } from "../types.js";

export type TrustedProvider = "GMAIL" | "DRIVE" | "BANK_FEED" | "STATEMENT";

export interface ProviderAttestation {
  algorithm: "HMAC-SHA256";
  keyId: string;
  signature: string;
}

export interface TrustedEvidenceRecord {
  provider: TrustedProvider;
  immutableId: string;
  capturedAt: string;
  fetchedAt: string;
  payload: Uint8Array;
  providerReference?: string;
  attestation?: ProviderAttestation;
  metadata?: {
    obligationId?: string;
    accountId?: string;
    stableAccountId?: string;
    amount?: number;
    transactionDate?: string;
    accountLegalOwner?: string;
    accountInstitution?: string;
    accountType?: string;
  };
}

export interface TrustedProvenanceCredentials {
  credentialId: string;
  attestationSecret?: string;
  verifyAttestation?: (input: {
    provider: TrustedProvider;
    immutableId: string;
    payloadHash: string;
    capturedAt: string;
    attestation: ProviderAttestation;
  }) => boolean | Promise<boolean>;
}

export interface ProvenanceVerificationOptions {
  credentials?: TrustedProvenanceCredentials;
  now?: Date;
  maxAgeMs?: number;
  source?: EvidenceSource;
}

export interface VerifiedProvenance {
  evidence: EvidenceRef;
  payloadHash: string;
  credentialId: string;
}

export interface ProvenanceRejection {
  status: "REJECTED";
  reason: string;
}

export interface ProvenanceVerificationSuccess {
  status: "VERIFIED";
  value: VerifiedProvenance;
}

export type ProvenanceVerificationResult = ProvenanceVerificationSuccess | ProvenanceRejection;
