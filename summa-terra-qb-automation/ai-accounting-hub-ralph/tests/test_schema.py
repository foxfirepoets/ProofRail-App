"""Infra-free schema tests: assert the ORM metadata matches SPEC §6."""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint

from app.models import AuditRow, Base, Bill, Company, ProofBundle, Vendor

EXPECTED_TABLES = {"companies", "vendors", "bills", "proof_bundles", "audit_rows"}


def test_all_canonical_tables_present():
    assert EXPECTED_TABLES <= set(Base.metadata.tables.keys())


def test_company_columns():
    cols = Company.__table__.columns
    assert {"id", "legal_name", "qb_file_id", "entity_type", "created_at", "updated_at"} <= set(
        cols.keys()
    )
    assert cols["qb_file_id"].unique is True
    assert cols["legal_name"].nullable is False


def test_vendor_fk_restrict_and_jsonb_default():
    cols = Vendor.__table__.columns
    assert cols["raw_extensions"].nullable is False
    fks = [
        fk
        for c in Vendor.__table__.constraints
        if isinstance(c, ForeignKeyConstraint)
        for fk in c.elements
    ]
    company_fk = [fk for fk in fks if fk.column.table.name == "companies"]
    assert company_fk, "vendors must reference companies"
    assert company_fk[0].ondelete == "RESTRICT"


def test_bill_amount_check_constraint():
    checks = [c for c in Bill.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any(c.name == "ck_bills_amount_nonneg" for c in checks)


def test_bill_status_default_drafted():
    default = Bill.__table__.columns["status"].server_default
    assert default is not None and "drafted" in str(default.arg)


def test_audit_row_hash_unique():
    assert AuditRow.__table__.columns["row_hash"].unique is True
    assert AuditRow.__table__.columns["prev_hash"].nullable is False


def test_proof_bundle_passed_defaults_false():
    default = ProofBundle.__table__.columns["passed"].server_default
    assert default is not None and "false" in str(default.arg).lower()
