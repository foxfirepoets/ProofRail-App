"""Assert the init migration declares the required extensions, indexes, and down-path."""
from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "20260626_1200_init_canonical.py"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_file_exists():
    assert MIGRATION.exists()


def test_extensions_created_idempotently():
    sql = _sql()
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in sql


def test_trgm_gin_index_present():
    assert "idx_vendors_name_trgm" in _sql()
    assert "gin (name gin_trgm_ops)" in _sql()


def test_amount_check_in_migration():
    assert "ck_bills_amount_nonneg" in _sql()
    assert "amount >= 0" in _sql()


def test_downgrade_drops_all_tables():
    sql = _sql()
    for table in ("audit_rows", "bills", "proof_bundles", "vendors", "companies"):
        assert table in sql.split("def downgrade")[1]
    assert "CASCADE" in sql.split("def downgrade")[1]
