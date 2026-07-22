"""qbXML codec tests: request emission, canonical parsing, and the lossless
raw_extensions round-trip (the key CHUNK_2 data-integrity guarantee). No DB."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.transport import qbxml

VENDOR_RESPONSE = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs>
<VendorQueryRs statusCode="0" statusSeverity="Info" statusMessage="Status OK">
<VendorRet>
  <ListID>80000001-1</ListID>
  <EditSequence>1410</EditSequence>
  <Name>Acme Concrete</Name>
  <CompanyName>Acme Concrete LLC</CompanyName>
  <AccountNumber>VEND-1001</AccountNumber>
  <VendorAddress><Addr1>1 Main St</Addr1><City>Austin</City></VendorAddress>
</VendorRet>
</VendorQueryRs>
</QBXMLMsgsRs></QBXML>"""

BILL_RESPONSE = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs>
<BillQueryRs statusCode="0" statusSeverity="Info" statusMessage="Status OK">
<BillRet>
  <TxnID>1A2-3B4</TxnID>
  <EditSequence>9</EditSequence>
  <RefNumber>PO-2291</RefNumber>
  <VendorRef><ListID>80000001-1</ListID><FullName>Acme Concrete</FullName></VendorRef>
  <AmountDue>12500.00</AmountDue>
  <ExpenseLineRet><AccountRef><FullName>6100</FullName></AccountRef><Amount>12500.00</Amount></ExpenseLineRet>
  <CustomField>preserved-verbatim</CustomField>
</BillRet>
</BillQueryRs>
</QBXMLMsgsRs></QBXML>"""

FILE_LOCKED_RESPONSE = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs>
<VendorQueryRs statusCode="3260" statusSeverity="Error"
  statusMessage="Insufficient permission level / file in use." />
</QBXMLMsgsRs></QBXML>"""


def test_build_vendor_query_is_read_only_wellformed():
    req = qbxml.build_vendor_query()
    assert "VendorQueryRq" in req
    assert "Add" not in req and "Mod" not in req  # read-only only


def test_build_bill_query_includes_line_items():
    req = qbxml.build_bill_query()
    assert "BillQueryRq" in req
    assert "<IncludeLineItems>true</IncludeLineItems>" in req


def test_parse_vendor_canonical_fields():
    [vendor] = qbxml.parse_vendors(VENDOR_RESPONSE)
    assert vendor["qb_list_id"] == "80000001-1"
    assert vendor["qb_edit_sequence"] == "1410"
    assert vendor["name"] == "Acme Concrete"


def test_parse_vendor_unknown_fields_preserved_verbatim():
    """Edge case: fields absent from the canonical schema survive in raw_extensions."""
    [vendor] = qbxml.parse_vendors(VENDOR_RESPONSE)
    raw = vendor["raw_extensions"]
    assert raw["CompanyName"] == "Acme Concrete LLC"
    assert raw["AccountNumber"] == "VEND-1001"
    # Nested structure preserved losslessly as a dict.
    assert raw["VendorAddress"] == {"Addr1": "1 Main St", "City": "Austin"}
    # Canonical-mapped tags are lifted out, not duplicated into the sidecar.
    assert "ListID" not in raw and "Name" not in raw


def test_parse_bill_canonical_and_vendor_link():
    [bill] = qbxml.parse_bills(BILL_RESPONSE)
    assert bill["qb_txn_id"] == "1A2-3B4"
    assert bill["qb_edit_sequence"] == "9"
    assert bill["po_ref"] == "PO-2291"
    assert bill["amount"] == Decimal("12500.00")
    assert bill["vendor_list_id"] == "80000001-1"
    assert bill["raw_extensions"]["CustomField"] == "preserved-verbatim"


def test_parse_bill_amount_falls_back_to_line_sum():
    no_total = BILL_RESPONSE.replace("<AmountDue>12500.00</AmountDue>", "")
    [bill] = qbxml.parse_bills(no_total)
    assert bill["amount"] == Decimal("12500.00")


def test_parse_raises_on_error_status_code():
    with pytest.raises(qbxml.QBXMLError) as exc:
        qbxml.parse_vendors(FILE_LOCKED_RESPONSE)
    assert exc.value.status_code == "3260"
