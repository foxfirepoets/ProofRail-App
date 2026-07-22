"""CHUNK_1_SCHEMA: assert the Summa Terra binding models + migration (SPEC_SUMMA_TERRA_BINDING §6/§13).

Infra-free metadata tests + migration-file assertions; one gated live round-trip.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import (
    Account,
    Base,
    Bill,
    BillLine,
    Class,
    Company,
    CostCode,
    CustomerJob,
    DrawPackage,
    FeeEntry,
    IntercompanyLink,
)

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "20260627_1300_summa_terra_binding.py"
)

BINDING_TABLES = {
    "accounts",
    "classes",
    "cost_codes",
    "customer_jobs",
    "draw_packages",
    "intercompany_links",
    "fee_entries",
    "bill_lines",
}


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_all_binding_tables_present():
    assert BINDING_TABLES <= set(Base.metadata.tables.keys())


def test_company_binding_columns():
    cols = Company.__table__.columns
    assert {"role", "qb_entity_code", "expense_dev_fee"} <= set(cols.keys())
    # role must stay nullable — it is backfilled per file, never defaulted.
    assert cols["role"].nullable is True
    assert cols["role"].server_default is None
    assert cols["expense_dev_fee"].nullable is False


def test_bill_binding_columns():
    cols = Bill.__table__.columns
    assert {"draw_package_id", "net_amount_due", "approval_id"} <= set(cols.keys())
    assert cols["draw_package_id"].nullable is True


def test_cost_code_uses_maps_to_account_not_cip_number():
    cols = CostCode.__table__.columns
    assert "maps_to_account" in cols
    assert "cip_account_number" not in cols
    assert cols["maps_to_account"].nullable is False


def test_uniqueness_constraints():
    def uq_cols(model) -> list[frozenset[str]]:
        return [
            frozenset(c.columns.keys())
            for c in model.__table__.constraints
            if isinstance(c, UniqueConstraint)
        ]

    assert frozenset({"company_id", "number"}) in uq_cols(Account)
    assert frozenset({"company_id", "code"}) in uq_cols(Class)
    assert frozenset({"company_id", "code"}) in uq_cols(CostCode)
    assert frozenset({"company_id", "path"}) in uq_cols(CustomerJob)
    assert frozenset({"company_id", "draw_number"}) in uq_cols(DrawPackage)
    assert frozenset({"draw_package_id", "fee_role"}) in uq_cols(FeeEntry)


def test_draw_package_total_check():
    checks = [c for c in DrawPackage.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any(c.name == "ck_draw_pkg_total_nonneg" for c in checks)


def test_intercompany_link_has_both_legs():
    cols = IntercompanyLink.__table__.columns
    assert {"partnership_company_id", "parent_company_id", "amount"} <= set(cols.keys())


def test_bill_line_cascades_from_bill():
    fk = next(iter(BillLine.__table__.c.bill_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_migration_chains_from_init():
    sql = _sql()
    assert 'revision: str = "20260627_1300"' in sql
    assert 'down_revision: str | None = "20260626_1200"' in sql


def test_migration_role_has_no_blanket_default():
    sql = _sql()
    up = sql.split("def upgrade")[1].split("def downgrade")[0]
    # role added without DEFAULT; expense_dev_fee may default.
    assert "ADD COLUMN role VARCHAR(16)," in up
    assert "ADD COLUMN role VARCHAR(16) DEFAULT" not in up


def test_migration_creates_view_and_downgrades_clean():
    sql = _sql()
    assert "CREATE VIEW v_intercompany_net" in sql
    down = sql.split("def downgrade")[1]
    assert "DROP VIEW IF EXISTS v_intercompany_net" in down
    for table in BINDING_TABLES:
        assert table in down
    assert "CASCADE" in down


@pytest.mark.integration
def test_binding_columns_live_and_role_nullable():
    """Live DB: after upgrade head, the binding tables + nullable role column exist."""
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("set RUN_INTEGRATION=1")
    from sqlalchemy import text

    from app.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        present = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
        }
        assert BINDING_TABLES <= present
        role_nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='companies' AND column_name='role'"
            )
        ).scalar()
        assert role_nullable == "YES"
        views = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.views WHERE table_schema='public'")
            )
        }
        assert "v_intercompany_net" in views
