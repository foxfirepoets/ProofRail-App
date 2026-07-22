"""``QBOAdapter`` — a STUB QuickBooks *Online* adapter behind the SAME seam.

This proves the "swappable adapter" thesis (SPEC §3, CHUNK_8 acceptance): a future
QBO/Intacct adapter implements the identical :class:`app.transport.adapter.AccountingAdapter`
read interface (plus the optional ``WriteableAccountingAdapter`` write seam), so swapping
it in requires **no change** to the canonical/workflow/proof callers — they depend only
on the interface and the canonical-shaped dict it returns.

It is deliberately a stub: instead of QB Desktop's qbXML-over-QBWC outbound poll, a real
QBO adapter would call the QBO REST API. Here we return canonical-shaped dicts from an
injected in-memory store and synthesise a write acknowledgement, with byte-for-byte the
same dict keys :class:`QBDesktopAdapter` emits — a 0% mapping delta at the caller boundary.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.transport.adapter import AccountingAdapter, QBXMLWriter

# The canonical row shapes the callers consume — identical to QBDesktopAdapter's
# ``_vendor_to_dict`` / ``_bill_to_dict`` output, so mapping code is shared, not forked.
VENDOR_KEYS = (
    "id",
    "company_id",
    "qb_list_id",
    "qb_edit_sequence",
    "name",
    "bank_fingerprint",
    "swarmscore",
    "raw_extensions",
)
BILL_KEYS = (
    "id",
    "company_id",
    "vendor_id",
    "qb_txn_id",
    "qb_edit_sequence",
    "po_ref",
    "amount",
    "status",
    "raw_extensions",
)


def _project(row: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Project an arbitrary source row onto the canonical key set (missing → None)."""
    return {k: row.get(k) for k in keys}


class QBOAdapter(AccountingAdapter):
    """Read-only QBO stub satisfying the canonical ``AccountingAdapter`` seam.

    The in-memory ``store`` stands in for the QBO REST backend: ``{company_id: {"vendors":
    [...], "bills": [...]}}``. Methods return canonical-shaped dicts so every existing
    caller (multi-company sync, unified search, the gated write path) works unchanged.
    """

    def __init__(self, store: Mapping[str, Mapping[str, list[dict[str, Any]]]] | None = None) -> None:
        self._store: dict[str, dict[str, list[dict[str, Any]]]] = {
            cid: {"vendors": list(data.get("vendors", [])), "bills": list(data.get("bills", []))}
            for cid, data in (store or {}).items()
        }

    # -- AccountingAdapter (reads) ----------------------------------------- #
    def list_vendors(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        rows = self._store.get(company_id, {}).get("vendors", [])
        return [_project(r, VENDOR_KEYS) for r in rows]

    def list_bills(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        rows = self._store.get(company_id, {}).get("bills", [])
        return [_project(r, BILL_KEYS) for r in rows]

    # -- WriteableAccountingAdapter (optional write seam) ------------------ #
    def add_bill(
        self,
        writer: QBXMLWriter,
        *,
        bill: Mapping[str, Any],
        vendor_list_id: str,
        account_name: str,
        request_id: str = "1",
    ) -> dict[str, Any]:
        """Synthesise a QBO ``Bill`` create ack in the SAME reconciliation shape.

        A real QBO adapter would POST to ``/v3/company/{id}/bill``; the qbXML ``writer``
        outbound-poll seam is unused by an API adapter (kept in the signature so the
        gated caller — ``execute_approved_write`` — needs no change). Returns the exact
        ``qb_txn_id`` / ``qb_edit_sequence`` keys the caller reconciles.
        """
        return {
            "qb_txn_id": f"QBO-{request_id}-{vendor_list_id}",
            "qb_edit_sequence": "1",
            "amount_due": str(bill.get("amount", 0)),
            "ref_number": bill.get("po_ref"),
        }
