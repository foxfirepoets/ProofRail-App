"""Hard invariants the catalog must satisfy after a load (SPEC_SUMMA_TERRA_BINDING §13.4/§7).

Each assertion queries the canonical store and raises AssertionFailure listing the offending
rows. The bootstrap runs these before declaring GREEN.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Class, CostCode

PARENT_FEE_ROLES = frozenset({"dev_inc_5_parent", "ceo_2_parent", "pres_1_parent"})
DRAW_BUCKETS = frozenset({"15200", "15300"})


class AssertionFailure(AssertionError):
    """A catalog invariant was violated; message lists the offending rows."""


def assert_split_at_file_level(session: Session, partnership_company_id: str) -> None:
    """A partnership file must hold no parent-only accounts and no parent fee_role items."""
    bad_acc = session.scalars(
        select(Account.number).where(
            Account.company_id == partnership_company_id, Account.parent_only.is_(True)
        )
    ).all()
    bad_cc = session.scalars(
        select(CostCode.code).where(
            CostCode.company_id == partnership_company_id,
            CostCode.fee_role.in_(PARENT_FEE_ROLES),
        )
    ).all()
    if bad_acc or bad_cc:
        raise AssertionFailure(
            f"split-at-file-level violated in partnership {partnership_company_id}: "
            f"parent_only accounts={list(bad_acc)}, parent fee_role codes={list(bad_cc)}"
        )


def assert_bucket_invariant(session: Session, company_id: str) -> None:
    """Every draw cost code must map to a draw CIP bucket (15200/15300)."""
    bad = session.scalars(
        select(CostCode.code).where(
            CostCode.company_id == company_id,
            CostCode.kind == "draw",
            CostCode.maps_to_account.notin_(DRAW_BUCKETS),
        )
    ).all()
    if bad:
        raise AssertionFailure(
            f"bucket invariant violated in {company_id}: draw codes off-bucket={list(bad)}"
        )


def assert_no_orphans(session: Session, company_id: str) -> None:
    """Every cost code's maps_to_account and default_class_code must resolve in-company."""
    acct_numbers = set(
        session.scalars(select(Account.number).where(Account.company_id == company_id))
    )
    class_codes = set(
        session.scalars(select(Class.code).where(Class.company_id == company_id))
    )
    orphans: list[str] = []
    for cc in session.scalars(select(CostCode).where(CostCode.company_id == company_id)):
        if cc.maps_to_account not in acct_numbers:
            orphans.append(f"{cc.code}->acct {cc.maps_to_account}")
        elif cc.default_class_code and cc.default_class_code not in class_codes:
            orphans.append(f"{cc.code}->class {cc.default_class_code}")
    if orphans:
        raise AssertionFailure(f"orphan references in {company_id}: {orphans}")
