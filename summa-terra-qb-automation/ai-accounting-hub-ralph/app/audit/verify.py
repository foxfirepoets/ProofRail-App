"""Offline AIVS chain validator (stdlib only).

Usage:
    python -m app.audit.verify <chain.json>
    cat chain.json | python -m app.audit.verify -

Input is a JSON array of audit rows (or an object with a top-level "rows" array).
Each row: row_id, session_id, action_type, actor, prev_hash, row_hash, and the
optional tool_name, cost_cents, timestamp, inputs, outputs.

Exit code 0 = chain intact; exit code 1 = chain broken (tamper/insert/delete/reorder).
This module imports only stdlib-backed package code (``app.audit.chain`` /
``app.audit.hashing`` use ``hashlib`` + ``json`` only).
"""
from __future__ import annotations

import json
import sys
from typing import Any

from app.audit.chain import AuditRecord, validate_chain
from app.audit.errors import AuditChainBroken


def _record_from_dict(d: dict[str, Any]) -> AuditRecord:
    return AuditRecord(
        row_id=int(d["row_id"]),
        session_id=str(d["session_id"]),
        action_type=str(d["action_type"]),
        actor=str(d.get("actor", "")),
        prev_hash=str(d["prev_hash"]),
        row_hash=str(d["row_hash"]),
        tool_name=d.get("tool_name"),
        cost_cents=int(d.get("cost_cents", 0)),
        timestamp=str(d.get("timestamp", "")),
        inputs=dict(d.get("inputs") or {}),
        outputs=dict(d.get("outputs") or {}),
    )


def load_rows(raw: str) -> list[AuditRecord]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("rows", [])
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of audit rows")
    return [_record_from_dict(d) for d in data]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in {"-h", "--help"}:
        sys.stderr.write("usage: python -m app.audit.verify <chain.json|->\n")
        return 2

    source = args[0]
    raw = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()

    try:
        records = load_rows(raw)
        validate_chain(records)
    except AuditChainBroken as exc:
        sys.stderr.write(f"CHAIN BROKEN: {exc}\n")
        return 1
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"CHAIN BROKEN: malformed chain: {exc}\n")
        return 1

    sys.stdout.write(f"CHAIN OK: {len(records)} row(s) validated\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
