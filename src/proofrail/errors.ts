export type ProofRailErrorCode =
  | "PR-002"
  | "PR-003"
  | "PR-012"
  | "PR-020"
  | "PR-030"
  | "PR-043"
  | "STATE_409"
  | "LOCKED_423"
  | "NOT_FOUND_404";

export class ProofRailError extends Error {
  constructor(
    public readonly code: ProofRailErrorCode,
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
  }
}

export function stateConflict(message: string, detail?: unknown): ProofRailError {
  return new ProofRailError("STATE_409", message, 409, detail);
}

export function moneyLocked(message: string, detail?: unknown): ProofRailError {
  return new ProofRailError("LOCKED_423", message, 423, detail);
}

export function notFound(message: string, detail?: unknown): ProofRailError {
  return new ProofRailError("NOT_FOUND_404", message, 404, detail);
}
