"""Live-DB integration test (skipped unless RUN_INTEGRATION=1).

Proves CHUNK_2 et al. can connect to the Supabase canonical store via DATABASE_URL
and that the five tables exist. This is the chunk's live-verification path.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_engine

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {"companies", "vendors", "bills", "proof_bundles", "audit_rows"}


def test_canonical_store_reachable_and_migrated():
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
    assert EXPECTED_TABLES <= present, f"missing: {EXPECTED_TABLES - present}"


def test_bill_amount_check_enforced():
    """Inserting a negative amount must be rejected by the CHECK constraint."""
    engine = get_engine()
    with engine.connect() as conn:
        company_id = conn.execute(
            text(
                "INSERT INTO companies (legal_name, entity_type) "
                "VALUES ('TEST CO', 'partnership') RETURNING id"
            )
        ).scalar()
        vendor_id = conn.execute(
            text(
                "INSERT INTO vendors (company_id, name) VALUES (:cid, 'TEST VENDOR') RETURNING id"
            ),
            {"cid": company_id},
        ).scalar()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO bills (company_id, vendor_id, amount, status) "
                    "VALUES (:cid, :vid, -1, 'drafted')"
                ),
                {"cid": company_id, "vid": vendor_id},
            )
        conn.rollback()
        # Clean up the test fixtures.
        conn.execute(text("DELETE FROM vendors WHERE id = :vid"), {"vid": vendor_id})
        conn.execute(text("DELETE FROM companies WHERE id = :cid"), {"cid": company_id})
        conn.commit()
