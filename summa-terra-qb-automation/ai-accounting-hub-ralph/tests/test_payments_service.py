"""PaymentsService orchestration — DB-free. Covers fail-closed, bank-change, atomic CAS,
and the no-raw-bank-detail invariant.
"""
from __future__ import annotations

import json
import threading

import pytest

from app.payments.fingerprint import compute_bank_fingerprint
from app.payments.release import ReleaseGuard
from app.payments.service import PaymentsService, VendorContext

SECRET = "unit-test-vcap-secret-which-is-long-enough"

RAW_BANK = {"account_number": "12345678", "routing_number": "021000021", "bank_name": "Acme Bank"}


class Recorder:
    """Captures collaborator calls and assigns deterministic bundle ids."""

    def __init__(self):
        self.bundles: list[dict] = []
        self.bills: list[dict] = []
        self.audits: list[dict] = []

    def write_bundle(self, session, bundle):
        bundle_id = f"bundle-{len(self.bundles)}"
        self.bundles.append({"id": bundle_id, **bundle})
        return bundle_id

    def commit_bill(self, session, draft, bundle_id):
        rec = {"id": f"bill-{len(self.bills)}", "draft": draft, "bundle_id": bundle_id}
        self.bills.append(rec)
        return type("Bill", (), {"id": rec["id"]})()

    def append_audit(self, session, **kwargs):
        self.audits.append(kwargs)
        return object()


def _service(rec: Recorder, *, ctx: VendorContext, required_tier="TRUSTED"):
    return PaymentsService(
        load_context=lambda s, c, v: ctx,
        write_bundle=rec.write_bundle,
        commit_bill=rec.commit_bill,
        append_audit=rec.append_audit,
        release_fn=lambda s, bid: True,
        vcap_secret=SECRET,
        required_tier=required_tier,
    )


def _draft(**over):
    d = {
        "company_id": "co-1",
        "vendor_id": "v-1",
        "invoice_number": "INV-2001",
        "po_ref": "PO-1",
        "amount": 4321.99,
        "line_items": [{"amount": 4321.99}],
    }
    d.update(over)
    return d


def test_happy_path_writes_bill_and_proof():
    rec = Recorder()
    svc = _service(rec, ctx=VendorContext(swarmscore=900))
    decision = svc.process_intake(None, _draft())

    assert decision["passed"] is True
    assert decision["decision"] == "APPROVED"
    assert decision["released"] is True
    assert decision["bill_id"] is not None
    assert decision["proof_signature"]
    assert len(rec.bills) == 1  # payment write happened
    assert len(rec.audits) == 1  # audit row on the decision
    assert rec.bundles[0]["passed"] is True


def test_fail_closed_block_writes_no_bill():
    rec = Recorder()
    # Existing identical bill → EXACT_DUPLICATE (critical) → blocked.
    ctx = VendorContext(
        swarmscore=900,
        existing_bills=[{"company_id": "co-1", "invoice_number": "INV-2001", "amount": 4321.99}],
    )
    svc = _service(rec, ctx=ctx)
    decision = svc.process_intake(None, _draft())

    assert decision["passed"] is False
    assert decision["reason"] == "INVOICEPROOF_FAILED"
    assert decision["bill_id"] is None
    assert decision["released"] is False
    assert rec.bills == []  # NO payment write
    # Proof + audit are still emitted for the block.
    assert rec.bundles and rec.bundles[0]["passed"] is False
    assert len(rec.audits) == 1


def test_bank_change_below_tier_blocks_and_escalates():
    rec = Recorder()
    stored_fp = compute_bank_fingerprint({"account_number": "00000000", "bank_name": "Old Bank"})
    ctx = VendorContext(bank_fingerprint=stored_fp, swarmscore=100)  # below TRUSTED
    svc = _service(rec, ctx=ctx)

    decision = svc.process_intake(None, _draft(bank_details=RAW_BANK))

    assert decision["passed"] is False
    assert decision["reason"] == "BANK_CHANGE_BLOCKED"
    assert decision["bankChange"]["detected"] is True
    assert decision["bankChange"]["blocked"] is True
    assert decision["bankChange"]["atep"]["allowed"] is False
    assert rec.bills == []  # no wire


def test_bank_change_trusted_tier_allows():
    rec = Recorder()
    stored_fp = compute_bank_fingerprint({"account_number": "00000000", "bank_name": "Old Bank"})
    ctx = VendorContext(bank_fingerprint=stored_fp, swarmscore=950)  # TRUSTED
    svc = _service(rec, ctx=ctx)

    decision = svc.process_intake(None, _draft(bank_details=RAW_BANK))
    assert decision["bankChange"]["detected"] is True
    assert decision["bankChange"]["blocked"] is False
    assert decision["passed"] is True
    assert len(rec.bills) == 1


def test_no_raw_bank_fields_in_any_stored_or_logged_structure():
    rec = Recorder()
    stored_fp = compute_bank_fingerprint({"account_number": "00000000"})
    ctx = VendorContext(bank_fingerprint=stored_fp, swarmscore=950)
    svc = _service(rec, ctx=ctx)
    decision = svc.process_intake(None, _draft(bank_details=RAW_BANK))

    fresh_fp = compute_bank_fingerprint(RAW_BANK)
    haystacks = [
        json.dumps(decision, default=str),
        json.dumps(rec.bundles, default=str),
        json.dumps(rec.bills, default=str),
        json.dumps(rec.audits, default=str),
    ]
    for blob in haystacks:
        assert "12345678" not in blob  # raw account number
        assert "021000021" not in blob  # raw routing number
    # The fingerprint (hash) IS allowed and present in the proof.
    assert fresh_fp in json.dumps(rec.bundles, default=str)


def test_atomic_cas_prevents_double_release_service():
    rec = Recorder()
    svc = _service(rec, ctx=VendorContext(swarmscore=900))
    assert svc.release_bundle(None, "bundle-x") is True
    assert svc.release_bundle(None, "bundle-x") is False  # second release refused


def test_release_guard_single_winner_under_concurrency():
    guard = ReleaseGuard()
    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        r = guard.release("same-id")
        with lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1  # exactly one winner
    assert results.count(False) == 39


def test_vcap_signature_is_verifiable():
    from app.payments.vcap import verify_signature

    rec = Recorder()
    svc = _service(rec, ctx=VendorContext(swarmscore=900))
    svc.process_intake(None, _draft())
    bundle = rec.bundles[0]
    body = bundle["payload"]["proof_body"]
    assert verify_signature(body, bundle["proof_signature"], secret=SECRET)


def test_missing_vcap_secret_fails_closed(monkeypatch):
    from app.payments.vcap import VCAP_SHARED_SECRET_ENV, VcapSecretMissing

    monkeypatch.delenv(VCAP_SHARED_SECRET_ENV, raising=False)
    rec = Recorder()
    svc = PaymentsService(
        load_context=lambda s, c, v: VendorContext(swarmscore=900),
        write_bundle=rec.write_bundle,
        commit_bill=rec.commit_bill,
        append_audit=rec.append_audit,
        release_fn=lambda s, bid: True,
        vcap_secret=None,  # no secret → cannot sign
    )
    with pytest.raises(VcapSecretMissing):
        svc.process_intake(None, _draft())
