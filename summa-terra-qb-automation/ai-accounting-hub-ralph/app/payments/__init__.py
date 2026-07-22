"""Atomic payments path (CHUNK_7): InvoiceProof Gate 1 + ATEP/bank-change Gate 4.

Public surface:
    from app.payments import run_invoiceproof, PaymentsService, compute_bank_fingerprint
"""
from __future__ import annotations

from app.payments.atep import evaluate_atep, tier_for_score
from app.payments.fingerprint import compute_bank_fingerprint, fingerprint_changed
from app.payments.invoiceproof import InvoiceProofError, run_invoiceproof
from app.payments.release import ReleaseGuard, sql_cas_release
from app.payments.service import PaymentsService, VendorContext
from app.payments.vcap import build_vcap_bundle, sign_proof, verify_signature

__all__ = [
    "InvoiceProofError",
    "PaymentsService",
    "ReleaseGuard",
    "VendorContext",
    "build_vcap_bundle",
    "compute_bank_fingerprint",
    "evaluate_atep",
    "fingerprint_changed",
    "run_invoiceproof",
    "sign_proof",
    "sql_cas_release",
    "tier_for_score",
    "verify_signature",
]
