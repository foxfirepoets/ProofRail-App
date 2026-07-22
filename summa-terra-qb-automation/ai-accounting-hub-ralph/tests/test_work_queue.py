"""Generic work-queue engine tests (FIN-1).

Offline tests are hermetic: pure-helper checks (fingerprint reuse, coding, amount, action
mapping, duplicate predicate via a tiny fake session), the registry shape (only the QuickBooks
write-back module stays pending), and an ``ast`` shadow-safety scan proving ``work_queue.py`` has
no QuickBooks / QBWC / BillAdd / payment / draw-engine path. The full intake -> exception ->
approve -> audit flow plus the two aggregation views run against the live canonical store, gated
by RUN_INTEGRATION=1, and roll their transaction back so nothing persists.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.dashboard import modules
from app.dashboard import work_queue as wq

WQ_FILE = Path(__file__).resolve().parents[1] / "app" / "dashboard" / "work_queue.py"


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------
def test_bank_fingerprint_reused_is_hash_never_raw():
    raw = "Routing 124003116 / Acct 0099887766"
    fp = wq.bank_fingerprint(raw)
    assert fp is not None
    assert len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)
    assert raw not in fp
    assert wq.bank_fingerprint(None) is None and wq.bank_fingerprint("") is None


def test_coding_missing_combinations():
    assert wq._coding_missing(None, None, None) == ["Customer:Job", "Class", "Item"]
    assert wq._coding_missing("Job", None, "Item") == ["Class"]
    assert wq._coding_missing("Job", "Class", "Item") == []


def test_to_cents_handles_blank_and_bad_input():
    assert wq._to_cents(None) is None
    assert wq._to_cents("") is None
    assert wq._to_cents("not-money") is None
    assert str(wq._to_cents("1500")) == "1500.00"
    assert str(wq._to_cents("12.005")) == "12.00"


def test_action_status_mapping_and_unknown_action():
    assert wq._ACTION_STATUS["approve"] == wq.ST_APPROVED
    assert wq._ACTION_STATUS["reject"] == wq.ST_REJECTED
    assert wq._ACTION_STATUS["needs-info"] == wq.ST_NEEDS_INFO
    # Unknown action is rejected before any DB access (session is never touched).
    with pytest.raises(wq.WorkItemError):
        wq.set_work_item_status(object(), "item-x", "post-to-qb")  # type: ignore[arg-type]


def test_workitem_module_registry_membership():
    assert wq.is_workitem_module("bank_feed") is True
    assert wq.is_workitem_module("vendor_setup") is True
    # Aggregation views and pending QB write-back are NOT WorkItem-backed.
    assert wq.is_workitem_module("month_end") is False
    assert wq.is_workitem_module("missing_dimensions") is False
    assert wq.is_workitem_module("qb_sync") is False
    # bank-sensitive modules flagged for fingerprint handling.
    assert wq.WORKITEM_MODULES["bank_feed"] is True
    assert wq.WORKITEM_MODULES["credit_card"] is True
    assert wq.WORKITEM_MODULES["vendor_setup"] is True
    assert wq.WORKITEM_MODULES["loan_draws"] is False


# ---------------------------------------------------------------------------
# Duplicate predicate (hermetic fake session — SQL scoping is exercised live)
# ---------------------------------------------------------------------------
class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self, _stmt):
        return _Scalars(self._rows)


def test_is_duplicate_when_reference_matches():
    sess = _FakeSession([object()])
    assert wq._is_duplicate(sess, "co", "bank_feed", "REF-1") is True  # type: ignore[arg-type]


def test_is_duplicate_no_reference_is_not():
    sess = _FakeSession([object()])
    assert wq._is_duplicate(sess, "co", "bank_feed", None) is False  # type: ignore[arg-type]


def test_is_duplicate_no_rows_is_not():
    sess = _FakeSession([])
    assert wq._is_duplicate(sess, "co", "bank_feed", "REF-1") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Registry + shadow safety
# ---------------------------------------------------------------------------
def test_only_qb_sync_is_pending():
    pending = {m.key for m in modules.MODULES if m.status == "pending"}
    assert pending == {"qb_sync"}
    # Every WorkItem-backed module + both aggregation views are functional with a /ui/m route.
    for key in (*wq.WORKITEM_MODULES, "month_end", "missing_dimensions"):
        m = modules.get_module(key)
        assert m is not None and m.status == "functional"
        assert m.route == f"/ui/m/{key}"


def test_work_queue_has_no_qb_write_path():
    forbidden_modules = ("transport", "qbwc", "draw_engine", "payments", "verify.execution")
    forbidden_calls = {"BillAdd", "bill_add", "process_draw", "add_bill", "execute_payment"}
    tree = ast.parse(WQ_FILE.read_text(encoding="utf-8"), filename=str(WQ_FILE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(m in n.name for m in forbidden_modules), f"import {n.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not any(m in mod for m in forbidden_modules), f"from {mod}"
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            assert name not in forbidden_calls, f"call {name}"


# ---------------------------------------------------------------------------
# Live flow (gated by RUN_INTEGRATION=1; transaction rolled back)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_live_work_queue_full_flow():
    from sqlalchemy.orm import Session

    from app.db import get_engine
    from app.models import Company

    with Session(get_engine()) as s:
        trans = s.begin()
        try:
            company = Company(legal_name="WQ Test Co", entity_type="partnership")
            s.add(company)
            s.flush()

            # 1. Intake fully-coded items in TWO modules -> appear in their lists, counts rise.
            before_bank = wq.work_item_count(s, "bank_feed")
            before_dist = wq.work_item_count(s, "distributions")
            r_bank = wq.intake_work_item(
                s, "bank_feed", company_id=company.id, title="ACH deposit",
                reference="BF-1001", counterparty="UFirst Bank", amount="1500.00",
                txn_date="2026-07-01", customer_job="407 W 12th", class_ref="Sitework",
                item_cost_code="012", bank_detail="OLD-BANK-ACCT-111",
            )
            r_dist = wq.intake_work_item(
                s, "distributions", company_id=company.id, title="Q2 distribution",
                reference="DIST-1", counterparty="Investor A", amount="25000.00",
                customer_job="407 W 12th", class_ref="Equity", item_cost_code="011",
            )
            assert r_bank["status"] == "intaken" and r_dist["status"] == "intaken"
            bank_items = wq.list_work_items(s, "bank_feed", company.id)
            assert any(it["id"] == r_bank["item_id"] for it in bank_items)
            assert wq.work_item_count(s, "bank_feed") == before_bank + 1
            assert wq.work_item_count(s, "distributions") == before_dist + 1

            # 2. Duplicate (same company + module + reference) -> DUPLICATE exception.
            r_dup = wq.intake_work_item(
                s, "bank_feed", company_id=company.id, title="ACH deposit (dup)",
                reference="BF-1001", counterparty="UFirst Bank", amount="1500.00",
                customer_job="407 W 12th", class_ref="Sitework", item_cost_code="012",
            )
            assert wq.EXC_DUPLICATE in r_dup["exceptions"]

            # 3. Missing-coding -> MISSING_CODING exception, still in review.
            r_missing = wq.intake_work_item(
                s, "credit_card", company_id=company.id, title="Card charge",
                reference="CC-9", counterparty="Home Depot", amount="412.10",
            )
            assert wq.EXC_MISSING_CODING in r_missing["exceptions"]
            assert r_missing["item_status"] == wq.ST_NEEDS_REVIEW

            # 4. Bank-change warning (fingerprint differs) — fingerprint only, never raw.
            r_bankchg = wq.intake_work_item(
                s, "bank_feed", company_id=company.id, title="ACH deposit (new bank)",
                reference="BF-1002", counterparty="UFirst Bank", amount="900.00",
                customer_job="407 W 12th", class_ref="Sitework", item_cost_code="012",
                bank_detail="NEW-BANK-ACCT-999",
            )
            assert wq.WARN_BANK_CHANGE in r_bankchg["warnings"]
            chg = wq.get_work_item(s, r_bankchg["item_id"])
            assert chg is not None
            # No raw bank field anywhere on the stored record.
            assert "NEW-BANK-ACCT-999" not in str(chg)
            assert chg["has_bank_fingerprint"] is True

            # 5. Approve -> canonical status changes AND an audit row is written.
            res = wq.set_work_item_status(s, r_dist["item_id"], "approve")
            assert res["status"] == wq.ST_APPROVED
            trail = wq.work_item_audit_trail(s, "distributions", r_dist["item_id"])
            assert any(a["action_type"].startswith("work_item.approve") for a in trail)
            assert any(a["action_type"].startswith("work_item.intake") for a in trail)

            # reject + needs-info also transition status only.
            assert wq.set_work_item_status(
                s, r_missing["item_id"], "needs-info")["status"] == wq.ST_NEEDS_INFO
            assert wq.set_work_item_status(
                s, r_dup["item_id"], "reject")["status"] == wq.ST_REJECTED

            # 6. Aggregation views surface the seeded exceptions / missing-dimension items.
            close = wq.month_end_exceptions(s)
            assert any(
                row["module_key"] == "credit_card" and row["exception"] == wq.EXC_MISSING_CODING
                for row in close
            )
            missing = wq.missing_dimensions_items(s)
            assert any(row["link"].endswith(r_missing["item_id"]) for row in missing)
        finally:
            trans.rollback()
