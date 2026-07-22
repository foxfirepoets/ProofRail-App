"""Stable ``AccountingAdapter`` interface + a read-only ``QBDesktopAdapter``.

Callers depend only on the interface, so a future QBO/Intacct adapter can replace
QB Desktop without touching them. The QB Desktop implementation reads the canonical
store and ingests qbXML query results into it (read-only against QB — it never emits
an Add/Mod request). Persistence is all-or-nothing per session: a stalled poll
leaves zero rows behind.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from app.models import Bill, Vendor
from app.transport import qbxml
from app.transport.qbwc import QBWCSession

# A writer is the outbound-poll channel: it hands a qbXML request to the ONE open
# company file (QBWC drains it on its poll cadence) and returns QB's raw response.
QBXMLWriter = Callable[[str], str]


class AccountingAdapter(ABC):
    """The swappable transport seam. Read methods only in this chunk."""

    @abstractmethod
    def list_vendors(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        """Return canonical vendor rows for a company."""

    @abstractmethod
    def list_bills(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        """Return canonical bill rows for a company."""


@runtime_checkable
class WriteableAccountingAdapter(Protocol):
    """Optional write seam layered on top of :class:`AccountingAdapter`.

    Kept separate so read-only adapters need not implement a write path. The gated
    write flow (VerifyAPI + AIVS verified) is the ONLY caller — see
    ``app.verify.execution.execute_approved_write``.
    """

    def add_bill(
        self,
        writer: QBXMLWriter,
        *,
        bill: Mapping[str, Any],
        vendor_list_id: str,
        account_name: str,
        request_id: str = ...,
    ) -> dict[str, Any]:
        """Emit ``BillAdd`` to the one company file and return reconciliation fields."""


def _vendor_to_dict(v: Vendor) -> dict[str, Any]:
    return {
        "id": v.id,
        "company_id": v.company_id,
        "qb_list_id": v.qb_list_id,
        "qb_edit_sequence": v.qb_edit_sequence,
        "name": v.name,
        "bank_fingerprint": v.bank_fingerprint,
        "swarmscore": v.swarmscore,
        "raw_extensions": v.raw_extensions,
    }


def _bill_to_dict(b: Bill) -> dict[str, Any]:
    return {
        "id": b.id,
        "company_id": b.company_id,
        "vendor_id": b.vendor_id,
        "qb_txn_id": b.qb_txn_id,
        "qb_edit_sequence": b.qb_edit_sequence,
        "po_ref": b.po_ref,
        "amount": b.amount,
        "status": b.status,
        "raw_extensions": b.raw_extensions,
    }


class QBDesktopAdapter(AccountingAdapter):
    """QuickBooks Desktop adapter (read-only sync via QBWC/qbXML)."""

    # -- AccountingAdapter (reads from the canonical store) ------------------ #
    def list_vendors(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        rows = session.query(Vendor).filter(Vendor.company_id == company_id).all()
        return [_vendor_to_dict(v) for v in rows]

    def list_bills(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        rows = session.query(Bill).filter(Bill.company_id == company_id).all()
        return [_bill_to_dict(b) for b in rows]

    # -- ORM construction from parsed qbXML --------------------------------- #
    @staticmethod
    def build_vendor(company_id: str, parsed: dict[str, Any]) -> Vendor:
        return Vendor(
            company_id=company_id,
            qb_list_id=parsed.get("qb_list_id"),
            qb_edit_sequence=parsed.get("qb_edit_sequence"),
            name=parsed.get("name") or "",
            raw_extensions=parsed.get("raw_extensions") or {},
        )

    @staticmethod
    def build_bill(company_id: str, vendor_id: str, parsed: dict[str, Any]) -> Bill:
        return Bill(
            company_id=company_id,
            vendor_id=vendor_id,
            qb_txn_id=parsed.get("qb_txn_id"),
            qb_edit_sequence=parsed.get("qb_edit_sequence"),
            po_ref=parsed.get("po_ref"),
            amount=parsed.get("amount") or 0,
            raw_extensions=parsed.get("raw_extensions") or {},
        )

    # -- Gated write-back (CHUNK_6_VERIFY) ---------------------------------- #
    def add_bill(
        self,
        writer: QBXMLWriter,
        *,
        bill: Mapping[str, Any],
        vendor_list_id: str,
        account_name: str,
        request_id: str = "1",
    ) -> dict[str, Any]:
        """Emit a ``BillAdd`` for an APPROVED bill to the one open company file.

        Builds the qbXML, hands it to the outbound-poll ``writer``, and parses QB's
        reply into reconciliation fields (``qb_txn_id`` / ``qb_edit_sequence`` / …).
        Surfaces a :class:`qbxml.QBXMLError` (e.g. ``3200`` EditSequence conflict)
        verbatim so the gated caller can re-base + retry or route to a human.
        """
        request = qbxml.build_bill_add(
            bill,
            vendor_list_id=vendor_list_id,
            account_name=account_name,
            request_id=request_id,
        )
        response = writer(request)
        return qbxml.parse_bill_add_response(response)

    def persist_session(
        self, db_session: Any, company_id: str, qbwc_session: QBWCSession
    ) -> dict[str, int]:
        """Write a *completed* session's vendors+bills into the canonical store.

        Refuses to commit a partial/errored session (fail-closed: no half-written
        rows). Bills are linked to vendors by qb_list_id captured in the same run.
        """
        if not qbwc_session.is_complete:
            raise ValueError("refusing to persist an incomplete or errored QBWC session")

        vendors_by_list_id: dict[str, Vendor] = {}
        for parsed in qbwc_session.vendors:
            vendor = self.build_vendor(company_id, parsed)
            db_session.add(vendor)
            if vendor.qb_list_id:
                vendors_by_list_id[vendor.qb_list_id] = vendor
        db_session.flush()  # assign vendor ids before linking bills

        bill_count = 0
        for parsed in qbwc_session.bills:
            list_id = parsed.get("vendor_list_id")
            linked = vendors_by_list_id.get(list_id) if list_id else None
            if linked is None:
                # Unknown vendor ref: skip rather than orphan a NOT NULL FK.
                continue
            db_session.add(self.build_bill(company_id, linked.id, parsed))
            bill_count += 1

        db_session.commit()
        return {"vendors": len(qbwc_session.vendors), "bills": bill_count}
