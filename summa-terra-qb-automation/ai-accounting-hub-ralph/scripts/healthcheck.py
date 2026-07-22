"""Confirm a live connection to the Supabase canonical store and that the
five canonical tables exist. Exit 0 on success, 1 on failure.

Usage: python scripts/healthcheck.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script (`python scripts/healthcheck.py`): ensure the
# project root (parent of this scripts/ dir) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db import get_engine  # noqa: E402

EXPECTED_TABLES = {"companies", "vendors", "bills", "proof_bundles", "audit_rows"}


def main() -> int:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            ).fetchall()
        present = {r[0] for r in rows}
        missing = EXPECTED_TABLES - present
        if missing:
            print(f"FAIL: connected, but missing tables: {sorted(missing)}")
            return 1
        print(f"OK: canonical store reachable; all tables present: {sorted(EXPECTED_TABLES)}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: could not verify canonical store: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
