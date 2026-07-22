"""CHUNK_2_PARSE: pure parser tests against the bundled QB CSV fixtures (no DB)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.catalog.parsers import (
    cost_code_kind,
    parse_accounts,
    parse_classes,
    parse_cost_codes,
    parse_customer_jobs,
    parse_vendors,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "import_files"


def test_account_counts_and_cip_flag():
    part = parse_accounts(FIX / "CSV_Chart_of_Accounts_Partnership.csv")
    parent = parse_accounts(FIX / "CSV_Chart_of_Accounts_Parent.csv")
    assert len(part) == 36
    assert len(parent) == 22
    cip = {a.number for a in part if a.is_cip_bucket}
    assert cip == {"15100", "15200", "15300", "15400", "15500"}
    bank = next(a for a in part if a.number == "10100")
    assert bank.acct_type == "Bank" and bank.statement == "BS"


def test_class_count_and_code_split():
    classes = parse_classes(FIX / "CSV_Classes.csv")
    assert len(classes) == 10
    site = next(c for c in classes if c.code == "10")
    assert site.name == "Site & Excavation"


def test_partnership_cost_codes():
    items = parse_cost_codes(FIX / "CSV_Items_Partnership.csv")
    assert len(items) == 68
    by_code = {i.code: i for i in items}
    assert by_code["003"].kind == "draw"
    assert by_code["003"].account_name == "CIP - Hard Costs"
    # 068 is the GC's profit cost line, NOT the developer fee.
    assert by_code["068"].kind == "draw" and by_code["068"].fee_role is None
    assert by_code["100"].kind == "lifecycle"
    assert by_code["FEE-DEV"].kind == "fee" and by_code["FEE-DEV"].fee_role == "dev_5_partnership"
    assert by_code["RETAINAGE-HELD"].kind == "retainage"


def test_parent_cost_codes_fee_roles():
    items = parse_cost_codes(FIX / "CSV_Items_Parent.csv")
    assert len(items) == 3
    roles = {i.code: i.fee_role for i in items}
    assert roles == {
        "FEE-DEV-INC": "dev_inc_5_parent",
        "FEE-CEO": "ceo_2_parent",
        "FEE-PRES": "pres_1_parent",
    }


def test_vendor_counts():
    assert len(parse_vendors(FIX / "CSV_Vendors_Partnership.csv")) == 44
    assert len(parse_vendors(FIX / "CSV_Vendors_Parent.csv")) == 2


def test_customer_jobs_hierarchy():
    jobs = parse_customer_jobs(FIX / "CSV_Customers_Jobs.csv")
    assert len(jobs) == 5
    sitework = next(j for j in jobs if j.path.endswith(":Sitework"))
    assert sitework.parent_path == "HL Hunter's Landing"
    root = next(j for j in jobs if j.path == "HL Hunter's Landing")
    assert root.parent_path is None


def test_kind_helper_edges():
    assert cost_code_kind("001") == "draw"
    assert cost_code_kind("069") == "draw"
    assert cost_code_kind("201") == "lifecycle"
    assert cost_code_kind("FEE-CEO") == "fee"
    assert cost_code_kind("RETAINAGE-HELD") == "retainage"


def test_missing_file_raises_clearly():
    with pytest.raises(FileNotFoundError, match="catalog CSV not found"):
        parse_accounts(FIX / "does_not_exist.csv")
