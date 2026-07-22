"""QBWC SOAP session + envelope tests: happy-path multi-stage poll, bad creds,
and the file-locked failure path (backoff, no partial commit). No DB."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from app.transport.metrics import PollMetrics
from app.transport.qbwc import QBWCSessionManager, dispatch_soap
from tests.test_transport_qbxml import BILL_RESPONSE, VENDOR_RESPONSE

USER, PWD = "qbwc", "s3cret"


def _manager() -> QBWCSessionManager:
    return QBWCSessionManager(metrics=PollMetrics(), username=USER, password=PWD)


def _soap(method: str, params: dict[str, str]) -> bytes:
    body = "".join(f"<{k}>{v}</{k}>" for k, v in params.items())
    return (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        f'<{method} xmlns="http://developer.intuit.com/">{body}</{method}>'
        "</soap:Body></soap:Envelope>"
    ).encode()


def _strings(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    return [e.text or "" for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "string"]


# -- authentication --------------------------------------------------------- #
def test_authenticate_success_returns_ticket():
    mgr = _manager()
    ticket, file_state = mgr.authenticate(USER, PWD)
    assert ticket and file_state == ""
    assert ticket in mgr.sessions


def test_authenticate_bad_credentials_returns_nvu():
    mgr = _manager()
    ticket, file_state = mgr.authenticate(USER, "wrong")
    assert ticket == "" and file_state == "nvu"
    assert mgr.sessions == {}


# -- happy path: full two-stage read-only sync ------------------------------ #
def test_full_session_parses_vendor_and_bill():
    mgr = _manager()
    ticket, _ = mgr.authenticate(USER, PWD)

    req1 = mgr.send_request_xml(ticket)
    assert "VendorQueryRq" in req1
    assert mgr.receive_response_xml(ticket, VENDOR_RESPONSE) == 50

    req2 = mgr.send_request_xml(ticket)
    assert "BillQueryRq" in req2
    assert mgr.receive_response_xml(ticket, BILL_RESPONSE) == 100

    session = mgr.sessions[ticket]
    assert session.is_complete
    assert session.vendors[0]["qb_list_id"] == "80000001-1"
    assert session.bills[0]["qb_txn_id"] == "1A2-3B4"
    # No more work; metric saw 2 polls.
    assert mgr.send_request_xml(ticket) == ""
    assert mgr.metrics.poll_count == 2
    assert mgr.metrics.max_queue_depth == 2


# -- failure path: file locked --------------------------------------------- #
def test_hresult_error_backs_off_and_blocks_persist():
    mgr = _manager()
    ticket, _ = mgr.authenticate(USER, PWD)
    mgr.send_request_xml(ticket)
    pct = mgr.receive_response_xml(ticket, "", hresult="0x80040420", message="File in use")
    assert pct < 0
    session = mgr.sessions[ticket]
    assert session.has_error and not session.is_complete
    assert session.vendors == []  # nothing parsed -> nothing to persist
    assert mgr.metrics.backoff_seconds() > 0
    assert mgr.get_last_error(ticket) == "File in use"


def test_status_code_error_is_caught_and_reported():
    from tests.test_transport_qbxml import FILE_LOCKED_RESPONSE

    mgr = _manager()
    ticket, _ = mgr.authenticate(USER, PWD)
    mgr.send_request_xml(ticket)
    pct = mgr.receive_response_xml(ticket, FILE_LOCKED_RESPONSE)
    assert pct < 0
    assert "3260" in mgr.get_last_error(ticket)
    assert not mgr.sessions[ticket].is_complete


# -- SOAP envelope round-trip ---------------------------------------------- #
def test_dispatch_authenticate_envelope():
    mgr = _manager()
    reply = dispatch_soap(_soap("authenticate", {"strUserName": USER, "strPassword": PWD}), mgr)
    values = _strings(reply)
    assert len(values) == 2
    assert values[0] in mgr.sessions  # first string is the ticket
    assert values[1] == ""


def test_dispatch_close_connection():
    mgr = _manager()
    ticket, _ = mgr.authenticate(USER, PWD)
    reply = dispatch_soap(_soap("closeConnection", {"ticket": ticket}), mgr)
    assert "OK" in reply
    assert ticket not in mgr.sessions
