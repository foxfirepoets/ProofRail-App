import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { PaymentOpsError } from "../src/payment-ops/errors.js";
import { PaymentOpsService } from "../src/payment-ops/service.js";
import {
  AccountIdentityStatus,
  ApprovalStatus,
  EvidenceRole,
  EvidenceSource,
  ObligationKind,
  ObligationState,
  PaymentMethod,
  OperatorTarget,
  NonBillOutflowType,
} from "../src/payment-ops/types.js";

const baseObligation = {
  kind: ObligationKind.BILL,
  description: "Monthly construction insurance",
  legalEntity: "STV CM, LLC",
  method: PaymentMethod.ACH,
  idempotencyKey: "base-obligation",
};

const payFromAccountStableId = "uccu-0970-stable";

function verification(obligationId?: string) {
  return {
    payee: "Example Insurance Co.",
    amount: 1250,
    dueDate: "2026-08-01",
    payFromAccountId: "UCCU-0970",
      accountIdentityStatus: AccountIdentityStatus.VERIFIED,
      payFromAccountStableId,
      payToReference: "policy-123",
      amountBasis: "July premium",
      evidence: [{
      id: "drive-account-and-invoice",
      source: EvidenceSource.DRIVE,
      sourceId: "drive-file-1",
        capturedAt: "2026-07-21T12:00:00.000Z",
        role: EvidenceRole.INVOICE,
      }, {
        id: "account-identity-1",
        source: EvidenceSource.DRIVE,
        sourceId: payFromAccountStableId,
        capturedAt: "2026-07-21T12:00:00.000Z",
        role: EvidenceRole.ACCOUNT_IDENTITY,
        obligationId,
        accountId: "UCCU-0970",
        stableAccountId: payFromAccountStableId,
        accountLegalOwner: "STV CM, LLC",
        accountInstitution: "UCCU",
        accountType: "OPERATING_CHECKING",
        providerReference: "drive-account-record-1",
      }],
  };
}

function paymentConfirmation() {
  return {
    id: "payment-confirmation-1",
    source: EvidenceSource.BANK_FEED,
    sourceId: "bank-feed-payment-1",
    capturedAt: "2026-07-21T12:00:00.000Z",
    role: EvidenceRole.PAYMENT_CONFIRMATION,
    accountId: "UCCU-0970",
    stableAccountId: payFromAccountStableId,
    amount: 1250,
    transactionDate: "2026-07-21",
    providerReference: "bank-provider-payment-1",
  };
}

function bankClearingEvidence(obligationId: string) {
  return {
    id: "bank-clearing-1",
    source: EvidenceSource.BANK_FEED,
    sourceId: "bank-feed-entry-1",
    capturedAt: "2026-07-22T12:00:00.000Z",
    role: EvidenceRole.CLEARING_PROOF,
    obligationId,
    accountId: "UCCU-0970",
    stableAccountId: payFromAccountStableId,
    amount: 1250,
    transactionDate: "2026-07-22",
    providerReference: "bank-provider-clearing-1",
  };
}

function approvedService() {
  const service = new PaymentOpsService();
  const created = service.create({ ...baseObligation, benCanPay: "YES", idempotencyKey: "approved-obligation" });
  service.verify(created.obligation.id, verification(created.obligation.id));
  const approved = service.requestApproval(created.obligation.id, { approved: true, approver: "Mike", requestDraftId: "approval-draft-1" }, "Mike");
  return { service, id: approved.obligation.id };
}

describe("simplified STV payment operations invariants", () => {
  it("replays the same obligation for an idempotency key", () => {
    const service = new PaymentOpsService();
    const first = service.create({ ...baseObligation, idempotencyKey: "gmail-msg-1" });
    const second = service.create({
      ...baseObligation,
      description: "A different duplicate payload",
      idempotencyKey: "gmail-msg-1",
    });

    assert.equal(second.obligation.id, first.obligation.id);
    assert.equal(service.list().length, 1);
    assert.equal(second.obligation.description, first.obligation.description);
  });

  it("rejects incomplete account, payee, amount, and due-date verification", () => {
    const service = new PaymentOpsService();
    const created = service.create(baseObligation);

    assert.throws(
      () => service.verify(created.obligation.id, {
      ...verification(),
        payee: "",
        amount: 0,
        dueDate: "",
        payFromAccountId: "",
        payFromAccountStableId: "",
        amountBasis: "",
        payToReference: "",
        accountIdentityStatus: AccountIdentityStatus.MISSING,
      }),
      (error: unknown) => {
        assert.ok(error instanceof PaymentOpsError);
        assert.equal(error.status, 409);
        assert.equal(error.code, "NEEDS_VERIFICATION");
        assert.deepEqual(error.missingGates, ["payee", "amount", "amountBasis", "dueDate", "payFromAccountId", "payFromAccountStableId", "payToReference", "accountIdentity"]);
        return true;
      },
    );
    assert.equal(service.get(created.obligation.id).state, ObligationState.DISCOVERED);
  });

  it("supports valid verification and approval transitions", () => {
    const service = new PaymentOpsService();
    const created = service.create({ ...baseObligation, benCanPay: "YES", idempotencyKey: "valid-verification" });

    const verified = service.verify(created.obligation.id, verification(created.obligation.id));
    assert.equal(verified.obligation.state, ObligationState.VERIFIED);
    assert.equal(verified.obligation.approval, ApprovalStatus.PENDING);

    const approved = service.requestApproval(created.obligation.id, {
      approved: true,
      approver: "Mike",
      scope: "transaction",
      requestDraftId: "approval-draft-2",
    }, "Mike");
    assert.equal(approved.obligation.state, ObligationState.APPROVED);
    assert.equal(approved.obligation.approval, ApprovalStatus.APPROVED);
    assert.equal(approved.obligation.approvals.at(-1)?.status, ApprovalStatus.APPROVED);
  });

  it("rejects illegal state transitions with a 409-style PaymentOpsError", () => {
    const service = new PaymentOpsService();
    const created = service.create(baseObligation);

    assert.throws(
      () => service.markPaid(created.obligation.id, paymentConfirmation()),
      (error: unknown) => {
        assert.ok(error instanceof PaymentOpsError);
        assert.equal(error.status, 409);
        assert.equal(error.code, "INVALID_STATE");
        return true;
      },
    );
  });

  it("defaults non-autopay obligations to Ben", () => {
    const service = new PaymentOpsService();
    const created = service.create(baseObligation);

    assert.equal(created.obligation.autopay, false);
    assert.equal(created.obligation.targetOperator, OperatorTarget.BEN);
  });

  it("requires and records an explicit Aubrey fallback reason", () => {
    const service = new PaymentOpsService();
    const created = service.create(baseObligation);

    assert.throws(
      () => service.markUnavailable(created.obligation.id, "   "),
      (error: unknown) => {
        assert.ok(error instanceof PaymentOpsError);
        assert.equal(error.status, 409);
        assert.equal(error.code, "AUBREY_REASON_REQUIRED");
        return true;
      },
    );

    const fallback = service.markUnavailable(created.obligation.id, "Ben unavailable during travel", "Ben", "aubrey-task-1");
    assert.equal(fallback.obligation.targetOperator, OperatorTarget.AUBREY);
    assert.equal(fallback.obligation.aubreyRequired, true);
    assert.equal(fallback.obligation.aubreyReason, "Ben unavailable during travel");
  });

  it("does not clear autopay without bank clearing evidence", () => {
    const service = new PaymentOpsService();
    const created = service.create({ ...baseObligation, method: PaymentMethod.AUTOPAY, autopay: true, idempotencyKey: "autopay-obligation" });
    const verified = service.verify(created.obligation.id, verification(created.obligation.id));
    assert.equal(verified.obligation.state, ObligationState.APPROVED);
    assert.equal(verified.obligation.approval, ApprovalStatus.NOT_REQUIRED);

    service.markScheduled(created.obligation.id);
    service.markPaid(created.obligation.id, { ...paymentConfirmation(), obligationId: created.obligation.id });

    assert.throws(
      () => service.clear(created.obligation.id, {
        ...paymentConfirmation(),
        id: "non-bank-clearing-1",
        role: EvidenceRole.CLEARING_PROOF,
        source: EvidenceSource.OTHER,
        obligationId: created.obligation.id,
        accountId: "UCCU-0970",
      }),
      (error: unknown) => {
        assert.ok(error instanceof PaymentOpsError);
        assert.equal(error.status, 409);
        assert.equal(error.code, "BANK_EVIDENCE_REQUIRED");
        return true;
      },
    );
    assert.equal(service.get(created.obligation.id).state, ObligationState.PAID_PENDING_CLEARING);

    const cleared = service.clear(created.obligation.id, bankClearingEvidence(created.obligation.id));
    assert.equal(cleared.obligation.state, ObligationState.CLEARED);
    assert.deepEqual(cleared.obligation.clearingEvidenceIds, ["bank-clearing-1"]);
  });

  it("keeps payment confirmation and bank clearing as separate required gates", () => {
    const { service, id } = approvedService();
    service.markScheduled(id);

    assert.throws(
      () => service.clear(id, bankClearingEvidence(id)),
      (error: unknown) => {
        assert.ok(error instanceof PaymentOpsError);
        assert.equal(error.status, 409);
        assert.equal(error.code, "INVALID_STATE");
        return true;
      },
    );
    assert.equal(service.get(id).state, ObligationState.SCHEDULED);

    const paid = service.markPaid(id, { ...paymentConfirmation(), obligationId: id });
    assert.equal(paid.obligation.state, ObligationState.PAID_PENDING_CLEARING);
    assert.deepEqual(paid.obligation.confirmationEvidenceIds, ["payment-confirmation-1"]);

    const cleared = service.clear(id, bankClearingEvidence(id));
    assert.equal(cleared.obligation.state, ObligationState.CLEARED);
    assert.deepEqual(cleared.obligation.clearingEvidenceIds, ["bank-clearing-1"]);
  });

  it("records non-bill outflows separately and does not treat them as bills", () => {
    const service = new PaymentOpsService();
    const outflow = service.createNonBill({
      type: NonBillOutflowType.INTERCOMPANY_TRANSFER,
      sourceEntity: "STV CM, LLC",
      destination: "12SB, LLC",
      amount: 5000,
      date: "2026-07-21",
    });

    assert.equal(service.list().length, 0);
    assert.equal(service.listNonBill().length, 1);
    assert.equal(service.listNonBill()[0]?.id, outflow.id);
    assert.equal(outflow.type, NonBillOutflowType.INTERCOMPANY_TRANSFER);
    assert.equal("state" in outflow, false);
    assert.equal("payee" in outflow, false);
  });
});
