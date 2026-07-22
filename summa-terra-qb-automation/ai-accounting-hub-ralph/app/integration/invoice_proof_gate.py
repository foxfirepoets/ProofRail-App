"""InvoiceProof Gate 1 — VCAP Full Bundle seal for AP money-movement (SPEC §5 Flow 1 Step 11).

This is the hard gate between ``/intents/bill`` intake and any downstream action.
It is called synchronously after the Bill row is created and before the Temporal
workflow is started. When Temporal wiring lands, this becomes an Activity.

Design invariants (MUST NOT be softened):
- GATE FAILS CLOSED: every failure path raises ``InvoiceProofGateFailed``; the
  caller MUST NOT catch-and-continue. No bill ever advances past draft without a
  ``passed=True`` ``proof_bundles`` row linked to it.
- Key is required: if ``SWARMSYNC_SA_KEY`` and ``VCAP_SHARED_SECRET`` are both
  absent the gate raises before any DB write (default deny, not default allow).
- ``proof_hash`` is a deterministic SHA-256 over the four identity fields so the
  same evidence always produces the same hash (idempotent re-run is detectable).
- ``proof_signature`` is HMAC-SHA256(proof_hash, key) — the key never appears in
  the DB, logs, or the returned ``ProofBundle``.
- ``passed=False`` bundles ARE written to the DB (evidence trail) before raising.
  The Bill's ``invoiceproof_bundle_id`` and ``status`` are updated ONLY on
  ``passed=True``.

Environment variables (at least one required):
    SWARMSYNC_SA_KEY    — SwarmSync self-issued ``sa_*`` key (preferred).
    VCAP_SHARED_SECRET  — VCAP shared secret (fallback, shared with vcap.py).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class InvoiceProofGateFailed(Exception):
    """Gate 1 did not pass — bill must not proceed to approval or QB.

    Attributes:
        bill_id: The bill that was blocked.
        reason:  Machine-readable reason code (e.g. ``INVOICEPROOF_CRITICAL``,
                 ``INVOICEPROOF_INVALID``, ``GATE1_KEY_MISSING``).
    """

    def __init__(self, bill_id: str, reason: str) -> None:
        self.bill_id = bill_id
        self.reason = reason
        super().__init__(f"InvoiceProof Gate 1 FAILED for bill {bill_id!r}: {reason}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SA_KEY_ENV = "SWARMSYNC_SA_KEY"
_VCAP_KEY_ENV = "VCAP_SHARED_SECRET"


class Gate1KeyMissingError(RuntimeError):
    """Raised when both signing keys are absent or empty.

    A typed subclass of RuntimeError so the generic 500 handler in main.py can
    catch it without leaking the env-var names in the HTTP response body.
    """


def _require_signing_key() -> str:
    """Return the HMAC key from env. Raises ``Gate1KeyMissingError`` if both absent/empty.

    Checks ``SWARMSYNC_SA_KEY`` first (SwarmSync self-issued key), then falls back
    to ``VCAP_SHARED_SECRET``. Both absent or empty → fail-closed raise, never default allow.
    """
    for env_var in (_SA_KEY_ENV, _VCAP_KEY_ENV):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    # Neither key is configured — Gate fails closed immediately.
    raise Gate1KeyMissingError(
        f"Gate 1 key unavailable: set {_SA_KEY_ENV} or {_VCAP_KEY_ENV} in the environment. "
        "Gate fails closed by default."
    )


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON — sorted keys, no extra whitespace, str() for non-serialisable types."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _compute_proof_hash(
    bill_id: str,
    bill_amount: float,
    vendor_name: str,
    gmail_invoiceproof: dict[str, Any],
) -> str:
    """SHA-256 over the four identity fields. Deterministic for replay detection."""
    canonical = _canonical_json(
        {
            "bill_id": bill_id,
            "amount": str(bill_amount),
            "vendor_name": vendor_name,
            "gmail_invoiceproof": gmail_invoiceproof,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sign_proof_hash(proof_hash: str, key: str) -> str:
    """HMAC-SHA256(proof_hash_hex_string, key). Returns hex digest."""
    return hmac.new(
        key.encode("utf-8"),
        proof_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _evaluate_passed(gmail_invoiceproof: dict[str, Any]) -> tuple[bool, str]:
    """Determine gate outcome from the gmail_invoiceproof evidence dict.

    Returns ``(passed, reason)`` where ``reason`` is non-empty only when
    ``passed=False``.

    Evaluation rules (fail-closed order):
    1. If the dict is empty or not a mapping → INVOICEPROOF_INVALID.
    2. Explicit ``passed`` key (bool) in the dict is the primary signal if present.
    3. If ``riskLevel`` is ``"CRITICAL"`` → INVOICEPROOF_CRITICAL.
    4. If ``blocked`` is ``True`` → INVOICEPROOF_BLOCKED.
    5. Otherwise → passed=True.
    """
    if not isinstance(gmail_invoiceproof, dict) or not gmail_invoiceproof:
        return False, "INVOICEPROOF_INVALID"

    # Explicit passed flag from System A (most authoritative when present).
    if "passed" in gmail_invoiceproof:
        explicit = gmail_invoiceproof["passed"]
        if not isinstance(explicit, bool):
            return False, "INVOICEPROOF_INVALID"
        if not explicit:
            risk = gmail_invoiceproof.get("riskLevel", "UNKNOWN")
            reason = f"INVOICEPROOF_{risk}" if risk != "UNKNOWN" else "INVOICEPROOF_FAILED"
            return False, reason
        return True, ""

    # Fall back to riskLevel / blocked fields.
    risk_level = str(gmail_invoiceproof.get("riskLevel", "")).upper()
    if risk_level == "CRITICAL":
        return False, "INVOICEPROOF_CRITICAL"

    blocked = gmail_invoiceproof.get("blocked", False)
    if blocked:
        return False, "INVOICEPROOF_BLOCKED"

    return True, ""


# ---------------------------------------------------------------------------
# Public gate function
# ---------------------------------------------------------------------------


def run_invoice_proof_gate1(
    bill_id: str,
    bill_amount: float,
    vendor_name: str,
    gmail_invoiceproof: dict[str, Any],
    db_session: Session,
) -> Any:
    """Gate 1: seal a VCAP Full Bundle for this invoice and link it to the bill.

    Must be called AFTER the ``Bill`` row exists in the DB and BEFORE the
    Temporal workflow is started. The function is idempotent on ``bill_id``
    only in the sense that a second call with identical evidence will produce
    an identical ``proof_hash``; a duplicate ``proof_bundles`` row WILL be
    inserted (duplicate detection is the caller's concern via ``gmail_tracker_id``
    idempotency at the ``/intents/bill`` level).

    Args:
        bill_id:           UUID of the already-inserted ``bills`` row.
        bill_amount:       Canonical bill amount (must match the bills row).
        vendor_name:       Human-readable vendor name (for the proof body).
        gmail_invoiceproof: Evidence dict from System A's Gmail AccountingOS
                           invoiceproof run (SPEC §5 Flow 1 Step 11).
        db_session:        Active SQLAlchemy session (caller manages commit).

    Returns:
        The persisted ``ProofBundle`` ORM row (``passed=True``).

    Raises:
        InvoiceProofGateFailed: if any check fails or the signing key is
            missing. The exception is raised AFTER persisting the failing
            bundle so the audit trail is complete even on block.
        RuntimeError: if the signing key is missing before any DB write
            (key absence is detected first to avoid a partial write on a
            configuration error).
    """
    from app.audit.service import append_audit_row
    from app.models import Bill, ProofBundle

    # --- 1. Key check first — fail closed before any DB work -------------------
    try:
        key = _require_signing_key()
    except RuntimeError as exc:
        # Raise as InvoiceProofGateFailed so the caller has a uniform type to catch.
        raise InvoiceProofGateFailed(bill_id, "GATE1_KEY_MISSING") from exc

    # --- 2. Compute proof_hash + proof_signature --------------------------------
    ph = _compute_proof_hash(bill_id, bill_amount, vendor_name, gmail_invoiceproof)
    sig = _sign_proof_hash(ph, key)

    # --- 3. Evaluate passed from evidence ---------------------------------------
    passed, failure_reason = _evaluate_passed(gmail_invoiceproof)

    # --- 4. INSERT proof_bundles row (always — block decisions need an audit row) ---
    bundle_row = ProofBundle(
        kind="invoice",
        vcap_state="VCAP_FULL_BUNDLE",
        proof_hash=ph,
        proof_signature=sig,
        passed=passed,
        payload={
            "bundle_type": "VCAP_FULL",
            "bill_id": bill_id,
            "vendor_name": vendor_name,
            "gmail_invoiceproof": gmail_invoiceproof,
        },
    )
    db_session.add(bundle_row)
    db_session.flush()  # populate bundle_row.id without committing

    bundle_id = str(bundle_row.id)

    # --- 5. UPDATE bill — only on passed=True -----------------------------------
    if passed:
        bill = db_session.get(Bill, bill_id)
        if bill is None:
            # Bill disappeared between insert and gate — treat as gate failure.
            passed = False
            failure_reason = "GATE1_BILL_NOT_FOUND"
        else:
            bill.invoiceproof_bundle_id = bundle_id
            bill.status = "verified"
            db_session.flush()

    # --- 6. Append AIVS audit chain row ----------------------------------------
    action_type = (
        "invoiceproof_gate1_passed" if passed else "invoiceproof_gate1_failed"
    )
    try:
        append_audit_row(
            db_session,
            session_id=bill_id,
            action_type=action_type,
            actor="gate1",
            tool_name="invoice_proof_gate",
            inputs={"bill_id": bill_id, "vendor_name": vendor_name},
            outputs={
                "passed": passed,
                "bundle_id": bundle_id,
                "failure_reason": failure_reason or None,
            },
        )
    except Exception as audit_exc:  # noqa: BLE001
        # Audit chain write failure is itself a gate failure (Gate 2 fail-closed
        # semantics propagated upward). Never silently swallow.
        raise InvoiceProofGateFailed(
            bill_id, f"GATE1_AIVS_WRITE_FAILED: {audit_exc}"
        ) from audit_exc

    # --- 7. Fail closed — raise after writing the evidence bundle ---------------
    if not passed:
        raise InvoiceProofGateFailed(bill_id, failure_reason or "INVOICEPROOF_FAILED")

    return bundle_row
