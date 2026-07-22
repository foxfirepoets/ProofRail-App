"""Adapter tests: the read interface (list_vendors/list_bills) over a fake session,
and all-or-nothing persistence of a synced session into the canonical store. No DB."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import Bill, Vendor
from app.transport.adapter import QBDesktopAdapter
from app.transport.qbwc import QBWCSession

COMPANY = "11111111-1111-1111-1111-111111111111"


class _FakeQuery:
    def __init__(self, rows: list):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Minimal Session double: records adds, assigns ids on flush, fakes query()."""

    def __init__(self, rows: dict | None = None):
        self.added: list = []
        self.committed = False
        self._rows = rows or {}
        self._next = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._next += 1
                obj.id = f"id-{self._next}"

    def commit(self):
        self.committed = True

    def query(self, model):
        return _FakeQuery(self._rows.get(model, []))


def _completed_session() -> QBWCSession:
    s = QBWCSession(ticket="t1")
    s.vendors = [
        {
            "qb_list_id": "80000001-1",
            "qb_edit_sequence": "1410",
            "name": "Acme Concrete",
            "raw_extensions": {"AccountNumber": "VEND-1001"},
        }
    ]
    s.bills = [
        {
            "qb_txn_id": "1A2-3B4",
            "qb_edit_sequence": "9",
            "po_ref": "PO-2291",
            "amount": Decimal("12500.00"),
            "vendor_list_id": "80000001-1",
            "raw_extensions": {"CustomField": "x"},
        }
    ]
    s.pending.clear()
    return s


def test_list_vendors_maps_rows():
    vendor = Vendor(company_id=COMPANY, name="Acme", qb_list_id="80000001-1", raw_extensions={})
    vendor.id = "v1"
    session = _FakeSession(rows={Vendor: [vendor]})
    out = QBDesktopAdapter().list_vendors(session, COMPANY)
    assert out == [
        {
            "id": "v1",
            "company_id": COMPANY,
            "qb_list_id": "80000001-1",
            "qb_edit_sequence": None,
            "name": "Acme",
            "bank_fingerprint": None,
            "swarmscore": None,
            "raw_extensions": {},
        }
    ]


def test_list_bills_maps_rows():
    bill = Bill(company_id=COMPANY, vendor_id="v1", amount=Decimal("10.00"), raw_extensions={})
    bill.id = "b1"
    session = _FakeSession(rows={Bill: [bill]})
    out = QBDesktopAdapter().list_bills(session, COMPANY)
    assert out[0]["id"] == "b1"
    assert out[0]["vendor_id"] == "v1"


def test_persist_completed_session_writes_vendor_and_linked_bill():
    session = _FakeSession()
    counts = QBDesktopAdapter().persist_session(session, COMPANY, _completed_session())
    assert counts == {"vendors": 1, "bills": 1}
    assert session.committed is True
    vendors = [o for o in session.added if isinstance(o, Vendor)]
    bills = [o for o in session.added if isinstance(o, Bill)]
    assert len(vendors) == 1 and len(bills) == 1
    # Bill linked to the freshly-flushed vendor id; raw_extensions preserved.
    assert bills[0].vendor_id == vendors[0].id
    assert vendors[0].raw_extensions == {"AccountNumber": "VEND-1001"}
    assert bills[0].raw_extensions == {"CustomField": "x"}


def test_persist_refuses_errored_session():
    bad = _completed_session()
    bad.last_error = "File in use"
    session = _FakeSession()
    with pytest.raises(ValueError):
        QBDesktopAdapter().persist_session(session, COMPANY, bad)
    assert session.added == [] and session.committed is False


def test_persist_refuses_incomplete_session():
    incomplete = QBWCSession(ticket="t2")  # pending stages remain
    session = _FakeSession()
    with pytest.raises(ValueError):
        QBDesktopAdapter().persist_session(session, COMPANY, incomplete)
    assert session.committed is False
