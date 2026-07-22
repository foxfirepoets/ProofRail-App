"""Pure CSV parsers for the QB Summa Terra Import_Files (SPEC_SUMMA_TERRA_BINDING §13.4).

No DB, no env, no network — deterministic on the same files. The CSVs are QB-upload-ready
and are the source of truth; these parsers mirror them 1:1 and never reshape them.

File name conventions (under the import dir):
    CSV_Chart_of_Accounts_{Partnership,Parent}.csv  -> AccountRow
    CSV_Classes.csv                                 -> ClassRow
    CSV_Items_{Partnership,Parent}.csv              -> CostCodeRow
    CSV_Vendors_{Partnership,Parent}.csv            -> VendorRow
    CSV_Customers_Jobs.csv                          -> CustomerJobRow
"""
from __future__ import annotations

import csv
from pathlib import Path

from app.catalog.rows import (
    AccountRow,
    ClassRow,
    CostCodeRow,
    CustomerJobRow,
    VendorRow,
)

CIP_BUCKETS = frozenset({"15100", "15200", "15300", "15400", "15500"})
LIFECYCLE_CODES = frozenset({"100", "101", "110", "120", "121", "122", "200", "201"})

# QB account type keyword -> (normalized acct_type, statement)
_ACCT_TYPE_MAP: dict[str, tuple[str, str]] = {
    "BANK": ("Bank", "BS"),
    "AR": ("AccountsReceivable", "BS"),
    "AP": ("AccountsPayable", "BS"),
    "CCARD": ("CreditCard", "BS"),
    "OCASSET": ("OtherCurrentAsset", "BS"),
    "FIXASSET": ("FixedAsset", "BS"),
    "OCLIAB": ("OtherCurrentLiability", "BS"),
    "LTLIAB": ("LongTermLiability", "BS"),
    "EQUITY": ("Equity", "BS"),
    "INC": ("Income", "PL"),
    "COGS": ("CostOfGoodsSold", "PL"),
    "EXP": ("Expense", "PL"),
    "EXINC": ("OtherIncomeExpense", "PL"),
}

_FEE_ROLE_MAP: dict[str, str] = {
    "FEE-DEV": "dev_5_partnership",
    "FEE-DEV-INC": "dev_inc_5_parent",
    "FEE-CEO": "ceo_2_parent",
    "FEE-PRES": "pres_1_parent",
}


def _open(path: str | Path) -> Path:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"catalog CSV not found: {p}")
    return p


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _split_code(name: str) -> tuple[str, str]:
    """'10 Site & Excavation' -> ('10', 'Site & Excavation'); single token -> (tok, tok)."""
    parts = name.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], parts[0])


def cost_code_kind(code: str) -> str:
    if code.startswith("FEE-"):
        return "fee"
    if code == "RETAINAGE-HELD":
        return "retainage"
    if code.isdigit():
        return "draw" if int(code) <= 69 else "lifecycle"
    return "lifecycle"


def parse_accounts(path: str | Path) -> list[AccountRow]:
    out: list[AccountRow] = []
    for r in _rows(_open(path)):
        number = r["Number"]
        qb_type = r["Type"].upper()
        acct_type, statement = _ACCT_TYPE_MAP.get(qb_type, (qb_type.title(), "PL"))
        out.append(
            AccountRow(
                number=number,
                name=r["Account Name"],
                acct_type=acct_type,
                statement=statement,
                is_cip_bucket=number in CIP_BUCKETS,
            )
        )
    return out


def parse_classes(path: str | Path) -> list[ClassRow]:
    out: list[ClassRow] = []
    for r in _rows(_open(path)):
        code, name = _split_code(r["Class Name"])
        out.append(ClassRow(code=code, name=name))
    return out


def parse_cost_codes(path: str | Path) -> list[CostCodeRow]:
    out: list[CostCodeRow] = []
    for r in _rows(_open(path)):
        code, _ = _split_code(r["Item Name"])
        out.append(
            CostCodeRow(
                code=code,
                name=r["Description"] or code,
                account_name=r["Account"],
                default_class_name=r["Default Class"] or None,
                kind=cost_code_kind(code),
                fee_role=_FEE_ROLE_MAP.get(code),
            )
        )
    return out


def parse_vendors(path: str | Path) -> list[VendorRow]:
    return [VendorRow(name=r["Vendor Name"]) for r in _rows(_open(path))]


def parse_customer_jobs(path: str | Path) -> list[CustomerJobRow]:
    out: list[CustomerJobRow] = []
    for r in _rows(_open(path)):
        full = r["Customer:Job"]
        parent = full.rsplit(":", 1)[0] if ":" in full else None
        out.append(CustomerJobRow(path=full, parent_path=parent))
    return out
