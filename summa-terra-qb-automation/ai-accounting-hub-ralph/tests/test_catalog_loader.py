"""CHUNK_3_CATALOG: live-DB loader tests (gated; transaction rolled back, no pollution)."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.loader import (
    CatalogError,
    load_accounts,
    load_classes,
    load_cost_codes,
)
from app.catalog.parsers import parse_accounts, parse_classes, parse_cost_codes
from app.catalog.rows import AccountRow, CostCodeRow
from app.models import Account, Company, CostCode

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


def _parent_only_numbers() -> frozenset[str]:
    part = {a.number for a in parse_accounts(FIX / "CSV_Chart_of_Accounts_Partnership.csv")}
    parent = {a.number for a in parse_accounts(FIX / "CSV_Chart_of_Accounts_Parent.csv")}
    return frozenset(parent - part)


def test_load_counts_and_resolution(session: Session):
    pid = _company(session, "partnership")
    load_accounts(session, pid, parse_accounts(FIX / "CSV_Chart_of_Accounts_Partnership.csv"))
    load_classes(session, pid, parse_classes(FIX / "CSV_Classes.csv"))
    cc = load_cost_codes(session, pid, parse_cost_codes(FIX / "CSV_Items_Partnership.csv"))
    assert cc.inserted == 68
    # FEE-DEV resolves to the capitalized-dev-fee CIP bucket.
    fee = session.scalars(
        select(CostCode).where(CostCode.company_id == pid, CostCode.code == "FEE-DEV")
    ).one()
    assert fee.maps_to_account == "15500"
    # every cost code resolved (0 orphans -> no NULL maps_to_account).
    nulls = session.scalars(
        select(CostCode).where(CostCode.company_id == pid, CostCode.maps_to_account.is_(None))
    ).all()
    assert nulls == []


def test_parent_only_flag(session: Session):
    pid = _company(session, "parent")
    load_accounts(
        session,
        pid,
        parse_accounts(FIX / "CSV_Chart_of_Accounts_Parent.csv"),
        parent_only_numbers=_parent_only_numbers(),
    )
    flagged = {
        a.number
        for a in session.scalars(select(Account).where(Account.company_id == pid, Account.parent_only.is_(True)))
    }
    assert {"60200", "60300", "21100", "21200", "40200", "12200"} <= flagged


def test_idempotent_reload(session: Session):
    pid = _company(session, "partnership")
    accts = parse_accounts(FIX / "CSV_Chart_of_Accounts_Partnership.csv")
    load_accounts(session, pid, accts)
    second = load_accounts(session, pid, accts)
    assert second.inserted == 0 and second.updated == 0
    assert second.unchanged == len(accts)


def test_orphan_account_raises(session: Session):
    pid = _company(session, "partnership")
    load_accounts(session, pid, [AccountRow("15300", "CIP - Hard Costs", "OtherCurrentAsset", "BS", True)])
    load_classes(session, pid, parse_classes(FIX / "CSV_Classes.csv"))
    bad = [CostCodeRow("999", "Bogus", "No Such Account", None, "draw", None)]
    with pytest.raises(CatalogError, match="not found"):
        load_cost_codes(session, pid, bad)


def test_bucket_invariant_raises(session: Session):
    pid = _company(session, "partnership")
    # 15100 is a CIP bucket but NOT a draw bucket; a draw code mapping to it must fail.
    load_accounts(session, pid, [AccountRow("15100", "CIP - Land & Acquisition", "OtherCurrentAsset", "BS", True)])
    bad = [CostCodeRow("002", "Excavation", "CIP - Land & Acquisition", None, "draw", None)]
    with pytest.raises(CatalogError, match="must be one of"):
        load_cost_codes(session, pid, bad)
