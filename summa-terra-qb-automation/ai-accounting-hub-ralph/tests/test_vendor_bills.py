"""Vendor Bills / Non-GC Invoices module tests (VB-4).

Offline tests are hermetic: pure-helper checks (fingerprint, coding, duplicate predicate via a
tiny fake session, action mapping) plus an ``ast`` shadow-safety scan proving the module has no
QuickBooks / QBWC / BillAdd / payment path. The full intake -> exception -> approve -> audit
flow against the live canonical store is gated by RUN_INTEGRATION=1 and rolls its transaction
back, so nothing persists.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.dashboard import modules
from app.dashboard import vendor_bills as vb

VB_FILE = Path(__file__).resolve().parents[1] / "app" / "dashboard" / "vendor_bills.py"


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------
def test_bank_fingerprint_is_hash_never_raw():
    raw = "Routing 124003116 / Acct 0099887766"
    fp = vb.bank_fingerprint(raw)
    assert fp is not None
    assert len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)
    assert raw not in fp  # the raw detail is never embedded
    # Deterministic + format-insensitive (spaces / slashes ignored).
    assert fp == vb.bank_fingerprint("routing124003116acct0099887766")


def test_bank_fingerprint_empty_is_none():
    assert vb.bank_fingerprint(None) is None
    assert vb.bank_fingerprint("") is None
    assert vb.bank_fingerprint("   ") is None


def test_bank_fingerprint_change_detectable():
    assert vb.bank_fingerprint("OLD-BANK-1") != vb.bank_fingerprint("NEW-BANK-2")


def test_coding_missing_combinations():
    assert vb._coding_missing(None, None, None) == ["Customer:Job", "Class", "Item"]
    assert vb._coding_missing("Job", None, "Item") == ["Class"]
    assert vb._coding_missing("Job", "Class", "Item") == []


def test_action_status_mapping_and_unknown_action():
    assert vb._ACTION_STATUS["approve"] == vb.ST_APPROVED
    assert vb._ACTION_STATUS["reject"] == vb.ST_REJECTED
    assert vb._ACTION_STATUS["needs-info"] == vb.ST_NEEDS_INFO
    # Unknown action is rejected before any DB access (session is never touched).
    with pytest.raises(vb.VendorBillError):
        vb.set_vendor_bill_status(object(), "bill-x", "post-to-qb")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Duplicate predicate (hermetic fake session — SQL scoping is exercised live)
# ---------------------------------------------------------------------------
class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self, _stmt):
        return _Scalars(self._rows)


class _FakeBill:
    def __init__(self, invoice_no, bill_type="vendor_bill"):
        self.raw_extensions = {"bill_type": bill_type, "invoice_no": invoice_no}


def test_is_duplicate_same_vendor_same_invoice():
    sess = _FakeSession([_FakeBill("INV-1")])
    assert vb._is_duplicate(sess, "co", "v", "INV-1") is True  # type: ignore[arg-type]


def test_is_duplicate_different_invoice_is_not():
    sess = _FakeSession([_FakeBill("INV-1")])
    assert vb._is_duplicate(sess, "co", "v", "INV-2") is False  # type: ignore[arg-type]


def test_is_duplicate_ignores_non_vendor_bill_rows():
    sess = _FakeSession([_FakeBill("INV-1", bill_type="gc_draw")])
    assert vb._is_duplicate(sess, "co", "v", "INV-1") is False  # type: ignore[arg-type]


def test_is_duplicate_no_invoice_is_not():
    sess = _FakeSession([_FakeBill("INV-1")])
    assert vb._is_duplicate(sess, "co", "v", None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Registry + shadow safety
# ---------------------------------------------------------------------------
def test_vendor_bills_module_is_functional():
    m = modules.get_module("vendor_bills")
    assert m is not None
    assert m.status == "functional"
    assert m.route == "/ui/vendor-bills"


def test_vendor_bills_has_no_qb_write_path():
    forbidden_modules = ("transport", "qbwc", "draw_engine", "payments", "verify.execution")
    forbidden_calls = {"BillAdd", "bill_add", "process_draw", "add_bill", "execute_payment"}
    tree = ast.parse(VB_FILE.read_text(encoding="utf-8"), filename=str(VB_FILE))
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
def test_live_vendor_bill_full_flow():
    from sqlalchemy.orm import Session

    from app.db import get_engine
    from app.models import Company, Vendor

    with Session(get_engine()) as s:
        trans = s.begin()
        try:
            company = Company(legal_name="VB Test Co", entity_type="partnership")
            s.add(company)
            s.flush()
            vendor = Vendor(company_id=company.id, name="Acme Supply LLC")
            vendor.bank_fingerprint = vb.bank_fingerprint("OLD-BANK-ACCT-111")
            s.add(vendor)
            s.flush()

            # 1. Intake a fully-coded invoice -> appears in the work queue, status pending.
            r1 = vb.intake_vendor_bill(
                s, company_id=company.id, vendor_name="Acme Supply LLC",
                invoice_no="INV-1001", amount="2500.00", due_date="2026-07-15",
                customer_job="407 W 12th", class_ref="Sitework", item_cost_code="012",
            )
            assert r1["status"] == "intaken"
            assert r1["bill_status"] == vb.ST_PENDING
            assert r1["exceptions"] == []
            bills = vb.list_vendor_bills(s, company.id)
            assert any(b["id"] == r1["bill_id"] for b in bills)

            # 2. Duplicate invoice (same vendor + invoice #) -> exception.
            r_dup = vb.intake_vendor_bill(
                s, company_id=company.id, vendor_name="Acme Supply LLC",
                invoice_no="INV-1001", amount="2500.00",
                customer_job="407 W 12th", class_ref="Sitework", item_cost_code="012",
            )
            assert vb.EXC_DUPLICATE_INVOICE in r_dup["exceptions"]

            # 3. Bank-change warning (fingerprint differs) — fingerprint only, never raw.
            r_bank = vb.intake_vendor_bill(
                s, company_id=company.id, vendor_name="Acme Supply LLC",
                invoice_no="INV-1002", amount="900.00",
                customer_job="407 W 12th", class_ref="Sitework", item_cost_code="012",
                bank_detail="NEW-BANK-ACCT-999",
            )
            assert vb.WARN_VENDOR_BANK_CHANGE in r_bank["warnings"]
            bank_bill = vb.get_vendor_bill(s, r_bank["bill_id"])
            assert bank_bill is not None
            # No raw bank field anywhere on the stored record.
            assert "NEW-BANK-ACCT-999" not in str(bank_bill)

            # 4. Missing-coding exception -> needs_info.
            r_missing = vb.intake_vendor_bill(
                s, company_id=company.id, vendor_name="Acme Supply LLC",
                invoice_no="INV-1003", amount="400.00",
            )
            assert vb.EXC_MISSING_CODING in r_missing["exceptions"]
            assert r_missing["bill_status"] == vb.ST_NEEDS_INFO

            # 5. Approve -> canonical status changes AND an audit row is written.
            res = vb.set_vendor_bill_status(s, r1["bill_id"], "approve")
            assert res["status"] == vb.ST_APPROVED
            trail = vb.vendor_bill_audit_trail(s, r1["bill_id"])
            assert any(a["action_type"] == "vendor_bill.approve" for a in trail)
            assert any(a["action_type"] == "vendor_bill.intake" for a in trail)
        finally:
            trans.rollback()
