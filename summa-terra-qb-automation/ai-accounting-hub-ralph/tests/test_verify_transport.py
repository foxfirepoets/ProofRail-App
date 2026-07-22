"""Add-only transport coverage for the gated BillAdd codec + adapter write method.

Lives under tests/test_verify_* (CHUNK_6_VERIFY ownership); the original
test_transport_* suite is left untouched and must stay green.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.transport import qbxml
from app.transport.adapter import QBDesktopAdapter

BILL = {"amount": Decimal("12500.00"), "po_ref": "PO-2291"}

ADD_OK = (
    '<?xml version="1.0"?><QBXML><QBXMLMsgsRs>'
    '<BillAddRs statusCode="0" statusSeverity="Info" statusMessage="Status OK">'
    "<BillRet><TxnID>NEW-1</TxnID><EditSequence>5</EditSequence>"
    "<RefNumber>PO-2291</RefNumber><AmountDue>12500.00</AmountDue>"
    "<CustomField>kept</CustomField></BillRet>"
    "</BillAddRs></QBXMLMsgsRs></QBXML>"
)

ADD_CONFLICT = (
    '<?xml version="1.0"?><QBXML><QBXMLMsgsRs>'
    '<BillAddRs statusCode="3200" statusSeverity="Error" '
    'statusMessage="edit sequence out of date" /></QBXMLMsgsRs></QBXML>'
)


def test_build_bill_add_is_wellformed_add_request():
    req = qbxml.build_bill_add(BILL, vendor_list_id="80000001-1", account_name="6100")
    assert "BillAddRq" in req
    assert "<ListID>80000001-1</ListID>" in req
    assert "<FullName>6100</FullName>" in req
    assert "<Amount>12500.00</Amount>" in req
    assert "<RefNumber>PO-2291</RefNumber>" in req


def test_parse_bill_add_reconciliation_fields():
    parsed = qbxml.parse_bill_add_response(ADD_OK)
    assert parsed["qb_txn_id"] == "NEW-1"
    assert parsed["qb_edit_sequence"] == "5"
    assert parsed["amount"] == Decimal("12500.00")
    assert parsed["raw_extensions"]["CustomField"] == "kept"


def test_parse_bill_add_raises_on_edit_conflict():
    with pytest.raises(qbxml.QBXMLError) as exc:
        qbxml.parse_bill_add_response(ADD_CONFLICT)
    assert exc.value.status_code == qbxml.EDIT_SEQUENCE_CONFLICT


def test_adapter_add_bill_round_trip():
    sent: list[str] = []

    def writer(req: str) -> str:
        sent.append(req)
        return ADD_OK

    parsed = QBDesktopAdapter().add_bill(
        writer, bill=BILL, vendor_list_id="80000001-1", account_name="6100"
    )
    assert parsed["qb_txn_id"] == "NEW-1"
    assert len(sent) == 1 and "BillAddRq" in sent[0]
