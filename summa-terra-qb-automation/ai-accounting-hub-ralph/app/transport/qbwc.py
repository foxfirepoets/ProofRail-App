"""QBWC SOAP endpoint logic: the five required methods plus the SOAP envelope
plumbing and a per-ticket sync session state machine.

Flow per QBWC session:
  authenticate  -> issue a ticket + queue the read work (vendor then bill query)
  sendRequestXML -> hand QBWC the next qbXML request (records a poll metric)
  receiveResponseXML -> parse QB's response into the session buffer; advance %
  getLastError  -> report why a poll stalled (file locked, etc.)
  closeConnection -> drop the session

Two phases, in strict order:
  1. READ phase (unchanged, always runs): VendorQuery then BillQuery. Parsed rows
     accumulate in-memory and are persisted only when the whole read phase
     completes cleanly (see adapter.persist_session) - an error never half-commits.
  2. WRITE phase (Phase 6, spec-qbwc-writeback-adapter-2026-07-01.md section 9,
     task 9): ONLY runs when the manager was constructed with a ``writeback`` config
     (a DB session factory + a canonical->QB entity resolver). It drains bills that
     are ``status='approved'`` AND proof-passed and emits ``BillAdd`` requests,
     driving each bill through ``qbwc_writeback.sync_bill_to_qb`` (which re-verifies
     the proof boundary DIRECTLY against the DB, fail closed, before every write).
     Each bill's DB mutations flush only when its write completes, so a stalled poll
     never half-commits a bill. When no writeback config is present the session is
     exactly the original READ-ONLY state machine - the connector Ben is authorizing
     keeps working untouched.
"""
from __future__ import annotations

import os
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

from app.transport import qbxml
from app.transport.metrics import PollMetrics

if TYPE_CHECKING:
    from app.transport.qbwc_writeback import BillAddFields, BillWriteDriver

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
QBWC_NS = "http://developer.intuit.com/"

# Ordered read work for one company file. The write phase is appended dynamically
# only when a WritebackConfig is present (see QBWCSession).
_STAGES: tuple[str, ...] = ("vendor_query", "bill_query")

# The write phase is a single logical stage that internally drains N bills; it is
# only ever entered when writeback is configured.
_WRITE_STAGE = "bill_writeback"


@dataclass
class WritebackConfig:
    """Optional write-phase wiring for a session manager (task 9/10/11).

    ``db_factory`` yields a live SQLAlchemy session for the write phase (the read
    phase is DB-free until adapter.persist_session). ``resolver`` turns a canonical
    bill dict into ``BillAddFields`` (canonical->QB refs, task 10) and MAY raise to
    fail a bill closed (unresolved -> exception). ``on_unresolved`` marks such a
    bill ``status='exception'`` and audits it. ``max_bills_per_session`` caps a
    single session's drain (business-hours polling clears realistic STV volume in
    one day, spec section 8).
    """

    db_factory: Callable[[], Any]
    resolver: Callable[[Any], BillAddFields]
    on_unresolved: Callable[[Any, Exception], None] | None = None
    max_bills_per_session: int = 100


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class QBWCSession:
    """In-memory state for one QBWC conversation (one company file)."""

    def __init__(
        self, ticket: str, company_file: str = "", *, write_enabled: bool = False
    ) -> None:
        self.ticket = ticket
        self.company_file = company_file
        stages = list(_STAGES) + ([_WRITE_STAGE] if write_enabled else [])
        self.pending: list[str] = stages
        self.total = len(stages)
        self.vendors: list[dict[str, Any]] = []
        self.bills: list[dict[str, Any]] = []
        self.last_error: str = ""

        # -- write-phase state (only used when write_enabled) --------------- #
        self.write_enabled = write_enabled
        self.write_started = False
        self.write_db: Any | None = None
        self._pending_bills: list[dict[str, Any]] = []
        self._active_driver: BillWriteDriver | None = None
        self._awaiting_write_response = False
        self.write_results: list[dict[str, Any]] = []

    @property
    def has_error(self) -> bool:
        return bool(self.last_error)

    @property
    def read_complete(self) -> bool:
        """Read phase drained with no error - safe to persist vendors/bills."""
        read_stages = {"vendor_query", "bill_query"}
        return not self.has_error and not (read_stages & set(self.pending))

    @property
    def is_complete(self) -> bool:
        """All work (read + any write) drained with no error - safe to persist."""
        return not self.pending and not self.has_error

    def current_stage(self) -> str | None:
        return self.pending[0] if self.pending else None


class QBWCSessionManager:
    """Holds active sessions and implements the five QBWC methods.

    Credentials come from the environment (QBWC_USERNAME/QBWC_PASSWORD) so secrets
    are never hard-coded. Metrics are recorded into the shared PollMetrics.
    """

    def __init__(
        self,
        metrics: PollMetrics | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        writeback: WritebackConfig | None = None,
    ) -> None:
        self.metrics = metrics or PollMetrics()
        self._username = username if username is not None else os.environ.get("QBWC_USERNAME", "")
        self._password = password if password is not None else os.environ.get("QBWC_PASSWORD", "")
        self.sessions: dict[str, QBWCSession] = {}
        # When None, the session is exactly the original READ-ONLY state machine.
        self.writeback = writeback

    # -- QBWC methods ------------------------------------------------------- #
    def authenticate(self, username: str, password: str) -> list[str]:
        """Return [ticket, fileState]. "" = use the open file; "nvu" = bad creds."""
        if not self._username or username != self._username or password != self._password:
            return ["", "nvu"]
        ticket = uuid.uuid4().hex
        self.sessions[ticket] = QBWCSession(ticket, write_enabled=self.writeback is not None)
        # "" tells QBWC to use whichever company file is currently open.
        return [ticket, ""]

    def send_request_xml(self, ticket: str, *_: Any) -> str:
        """Hand QBWC the next qbXML request, or "" when no work remains."""
        session = self.sessions.get(ticket)
        if session is None or session.has_error:
            return ""
        stage = session.current_stage()
        if stage is None:
            return ""
        self.metrics.record_poll(queue_depth=len(session.pending))
        if stage == "vendor_query":
            return qbxml.build_vendor_query()
        if stage == "bill_query":
            return qbxml.build_bill_query()
        # Write phase (only reachable when writeback is configured).
        return self._write_send(session)

    def receive_response_xml(
        self, ticket: str, response: str, hresult: str = "", message: str = ""
    ) -> int:
        """Parse QB's response into the session. Returns percent-complete (0-100),
        or a negative value to signal QBWC that the poll errored (triggers backoff).
        """
        session = self.sessions.get(ticket)
        if session is None:
            return -1
        # QBWC reports a COM HRESULT on transport failures (e.g. file locked).
        if hresult:
            session.last_error = message or f"QBWC HRESULT {hresult}"
            self.metrics.record_error(session.last_error)
            session.pending.clear()  # stop the run; nothing gets persisted
            self._teardown_write(session)
            return -1
        stage = session.current_stage()
        if stage is None:
            return 100
        if stage == _WRITE_STAGE:
            return self._write_receive(session, response)
        try:
            if stage == "vendor_query":
                session.vendors = qbxml.parse_vendors(response)
            else:
                session.bills = qbxml.parse_bills(response)
        except qbxml.QBXMLError as exc:
            session.last_error = str(exc)
            self.metrics.record_error(session.last_error)
            session.pending.clear()
            return -1
        session.pending.pop(0)
        if session.is_complete:
            self.metrics.record_success()
            return 100
        done = session.total - len(session.pending)
        return int(100 * done / session.total)

    # -- write phase (spec section 9, task 9) ------------------------------- #
    def _write_send(self, session: QBWCSession) -> str:
        """Emit the next BillAdd for the write phase, or "" when the drain is done.

        Lazily starts the write phase on first entry (opens a DB session, selects
        approved + proof-passed bills), then drives ONE bill at a time via
        ``BillWriteDriver`` (which runs ``sync_bill_to_qb`` - the proof-boundary
        re-check lives there and fires before every write). Returns the qbXML for
        the current bill's pending round-trip, or "" once every bill is finished.
        """
        from app.transport import qbwc_writeback as wb

        cfg = self.writeback
        if cfg is None:  # defensive: write stage present but no config -> no-op
            session.pending.pop(0)
            return ""

        if not session.write_started:
            session.write_started = True
            session.write_db = cfg.db_factory()
            rows = wb.select_pending_bills(
                session.write_db, limit=cfg.max_bills_per_session
            )
            session._pending_bills = list(rows)

        # Advance until we have a driver with a request to emit, or nothing left.
        # ``BillWriteDriver.next_request()`` returns the next qbXML round-trip for
        # the current bill (the first BillAdd OR a post-response retry), or None
        # when that bill is finished - so the same call both emits retries and
        # detects completion.
        while True:
            driver = session._active_driver
            if driver is None:
                if not session._pending_bills:
                    # Drain complete: close the write stage.
                    session.pending.pop(0)
                    if session.is_complete:
                        self.metrics.record_success()
                    return ""
                bill = session._pending_bills.pop(0)
                driver = wb.BillWriteDriver(
                    session.write_db,
                    bill,
                    resolver=cfg.resolver,
                    on_unresolved=cfg.on_unresolved,
                )
                session._active_driver = driver

            request = driver.next_request()
            if request is not None:
                session._awaiting_write_response = True
                return request
            # This bill finished (unresolved / session-gap / write complete /
            # terminal exception). Record its result and move to the next bill.
            self._collect_driver_result(session, driver)
            session._active_driver = None
            # loop to the next bill

    def _write_receive(self, session: QBWCSession, response: str) -> int:
        """Feed QB's BillAdd reply back into the active driver; advance the drain.

        The driver's worker resumes on ``deliver_response`` and either finishes the
        bill or queues a retry request. Either way, the NEXT ``sendRequestXML``
        (``_write_send``) calls ``next_request()`` again, which emits the retry or
        returns None (finished) - so completion/retry is handled in exactly one
        place and never here.
        """
        driver = session._active_driver
        if driver is not None and session._awaiting_write_response:
            session._awaiting_write_response = False
            driver.deliver_response(response)

        # Coarse progress signal for QBWC (write phase is the tail of the session).
        # Real completion (100) is reported by _write_send popping the write stage,
        # observed on the following send/receive; here we stay < 100 while draining.
        done_units = session.total - len(session.pending)
        return min(99, int(100 * max(done_units, 1) / session.total))

    def _collect_driver_result(self, session: QBWCSession, driver: BillWriteDriver) -> None:
        if driver.result is not None:
            session.write_results.append(driver.result)

    def _teardown_write(self, session: QBWCSession) -> None:
        session._active_driver = None

    def get_last_error(self, ticket: str) -> str:
        session = self.sessions.get(ticket)
        return session.last_error if session else ""

    def close_connection(self, ticket: str) -> str:
        self.sessions.pop(ticket, None)
        return "OK"


# --------------------------------------------------------------------------- #
# SOAP envelope handling
# --------------------------------------------------------------------------- #
def _envelope(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body>'
        f"{inner}</soap:Body></soap:Envelope>"
    )


def _string_array_response(method: str, values: list[str]) -> str:
    items = "".join(f"<string>{escape(v)}</string>" for v in values)
    return (
        f'<{method}Response xmlns="{QBWC_NS}"><{method}Result>'
        f"{items}</{method}Result></{method}Response>"
    )


def _scalar_response(method: str, value: str) -> str:
    return (
        f'<{method}Response xmlns="{QBWC_NS}">'
        f"<{method}Result>{escape(value)}</{method}Result></{method}Response>"
    )


def _parse_request(body: bytes) -> tuple[str, dict[str, str]]:
    root = ET.fromstring(body)
    soap_body = root.find(f"{{{SOAP_NS}}}Body")
    if soap_body is None or len(soap_body) == 0:
        raise ValueError("missing SOAP Body")
    method_el = list(soap_body)[0]
    method = _local(method_el.tag)
    params = {_local(child.tag): (child.text or "") for child in method_el}
    return method, params


def dispatch_soap(body: bytes, manager: QBWCSessionManager) -> str:
    """Parse a QBWC SOAP request, run the matching method, and serialise the reply."""
    method, p = _parse_request(body)
    if method == "authenticate":
        result = manager.authenticate(p.get("strUserName", ""), p.get("strPassword", ""))
        return _envelope(_string_array_response("authenticate", result))
    if method == "sendRequestXML":
        xml = manager.send_request_xml(
            p.get("ticket", ""),
            p.get("strHCPResponse", ""),
            p.get("strCompanyFileName", ""),
        )
        return _envelope(_scalar_response("sendRequestXML", xml))
    if method == "receiveResponseXML":
        pct = manager.receive_response_xml(
            p.get("ticket", ""),
            p.get("response", ""),
            p.get("hresult", ""),
            p.get("message", ""),
        )
        return _envelope(_scalar_response("receiveResponseXML", str(pct)))
    if method == "getLastError":
        return _envelope(
            _scalar_response("getLastError", manager.get_last_error(p.get("ticket", "")))
        )
    if method == "closeConnection":
        return _envelope(
            _scalar_response("closeConnection", manager.close_connection(p.get("ticket", "")))
        )
    # connectionError / clientVersion / serverVersion are optional QBWC callbacks.
    if method in ("clientVersion", "serverVersion"):
        return _envelope(_scalar_response(method, ""))
    if method == "connectionError":
        return _envelope(_scalar_response("connectionError", "done"))
    raise ValueError(f"unsupported QBWC method: {method}")
