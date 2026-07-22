"""QBOAdapter swappable-seam tests (CHUNK_8_SCALE).

Edge case: the QBO stub is swapped in for read AND write operations and the callers
are unaffected — it satisfies the SAME ``AccountingAdapter`` interface and returns
canonical-shaped dicts with byte-identical keys (a 0% caller-side mapping delta).
"""
from __future__ import annotations

from decimal import Decimal

from app.models import Bill
from app.scale.qbo_adapter import BILL_KEYS, VENDOR_KEYS, QBOAdapter
from app.scale.sync import MultiCompanySync
from app.transport.adapter import AccountingAdapter, WriteableAccountingAdapter
from app.verify.execution import execute_approved_write

COMPANY = "11111111-1111-1111-1111-111111111111"
GOOD_HEAD = "a" * 64

STORE = {
    COMPANY: {
        "vendors": [{"id": "v1", "company_id": COMPANY, "name": "Globex"}],
        "bills": [{"id": "b1", "company_id": COMPANY, "po_ref": "PO-9", "amount": 50, "status": "synced"}],
    }
}


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = f"pb-{len(self.added)}"


def test_qbo_adapter_satisfies_the_interface():
    qbo = QBOAdapter()
    # Same read seam as QB Desktop (ABC) AND the optional write seam (Protocol).
    assert isinstance(qbo, AccountingAdapter)
    assert isinstance(qbo, WriteableAccountingAdapter)


def test_qbo_returns_canonical_shaped_dicts_identical_to_qb_desktop():
    qbo = QBOAdapter(STORE)
    vendors = qbo.list_vendors(None, COMPANY)
    bills = qbo.list_bills(None, COMPANY)
    # Key sets match the canonical projection callers depend on — no mapping fork.
    assert set(vendors[0]) == set(VENDOR_KEYS)
    assert set(bills[0]) == set(BILL_KEYS)
    # And exactly the same keys QBDesktopAdapter emits from the ORM.
    desk_keys = {
        "id", "company_id", "qb_list_id", "qb_edit_sequence", "name",
        "bank_fingerprint", "swarmscore", "raw_extensions",
    }
    assert set(vendors[0]) == desk_keys


def test_multi_company_sync_works_unchanged_with_qbo_swapped_in():
    # The SAME orchestrator, given the QBO adapter instead of QB Desktop, with no edits.
    sync = MultiCompanySync(company_ids=(COMPANY,), adapter=QBOAdapter(STORE))
    states = sync.sync_all(session=None)
    assert states[0].vendor_count == 1 and states[0].bill_count == 1
    assert sync.search("Globex")[0]["company_id"] == COMPANY


def test_gated_write_path_accepts_qbo_adapter_without_caller_changes():
    # execute_approved_write (CHUNK_6) is the write caller; swapping the adapter is a
    # one-line change to a single argument — the gate logic is untouched.
    session = _FakeSession()
    sent: list[str] = []

    def writer(req: str) -> str:  # the qbXML outbound seam (unused by the QBO stub)
        sent.append(req)
        return req

    bill = Bill(company_id=COMPANY, vendor_id="v1", amount=Decimal("125.00"),
                po_ref="PO-9", status="approved", raw_extensions={})
    bill.id = "b1"

    out = execute_approved_write(
        session, bill,
        vendor_list_id="80000001-1",
        account_name="6100",
        writer=writer,
        aivs_head=GOOD_HEAD,
        known_accounts=["6100"],
        load_chain=lambda _s, _sid: [],
        adapter=QBOAdapter(),  # <-- the only change vs a QB Desktop write
    )

    assert out["error"] is None
    assert out["data"]["qb_txn_id"].startswith("QBO-")
    assert bill.status == "synced"  # reconciled by the unchanged caller
