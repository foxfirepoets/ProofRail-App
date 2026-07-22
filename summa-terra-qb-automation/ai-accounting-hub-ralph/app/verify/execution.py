"""Gated qbXML write-back execution service (CHUNK_6_VERIFY).

``execute_approved_write`` is the entrypoint the workflow's autonomous-execution
step calls AFTER a human approves an intent. It enforces, in order and all
fail-closed:

1. **VerifyAPI (Gate 3)** — ``run_verifyapi`` must return VERIFIED/COMPLETE + low
   risk, carrying an ``independent_attestor_signature``. A non-VERIFIED verdict →
   ``VERIFY_NOT_READY`` (409) + route to the human queue. A ``proof_bundles`` row
   (kind='verifyapi') is written for EVERY verdict.
2. **AIVS chain (Gate 2)** — ``validate_chain`` must pass; ``AuditChainBroken``
   blocks the write (fail-closed).
3. **CoA drift pre-check** — a referenced account missing from the file →
   ``COA_DRIFT`` (422) BEFORE any qbXML is emitted (never a silent failure).
4. **Write + optimistic lock** — emit ``BillAdd`` via the adapter; on a QB
   ``EditSequence`` conflict re-read from QB, re-base the canonical record, and
   retry exactly once, else ``QB_EDIT_CONFLICT`` (409) + route to human.

On success the returned ``qb_txn_id`` / ``qb_edit_sequence`` are reconciled into
the canonical ``bills`` row (status → ``synced``) and an ``{data,error,meta}``
envelope is returned. The write is meant to run async, drained on the QBWC poll
cadence: ``writer`` IS that outbound-poll seam (request in, QB response out).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from app.audit import AuditChainBroken, AuditRecord, validate_chain, write_proof_bundle
from app.transport import qbxml
from app.transport.adapter import QBDesktopAdapter, QBXMLWriter, WriteableAccountingAdapter
from app.verify.errors import CoADrift, QBEditConflict, VerifyError, VerifyNotReady
from app.verify.verifyapi import VerifyVerdict, run_verifyapi, verdict_to_bundle

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ChainLoader = Callable[["Session", str], Sequence[AuditRecord]]
ChainValidator = Callable[[Sequence[AuditRecord]], Any]
HumanRouter = Callable[[dict[str, Any]], None]
# Re-reads the bill's current state from QB (txn id + edit sequence) for re-basing.
QBReReader = Callable[[], dict[str, Any]]

SYNCED = "synced"


def _default_load_chain(session: Session, session_id: str) -> list[AuditRecord]:
    """Load the persisted AIVS chain for a session (integration/real-DB path only)."""
    from app.audit.service import _record_from_orm
    from app.models import AuditRow

    rows = (
        session.query(AuditRow)
        .filter(AuditRow.session_id == session_id)
        .order_by(AuditRow.row_id.asc())
        .all()
    )
    return [_record_from_orm(r) for r in rows]


def _ok(data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta}


def _err(exc: VerifyError, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": None,
        "error": {
            "code": exc.code,
            "http_status": exc.http_status,
            "message": exc.message,
            "detail": exc.detail,
        },
        "meta": meta,
    }


def _bill_subject(bill: Any, *, aivs_head: str) -> dict[str, Any]:
    """Project the canonical bill into the VerifyAPI subject (deterministic)."""
    return {
        "bill_id": getattr(bill, "id", None),
        "company_id": getattr(bill, "company_id", None),
        "vendor_id": getattr(bill, "vendor_id", None),
        "amount": getattr(bill, "amount", None),
        "po_ref": getattr(bill, "po_ref", None),
        "status": getattr(bill, "status", None),
        "aivs_head": aivs_head,
    }


def _bill_payload(bill: Any) -> dict[str, Any]:
    """Adapter-facing view of the bill (decoupled from the ORM)."""
    return {"amount": getattr(bill, "amount", None), "po_ref": getattr(bill, "po_ref", None)}


def _reconcile(session: Any, bill: Any, parsed: dict[str, Any]) -> None:
    """Write QB's returned identity back into the canonical bill row."""
    bill.qb_txn_id = parsed.get("qb_txn_id")
    bill.qb_edit_sequence = parsed.get("qb_edit_sequence")
    bill.status = SYNCED
    if session is not None and hasattr(session, "flush"):
        session.flush()


def execute_approved_write(
    session: Any,
    bill: Any,
    *,
    vendor_list_id: str,
    account_name: str,
    writer: QBXMLWriter,
    aivs_head: str,
    session_id: str | None = None,
    adapter: WriteableAccountingAdapter | None = None,
    known_accounts: Sequence[str] | None = None,
    load_chain: ChainLoader = _default_load_chain,
    chain_validator: ChainValidator = validate_chain,
    re_read_bill: QBReReader | None = None,
    route_to_human: HumanRouter | None = None,
) -> dict[str, Any]:
    """Run the gated write path for ONE approved bill. Returns an envelope.

    See the module docstring for the ordered, fail-closed gate sequence. ``adapter``
    defaults to :class:`QBDesktopAdapter`; ``known_accounts`` (when provided) drives
    the pre-write CoA-drift check; ``re_read_bill`` supplies QB's fresh state for the
    single EditSequence retry; ``route_to_human`` receives a task on any gate failure.
    """
    adapter = adapter or QBDesktopAdapter()
    sid = session_id or str(getattr(bill, "id", "")) or ""
    meta: dict[str, Any] = {"bill_id": getattr(bill, "id", None), "session_id": sid}

    def _route(reason: str, code: str) -> None:
        if route_to_human is not None:
            route_to_human(
                {"bill_id": getattr(bill, "id", None), "reason": reason, "code": code}
            )

    # -- Gate 3: VerifyAPI (always write a proof bundle, advancing or not) ---- #
    verdict: VerifyVerdict = run_verifyapi(_bill_subject(bill, aivs_head=aivs_head))
    write_proof_bundle(session, verdict_to_bundle(verdict))
    meta["independent_attestor_signature"] = verdict.independent_attestor_signature
    if not verdict.advance:
        exc: VerifyError = VerifyNotReady(
            "VerifyAPI did not reach VERIFIED + low risk",
            detail={"reasons": verdict.reasons, "risk": verdict.risk},
        )
        _route(exc.message, exc.code)
        return _err(exc, meta)

    # -- Gate 2: AIVS chain must validate (fail-closed) ---------------------- #
    try:
        records = load_chain(session, sid)
        chain_validator(records)
    except AuditChainBroken as broken:
        exc = VerifyError(str(broken))
        exc.code = AuditChainBroken.code
        exc.http_status = 409
        _route(str(broken), AuditChainBroken.code)
        return _err(exc, meta)

    # -- CoA drift caught PRE-write (never a silent failure) ----------------- #
    if known_accounts is not None and account_name not in set(known_accounts):
        exc = CoADrift(
            f"account {account_name!r} is missing from the company file",
            detail={"account": account_name},
        )
        _route(exc.message, exc.code)
        return _err(exc, meta)

    # -- Write BillAdd; re-base + retry once on EditSequence conflict --------- #
    try:
        parsed = adapter.add_bill(
            writer,
            bill=_bill_payload(bill),
            vendor_list_id=vendor_list_id,
            account_name=account_name,
        )
    except qbxml.QBXMLError as first:
        if first.status_code != qbxml.EDIT_SEQUENCE_CONFLICT or re_read_bill is None:
            return _coa_or_conflict(first, _route, meta)
        # Optimistic-lock conflict: re-read from QB, re-base, retry exactly once.
        fresh = re_read_bill()
        bill.qb_txn_id = fresh.get("qb_txn_id")
        bill.qb_edit_sequence = fresh.get("qb_edit_sequence")
        meta["rebased"] = True
        try:
            parsed = adapter.add_bill(
                writer,
                bill=_bill_payload(bill),
                vendor_list_id=vendor_list_id,
                account_name=account_name,
                request_id="2",
            )
        except qbxml.QBXMLError as second:
            return _coa_or_conflict(second, _route, meta, after_retry=True)

    _reconcile(session, bill, parsed)
    meta["qb_txn_id"] = parsed.get("qb_txn_id")
    return _ok(
        {
            "bill_id": getattr(bill, "id", None),
            "status": getattr(bill, "status", None),
            "qb_txn_id": parsed.get("qb_txn_id"),
            "qb_edit_sequence": parsed.get("qb_edit_sequence"),
        },
        meta,
    )


def _coa_or_conflict(
    err: qbxml.QBXMLError,
    route: Callable[[str, str], None],
    meta: dict[str, Any],
    *,
    after_retry: bool = False,
) -> dict[str, Any]:
    """Map a terminal QB write error to a fail-closed envelope + human route."""
    if err.status_code == qbxml.ACCOUNT_NOT_FOUND:
        exc: VerifyError = CoADrift(
            f"QB rejected the write: {err.message}", detail={"qb_status": err.status_code}
        )
    elif err.status_code == qbxml.EDIT_SEQUENCE_CONFLICT:
        msg = "EditSequence conflict persisted after one retry" if after_retry else err.message
        exc = QBEditConflict(msg, detail={"qb_status": err.status_code})
    else:
        exc = VerifyError(f"QB write failed: {err.message}", detail={"qb_status": err.status_code})
        exc.http_status = 502
    route(exc.message, exc.code)
    return _err(exc, meta)
