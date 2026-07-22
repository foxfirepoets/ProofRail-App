"""QBWC write-back adapter driver (Phase 6 — spec-qbwc-writeback-adapter-2026-07-01.md).

Drains approved, proof-gated ``bills`` rows and writes them into QuickBooks
Desktop as real ``BillAdd`` transactions. This is the ONLY code path in the
system permitted to write a BillAdd to QuickBooks (spec §9) — the money/proof
boundary crossing referenced in CLAUDE.md's "gates fail closed; never write to
books/QB without a valid proof" guardrail.

Distinct from ``app.verify.execution.execute_approved_write`` (CHUNK_6_VERIFY):
that module gates a write behind VerifyAPI (Gate 3) + the in-memory AIVS chain
for the *autonomous-execution* workflow step. This module is the QBWC-poll-
cycle-facing adapter (spec §4/§7/§9) — it re-verifies the proof boundary
DIRECTLY against the DB (``invoiceproof_bundle_id`` + ``proof_bundles.passed``
+ ``status='approved'``) rather than trusting VerifyAPI/AIVS state, because the
QBWC poll cycle runs independently of (and after) that workflow step and must
never assume an upstream caller's claim that a bill is fine.

Scope boundary (documented, not a gap in disguise — see the Phase 6 build
report): this module implements the query handler, the BillAdd qbXML request
builder, the response handler, the session-gap re-check, and the EditSequence
conflict retry-then-exception flow as clean, independently testable functions.
Wiring these into the *live* per-ticket QBWC SOAP session stage sequence
(``app.transport.qbwc.QBWCSessionManager._STAGES``, currently read-only
vendor_query/bill_query) is a follow-up integration step, not done here, to
avoid touching that already-tested state machine outside this spec's explicit
scope.

Reuses (does not rebuild):
  - ``app.audit.service.append_audit_row`` for the AIVS audit trail (Gate 2).
  - ``app.transport.qbxml.build_bill_add_writeback`` / ``parse_bill_add_response``
    for the qbXML codec (including the ``3200`` EditSequence-conflict / ``3140``
    account-not-found status codes already defined there).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.audit.service import append_audit_row
from app.transport import qbxml
from app.transport.adapter import QBXMLWriter

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

APPROVED = "approved"
QB_SYNCED = "qb_synced"
EXCEPTION = "exception"

# Session-gap re-check (spec §7): given the bill under consideration, look for
# an existing QuickBooks record (by requestID/vendor/amount match) and return
# its reconciliation fields, or None if nothing was found. Supplied by the
# caller (e.g. a BillQuery filtered by RefNumber) — never built here, since no
# real QuickBooks session exists in this environment (mocked in tests only).
ExistingRecordChecker = Callable[[Any], dict[str, Any] | None]

# Re-reads the bill's current EditSequence from QB for the single retry.
QBReReader = Callable[[], dict[str, Any]]


class ProofBoundaryRefused(Exception):
    """The defense-in-depth proof-boundary re-check (spec §9) refused a write.

    This is the single highest-stakes check in the entire QBWC write-back
    adapter. It MUST be re-verified directly against the DB immediately before
    building any BillAdd request, even though the caller (the query handler
    itself) already filtered on ``status='approved'`` — never trust an
    upstream flag. Never remove or weaken this check (spec §18 AI Agent
    Execution Contract).
    """

    def __init__(self, reason: str, *, bill_id: str | None = None) -> None:
        self.reason = reason
        self.bill_id = bill_id
        super().__init__(reason)


@dataclass(frozen=True)
class BillAddFields:
    """Resolved QB references for one BillAdd (spec §6).

    Sourced by the caller from the vendor/cost-code/Class/Customer:Job mapping
    (``SPEC_SUMMA_TERRA_BINDING.md``) — this module only consumes the already-
    resolved values, it does not do vendor/cost-code lookup itself.
    """

    vendor_list_id: str
    account_name: str
    class_name: str | None = None
    customer_job: str | None = None
    draw_number: str | int | None = None


# --------------------------------------------------------------------------- #
# bill/mapping helpers — sync_bill_to_qb works against either an ORM ``Bill``
# row (attribute access, mutated + flushed for real persistence) or a plain
# dict (used freely in unit tests without a live DB).
# --------------------------------------------------------------------------- #
def _get(bill: Any, key: str, default: Any = None) -> Any:
    if isinstance(bill, Mapping):
        return bill.get(key, default)
    return getattr(bill, key, default)


def _set(bill: Any, key: str, value: Any) -> None:
    if isinstance(bill, MutableMapping):
        bill[key] = value
    else:
        setattr(bill, key, value)


def _bill_id(bill: Any) -> str:
    return str(_get(bill, "id", ""))


# --------------------------------------------------------------------------- #
# Query handler (spec §4/§13) — the outbox-style drain query.
# --------------------------------------------------------------------------- #
def select_pending_bills(session: Session, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Select bills ready for a QBWC drain: ``status='approved' AND qb_txn_id IS NULL``.

    Raw SQL (mirrors the established pattern in intents_router.py /
    daily_digest.py) so this is trivially unit-testable against a mocked
    session (``session.execute(...).mappings().all()``) without a live DB, and
    matches the partial index ``idx_bills_pending_qb_sync`` exactly. The
    ``qb_txn_id IS NULL`` clause IS the idempotency filter (spec §7 table) — a
    bill that already has a TxnID recorded is never re-selected here.
    """
    query = (
        "SELECT id, company_id, vendor_id, amount, po_ref, status, "
        "invoiceproof_bundle_id, qb_txn_id, qb_edit_sequence, qb_sync_attempts, "
        "draw_package_id, created_at "
        "FROM bills "
        "WHERE status = 'approved' AND qb_txn_id IS NULL "
        "ORDER BY created_at ASC"
    )
    params: dict[str, Any] = {}
    if limit is not None:
        query += " LIMIT :limit"
        params["limit"] = limit
    rows = session.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# Proof-boundary re-check (spec §9) — defense in depth, never skipped.
# --------------------------------------------------------------------------- #
def verify_proof_boundary(session: Session, bill_id: str) -> None:
    """Re-verify, directly against the DB, right now, that:

      1. ``bills.status = 'approved'``, AND
      2. ``bills.invoiceproof_bundle_id IS NOT NULL``, AND
      3. the referenced ``proof_bundles.passed = True``.

    Raises :class:`ProofBoundaryRefused` (fail-closed) if any check fails.
    Called immediately before building ANY BillAdd request — never removed,
    never weakened, even though the query handler already filtered on
    ``status='approved'`` (a bill's status/proof state can change between the
    query and the write within the same poll cycle).
    """
    row = (
        session.execute(
            text(
                "SELECT id, status, invoiceproof_bundle_id FROM bills "
                "WHERE id = :bid LIMIT 1"
            ),
            {"bid": str(bill_id)},
        )
        .mappings()
        .first()
    )

    if row is None:
        raise ProofBoundaryRefused(f"bill {bill_id} not found", bill_id=str(bill_id))

    if row["status"] != APPROVED:
        raise ProofBoundaryRefused(
            f"bill {bill_id} status is {row['status']!r}, not 'approved' — refusing to write",
            bill_id=str(bill_id),
        )

    bundle_id = row["invoiceproof_bundle_id"]
    if bundle_id is None:
        raise ProofBoundaryRefused(
            f"bill {bill_id} has no invoiceproof_bundle_id — Gate 1 never ran or never linked",
            bill_id=str(bill_id),
        )

    proof_row = (
        session.execute(
            text("SELECT passed FROM proof_bundles WHERE id = :bid LIMIT 1"),
            {"bid": str(bundle_id)},
        )
        .mappings()
        .first()
    )

    if proof_row is None or not proof_row["passed"]:
        raise ProofBoundaryRefused(
            f"bill {bill_id} proof_bundles.passed is not True — Gate 1 fails closed",
            bill_id=str(bill_id),
        )


# --------------------------------------------------------------------------- #
# Envelope helpers (same {data,error,meta} shape as app.verify.execution).
# --------------------------------------------------------------------------- #
def _ok(data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta}


def _err(code: str, message: str, meta: dict[str, Any], *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": None, "error": {"code": code, "message": message, "detail": detail or {}}, "meta": meta}


# --------------------------------------------------------------------------- #
# BillAdd write + response handler
# --------------------------------------------------------------------------- #
def _write_bill_add(
    writer: QBXMLWriter, bill: Any, fields: BillAddFields, *, request_id: str
) -> dict[str, Any]:
    request = qbxml.build_bill_add_writeback(
        {"amount": _get(bill, "amount"), "po_ref": _get(bill, "po_ref")},
        vendor_list_id=fields.vendor_list_id,
        account_name=fields.account_name,
        class_name=fields.class_name,
        customer_job=fields.customer_job,
        draw_number=fields.draw_number,
        request_id=request_id,
    )
    response = writer(request)
    return qbxml.parse_bill_add_response(response)


def _reconcile_synced(session: Session, bill: Any, parsed: Mapping[str, Any]) -> None:
    """Response handler (spec §4/§18): write QB's identity back + status='qb_synced'."""
    _set(bill, "qb_txn_id", parsed.get("qb_txn_id"))
    _set(bill, "qb_edit_sequence", parsed.get("qb_edit_sequence"))
    _set(bill, "qb_synced_at", datetime.now(UTC))
    _set(bill, "status", QB_SYNCED)
    if hasattr(session, "flush"):
        session.flush()


def _mark_exception(session: Session, bill: Any) -> None:
    _set(bill, "status", EXCEPTION)
    if hasattr(session, "flush"):
        session.flush()


def mark_bill_exception(
    session: Session,
    bill: Any,
    reason: str,
    *,
    code: str = "ENTITY_UNRESOLVED",
    actor: str = "app.transport.qbwc",
) -> None:
    """Fail-closed handler for a bill that cannot be written (task 10).

    Sets ``status='exception'`` with an auditable reason and appends an AIVS row.
    Used when canonical→QB entity resolution fails (unresolved vendor/account/etc.):
    the bill is skipped, never guessed, and surfaced for human review (spec §7/§9).
    Writes the bill's row directly (raw SQL) so it works against a live DB session
    regardless of whether ``bill`` is an ORM row or a plain dict.
    """
    bill_id = _bill_id(bill)
    _set(bill, "status", EXCEPTION)
    if hasattr(session, "execute"):
        try:
            session.execute(
                text("UPDATE bills SET status = 'exception', updated_at = now() WHERE id = :bid"),
                {"bid": bill_id},
            )
        except Exception:  # noqa: BLE001 - audit still records the exception below
            pass
    append_audit_row(
        session,
        session_id=bill_id,
        action_type="qb_write_exception",
        actor=actor,
        tool_name="qbwc.entity_resolution",
        inputs={"bill_id": bill_id, "code": code},
        outputs={"code": code, "reason": reason},
    )


def sync_bill_to_qb(
    session: Session,
    bill: Any,
    *,
    writer: QBXMLWriter,
    fields: BillAddFields,
    check_existing: ExistingRecordChecker | None = None,
    re_read_bill: QBReReader | None = None,
    actor: str = "app.transport.qbwc_writeback",
) -> dict[str, Any]:
    """Drive one bill through one QBWC poll-cycle write attempt (spec §4/§7/§9).

    Order (every step fail-closed):
      1. Re-verify the proof boundary DIRECTLY against the DB
         (:func:`verify_proof_boundary` — raises :class:`ProofBoundaryRefused`,
         never caught here, so a caller cannot silently ignore a refusal).
      2. Session-gap re-check (spec §7): if ``check_existing`` finds this bill
         already posted to QB (a prior, interrupted session), reconcile the
         existing record WITHOUT resubmitting — the core idempotency edge case.
      3. Otherwise emit ``BillAdd``. On a ``3200`` EditSequence conflict,
         re-read + re-base via ``re_read_bill`` and retry exactly once; a
         second failure (of any kind) marks the bill ``'exception'`` and stops
         (no infinite loop, spec §7).

    ``qb_sync_attempts`` is incremented exactly once per call (one poll-cycle
    attempt), regardless of how many internal qbXML round-trips it takes —
    it is a staleness signal for the daily digest, not a hard retry cap
    (business-hours gaps are expected, spec §8).
    """
    bill_id = _bill_id(bill)
    meta: dict[str, Any] = {"bill_id": bill_id}

    verify_proof_boundary(session, bill_id)

    _set(bill, "qb_sync_attempts", (_get(bill, "qb_sync_attempts", 0) or 0) + 1)

    # -- Session-gap re-check: never blindly resubmit (spec §7) -------------- #
    if check_existing is not None:
        existing = check_existing(bill)
        if existing is not None:
            _reconcile_synced(session, bill, existing)
            append_audit_row(
                session,
                session_id=bill_id,
                action_type="qb_write_confirmed",
                actor=actor,
                tool_name="qbwc_writeback.sync_bill_to_qb",
                inputs={"bill_id": bill_id, "path": "session_gap_recovered"},
                outputs={
                    "qb_txn_id": existing.get("qb_txn_id"),
                    "qb_edit_sequence": existing.get("qb_edit_sequence"),
                },
            )
            meta["session_gap_recovered"] = True
            return _ok(
                {"bill_id": bill_id, "status": _get(bill, "status"), "qb_txn_id": existing.get("qb_txn_id")},
                meta,
            )

    # -- Write BillAdd; re-base + retry once on EditSequence conflict -------- #
    try:
        parsed = _write_bill_add(writer, bill, fields, request_id=bill_id)
    except qbxml.QBXMLError as first:
        if first.status_code != qbxml.EDIT_SEQUENCE_CONFLICT or re_read_bill is None:
            return _fail_exception(session, bill, first, meta, actor=actor)
        fresh = re_read_bill()
        _set(bill, "qb_edit_sequence", fresh.get("qb_edit_sequence"))
        meta["rebased"] = True
        try:
            parsed = _write_bill_add(writer, bill, fields, request_id=f"{bill_id}-retry")
        except qbxml.QBXMLError as second:
            return _fail_exception(session, bill, second, meta, actor=actor, after_retry=True)

    _reconcile_synced(session, bill, parsed)
    append_audit_row(
        session,
        session_id=bill_id,
        action_type="qb_write_confirmed",
        actor=actor,
        tool_name="qbwc_writeback.sync_bill_to_qb",
        inputs={"bill_id": bill_id, "request_id": bill_id},
        outputs={"qb_txn_id": parsed.get("qb_txn_id"), "qb_edit_sequence": parsed.get("qb_edit_sequence")},
    )
    meta["qb_txn_id"] = parsed.get("qb_txn_id")
    return _ok(
        {
            "bill_id": bill_id,
            "status": _get(bill, "status"),
            "qb_txn_id": parsed.get("qb_txn_id"),
            "qb_edit_sequence": parsed.get("qb_edit_sequence"),
        },
        meta,
    )


def _fail_exception(
    session: Session,
    bill: Any,
    err: qbxml.QBXMLError,
    meta: dict[str, Any],
    *,
    actor: str,
    after_retry: bool = False,
) -> dict[str, Any]:
    """Terminal write failure (spec §7): mark 'exception', audit, stop. No loop."""
    _mark_exception(session, bill)
    bill_id = _bill_id(bill)
    if err.status_code == qbxml.EDIT_SEQUENCE_CONFLICT:
        reason = (
            f"EditSequence conflict persisted after one retry: {err.message}"
            if after_retry
            else f"EditSequence conflict with no re_read_bill supplied - failing closed: {err.message}"
        )
        code = "QB_EDIT_CONFLICT"
    elif err.status_code == qbxml.ACCOUNT_NOT_FOUND:
        reason = f"QB rejected the write (list reference drift): {err.message}"
        code = "QB_LIST_REFERENCE_MISSING"
    else:
        reason = f"QB write failed: {err.message}"
        code = "QB_WRITE_FAILED"
    append_audit_row(
        session,
        session_id=bill_id,
        action_type="qb_write_exception",
        actor=actor,
        tool_name="qbwc_writeback.sync_bill_to_qb",
        inputs={"bill_id": bill_id, "qb_status_code": err.status_code},
        outputs={"code": code, "reason": reason},
    )
    meta["after_retry"] = after_retry
    return _err(code, reason, meta, detail={"qb_status": err.status_code})


# --------------------------------------------------------------------------- #
# Live-session write driver (spec section 4/9, task 9) - binds sync_bill_to_qb
# to the QBWC split sendRequestXML / receiveResponseXML poll cycle.
#
# QBWC never hands us a synchronous request->response call: it asks for a qbXML
# request (sendRequestXML) and delivers QuickBooks' reply on a *later* callback
# (receiveResponseXML). sync_bill_to_qb, however, calls a synchronous
# ``writer(request) -> response`` and may call it more than once (the EditSequence
# re-base retry). To reuse sync_bill_to_qb *verbatim* - never duplicating its
# proof-boundary re-check, session-gap reconciliation, or retry logic - the driver
# below runs it on a short-lived worker thread whose ``writer`` blocks on a queue.
#
# This thread is NOT a poller or an inbound listener (Guardrails): it exists only
# for the span of ONE bill's write inside ONE QBWC handshake, is fed exclusively by
# the outbound-poll SOAP callbacks, and is joined the moment the bill finishes.
# One bill is driven per poll request; the session advances to the next pending
# bill on the following poll, so a stalled / half-finished poll never half-commits
# (each bill's DB mutations flush only when sync_bill_to_qb completes it).
# --------------------------------------------------------------------------- #

# Resolves a canonical bill into BillAddFields, or raises (EntityResolutionError et
# al.) to signal "unresolved -> mark exception, skip the write" (fail closed).
# Injected by the caller so this module need not import the resolver (keeps the
# write path atomic and avoids an import cycle).
FieldsResolver = Callable[[Any], BillAddFields]

# Invoked when a bill cannot be resolved to QB refs: the live session marks it
# ``status='exception'`` with a reason and audits it. Injected so all DB writes
# stay on the session side.
UnresolvedHandler = Callable[[Any, Exception], None]

_WRITER_TIMEOUT_S = 300.0  # a poll round-trip is seconds, not minutes


class BillWriteDriver:
    """Drive ONE bill's :func:`sync_bill_to_qb` across the split QBWC poll cycle.

    Usage from the session state machine::

        driver = BillWriteDriver(db, bill, resolver=..., on_unresolved=...)
        req = driver.next_request()        # -> qbXML to hand QBWC, or None
        # ...QBWC returns a response...
        driver.deliver_response(resp_xml)  # feed QB's reply back in
        if driver.done:
            result = driver.result

    ``next_request()`` returns ``None`` (and sets ``done``) when the bill needs no
    QB round-trip - e.g. it failed entity resolution (fail closed, no write) or a
    session-gap re-check reconciled it without resubmitting. Otherwise it returns
    the BillAdd qbXML; ``deliver_response`` resumes the worker with QB's reply, and
    the NEXT ``next_request()`` emits a retry request or returns None (finished).
    """

    def __init__(
        self,
        session: Any,
        bill: Any,
        *,
        resolver: FieldsResolver,
        on_unresolved: UnresolvedHandler | None = None,
        check_existing: ExistingRecordChecker | None = None,
        re_read_bill: QBReReader | None = None,
        actor: str = "app.transport.qbwc_writeback",
    ) -> None:
        self.session = session
        self.bill = bill
        self.resolver = resolver
        self.on_unresolved = on_unresolved
        self.check_existing = check_existing
        self.re_read_bill = re_read_bill
        self.actor = actor

        self._fields: BillAddFields | None = None
        self.result: dict[str, Any] | None = None
        self.done: bool = False

        # Lazy imports: threading/queue only needed for the live driver.
        import queue

        self._req_q: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._resp_q: queue.Queue[str] = queue.Queue(maxsize=1)
        self._thread: Any | None = None
        self._sentinel = object()  # "no more requests" marker on the request queue

    # -- worker side -------------------------------------------------------- #
    def _writer(self, request: str) -> str:
        """The synchronous writer sync_bill_to_qb calls; bridges to the poll cycle."""
        self._req_q.put(request)
        return self._resp_q.get(timeout=_WRITER_TIMEOUT_S)

    def _worker(self) -> None:
        try:
            assert self._fields is not None
            result = sync_bill_to_qb(
                self.session,
                self.bill,
                writer=self._writer,
                fields=self._fields,
                check_existing=self.check_existing,
                re_read_bill=self.re_read_bill,
                actor=self.actor,
            )
        except ProofBoundaryRefused as exc:
            # Highest-stakes refusal - surface it, never swallow it.
            result = _err(
                "PROOF_BOUNDARY_REFUSED",
                exc.reason,
                {"bill_id": _bill_id(self.bill), "proof_refused": True},
            )
        except BaseException as exc:  # noqa: BLE001 - report, never hang the session
            result = _err(
                "WRITE_DRIVER_ERROR",
                f"{type(exc).__name__}: {exc}",
                {"bill_id": _bill_id(self.bill)},
            )
        self.result = result
        # Signal completion: no further requests will come from the worker.
        self._req_q.put(self._sentinel)

    # -- session side ------------------------------------------------------- #
    def next_request(self) -> str | None:
        """Return the next qbXML request for QBWC, or None if this bill is done."""
        if self.done:
            return None

        # First call: resolve entities (fail closed) then start the worker.
        if self._thread is None:
            try:
                self._fields = self.resolver(self.bill)
            except Exception as exc:  # noqa: BLE001 - fail closed on ANY resolve error
                if self.on_unresolved is not None:
                    self.on_unresolved(self.bill, exc)
                self.result = _err(
                    getattr(exc, "code", "ENTITY_UNRESOLVED"),
                    str(exc),
                    {"bill_id": _bill_id(self.bill), "unresolved": True},
                )
                self.done = True
                return None

            import threading

            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

        item = self._req_q.get(timeout=_WRITER_TIMEOUT_S)
        if item is self._sentinel:
            # Worker finished without needing (another) round-trip - e.g. a
            # session-gap re-check reconciled the bill without resubmitting.
            self._finish()
            return None
        return item  # a qbXML request string

    def deliver_response(self, response_xml: str) -> None:
        """Feed QuickBooks' reply to the suspended write and let it advance."""
        if self.done or self._thread is None:
            return
        self._resp_q.put(response_xml)

    def _finish(self) -> None:
        self.done = True
        if self._thread is not None:
            self._thread.join(timeout=_WRITER_TIMEOUT_S)
            self._thread = None
