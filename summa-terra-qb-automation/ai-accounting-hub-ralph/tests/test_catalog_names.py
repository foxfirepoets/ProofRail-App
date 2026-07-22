"""CHUNK_4_NAMES: live-DB vendor + customer:job loader tests (gated; rolled back)."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.loader import CatalogError, load_customer_jobs, load_vendors
from app.catalog.parsers import parse_customer_jobs, parse_vendors
from app.catalog.rows import VendorRow
from app.models import Company, CustomerJob, Vendor

FIX = Path(__file__).resolve().parent / "fixtures" / "import_files"
pytestmark = pytest.mark.integration


@pytest.fixture
def session() -> Iterator[Session]:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("set RUN_INTEGRATION=1")
    from app.db import get_engine

    s = Session(get_engine())
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _company(session: Session, role: str) -> str:
    c = Company(legal_name=f"TEST {role}", entity_type="test", role=role)
    session.add(c)
    session.flush()
    return c.id


def test_partnership_vendors_and_jobs(session: Session):
    pid = _company(session, "partnership")
    v = load_vendors(
        session, pid, parse_vendors(FIX / "CSV_Vendors_Partnership.csv"), company_role="partnership"
    )
    j = load_customer_jobs(session, pid, parse_customer_jobs(FIX / "CSV_Customers_Jobs.csv"))
    assert v.inserted == 44
    assert j.inserted == 5
    names = {x.name for x in session.scalars(select(Vendor).where(Vendor.company_id == pid))}
    assert "IC - Summa Terra Ventures" in names
    assert not any(n.upper().startswith("EXEC") for n in names)
    sitework = session.scalars(
        select(CustomerJob).where(
            CustomerJob.company_id == pid, CustomerJob.path == "HL Hunter's Landing:Sitework"
        )
    ).one()
    assert sitework.parent_path == "HL Hunter's Landing"


def test_parent_vendors_have_exec(session: Session):
    pid = _company(session, "parent")
    v = load_vendors(
        session, pid, parse_vendors(FIX / "CSV_Vendors_Parent.csv"), company_role="parent"
    )
    assert v.inserted == 2
    names = {x.name for x in session.scalars(select(Vendor).where(Vendor.company_id == pid))}
    assert any(n.upper().startswith("EXEC") for n in names)


def test_exec_into_partnership_rejected(session: Session):
    pid = _company(session, "partnership")
    with pytest.raises(CatalogError, match="EXEC"):
        load_vendors(session, pid, [VendorRow("EXEC - Mike Watson")], company_role="partnership")


def test_idempotent_vendor_reload(session: Session):
    pid = _company(session, "partnership")
    rows = parse_vendors(FIX / "CSV_Vendors_Partnership.csv")
    load_vendors(session, pid, rows, company_role="partnership")
    second = load_vendors(session, pid, rows, company_role="partnership")
    assert second.inserted == 0 and second.updated == 0
