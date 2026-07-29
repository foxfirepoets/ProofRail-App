import { createHmac, createHash, timingSafeEqual } from "node:crypto";
import { EvidenceRole, EvidenceSource } from "../types.js";
import {
  ProvenanceVerificationOptions,
  ProvenanceVerificationResult,
  TrustedEvidenceRecord,
  TrustedProvenanceCredentials,
  TrustedProvider,
} from "./types.js";

const DEFAULT_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export class TrustedProvenanceVerifier {
  public constructor(
    private readonly provider: TrustedProvider,
    private readonly role: EvidenceRole,
    private readonly options: ProvenanceVerificationOptions,
  ) {}

  public async verify(record: TrustedEvidenceRecord): Promise<ProvenanceVerificationResult> {
    const credentials = this.options.credentials;
    if (!credentials?.credentialId) return rejected("Trusted provider credentials are unavailable");
    if (record.provider !== this.provider) return rejected("Evidence provider does not match verifier");
    if (!record.immutableId.trim()) return rejected("Provider-issued immutable ID is required");
    if (!(record.payload instanceof Uint8Array) || record.payload.byteLength === 0) {
      return rejected("Raw provider payload bytes are required");
    }

    const capturedAt = Date.parse(record.capturedAt);
    const fetchedAt = Date.parse(record.fetchedAt);
    const now = (this.options.now ?? new Date()).getTime();
    if (!Number.isFinite(capturedAt) || !Number.isFinite(fetchedAt)) return rejected("Captured and fetched timestamps are required");
    if (capturedAt > fetchedAt || fetchedAt > now) return rejected("Evidence timestamps are invalid or from the future");
    if (now - fetchedAt > (this.options.maxAgeMs ?? DEFAULT_MAX_AGE_MS)) return rejected("Evidence attestation is stale");

    const payloadHash = createHash("sha256").update(record.payload).digest("hex");
    const attestation = record.attestation;
    if (!attestation?.keyId || !attestation.signature || attestation.algorithm !== "HMAC-SHA256") {
      return rejected("Signed provider attestation is required");
    }
    const attestationInput = {
      provider: record.provider,
      immutableId: record.immutableId,
      payloadHash,
      capturedAt: new Date(capturedAt).toISOString(),
      attestation,
    };
    const verified = credentials.verifyAttestation
      ? await credentials.verifyAttestation(attestationInput)
      : this.verifyHmac(attestationInput, credentials.attestationSecret);
    if (!verified) return rejected("Provider attestation could not be verified");

    const source = this.options.source ?? sourceForProvider(record.provider);
    return {
      status: "VERIFIED",
      value: {
        credentialId: credentials.credentialId,
        payloadHash,
        evidence: {
          id: `evidence:${createHash("sha256").update(`${record.provider}:${record.immutableId}:${payloadHash}`).digest("hex")}`,
          source,
          sourceId: record.immutableId,
          capturedAt: new Date(capturedAt).toISOString(),
          role: this.role,
          hash: payloadHash,
          fingerprint: payloadHash,
          providerReference: record.providerReference ?? record.immutableId,
          provenanceVerified: true,
          provenanceCredentialId: credentials.credentialId,
          provenancePayloadHash: payloadHash,
          providerImmutableId: record.immutableId,
          ...record.metadata,
        },
      },
    };
  }

  private verifyHmac(input: Parameters<NonNullable<TrustedProvenanceCredentials["verifyAttestation"]>>[0], secret?: string): boolean {
    if (!secret) return false;
    const signed = `${input.provider}:${input.immutableId}:${input.payloadHash}:${input.capturedAt}:${input.attestation.keyId}`;
    const expected = createHmac("sha256", secret).update(signed).digest("hex");
    const actual = input.attestation.signature;
    if (expected.length !== actual.length) return false;
    return timingSafeEqual(Buffer.from(expected), Buffer.from(actual));
  }
}

export class GmailProvenanceVerifier extends TrustedProvenanceVerifier {
  public constructor(options: ProvenanceVerificationOptions) {
    super("GMAIL", EvidenceRole.INSTRUCTION, options);
  }
}

export class DriveProvenanceVerifier extends TrustedProvenanceVerifier {
  public constructor(options: ProvenanceVerificationOptions) {
    super("DRIVE", EvidenceRole.INSTRUCTION, options);
  }
}

export class BankFeedProvenanceVerifier extends TrustedProvenanceVerifier {
  public constructor(options: ProvenanceVerificationOptions, role = EvidenceRole.CLEARING_PROOF) {
    super("BANK_FEED", role, options);
  }
}

export class StatementProvenanceVerifier extends TrustedProvenanceVerifier {
  public constructor(options: ProvenanceVerificationOptions, role = EvidenceRole.CLEARING_PROOF) {
    super("STATEMENT", role, options);
  }
}

function sourceForProvider(provider: TrustedProvider): EvidenceSource {
  return provider === "GMAIL" ? EvidenceSource.GMAIL
    : provider === "DRIVE" ? EvidenceSource.DRIVE
      : provider === "BANK_FEED" ? EvidenceSource.BANK_FEED
        : EvidenceSource.STATEMENT;
}

function rejected(reason: string): ProvenanceVerificationResult {
  return { status: "REJECTED", reason };
}
