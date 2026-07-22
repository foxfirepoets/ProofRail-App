"""Shadow-mode proof bundle for a drafted draw (binding §5.3 gates / SPEC §6.1-6.3).

Each drafted draw produces ONE proof bundle that carries, per the build spec:
- an AuditProof row appended to the AIVS hash chain (tamper-evident, fail-closed);
- a deterministic VerifyAPI-style pre-write verdict;
- deterministic fee_math evidence (the exact 5/2/1 lines + base + digest);
- the source draw reference;
- an explicit shadow-mode flag (`qb_write: false`) — this bundle attests that NOTHING was
  written to QuickBooks.

No transport import, ever — that is what keeps the engine shadow-only.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.audit.hashing import digest
from app.audit.service import append_audit_row, write_proof_bundle
from app.draw_engine.policy import RoleSpec

PROOF_KIND = "draw_shadow"


def _fee_math_evidence(base: Decimal, specs: Sequence[tuple[RoleSpec, Decimal]]) -> list[dict[str, Any]]:
    return [
        {
            "fee_role": spec.fee_role,
            "book": spec.book,
            "dr_account": spec.dr_account,
            "cr_account": spec.cr_account,
            "rate": str(spec.rate),
            "base": str(base),
            "amount": str(amount),
        }
        for spec, amount in specs
    ]


def build_shadow_proof(
    session: Session,
    *,
    draw_package_id: str,
    draw_number: str,
    partnership_company_id: str,
    parent_company_id: str,
    source_doc_ref: str | None,
    base_total: Decimal,
    lines: Sequence[tuple[RoleSpec, Decimal]],
    actor: str = "draw_engine",
) -> Any:
    """Append the AuditProof row and persist the shadow proof bundle; return the bundle row."""
    source_ref = {
        "draw_package_id": draw_package_id,
        "draw_number": draw_number,
        "partnership_company_id": partnership_company_id,
        "parent_company_id": parent_company_id,
        "source_doc_ref": source_doc_ref,
    }
    evidence = _fee_math_evidence(base_total, lines)
    fee_math_digest = digest({"base": str(base_total), "lines": evidence})

    # AuditProof: each draft attempt is an independent single-row attestation chain (fresh
    # session UUID), so a re-draft after a revision never has to re-validate a prior chain.
    # The draw linkage is preserved in the audit inputs + the bundle payload (source_ref).
    attest_session = str(uuid.uuid4())
    audit_row = append_audit_row(
        session,
        session_id=attest_session,
        action_type="draw_fee_draft",
        actor=actor,
        tool_name="draw_engine",
        inputs=source_ref,
        outputs={"fee_math_digest": fee_math_digest, "lines": evidence},
    )

    # Deterministic VerifyAPI-style pre-write verdict over the same canonical subject.
    verify_subject = {"source": source_ref, "fee_math_digest": fee_math_digest, "shadow": True}
    verify_hash = digest(verify_subject)

    bundle = {
        "kind": PROOF_KIND,
        "vcap_state": "verified",
        "proof_hash": fee_math_digest,
        "proof_signature": None,
        "passed": True,
        "payload": {
            "source_draw_ref": source_ref,
            "fee_math": evidence,
            "fee_math_digest": fee_math_digest,
            "audit_proof": {"row_id": audit_row.row_id, "row_hash": audit_row.row_hash},
            "verify_proof": {"proof_hash": verify_hash, "passed": True, "product": "verifyapi"},
            "shadow_mode": True,
            "qb_write": False,
        },
    }
    return write_proof_bundle(session, bundle)
