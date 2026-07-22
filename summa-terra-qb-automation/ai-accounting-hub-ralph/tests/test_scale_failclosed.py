"""Fail-closed-under-outage tests (CHUNK_8_SCALE).

Failure case: a simulated proof-service OUTAGE (a proof callable raises) at ANY gate
blocks the pipeline and NO qbXML write proceeds. The writer is the last step, so the
proof of "no write" is simply that the writer was never called.
"""
from __future__ import annotations

from app.audit import AuditChainBroken
from app.scale.pipeline import INVOICEPROOF, VERIFY
from tests.test_scale_pipeline import run_green_pipeline


def _spy_writer():
    sent: list[str] = []

    def writer(req: str) -> str:
        sent.append(req)  # pragma: no cover - must never run when a gate fails closed
        return req

    return writer, sent


def test_invoiceproof_outage_blocks_and_no_write(monkeypatch):
    # Gate 1 proof callable raises (proof service unreachable).
    def boom(_evidence):
        raise RuntimeError("proof service unreachable")

    monkeypatch.setattr("app.payments.service.run_invoiceproof", boom)
    writer, sent = _spy_writer()

    result = run_green_pipeline(writer)

    assert result.blocked is True and result.green is False
    assert result.stage == INVOICEPROOF
    assert sent == []  # fail-closed: no write attempted


def test_aivs_chain_outage_blocks_and_no_write():
    # Gate 2 (AIVS validate) raises at the verify gate → write blocked, routed to human.
    def broken_validator(_records):
        raise AuditChainBroken("prev_hash mismatch", index=1, row_id=2)

    writer, sent = _spy_writer()
    result = run_green_pipeline(writer, chain_validator=broken_validator)

    assert result.blocked is True and result.green is False
    assert result.stage == VERIFY
    assert result.writeback["error"]["code"] == "AUDIT_CHAIN_BROKEN"
    assert sent == []  # fail-closed: write blocked before the writer


def test_verifyapi_outage_blocks_and_no_write(monkeypatch):
    # Gate 3 proof callable raises (VerifyAPI proof service down).
    def boom(_subject):
        raise RuntimeError("verifyapi service down")

    monkeypatch.setattr("app.verify.execution.run_verifyapi", boom)
    writer, sent = _spy_writer()

    result = run_green_pipeline(writer)

    assert result.blocked is True and result.green is False
    assert result.stage == VERIFY
    assert sent == []  # fail-closed: no write proceeds under the outage
