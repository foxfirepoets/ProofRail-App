"""CHUNK_5_BOOTSTRAP: end-to-end plug-and-play bootstrap tests (gated; dry-run = no commit)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.catalog import bootstrap
from app.catalog.assertions import AssertionFailure, assert_split_at_file_level
from app.models import Account, Bill, Company, CostCode, CustomerJob, DrawPackage, Vendor

FIX = Path(__file__).resolve().parent / "fixtures" / "import_files"
pytestmark = pytest.mark.integration

PARENT = "TEST-BOOT Parent"
PARTNERSHIP = "TEST-BOOT Partnership"


def _require_live() -> None:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("set RUN_INTEGRATION=1")


def _count(session: Session, model: type, company_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(model).where(model.company_id == company_id)
    )


@pytest.fixture
def cleanup():
    """Remove TEST-BOOT companies (and their cascades) before and after each test."""
    _require_live()
    from app.db import get_engine

    def _purge() -> None:
        with Session(get_engine()) as s:
            ids = list(
                s.scalars(
                    select(Company.id).where(Company.legal_name.in_([PARENT, PARTNERSHIP]))
                )
            )
            if ids:
                # Delete non-cascading children first (vendors/bills/draw_packages use
                # RESTRICT/no-cascade); the company delete cascades accounts/classes/
                # cost_codes/customer_jobs.
                for model in (Vendor, Bill, DrawPackage):
                    s.execute(delete(model).where(model.company_id.in_(ids)))
                s.execute(delete(Company).where(Company.id.in_(ids)))
            s.commit()

    _purge()
    yield
    _purge()


def test_dry_run_commits_nothing(cleanup):
    rc = bootstrap.run(PARENT, PARTNERSHIP, FIX, dry_run=True)
    assert rc == 0
    from app.db import get_engine

    with Session(get_engine()) as s:
        present = s.scalars(
            select(Company).where(Company.legal_name.in_([PARENT, PARTNERSHIP]))
        ).all()
        assert present == []


def test_full_bootstrap_counts_and_green(cleanup):
    rc = bootstrap.run(PARENT, PARTNERSHIP, FIX, dry_run=False)
    assert rc == 0
    from app.db import get_engine

    with Session(get_engine()) as s:
        parent = s.scalars(select(Company).where(Company.legal_name == PARENT)).one()
        part = s.scalars(select(Company).where(Company.legal_name == PARTNERSHIP)).one()
        assert parent.role == "parent" and part.role == "partnership"
        assert _count(s, Account, parent.id) == 22
        assert _count(s, CostCode, parent.id) == 3
        assert _count(s, Vendor, parent.id) == 2
        assert _count(s, Account, part.id) == 36
        assert _count(s, CostCode, part.id) == 68
        assert _count(s, Vendor, part.id) == 44
        assert _count(s, CustomerJob, part.id) == 5
        # split-at-file-level holds for the partnership.
        assert_split_at_file_level(s, part.id)


def test_second_run_is_idempotent(cleanup):
    assert bootstrap.run(PARENT, PARTNERSHIP, FIX, dry_run=False) == 0
    from app.db import get_engine

    with Session(get_engine()) as s:
        parent = s.scalars(select(Company).where(Company.legal_name == PARENT)).one()
        before = _count(s, CostCode, parent.id)
    # second run must not change row counts.
    assert bootstrap.run(PARENT, PARTNERSHIP, FIX, dry_run=False) == 0
    with Session(get_engine()) as s:
        parent = s.scalars(select(Company).where(Company.legal_name == PARENT)).one()
        assert _count(s, CostCode, parent.id) == before


def test_seeded_parent_only_breaks_split(cleanup):
    assert bootstrap.run(PARENT, PARTNERSHIP, FIX, dry_run=False) == 0
    from app.db import get_engine

    with Session(get_engine()) as s:
        part = s.scalars(select(Company).where(Company.legal_name == PARTNERSHIP)).one()
        # poison: flip a partnership account to parent_only.
        acct = s.scalars(
            select(Account).where(Account.company_id == part.id, Account.number == "10100")
        ).one()
        acct.parent_only = True
        s.flush()
        with pytest.raises(AssertionFailure, match="split-at-file-level"):
            assert_split_at_file_level(s, part.id)
        s.rollback()
