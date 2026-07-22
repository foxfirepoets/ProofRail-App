"""Tests for the stdlib verify.py-style CLI validator (exit 0 / exit 1)."""
from __future__ import annotations

import json

from app.audit import build_aivs_bundle
from app.audit.chain import AuditRecord, append_to_chain
from app.audit.verify import main

SESSION = "22222222-2222-2222-2222-222222222222"


def _chain(n: int = 3) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    for i in range(1, n + 1):
        append_to_chain(
            records,
            row_id=i,
            session_id=SESSION,
            action_type="approve",
            actor="ai",
            tool_name="post_bill",
            cost_cents=10 * i,
            timestamp=f"2026-06-26T00:00:0{i}Z",
            inputs={"amount": i},
            outputs={"ok": True},
        )
    return records


def _to_json_rows(records: list[AuditRecord]) -> list[dict]:
    return [
        {
            "row_id": r.row_id,
            "session_id": r.session_id,
            "action_type": r.action_type,
            "actor": r.actor,
            "prev_hash": r.prev_hash,
            "row_hash": r.row_hash,
            "tool_name": r.tool_name,
            "cost_cents": r.cost_cents,
            "timestamp": r.timestamp,
            "inputs": r.inputs,
            "outputs": r.outputs,
        }
        for r in records
    ]


def test_verify_exits_0_on_valid_chain(tmp_path) -> None:
    path = tmp_path / "chain.json"
    path.write_text(json.dumps(_to_json_rows(_chain(3))), encoding="utf-8")
    assert main([str(path)]) == 0


def test_verify_exits_1_on_tampered_inputs(tmp_path) -> None:
    rows = _to_json_rows(_chain(3))
    rows[1]["inputs"] = {"amount": 999}  # tamper, row_hash now stale
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    assert main([str(path)]) == 1


def test_verify_exits_1_on_reorder(tmp_path) -> None:
    rows = _to_json_rows(_chain(3))
    rows[0], rows[1] = rows[1], rows[0]
    path = tmp_path / "reorder.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    assert main([str(path)]) == 1


def test_verify_exits_1_on_malformed(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert main([str(path)]) == 1


def test_verify_accepts_rows_object_wrapper(tmp_path) -> None:
    path = tmp_path / "wrapped.json"
    path.write_text(json.dumps({"rows": _to_json_rows(_chain(2))}), encoding="utf-8")
    assert main([str(path)]) == 0


def test_build_bundle_for_valid_chain() -> None:
    records = _chain(3)
    bundle = build_aivs_bundle(records)
    assert bundle["kind"] == "auditproof"
    assert bundle["passed"] is True
    assert bundle["proof_hash"] == records[-1].row_hash
    assert bundle["payload"]["row_count"] == 3
    # signing off by default => no signature
    assert bundle["proof_signature"] is None
