"""CHUNK_6 shadow draw engine — pure guards (offline) + live-DB engine tests (gated).

Live tests run in a rolled-back transaction (no DB pollution), mirroring the catalog tests.
Proves Draw #29 exact amounts, idempotency, approval gating, revised/rejected handling, the
exception engine, intercompany net=0, the 13% double-count block, and the shadow-mode
guarantee (zero QuickBooks writes).
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.draw_engine import engine, policy
from app.draw_engine.exceptions import net_intercompany, scan_exceptions
from app.draw_engine.reconcile import (
    cross_book_reconciliation,
    parent_commission_register,
    partnership_draw_vs_fee,
)
from app.models import Account, Company, DrawPackage, FeeEntry, ProofBundle

DRAW_29_TOTAL = Decimal("962845.68")
ENGINE_DIR = Path(__file__).resolve().parent.parent / "app" / "draw_engine"


# ─────────────────────────── offline (pure) guards ───────────────────────────

def test_engine_source_never_imports_transport():
    """Shadow-mode structural guard: no draw_engine module may import the QBWC transport.

    Inspects import statements only (prose in docstrings may mention 'transport'/'qbwc').
    """
    for py in ENGINE_DIR.glob("*.py"):
        for line in py.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                low = stripped.lower()
                assert "transport" not in low, f"{py.name} imports transport (breaks shadow mode)"
                assert "qbwc" not in low, f"{py.name} imports qbwc (breaks shadow mode)"


def test_capitalize_policy_resolution():
    # override wins; else company default; capitalize = not expense.
    assert policy.capitalize_dev_fee(company_expense_default=False, override=None) is True
    assert policy.capitalize_dev_fee(company_expense_default=True, override=None) is False
    assert policy.capitalize_dev_fee(company_expense_default=True, override=False) is True
    assert policy.capitalize_dev_fee(company_expense_default=False, override=True) is False
    assert policy.partnership_dr_account(True) == policy.ACCT_CIP_DEV_FEE
    assert policy.partnership_dr_account(False) == policy.ACCT_DEV_FEE_EXPENSE


def test_commissions_are_structurally_parent_only():
    from app.catalog.fee_math import ROLE_DEV_PARTNERSHIP

    assert policy.COMMISSION_ROLES <= policy.PARENT_ONLY_ROLES
    assert ROLE_DEV_PARTNERSHIP not in policy.PARENT_ONLY_ROLES


# ─────────────────────────── live-DB engine tests ───────────────────────────

pytestmark_live = pytest.mark.integration

PART_ACCTS = [("15500", "CIP Dev Fee", "Other Current Asset"), ("60100", "Dev Fee Exp", "Expense"),
              ("21000", "Due-To Summa", "Other Current Liability")]
PARENT_ACCTS = [("12200", "Due-From", "Other Current Asset"), ("40200", "Dev Fee Income", "Income"),
                ("60200", "CEO Comm Exp", "Expense"), ("21100", "Payable Watson", "Other Current Liability"),
                ("60300", "Pres Comm Exp", "Expense"), ("21200", "Payable Christensen", "Other Current Liability")]


@pytest.fixture
def book() -> Iterator[dict]:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("set RUN_INTEGRATION=1")
    from app.db import get_engine

    s = Session(get_engine())
    try:
        parent = Company(legal_name="TEST-DE Parent", entity_type="management", role="parent",
                         expense_dev_fee=False)
        part = Company(legal_name="TEST-DE Partnership", entity_type="partnership", role="partnership",
                       expense_dev_fee=False)
        s.add_all([parent, part])
        s.flush()
        for num, name, typ in PARENT_ACCTS:
            s.add(Account(company_id=parent.id, number=num, name=name, acct_type=typ, statement="BS"))
        for num, name, typ in PART_ACCTS:
            s.add(Account(company_id=part.id, number=num, name=name, acct_type=typ, statement="BS"))
        draw = DrawPackage(
            company_id=part.id, draw_number="29", customer_job="Hunters Landing",
            package_total=DRAW_29_TOTAL, status="approved_for_accounting",
            cm_approved=True, watson_approved=True, source_doc_ref="DRAW-29.pdf",
        )
        s.add(draw)
        s.flush()
        yield {"s": s, "parent": parent.id, "part": part.id, "draw": draw.id}
    finally:
        s.rollback()
        s.close()


def _live(s: Session, draw_id: str) -> list[FeeEntry]:
    return list(s.scalars(select(FeeEntry).where(
        FeeEntry.draw_package_id == draw_id, FeeEntry.status != "void")).all())


@pytest.mark.integration
def test_draw29_exact_amounts_and_zero_partnership_commission(book):
    s, draw_id, part = book["s"], book["draw"], book["part"]
    res = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert res.drafted and not res.idempotent
    amt = res.amounts
    assert amt["dev_5_partnership"] == "48142.28"
    assert amt["dev_inc_5_parent"] == "48142.28"
    assert amt["ceo_2_parent"] == "19256.91"
    assert amt["pres_1_parent"] == "9628.46"
    # partnership book carries the 5% only — zero commission entries.
    part_entries = [e for e in _live(s, draw_id) if e.book_company_id == part]
    assert len(part_entries) == 1
    assert part_entries[0].fee_role == "dev_5_partnership"


@pytest.mark.integration
def test_capitalization_dr_account(book):
    s, draw_id = book["s"], book["draw"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    dev = next(e for e in _live(s, draw_id) if e.fee_role == "dev_5_partnership")
    assert dev.dr_account == policy.ACCT_CIP_DEV_FEE  # default = capitalize


@pytest.mark.integration
def test_idempotent_double_run_no_duplicates(book):
    s, draw_id = book["s"], book["draw"]
    r1 = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert r1.drafted
    r2 = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert r2.idempotent and not r2.drafted
    assert len(_live(s, draw_id)) == 4  # still exactly 4, no duplication


@pytest.mark.integration
def test_rejected_draw_creates_no_drafts(book):
    s, draw_id = book["s"], book["draw"]
    draw = s.get(DrawPackage, draw_id)
    draw.status = "rejected"
    s.flush()
    res = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert not res.drafted
    assert len(_live(s, draw_id)) == 0


@pytest.mark.integration
def test_submitted_draw_not_eligible(book):
    s, draw_id = book["s"], book["draw"]
    draw = s.get(DrawPackage, draw_id)
    draw.status = "submitted"
    s.flush()
    ok, reason = engine.is_fee_eligible(draw)
    assert not ok and "approved_for_accounting" in reason


@pytest.mark.integration
def test_missing_watson_approval_blocks(book):
    s, draw_id = book["s"], book["draw"]
    draw = s.get(DrawPackage, draw_id)
    draw.watson_approved = False
    s.flush()
    res = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert not res.drafted and "Watson" in res.reason


@pytest.mark.integration
def test_revised_invalidates_draft_and_requires_reapproval(book):
    s, draw_id = book["s"], book["draw"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert len(_live(s, draw_id)) == 4
    # draw revised after drafting → drafts voided, reapproval required
    draw = s.get(DrawPackage, draw_id)
    draw.status = "revised"
    s.flush()
    res = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert not res.drafted and "voided" in res.reason
    assert len(_live(s, draw_id)) == 0
    # re-approve → redrafts cleanly
    draw.status = "approved_for_accounting"
    s.flush()
    res2 = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert res2.drafted
    assert len(_live(s, draw_id)) == 4


@pytest.mark.integration
def test_wrong_amount_triggers_exception(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    dev = next(e for e in _live(s, draw_id) if e.fee_role == "dev_5_partnership")
    dev.amount = Decimal("1.00")  # corrupt the 5%
    s.flush()
    codes = {e.code for e in scan_exceptions(s, part, parent)}
    assert "FEE_AMOUNT_WRONG" in codes


@pytest.mark.integration
def test_commission_on_partnership_is_flagged(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    # poison: mis-book the CEO commission onto the partnership file
    ceo = next(e for e in _live(s, draw_id) if e.fee_role == "ceo_2_parent")
    ceo.book_company_id = part
    s.flush()
    codes = {e.code for e in scan_exceptions(s, part, parent)}
    assert "COMMISSION_ON_PARTNERSHIP" in codes


@pytest.mark.integration
def test_missing_commission_is_flagged(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    ceo = next(e for e in _live(s, draw_id) if e.fee_role == "ceo_2_parent")
    ceo.status = "void"  # drop the 2%
    s.flush()
    codes = {e.code for e in scan_exceptions(s, part, parent)}
    assert "MISSING_CEO_COMMISSION" in codes


@pytest.mark.integration
def test_draw_total_changed_after_draft_is_flagged(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    draw = s.get(DrawPackage, draw_id)
    draw.package_total = Decimal("1000000.00")  # changed after drafting
    s.flush()
    codes = {e.code for e in scan_exceptions(s, part, parent)}
    assert "DRAW_TOTAL_CHANGED" in codes


@pytest.mark.integration
def test_clean_draw_has_zero_exceptions_and_green_reports(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert scan_exceptions(s, part, parent) == []
    assert all(r["ok"] for r in partnership_draw_vs_fee(s, part))
    assert all(r["ok"] for r in parent_commission_register(s, parent))
    assert all(r["ok"] for r in cross_book_reconciliation(s, part, parent))


@pytest.mark.integration
def test_intercompany_nets_to_zero(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    assert net_intercompany(s, part, parent) == Decimal("0")


@pytest.mark.integration
def test_cross_book_counts_5pct_once_not_13pct(book):
    s, draw_id, part, parent = book["s"], book["draw"], book["part"], book["parent"]
    engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    row = cross_book_reconciliation(s, part, parent)[0]
    # distinct economic charge = 8% ($77,027.65), never the 13% double-count ($125,169.93).
    assert row["distinct_economic_total_8pct"] == "77027.65"
    assert row["distinct_economic_total_8pct"] != "125169.93"


@pytest.mark.integration
def test_shadow_mode_zero_quickbooks_writes(book):
    s, draw_id = book["s"], book["draw"]
    res = engine.process_draw(s, draw_id, parent_company_id=book["parent"])
    for e in _live(s, draw_id):
        assert e.status == "drafted"  # never queued/sent
        assert e.qb_txn_id is None  # no QB transaction id assigned
    bundle = s.get(ProofBundle, res.proof_bundle_id)
    assert bundle.payload["shadow_mode"] is True
    assert bundle.payload["qb_write"] is False
