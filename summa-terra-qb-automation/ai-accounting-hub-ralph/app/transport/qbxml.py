"""qbXML codec: emit VendorQuery/BillQuery requests and parse responses into
canonical vendor/bill dicts, preserving every QB-native field not in the canonical
schema inside ``raw_extensions`` (lossless round-trip).

READ-ONLY: this module emits *Query* requests only. No Add/Mod/Delete requests.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.sax.saxutils import escape

# qbXML SDK version targeted by the emitted requests. Enterprise supports >= 13.0.
QBXML_VERSION = "13.0"

# qbXML status codes the write path discriminates on (see CHUNK_6_VERIFY).
EDIT_SEQUENCE_CONFLICT = "3200"  # "The provided edit sequence ... is out of date."
ACCOUNT_NOT_FOUND = "3140"       # "There is an invalid reference to a QuickBooks account."

# Canonical column mappings. Tags listed here are lifted out of the qbXML element
# into first-class canonical fields; everything else round-trips via raw_extensions.
_VENDOR_CANONICAL = {"ListID": "qb_list_id", "EditSequence": "qb_edit_sequence", "Name": "name"}
_BILL_CANONICAL = {
    "TxnID": "qb_txn_id",
    "EditSequence": "qb_edit_sequence",
    "RefNumber": "po_ref",
    "AmountDue": "amount",
}


class QBXMLError(Exception):
    """A qbXML response carried a non-zero statusCode (e.g. file locked, 3260)."""

    def __init__(self, status_code: str, message: str | None = None) -> None:
        self.status_code = status_code
        self.message = message or ""
        super().__init__(f"qbXML status {status_code}: {self.message}")


# --------------------------------------------------------------------------- #
# Request emission (read-only queries only)
# --------------------------------------------------------------------------- #
def _qbxml_doc(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<?qbxml version="{QBXML_VERSION}"?>\n'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"{inner}"
        "</QBXMLMsgsRq></QBXML>"
    )


def build_vendor_query(request_id: str = "1", max_returned: int | None = None) -> str:
    """Emit a qbXML ``VendorQueryRq`` (returns all vendors by default)."""
    inner = f'<VendorQueryRq requestID="{request_id}">'
    if max_returned is not None:
        inner += f"<MaxReturned>{max_returned}</MaxReturned>"
    inner += "<ActiveStatus>All</ActiveStatus></VendorQueryRq>"
    return _qbxml_doc(inner)


def build_bill_query(request_id: str = "2", include_line_items: bool = True) -> str:
    """Emit a qbXML ``BillQueryRq`` (returns all bills, with line items)."""
    inner = f'<BillQueryRq requestID="{request_id}">'
    inner += f"<IncludeLineItems>{'true' if include_line_items else 'false'}</IncludeLineItems>"
    inner += "</BillQueryRq>"
    return _qbxml_doc(inner)


# --------------------------------------------------------------------------- #
# Write-back request emission (CHUNK_6_VERIFY — gated BillAdd, add-only).
#
# Unlike the read-only queries above, BillAdd MUTATES the company file and so is
# only ever emitted behind the VerifyAPI + AIVS gates (see app.verify.execution).
# --------------------------------------------------------------------------- #
def _format_amount(value: Any) -> str:
    return f"{_as_decimal(value):.2f}"


def build_bill_add(
    bill: Mapping[str, Any],
    *,
    vendor_list_id: str,
    account_name: str,
    request_id: str = "1",
) -> str:
    """Emit a qbXML ``BillAddRq`` for one approved canonical bill.

    A single expense line is posted to ``account_name`` for the bill amount; the
    optional ``po_ref`` rides along as the QB ``RefNumber``. The request is the
    only Add/Mod the transport ever emits, and only the gated write path calls it.
    """
    parts = [
        f'<BillAddRq requestID="{escape(request_id)}">',
        "<BillAdd>",
        f"<VendorRef><ListID>{escape(str(vendor_list_id))}</ListID></VendorRef>",
    ]
    po_ref = bill.get("po_ref")
    if po_ref:
        parts.append(f"<RefNumber>{escape(str(po_ref))}</RefNumber>")
    parts.append("<ExpenseLineAdd>")
    parts.append(f"<AccountRef><FullName>{escape(str(account_name))}</FullName></AccountRef>")
    parts.append(f"<Amount>{_format_amount(bill.get('amount'))}</Amount>")
    parts.append("</ExpenseLineAdd>")
    parts.append("</BillAdd>")
    parts.append("</BillAddRq>")
    return _qbxml_doc("".join(parts))


def build_bill_add_writeback(
    bill: Mapping[str, Any],
    *,
    vendor_list_id: str,
    account_name: str,
    class_name: str | None = None,
    customer_job: str | None = None,
    draw_number: str | int | None = None,
    request_id: str = "1",
) -> str:
    """Emit a qbXML ``BillAddRq`` for the QBWC write-back adapter (Phase 6 Spec B §6).

    Distinct from :func:`build_bill_add` (CHUNK_6_VERIFY's simpler single-account
    write): this variant additionally maps the Summa Terra dimensional model onto
    the ``ExpenseLineAdd`` — cost-code ``AccountRef``, ``ClassRef`` (phase/entity
    Class), ``CustomerRef`` (Customer:Job), and a ``Draw #`` custom field via
    ``DataExtRef`` (SDK-standard mechanism for a custom field on a line/txn) — so
    a synced bill carries the same dimensions the canonical bill row does.

    ``request_id`` is set by the caller to the bill's canonical UUID (spec §6) so
    a QBWC response can be correlated back to the originating bill even across a
    session gap (spec §7's core idempotency edge case).
    """
    parts = [
        f'<BillAddRq requestID="{escape(request_id)}">',
        "<BillAdd>",
        f"<VendorRef><ListID>{escape(str(vendor_list_id))}</ListID></VendorRef>",
    ]
    po_ref = bill.get("po_ref")
    if po_ref:
        parts.append(f"<RefNumber>{escape(str(po_ref))}</RefNumber>")
    parts.append("<ExpenseLineAdd>")
    parts.append(f"<AccountRef><FullName>{escape(str(account_name))}</FullName></AccountRef>")
    parts.append(f"<Amount>{_format_amount(bill.get('amount'))}</Amount>")
    if class_name:
        parts.append(f"<ClassRef><FullName>{escape(str(class_name))}</FullName></ClassRef>")
    if customer_job:
        parts.append(
            f"<CustomerRef><FullName>{escape(str(customer_job))}</FullName></CustomerRef>"
        )
    parts.append("</ExpenseLineAdd>")
    if draw_number is not None and draw_number != "":
        parts.append(
            "<DataExtRef><OwnerID></OwnerID><DataExtName>Draw #</DataExtName>"
            f"<DataExtValue>{escape(str(draw_number))}</DataExtValue></DataExtRef>"
        )
    parts.append("</BillAdd>")
    parts.append("</BillAddRq>")
    return _qbxml_doc("".join(parts))


def parse_bill_add_response(response_xml: str) -> dict[str, Any]:
    """Parse a ``BillAddRs`` into the reconciliation fields for the canonical bill.

    Raises :class:`QBXMLError` on a non-zero status (e.g. ``3200`` EditSequence
    conflict, ``3140`` missing account) so the caller can route fail-closed.
    Returns ``qb_txn_id``, ``qb_edit_sequence``, ``po_ref``, ``amount`` (Decimal),
    and the lossless ``raw_extensions`` sidecar.
    """
    root = ET.fromstring(response_xml)
    _check_status(root, "BillAddRs")
    ret = root.find(".//BillRet")
    if ret is None:
        raise QBXMLError("unknown", "BillAddRs carried no BillRet element")
    full = _element_to_value(ret)
    if not isinstance(full, dict):
        raise QBXMLError("unknown", "BillAddRs BillRet was not a structured element")
    canonical, raw = _split_canonical(full, _BILL_CANONICAL)
    amount = canonical.get("amount")
    canonical["amount"] = _as_decimal(amount) if amount else _sum_line_amounts(full)
    canonical["raw_extensions"] = raw
    return canonical


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #
def _element_to_value(el: ET.Element) -> Any:
    """Convert a qbXML element subtree to a JSON-serialisable value.

    Leaf elements become their stripped text; container elements become a dict
    keyed by child tag (repeated tags collapse into a list). This is lossless for
    qbXML *Ret element data, which carries no attributes on data nodes.
    """
    children = list(el)
    if not children:
        return (el.text or "").strip()
    result: dict[str, Any] = {}
    for child in children:
        tag = child.tag
        value = _element_to_value(child)
        if tag in result:
            existing = result[tag]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[tag] = [existing, value]
        else:
            result[tag] = value
    return result


def _check_status(root: ET.Element, rs_tag: str) -> None:
    rs = root.find(f".//{rs_tag}")
    if rs is None:
        return
    code = rs.get("statusCode")
    if code not in (None, "0"):
        raise QBXMLError(code or "unknown", rs.get("statusMessage"))


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _sum_line_amounts(full: dict[str, Any]) -> Decimal:
    total = Decimal("0")
    for line_tag in ("ExpenseLineRet", "ItemLineRet"):
        for line in _to_list(full.get(line_tag)):
            if isinstance(line, dict) and "Amount" in line:
                total += _as_decimal(line["Amount"])
    return total


def _split_canonical(
    full: dict[str, Any], mapping: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pop canonical-mapped tags out; whatever remains is the lossless sidecar."""
    raw = dict(full)
    canonical: dict[str, Any] = {}
    for qb_tag, column in mapping.items():
        canonical[column] = raw.pop(qb_tag, None)
    return canonical, raw


def parse_vendors(response_xml: str) -> list[dict[str, Any]]:
    """Parse a ``VendorQueryRs`` into canonical vendor dicts.

    Each dict: ``qb_list_id``, ``qb_edit_sequence``, ``name``, ``raw_extensions``.
    """
    root = ET.fromstring(response_xml)
    _check_status(root, "VendorQueryRs")
    vendors: list[dict[str, Any]] = []
    for ret in root.iter("VendorRet"):
        full = _element_to_value(ret)
        if not isinstance(full, dict):
            continue
        canonical, raw = _split_canonical(full, _VENDOR_CANONICAL)
        canonical["raw_extensions"] = raw
        vendors.append(canonical)
    return vendors


def parse_bills(response_xml: str) -> list[dict[str, Any]]:
    """Parse a ``BillQueryRs`` into canonical bill dicts.

    Each dict: ``qb_txn_id``, ``qb_edit_sequence``, ``po_ref``, ``amount``
    (Decimal), ``vendor_list_id`` (for FK resolution), ``raw_extensions``.
    """
    root = ET.fromstring(response_xml)
    _check_status(root, "BillQueryRs")
    bills: list[dict[str, Any]] = []
    for ret in root.iter("BillRet"):
        full = _element_to_value(ret)
        if not isinstance(full, dict):
            continue
        canonical, raw = _split_canonical(full, _BILL_CANONICAL)
        amount = canonical.get("amount")
        canonical["amount"] = _as_decimal(amount) if amount else _sum_line_amounts(full)
        vendor_ref = full.get("VendorRef")
        canonical["vendor_list_id"] = (
            vendor_ref.get("ListID") if isinstance(vendor_ref, dict) else None
        )
        canonical["raw_extensions"] = raw
        bills.append(canonical)
    return bills
