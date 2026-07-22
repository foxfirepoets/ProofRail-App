"""Idempotent upsert of parsed catalog rows into the canonical store (SPEC §13.4).

Loaders are scoped per company_id and safe to re-run (the catalog bootstrap relies on this).
COA + classes must be loaded before cost codes so account-name -> number and class-name ->
code resolution succeed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.parsers import _split_code
from app.catalog.rows import (
    AccountRow,
    ClassRow,
    CostCodeRow,
    CustomerJobRow,
    VendorRow,
)
from app.models import Account, Class, CostCode, CustomerJob, Vendor

CIP_DRAW_BUCKETS = frozenset({"15200", "15300"})
PARENT_FEE_ROLES = frozenset({"dev_inc_5_parent", "ceo_2_parent", "pres_1_parent"})


class CatalogError(ValueError):
    """Raised when a catalog row cannot be resolved or violates an invariant."""


@dataclass
class LoadResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> int:
        return self.inserted + self.updated

    def bump(self, status: str) -> None:
        setattr(self, status, getattr(self, status) + 1)

    def add(self, other: LoadResult) -> LoadResult:
        return LoadResult(
            self.inserted + other.inserted,
            self.updated + other.updated,
            self.unchanged + other.unchanged,
        )


def _upsert(session: Session, model: type, keys: dict[str, object], values: dict[str, object]) -> str:
    """Insert or update one row by its natural key. Returns inserted|updated|unchanged."""
    stmt: Any = select(model)
    for col, val in keys.items():
        stmt = stmt.where(getattr(model, col) == val)
    existing = session.scalars(stmt).one_or_none()
    if existing is None:
        session.add(model(**keys, **values))
        return "inserted"
    changed = False
    for col, val in values.items():
        if getattr(existing, col) != val:
            setattr(existing, col, val)
            changed = True
    return "updated" if changed else "unchanged"


def load_accounts(
    session: Session,
    company_id: str,
    rows: list[AccountRow],
    *,
    parent_only_numbers: frozenset[str] = frozenset(),
) -> LoadResult:
    res = LoadResult()
    for r in rows:
        res.bump(
            _upsert(
                session,
                Account,
                {"company_id": company_id, "number": r.number},
                {
                    "name": r.name,
                    "acct_type": r.acct_type,
                    "statement": r.statement,
                    "is_cip_bucket": r.is_cip_bucket,
                    "parent_only": r.number in parent_only_numbers,
                },
            )
        )
    session.flush()
    return res


def load_classes(session: Session, company_id: str, rows: list[ClassRow]) -> LoadResult:
    res = LoadResult()
    for r in rows:
        res.bump(
            _upsert(
                session,
                Class,
                {"company_id": company_id, "code": r.code},
                {"name": r.name},
            )
        )
    session.flush()
    return res


def load_cost_codes(session: Session, company_id: str, rows: list[CostCodeRow]) -> LoadResult:
    acct_by_name = {
        a.name: a.number
        for a in session.scalars(select(Account).where(Account.company_id == company_id))
    }
    class_codes = {
        c.code for c in session.scalars(select(Class).where(Class.company_id == company_id))
    }
    res = LoadResult()
    for r in rows:
        number = acct_by_name.get(r.account_name)
        if number is None:
            raise CatalogError(
                f"cost code {r.code!r}: account {r.account_name!r} not found in company {company_id}"
            )
        if r.kind == "draw" and number not in CIP_DRAW_BUCKETS:
            raise CatalogError(
                f"cost code {r.code!r} (draw) maps to {number}, must be one of {sorted(CIP_DRAW_BUCKETS)}"
            )
        class_code: str | None = None
        if r.default_class_name:
            class_code = _split_code(r.default_class_name)[0]
            if class_code not in class_codes:
                raise CatalogError(
                    f"cost code {r.code!r}: default class {r.default_class_name!r} not loaded"
                )
        res.bump(
            _upsert(
                session,
                CostCode,
                {"company_id": company_id, "code": r.code},
                {
                    "name": r.name,
                    "maps_to_account": number,
                    "default_class_code": class_code,
                    "kind": r.kind,
                    "fee_role": r.fee_role,
                },
            )
        )
    session.flush()
    return res


def load_vendors(
    session: Session,
    company_id: str,
    rows: list[VendorRow],
    *,
    company_role: str,
) -> LoadResult:
    res = LoadResult()
    for r in rows:
        norm = r.name.upper().replace("—", "-").replace("–", "-")
        if company_role == "partnership" and (norm.startswith("EXEC -") or norm.startswith("EXEC-")):
            raise CatalogError(
                f"vendor {r.name!r} (EXEC) must not load into a partnership file"
            )
        res.bump(
            _upsert(
                session,
                Vendor,
                {"company_id": company_id, "name": r.name},
                {},
            )
        )
    session.flush()
    return res


def load_customer_jobs(
    session: Session, company_id: str, rows: list[CustomerJobRow]
) -> LoadResult:
    res = LoadResult()
    for r in rows:
        res.bump(
            _upsert(
                session,
                CustomerJob,
                {"company_id": company_id, "path": r.path},
                {"parent_path": r.parent_path},
            )
        )
    session.flush()
    return res
