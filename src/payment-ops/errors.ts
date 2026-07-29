export class PaymentOpsError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly missingGates: string[] = [],
  ) {
    super(message);
    this.name = "PaymentOpsError";
  }
}
