import { task } from "@trigger.dev/sdk";
import { proofRailRepository, proofRailService } from "../proofrail/container.js";

export const nightlyGates = task({
  id: "nightly-gates",
  retry: { maxAttempts: 3, minTimeoutInMs: 1_000, maxTimeoutInMs: 10_000, factor: 2 },
  run: async () => {
    const results = [
      { gate: "G-A", pass: true, summary: "BS-by-Location gate placeholder wired; replace with QBO report read." },
      { gate: "G-B", pass: true, summary: "Unclassified queue gate placeholder wired." },
      { gate: "G-C", pass: true, summary: "Intercompany mirror gate placeholder wired." },
      { gate: "G-D", pass: true, summary: "Forbidden account posting gate placeholder wired." },
      { gate: "G-E", pass: true, summary: "Fee compliance gate placeholder wired." },
      { gate: "G-F", pass: true, summary: "Arixa protected amount gate placeholder wired." },
    ];
    const verdict = results.every((result) => result.pass) ? "GREEN" : "RED";
    return proofRailService.saveGateRun(verdict, results);
  },
});

export const heartbeatWatch = task({
  id: "heartbeat-watch",
  run: async () => {
    const intakeCount = await proofRailRepository.countIntakes();
    return {
      intake_count: intakeCount,
      status: intakeCount === 0 ? "NO_INTAKE_SEEN" : "OK",
    };
  },
});

export const qboTokenRefresh = task({
  id: "qbo-token-refresh",
  retry: { maxAttempts: 3, minTimeoutInMs: 2_000, maxTimeoutInMs: 30_000, factor: 2 },
  run: async () => ({
    status: "DELEGATED_TO_SANDBOX_SCRIPT",
    command: "npm run qbo:check",
  }),
});

export const proofReplayQueue = task({
  id: "proof-replay-queue",
  run: async () => ({ replayed: 0, status: "EMPTY" }),
});

export const qboReconcilePoll = task({
  id: "qbo-reconcile-poll",
  retry: { maxAttempts: 3, minTimeoutInMs: 2_000, maxTimeoutInMs: 30_000, factor: 2 },
  run: async () => ({
    status: "WIRED",
    note: "Replace placeholder with read-only QBO BalanceSheet and transaction-count checks before production.",
  }),
});
