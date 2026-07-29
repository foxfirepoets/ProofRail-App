import { createHash, createHmac } from "node:crypto";
import test from "node:test";
import assert from "node:assert/strict";
import { EvidenceRole } from "../src/payment-ops/types.js";
import { GmailProvenanceVerifier } from "../src/payment-ops/provenance/index.js";

const secret = "test-provider-secret";
const now = new Date("2026-07-21T12:00:00.000Z");

function record(payload: Uint8Array, signature: string) {
  return {
    provider: "GMAIL" as const,
    immutableId: "gmail-message-immutable-1",
    capturedAt: "2026-07-21T11:00:00.000Z",
    fetchedAt: "2026-07-21T11:30:00.000Z",
    payload,
    attestation: { algorithm: "HMAC-SHA256" as const, keyId: "gmail-key-1", signature },
  };
}

function sign(payload: Uint8Array): string {
  const hash = createHash("sha256").update(payload).digest("hex");
  return createHmac("sha256", secret)
    .update(`GMAIL:gmail-message-immutable-1:${hash}:2026-07-21T11:00:00.000Z:gmail-key-1`)
    .digest("hex");
}

test("trusted provenance computes payload hash and maps verified Gmail evidence", async () => {
  const payload = new TextEncoder().encode("provider payload");
  const result = await new GmailProvenanceVerifier({ credentials: { credentialId: "cred-1", attestationSecret: secret }, now }).verify(record(payload, sign(payload)));
  assert.equal(result.status, "VERIFIED");
  if (result.status === "VERIFIED") {
    assert.equal(result.value.evidence.role, EvidenceRole.INSTRUCTION);
    assert.equal(result.value.evidence.sourceId, "gmail-message-immutable-1");
    assert.equal(result.value.evidence.hash, result.value.payloadHash);
  }
});

test("caller-provided fingerprint without attestation is rejected", async () => {
  const result = await new GmailProvenanceVerifier({ credentials: { credentialId: "cred-1", attestationSecret: secret }, now }).verify({ ...record(new Uint8Array([1]), ""), attestation: undefined });
  assert.deepEqual(result, { status: "REJECTED", reason: "Signed provider attestation is required" });
});

test("mismatched payload, stale evidence, and missing credentials fail closed", async () => {
  const payload = new TextEncoder().encode("provider payload");
  const mismatch = await new GmailProvenanceVerifier({ credentials: { credentialId: "cred-1", attestationSecret: secret }, now }).verify(record(new TextEncoder().encode("tampered"), sign(payload)));
  assert.equal(mismatch.status, "REJECTED");
  const stale = await new GmailProvenanceVerifier({ credentials: { credentialId: "cred-1", attestationSecret: secret }, now, maxAgeMs: 1 }).verify(record(payload, sign(payload)));
  assert.equal(stale.status, "REJECTED");
  const unavailable = await new GmailProvenanceVerifier({ now }).verify(record(payload, sign(payload)));
  assert.equal(unavailable.status, "REJECTED");
});
