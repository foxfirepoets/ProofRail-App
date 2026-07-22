"""VerifyAPI gate (Gate 3) unit tests — deterministic, in-process, DB-free."""
from __future__ import annotations

from decimal import Decimal

from app.verify.verifyapi import (
    NOT_READY,
    RISK_LOW,
    VERIFIED,
    run_verifyapi,
    verdict_to_bundle,
)

GOOD_HEAD = "a" * 64


def _subject(**over) -> dict:
    base = {
        "bill_id": "b1",
        "vendor_id": "v1",
        "amount": Decimal("12500.00"),
        "status": "approved",
        "aivs_head": GOOD_HEAD,
    }
    base.update(over)
    return base


def test_verified_low_risk_carries_attestor_signature():
    v = run_verifyapi(_subject())
    assert v.status == VERIFIED
    assert v.risk == RISK_LOW
    assert v.advance is True
    assert v.independent_attestor_signature  # non-empty hex HMAC


def test_verdict_is_deterministic():
    a = run_verifyapi(_subject())
    b = run_verifyapi(_subject())
    assert a.proof_hash == b.proof_hash
    assert a.independent_attestor_signature == b.independent_attestor_signature


def test_non_approved_status_does_not_advance():
    v = run_verifyapi(_subject(status="drafted"))
    assert v.status == NOT_READY
    assert v.advance is False
    assert v.independent_attestor_signature is None


def test_non_positive_amount_blocks():
    v = run_verifyapi(_subject(amount=Decimal("0")))
    assert v.advance is False
    assert any("positive" in r for r in v.reasons)


def test_genesis_or_empty_aivs_head_blocks():
    assert run_verifyapi(_subject(aivs_head="0" * 64)).advance is False
    assert run_verifyapi(_subject(aivs_head="")).advance is False


def test_missing_vendor_blocks():
    v = run_verifyapi(_subject(vendor_id=None))
    assert v.advance is False
    assert any("vendor_id" in r for r in v.reasons)


def test_bundle_shape_for_verified():
    bundle = verdict_to_bundle(run_verifyapi(_subject()))
    assert bundle["kind"] == "verifyapi"
    assert bundle["passed"] is True
    assert bundle["vcap_state"] == "verified"
    assert bundle["proof_signature"]


def test_bundle_shape_for_not_ready():
    bundle = verdict_to_bundle(run_verifyapi(_subject(status="drafted")))
    assert bundle["kind"] == "verifyapi"
    assert bundle["passed"] is False
    assert bundle["vcap_state"] == "not_ready"
    assert bundle["proof_signature"] is None
