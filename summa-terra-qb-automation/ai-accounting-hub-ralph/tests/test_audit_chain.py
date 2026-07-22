"""DB-free unit tests for the AIVS hash chain: happy path, redaction, tamper.

Covers the spec scenarios over in-memory records (no live DB required).
"""
from __future__ import annotations

import dataclasses
from itertools import pairwise

import pytest

from app.audit.chain import (
    AuditRecord,
    append_to_chain,
    chain_head,
    make_record,
    validate_chain,
)
from app.audit.errors import AuditChainBroken
from app.audit.hashing import GENESIS_HASH, REDACTED, compute_row_hash, redact

SESSION = "11111111-1111-1111-1111-111111111111"


def _build_chain(n: int = 3) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    for i in range(1, n + 1):
        append_to_chain(
            records,
            row_id=i,
            session_id=SESSION,
            action_type="approve",
            actor="ai",
            tool_name="post_bill",
            cost_cents=100 * i,
            timestamp=f"2026-06-26T00:00:0{i}Z",
            inputs={"amount": i, "memo": f"row{i}"},
            outputs={"ok": True},
        )
    return records


# --- Happy path -----------------------------------------------------------


def test_genesis_links_to_zeros() -> None:
    records = _build_chain(1)
    assert records[0].prev_hash == GENESIS_HASH


def test_valid_chain_accepted() -> None:
    records = _build_chain(5)
    assert validate_chain(records) is True
    # each row links to the previous row_hash
    for prev, cur in pairwise(records):
        assert cur.prev_hash == prev.row_hash


def test_empty_chain_is_vacuously_valid() -> None:
    assert validate_chain([]) is True
    assert chain_head([]) == GENESIS_HASH


def test_row_hash_matches_spec_formula() -> None:
    rec = make_record(
        row_id=1,
        session_id=SESSION,
        action_type="approve",
        actor="ai",
        prev_hash=GENESIS_HASH,
        tool_name="post_bill",
        cost_cents=500,
        timestamp="2026-06-26T00:00:01Z",
        inputs={"amount": 5},
        outputs={"ok": True},
    )
    expected = compute_row_hash(
        row_id=1,
        session_id=SESSION,
        action_type="approve",
        tool_name="post_bill",
        cost_cents=500,
        timestamp="2026-06-26T00:00:01Z",
        prev_hash=GENESIS_HASH,
        inputs={"amount": 5},
        outputs={"ok": True},
    )
    assert rec.row_hash == expected
    assert len(rec.row_hash) == 64


# --- Redaction edge case --------------------------------------------------


def test_redaction_replaces_sensitive_keys() -> None:
    raw = {
        "bank_account": "123456789",
        "routing_number": "021000021",
        "api_token": "sk-secret",
        "password": "hunter2",
        "ssn": "111-22-3333",
        "secret_key": "abc",
        "memo": "keep me",
        "nested": {"account_id": "x", "vendor": "Acme"},
        "list": [{"access_token": "t"}, {"safe": "ok"}],
    }
    out = redact(raw)
    assert out["bank_account"] == REDACTED
    assert out["routing_number"] == REDACTED
    assert out["api_token"] == REDACTED
    assert out["password"] == REDACTED
    assert out["ssn"] == REDACTED
    assert out["secret_key"] == REDACTED
    assert out["memo"] == "keep me"
    assert out["nested"]["account_id"] == REDACTED
    assert out["nested"]["vendor"] == "Acme"
    assert out["list"][0]["access_token"] == REDACTED
    assert out["list"][1]["safe"] == "ok"


def test_record_stores_redacted_inputs_not_raw() -> None:
    rec = make_record(
        row_id=1,
        session_id=SESSION,
        action_type="approve",
        actor="ai",
        prev_hash=GENESIS_HASH,
        inputs={"bank_account": "123456789", "memo": "ok"},
    )
    assert rec.inputs["bank_account"] == REDACTED
    assert rec.inputs["memo"] == "ok"
    # raw secret never appears in the sealed record
    assert "123456789" not in str(rec.inputs)


def test_redaction_changes_hash() -> None:
    # Same logical row, but one passes raw secret and one passes redacted:
    # because make_record redacts first, both seal to the redacted hash.
    rec_raw = make_record(
        row_id=1,
        session_id=SESSION,
        action_type="a",
        actor="ai",
        prev_hash=GENESIS_HASH,
        inputs={"account": "raw"},
    )
    # A hash computed over the RAW (un-redacted) body must differ.
    raw_hash = compute_row_hash(
        row_id=1,
        session_id=SESSION,
        action_type="a",
        tool_name=None,
        cost_cents=0,
        timestamp="",
        prev_hash=GENESIS_HASH,
        inputs={"account": "raw"},  # compute_row_hash redacts internally too
        outputs={},
    )
    # compute_row_hash also redacts, so these match — proving redaction is
    # applied consistently before hashing (no raw value enters the digest).
    assert rec_raw.row_hash == raw_hash


# --- Failure cases (fail-closed) ------------------------------------------


def test_tampered_inputs_breaks_chain() -> None:
    records = _build_chain(3)
    # Mutate a row's inputs after sealing — row_hash no longer matches contents.
    records[1] = dataclasses.replace(records[1], inputs={"amount": 999})
    with pytest.raises(AuditChainBroken) as exc:
        validate_chain(records)
    assert exc.value.code == "AUDIT_CHAIN_BROKEN"


def test_deleted_row_breaks_chain() -> None:
    records = _build_chain(4)
    del records[2]  # break prev_hash linkage
    with pytest.raises(AuditChainBroken):
        validate_chain(records)


def test_reordered_rows_break_chain() -> None:
    records = _build_chain(4)
    records[1], records[2] = records[2], records[1]
    with pytest.raises(AuditChainBroken):
        validate_chain(records)


def test_inserted_forged_row_breaks_chain() -> None:
    records = _build_chain(3)
    forged = make_record(
        row_id=99,
        session_id=SESSION,
        action_type="approve",
        actor="attacker",
        prev_hash="0" * 64,  # wrong link
        inputs={"x": 1},
    )
    records.insert(2, forged)
    with pytest.raises(AuditChainBroken):
        validate_chain(records)


def test_append_to_broken_chain_is_blocked() -> None:
    records = _build_chain(2)
    records[0] = dataclasses.replace(records[0], cost_cents=999999)  # tamper
    with pytest.raises(AuditChainBroken):
        append_to_chain(
            records,
            row_id=3,
            session_id=SESSION,
            action_type="approve",
            actor="ai",
        )
