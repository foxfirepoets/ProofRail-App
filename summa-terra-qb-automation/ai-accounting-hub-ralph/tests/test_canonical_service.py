"""Unit tests for the canonical read service — no live DB.

A FakeSession returns canned rows so query/transform/namespacing/validation logic is
exercised deterministically (the real pg_trgm SQL is never executed here).
"""
from __future__ import annotations

import pytest

from app.canonical import service


class FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict]:
        return self._rows


class FakeSession:
    """Mimics the slice of SQLAlchemy Session the service uses."""

    def __init__(self, exec_results: list[list[dict]] | None = None, store: dict | None = None):
        self._exec_results = list(exec_results or [])
        self._store = store or {}

    def execute(self, _stmt):  # noqa: ANN001 - stmt is ignored by the fake
        if not self._exec_results:
            return FakeResult([])
        return FakeResult(self._exec_results.pop(0))

    def get(self, model, ident):  # noqa: ANN001
        return self._store.get((model, ident))


# --- validation -------------------------------------------------------------

def test_validate_query_trims_and_returns():
    assert service.validate_query("  acme  ") == "acme"


def test_validate_query_empty_raises():
    with pytest.raises(service.SearchValidationError):
        service.validate_query("   ")


def test_validate_query_none_raises():
    with pytest.raises(service.SearchValidationError):
        service.validate_query(None)


def test_validate_query_oversized_raises():
    with pytest.raises(service.SearchValidationError):
        service.validate_query("x" * (service.MAX_Q_LEN + 1))


# --- search namespacing / transforms ---------------------------------------

def test_search_namespaces_by_company_id():
    # Same vendor name in two companies -> both returned, each tagged its company_id.
    vendor_rows = [
        {"company_id": "co-1", "id": "v-1", "name": "Acme Supply", "score": 0.9},
        {"company_id": "co-2", "id": "v-2", "name": "Acme Supply", "score": 0.8},
    ]
    session = FakeSession(exec_results=[vendor_rows, []])  # vendors, then bills

    results = service.search(session, "Acme", limit=10)

    assert len(results) == 2
    company_ids = {r["company_id"] for r in results}
    assert company_ids == {"co-1", "co-2"}
    namespaced = {r["namespaced_id"] for r in results}
    assert namespaced == {"co-1:v-1", "co-2:v-2"}
    assert all(r["kind"] == "vendor" for r in results)


def test_search_merges_vendors_and_bills_sorted_by_score():
    vendor_rows = [{"company_id": "co-1", "id": "v-1", "name": "Acme", "score": 0.5}]
    bill_rows = [
        {
            "company_id": "co-1",
            "id": "b-1",
            "po_ref": "PO-Acme-1",
            "amount": 250.0,
            "status": "drafted",
            "vendor_name": "Acme",
            "score": 0.95,
        }
    ]
    session = FakeSession(exec_results=[vendor_rows, bill_rows])

    results = service.search(session, "Acme", limit=10)

    assert [r["kind"] for r in results] == ["bill", "vendor"]  # bill scored higher
    bill = results[0]
    assert bill["namespaced_id"] == "co-1:b-1"
    assert bill["amount"] == 250.0
    assert bill["po_ref"] == "PO-Acme-1"


def test_search_respects_limit():
    vendor_rows = [
        {"company_id": "co-1", "id": f"v-{i}", "name": "Acme", "score": 0.5} for i in range(5)
    ]
    session = FakeSession(exec_results=[vendor_rows, []])
    results = service.search(session, "Acme", limit=3)
    assert len(results) == 3


# --- record reads -----------------------------------------------------------

class _FakeVendor:
    id = "v-1"
    company_id = "co-1"
    qb_list_id = "L-1"
    qb_edit_sequence = "1"
    name = "Acme Supply"
    bank_fingerprint = None
    swarmscore = 42
    raw_extensions = {"custom": "x"}


class _FakeBill:
    id = "b-1"
    company_id = "co-1"
    vendor_id = "v-1"
    qb_txn_id = "T-1"
    qb_edit_sequence = "1"
    po_ref = "PO-1"
    amount = 99.5
    status = "drafted"
    invoiceproof_bundle_id = None
    raw_extensions = {"k": "v"}


def test_get_vendor_includes_raw_extensions():
    from app.models import Vendor

    session = FakeSession(store={(Vendor, "v-1"): _FakeVendor()})
    out = service.get_vendor(session, "v-1")
    assert out is not None
    assert out["raw_extensions"] == {"custom": "x"}
    assert out["company_id"] == "co-1"


def test_get_vendor_missing_returns_none():
    session = FakeSession(store={})
    assert service.get_vendor(session, "nope") is None


def test_get_bill_includes_raw_extensions_and_amount_float():
    from app.models import Bill

    session = FakeSession(store={(Bill, "b-1"): _FakeBill()})
    out = service.get_bill(session, "b-1")
    assert out is not None
    assert out["raw_extensions"] == {"k": "v"}
    assert out["amount"] == 99.5


def test_get_bill_missing_returns_none():
    assert service.get_bill(FakeSession(store={}), "nope") is None


# --- dashboard --------------------------------------------------------------

def test_dashboard_aggregates_per_company():
    companies = [
        {"id": "co-1", "legal_name": "Alpha LLC"},
        {"id": "co-2", "legal_name": "Beta LLC"},
    ]
    vendor_counts = [{"company_id": "co-1", "n": 3}]
    bill_aggs = [{"company_id": "co-1", "n": 2, "total": 500.0}]
    session = FakeSession(exec_results=[companies, vendor_counts, bill_aggs])

    rows = service.dashboard(session)

    by_id = {r["company_id"]: r for r in rows}
    assert by_id["co-1"]["vendor_count"] == 3
    assert by_id["co-1"]["bill_count"] == 2
    assert by_id["co-1"]["bill_total"] == 500.0
    # Company with no vendors/bills still appears with zeros.
    assert by_id["co-2"]["vendor_count"] == 0
    assert by_id["co-2"]["bill_count"] == 0
    assert by_id["co-2"]["bill_total"] == 0.0
