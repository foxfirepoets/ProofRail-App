"use client";

import { useEffect, useState } from "react";
import styles from "./page.module.css";

type EvidenceRef = {
  id: string;
  role?: string;
  source?: string;
  sourceId?: string;
  capturedAt?: string;
};

type AccountIdentity = {
  lastFour?: string;
};

type ApprovalLog = {
  approver?: string;
  status?: string;
  timestamp?: string;
};

type Obligation = {
  id: string;
  legalEntity: string;
  payee: string;
  dueDate?: string;
  amount?: number;
  amountBasis?: string;
  payToReference?: string;
  method: string;
  approval: string;
  approvals?: ApprovalLog[];
  targetOperator: string;
  accountIdentityStatus: "VERIFIED" | "CONFLICT" | "MISSING";
  state?: string;
  evidence?: EvidenceRef[];
  confirmationEvidenceIds?: string[];
  clearingEvidenceIds?: string[];
  accountIdentity?: AccountIdentity;
  conflictReason?: string;
};

type LoadState = "loading" | "ready" | "error";

const apiBaseUrl = process.env.NEXT_PUBLIC_PAYMENT_OPS_API_BASE_URL?.replace(/\/$/, "");

function formatAmount(amount?: number) {
  if (amount === undefined) return "Not provided";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function statusLabel(value?: string) {
  return value?.replaceAll("_", " ") || "Not recorded";
}

function accountLabel(obligation: Obligation) {
  const lastFour = obligation.accountIdentity?.lastFour?.match(/^\d{4}$/)?.[0];
  return lastFour ? `Protected account ···· ${lastFour}` : "Protected account identity";
}

function evidenceSummary(obligation: Obligation) {
  const evidenceCount = obligation.evidence?.length ?? 0;
  const confirmationCount = obligation.confirmationEvidenceIds?.length ?? 0;
  const clearingCount = obligation.clearingEvidenceIds?.length ?? 0;
  return `${evidenceCount} evidence link${evidenceCount === 1 ? "" : "s"} · ${confirmationCount} confirmation · ${clearingCount} clearing proof`;
}

export default function PaymentOpsPage() {
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string>();

  useEffect(() => {
    if (!apiBaseUrl) {
      setLoadState("ready");
      return;
    }

    const controller = new AbortController();
    fetch(`${apiBaseUrl}/payment-obligations`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Payment register returned ${response.status}.`);
        const payload: unknown = await response.json();
        const rows = Array.isArray(payload)
          ? payload
          : payload && typeof payload === "object" && "items" in payload && Array.isArray(payload.items)
            ? payload.items
            : [];
        setObligations(rows as Obligation[]);
        setLoadState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setErrorMessage(error instanceof Error ? error.message : "The payment register could not be loaded.");
        setLoadState("error");
      });

    return () => controller.abort();
  }, []);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>ProofRail · operator view</p>
          <h1>STV payment operations</h1>
          <p className={styles.intro}>
            One place to review what is due, who receives it, which protected account pays, and what proof is still missing.
          </p>
        </div>
        <div className={styles.lockBadge} aria-label="Fail-closed payment status">
          <span aria-hidden="true">●</span> Fail closed
          <small>No money movement from this screen</small>
        </div>
      </header>

      <section className={styles.workflow} aria-labelledby="workflow-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Control path</p>
            <h2 id="workflow-title">Review before anyone pays</h2>
          </div>
          <p className={styles.gateNote}>A missing proof or account conflict blocks execution.</p>
        </div>
        <ol className={styles.steps}>
          <li><span>1</span><strong>Verify</strong><small>entity · payee · amount · account</small></li>
          <li><span>2</span><strong>Approve</strong><small>Mike or standing policy</small></li>
          <li><span>3</span><strong>Execute manually</strong><small>Ben first · Aubrey fallback</small></li>
          <li><span>4</span><strong>Prove and clear</strong><small>confirmation · bank evidence</small></li>
        </ol>
      </section>

      <section className={styles.register} aria-labelledby="register-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Canonical queue</p>
            <h2 id="register-title">Payment control register</h2>
          </div>
          {apiBaseUrl ? <span className={styles.source}>Source: configured payment register</span> : <span className={styles.source}>Source: not connected</span>}
        </div>

        {loadState === "loading" && <p className={styles.state} role="status">Loading payment obligations…</p>}
        {loadState === "error" && (
          <div className={`${styles.state} ${styles.error}`} role="alert">
            <strong>Payment obligations could not be loaded.</strong>
            <p>{errorMessage}</p>
            <p>Nothing on this screen is executable until the register is available.</p>
          </div>
        )}
        {loadState === "ready" && obligations.length === 0 && (
          <div className={styles.empty} role="status">
            <h3>No payment obligations loaded</h3>
            <p>
              {apiBaseUrl
                ? "The connected register has no rows to display. This screen does not invent payment data."
                : "Connect a payment-obligations API to display the canonical queue. This screen does not invent payment data."}
            </p>
            <p className={styles.muted}>Set <code>NEXT_PUBLIC_PAYMENT_OPS_API_BASE_URL</code> for the read-only register source.</p>
          </div>
        )}
        {loadState === "ready" && obligations.length > 0 && (
          <div className={styles.tableWrap}>
            <table>
              <caption className={styles.srOnly}>Payment obligations and their execution gates</caption>
              <thead>
                <tr>
                  <th scope="col">Entity / payee</th><th scope="col">Due</th><th scope="col">Amount</th>
                  <th scope="col">Pay from</th><th scope="col">Method</th><th scope="col">Approval</th>
                  <th scope="col">Operator</th><th scope="col">State / proof</th>
                </tr>
              </thead>
              <tbody>
                {obligations.map((obligation) => {
                  const evidence = obligation.evidence ?? [];
                  const blocked = obligation.accountIdentityStatus !== "VERIFIED" || evidence.length === 0;
                  const approvalLog = obligation.approvals?.at(-1);
                  return (
                    <tr key={obligation.id}>
                      <td><strong>{obligation.legalEntity || "Entity not recorded"}</strong><span>{obligation.payee || "Payee not recorded"}</span><span>To: {obligation.payToReference || "Pay-to reference not recorded"}</span></td>
                      <td>{obligation.dueDate || "Not provided"}</td>
                      <td><strong>{formatAmount(obligation.amount)}</strong><span>Basis: {obligation.amountBasis || "Not recorded"}</span></td>
                      <td><strong>{accountLabel(obligation)}</strong><span className={obligation.accountIdentityStatus === "VERIFIED" ? styles.verified : styles.blocked}>{statusLabel(obligation.accountIdentityStatus)}</span>{obligation.accountIdentityStatus === "CONFLICT" && <span className={styles.conflict}>Conflict</span>}{obligation.conflictReason && <span className={styles.conflictDetail}>{obligation.conflictReason}</span>}</td>
                      <td>{statusLabel(obligation.method)}</td>
                      <td><strong>{statusLabel(obligation.approval)}</strong>{approvalLog && <span>{approvalLog.approver || "Approver not recorded"} · {statusLabel(approvalLog.status)}</span>}</td>
                      <td><strong>{statusLabel(obligation.targetOperator)}</strong></td>
                      <td><strong>{statusLabel(obligation.state)}</strong><span className={blocked ? styles.blocked : styles.verified}>{blocked ? "Proof blocked — verification or evidence needed" : "Evidence linked"}</span><span>{evidenceSummary(obligation)}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <aside className={styles.notice} aria-label="Operator safety notice">
        <strong>Operator safety notice</strong>
        <span>Use this view to review and prepare a human task. Email remains draft-only, and payment execution remains outside the app.</span>
      </aside>
    </main>
  );
}
