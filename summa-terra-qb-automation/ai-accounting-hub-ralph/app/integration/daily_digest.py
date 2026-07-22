"""daily_digest.py -- Daily "STV Integration Health" digest email to Ben.

Spec reference: spec-stv-integration-layer-2026-06-29.md §16 ("Daily digest
email (automated, sent to Ben)"), which also backs DoD condition #10
("Daily digest email: delivered to Ben's inbox with correct content from
staging."). Alert thresholds are taken from the §16 metrics tables.

What this module does:
  - Aggregates a handful of read-only health metrics from the canonical
    store (System B, fdnwlcomuddzmluvbylg) and, when a session is supplied,
    the System A outbox table (ejxrbxoncsgglrqvjulg).
  - Renders the fixed plain-text digest template from §16, including an
    auto-generated "Action items" section driven by threshold checks.
  - Sends the digest via stdlib ``smtplib`` -- no new dependency was added
    for this feature; SMTP send is exactly what the standard library is
    for.

Must-not-break / safety notes:
  - Read-only. This module NEVER writes to bills, draw_packages, audit_rows,
    proof_bundles, or integration_outbox. It only SELECTs.
  - SMTP credentials (``settings.smtp_password``) are NEVER logged or
    printed anywhere in this module.
  - System A vs System B session separation (mirrors outbox_writer.py /
    outbox_delivery_job.py): ``_aggregate_outbox`` MUST receive a System A
    (ejxrbxoncsgglrqvjulg) session -- never System B's ``app.db.get_session``
    session. All other aggregators MUST receive a System B
    (fdnwlcomuddzmluvbylg) session. The two are never interchangeable and
    this module never opens a System A connection itself -- the caller is
    responsible for supplying (or omitting) it.
  - No Temporal workflow-listing API exists anywhere in this codebase today
    (checked app/workflow/temporal_engine.py). "Temporal: N active
    workflows, N escalated" is therefore approximated using
    bills.status='verified' as a proxy for "a Temporal workflow is blocked
    on the human approval signal" (see app/integration/approval_ui.py for
    that state transition). This is a DOCUMENTED APPROXIMATION, not an
    exact count -- see ``_aggregate_temporal_proxy`` below.
  - System A session is optional: when the caller does not have a System A
    DB handle available (e.g. System B and System A are separate Railway
    services and a live cross-service connection isn't wired up yet at
    call time), outbox stats render as an explicit "N/A -- System A
    session not provided" rather than fabricating zero counts.

Trigger mechanism (deliberately minimal -- no new scheduler framework):
  This module exposes a plain callable, ``send_daily_digest``, plus a
  ``python -m app.integration.daily_digest`` CLI entrypoint for manual /
  cron-wrapped invocation. Wiring a real recurring trigger (Railway cron,
  Temporal schedule, etc.) is an explicit follow-up -- DoD condition #10
  only requires that the email "delivered to Ben's inbox with correct
  content from staging", not that it runs on an automatic timer yet.
"""
from __future__ import annotations

import argparse
import logging
import smtplib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.chain import AuditRecord, validate_chain
from app.audit.errors import AuditChainBroken
from app.config import settings

logger = logging.getLogger(__name__)

# Alert thresholds (spec §16 metrics tables).
_OUTBOX_PENDING_THRESHOLD = 20
_EXCEPTION_QUEUE_AGE_THRESHOLD_HOURS = 24.0
_TEMPORAL_ESCALATION_THRESHOLD_HOURS = 48.0
# Phase 6 (spec-qbwc-writeback-adapter-2026-07-01.md §7/§16): business-hours,
# session-tied QBWC polling means off-hours/weekend gaps are EXPECTED, not
# errors — only escalate once a bill has sat approved-but-unsynced longer than
# a normal business gap would explain ("e.g. >3 business days", spec §7 table).
_QB_SYNC_PENDING_AGE_THRESHOLD_HOURS = 72.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class OutboxStats:
    """Counts from System A ``integration_outbox``. ``available=False`` means
    no System A session was supplied -- counts are not meaningful and must
    not be treated as zero."""

    delivered: int = 0
    pending: int = 0
    failed: int = 0
    available: bool = True


@dataclass
class BillStats:
    """Counts of bills created "today" (UTC), by status."""

    drafted: int = 0
    verified: int = 0
    approved: int = 0


@dataclass
class ExceptionQueueStats:
    """``bills.status='exception'`` IS the exception queue (no separate table)."""

    open_count: int = 0
    oldest_age_hours: float | None = None


@dataclass
class TemporalStats:
    """Approximation of Temporal workflow state via bills.status='verified'.

    See module docstring: no direct Temporal workflow-listing API exists in
    this codebase, so 'active' == count of bills awaiting the human approval
    signal, and 'escalated' == the subset of those older than 48h.
    """

    active: int = 0
    escalated: int = 0


@dataclass
class PendingQBSyncStats:
    """``bills WHERE status='approved' AND qb_txn_id IS NULL`` (Phase 6 §16).

    Approved bills waiting for the next business-hours QBWC poll session to
    drain them. A non-zero count/age here is EXPECTED during off-hours gaps
    (spec §7/§8) — only ``render_digest_text`` flags it as an action item once
    ``oldest_age_hours`` exceeds ``_QB_SYNC_PENDING_AGE_THRESHOLD_HOURS``.
    """

    count: int = 0
    oldest_age_hours: float | None = None


@dataclass
class DigestResult:
    """Everything ``send_daily_digest`` computed, for logging/testability."""

    body: str
    outbox: OutboxStats
    bills: BillStats
    exception_queue: ExceptionQueueStats
    aivs_status: str
    temporal: TemporalStats
    proof_bundle_gaps: list[str] = field(default_factory=list)
    pending_qb_sync: PendingQBSyncStats = field(default_factory=PendingQBSyncStats)


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------


def _aggregate_outbox(system_a_session: Session) -> OutboxStats:
    """Delivered / pending / failed counts from System A ``integration_outbox``.

    ``system_a_session`` MUST be a System A (ejxrbxoncsgglrqvjulg) session --
    never System B's ``app.db.get_session()`` session. Mirrors the raw
    ``text()`` query style used in outbox_delivery_job.py.
    """
    rows = (
        system_a_session.execute(
            text(
                """
                SELECT status, COUNT(*) AS n
                  FROM integration_outbox
                 GROUP BY status
                """
            )
        )
        .mappings()
        .all()
    )
    stats = OutboxStats()
    for row in rows:
        status = str(row["status"])
        count = int(row["n"])
        if status == "delivered":
            stats.delivered = count
        elif status == "pending":
            stats.pending = count
        elif status == "failed":
            stats.failed = count
    return stats


def _start_of_utc_day() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _aggregate_bills(system_b_session: Session) -> BillStats:
    """Drafted / verified / approved bill counts for "today" (UTC calendar day)."""
    rows = (
        system_b_session.execute(
            text(
                """
                SELECT status, COUNT(*) AS n
                  FROM bills
                 WHERE created_at >= :start_of_day
                 GROUP BY status
                """
            ),
            {"start_of_day": _start_of_utc_day()},
        )
        .mappings()
        .all()
    )
    stats = BillStats()
    for row in rows:
        status = str(row["status"])
        count = int(row["n"])
        if status == "drafted":
            stats.drafted = count
        elif status == "verified":
            stats.verified = count
        elif status == "approved":
            stats.approved = count
    return stats


def _aggregate_exception_queue(system_b_session: Session) -> ExceptionQueueStats:
    """Count + oldest age (hours) of ``bills.status='exception'`` rows.

    ``bills.status='exception'`` IS the exception queue -- there is no
    separate exception-queue table (confirmed in app/integration/intents_router.py).
    """
    rows = (
        system_b_session.execute(
            text(
                """
                SELECT created_at
                  FROM bills
                 WHERE status = 'exception'
                 ORDER BY created_at ASC
                """
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return ExceptionQueueStats(open_count=0, oldest_age_hours=None)

    oldest_created_at = rows[0]["created_at"]
    now = datetime.now(UTC)
    if oldest_created_at.tzinfo is None:
        oldest_created_at = oldest_created_at.replace(tzinfo=UTC)
    age_hours = (now - oldest_created_at).total_seconds() / 3600.0
    return ExceptionQueueStats(open_count=len(rows), oldest_age_hours=age_hours)


def _aggregate_aivs_chain(system_b_session: Session) -> str:
    """"VALID" or "BROKEN" -- validates the full ``audit_rows`` AIVS hash chain."""
    rows = (
        system_b_session.execute(
            text(
                """
                SELECT row_id, session_id, action_type, tool_name, actor,
                       prev_hash, row_hash, inputs_json, outputs_json
                  FROM audit_rows
                 ORDER BY row_id ASC
                """
            )
        )
        .mappings()
        .all()
    )
    records = [
        AuditRecord(
            row_id=int(row["row_id"]),
            session_id=str(row["session_id"]),
            action_type=str(row["action_type"]),
            actor=str(row["actor"]),
            prev_hash=str(row["prev_hash"]),
            row_hash=str(row["row_hash"]),
            tool_name=row.get("tool_name"),
            inputs=dict(row.get("inputs_json") or {}),
            outputs=dict(row.get("outputs_json") or {}),
        )
        for row in rows
    ]
    try:
        validate_chain(records)
    except AuditChainBroken:
        logger.error("daily_digest: AIVS chain validation FAILED -- BROKEN")
        return "BROKEN"
    return "VALID"


def _aggregate_pending_qb_sync(system_b_session: Session) -> PendingQBSyncStats:
    """Count + oldest age (hours) of ``bills`` approved but not yet synced to QB.

    Phase 6 (spec-qbwc-writeback-adapter-2026-07-01.md §16): reuses this
    module's existing aggregation pattern rather than building a new monitor.
    Matches the partial index ``idx_bills_pending_qb_sync`` (migration
    20260701_1300) exactly: ``status='approved' AND qb_txn_id IS NULL``.
    """
    rows = (
        system_b_session.execute(
            text(
                """
                SELECT created_at
                  FROM bills
                 WHERE status = 'approved'
                   AND qb_txn_id IS NULL
                 ORDER BY created_at ASC
                """
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return PendingQBSyncStats(count=0, oldest_age_hours=None)

    oldest_created_at = rows[0]["created_at"]
    now = datetime.now(UTC)
    if oldest_created_at.tzinfo is None:
        oldest_created_at = oldest_created_at.replace(tzinfo=UTC)
    age_hours = (now - oldest_created_at).total_seconds() / 3600.0
    return PendingQBSyncStats(count=len(rows), oldest_age_hours=age_hours)


def _aggregate_temporal_proxy(system_b_session: Session) -> TemporalStats:
    """Approximate 'active Temporal workflows' via bills.status='verified'.

    DOCUMENTED APPROXIMATION -- see module docstring. There is no direct
    Temporal workflow-listing API in this codebase; 'verified' is the state
    between 'drafted' and 'approved' where a Temporal workflow is blocked on
    the human approval signal (app/integration/approval_ui.py).
    """
    rows = (
        system_b_session.execute(
            text(
                """
                SELECT created_at
                  FROM bills
                 WHERE status = 'verified'
                """
            )
        )
        .mappings()
        .all()
    )
    now = datetime.now(UTC)
    escalated = 0
    for row in rows:
        created_at = row["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        age_hours = (now - created_at).total_seconds() / 3600.0
        if age_hours > _TEMPORAL_ESCALATION_THRESHOLD_HOURS:
            escalated += 1
    return TemporalStats(active=len(rows), escalated=escalated)


def _aggregate_proof_bundle_coverage(system_b_session: Session) -> list[str]:
    """bill ids for approved bills missing a passed=True proof_bundles row."""
    rows = (
        system_b_session.execute(
            text(
                """
                SELECT b.id AS bill_id
                  FROM bills b
                  LEFT JOIN proof_bundles pb ON pb.id = b.invoiceproof_bundle_id
                 WHERE b.status = 'approved'
                   AND (b.invoiceproof_bundle_id IS NULL OR pb.passed IS NOT TRUE)
                """
            )
        )
        .mappings()
        .all()
    )
    return [str(row["bill_id"]) for row in rows]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_digest_text(
    *,
    report_date: str,
    outbox: OutboxStats,
    bills: BillStats,
    exception_queue: ExceptionQueueStats,
    aivs_status: str,
    temporal: TemporalStats,
    proof_bundle_gaps: list[str],
    dashboard_ok: bool = True,
    pending_qb_sync: PendingQBSyncStats | None = None,
) -> str:
    """Build the exact plain-text digest matching spec §16's template."""
    if outbox.available:
        outbox_line = (
            f"Outbox: {outbox.delivered} delivered, {outbox.pending} pending, "
            f"{outbox.failed} failed"
        )
    else:
        outbox_line = "Outbox: N/A -- System A session not provided"

    if exception_queue.open_count > 0 and exception_queue.oldest_age_hours is not None:
        oldest_str = f"{exception_queue.oldest_age_hours:.1f}"
    else:
        oldest_str = "0"

    qb_sync = pending_qb_sync or PendingQBSyncStats()
    if qb_sync.count > 0 and qb_sync.oldest_age_hours is not None:
        qb_sync_oldest_str = f"{qb_sync.oldest_age_hours:.1f}"
    else:
        qb_sync_oldest_str = "0"

    lines: list[str] = [
        f"STV Integration Health — {report_date}",
        "=====================================",
        outbox_line,
        f"Bills today: {bills.drafted} drafted, {bills.verified} verified, "
        f"{bills.approved} approved",
        f"Exception queue: {exception_queue.open_count} open items "
        f"(oldest: {oldest_str} hours)",
        f"QB sync backlog: {qb_sync.count} approved bill(s) awaiting QuickBooks "
        f"sync (oldest: {qb_sync_oldest_str} hours)",
        f"AIVS chain: {aivs_status}",
        f"Temporal: {temporal.active} active workflows, {temporal.escalated} "
        "escalated (>48h)",
        f"Dashboard: System B section {'loading OK' if dashboard_ok else 'NOT loading'}",
        "",
        "Action items:",
    ]

    action_items: list[str] = []
    if outbox.available and outbox.failed > 0:
        action_items.append(
            f"- {outbox.failed} outbox delivery failure(s) — investigate integration_outbox"
        )
    if outbox.available and outbox.pending > _OUTBOX_PENDING_THRESHOLD:
        action_items.append(
            f"- Outbox pending backlog is {outbox.pending} (> {_OUTBOX_PENDING_THRESHOLD}) "
            "— check outbox_delivery_job"
        )
    if (
        exception_queue.oldest_age_hours is not None
        and exception_queue.oldest_age_hours > _EXCEPTION_QUEUE_AGE_THRESHOLD_HOURS
    ):
        action_items.append(
            f"- Exception queue has an item open {exception_queue.oldest_age_hours:.1f}h "
            f"(> {_EXCEPTION_QUEUE_AGE_THRESHOLD_HOURS:.0f}h) — needs human resolution"
        )
    if aivs_status == "BROKEN":
        action_items.append(
            "- P0: AIVS hash chain is BROKEN — audit_rows integrity compromised, escalate immediately"
        )
    if temporal.escalated > 0:
        action_items.append(
            f"- {temporal.escalated} approval(s) waiting >48h without a signal — escalate"
        )
    if proof_bundle_gaps:
        preview = ", ".join(proof_bundle_gaps[:5])
        more = f" (+{len(proof_bundle_gaps) - 5} more)" if len(proof_bundle_gaps) > 5 else ""
        action_items.append(
            f"- {len(proof_bundle_gaps)} approved bill(s) missing a passed proof bundle: "
            f"{preview}{more}"
        )
    if (
        qb_sync.oldest_age_hours is not None
        and qb_sync.oldest_age_hours > _QB_SYNC_PENDING_AGE_THRESHOLD_HOURS
    ):
        action_items.append(
            f"- {qb_sync.count} approved bill(s) awaiting QB sync, oldest "
            f"{qb_sync.oldest_age_hours:.1f}h (> {_QB_SYNC_PENDING_AGE_THRESHOLD_HOURS:.0f}h "
            "— longer than a normal business-hours gap explains) — check the QBWC session"
        )
    if not dashboard_ok:
        action_items.append("- Dashboard System B section is NOT loading — investigate")

    if action_items:
        lines.extend(action_items)
    else:
        lines.append("- (none — all systems nominal)")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Email send
# ---------------------------------------------------------------------------


def send_digest_email(subject: str, body: str) -> None:
    """Send the digest via stdlib smtplib. Raises loudly on missing config.

    NEVER logs settings.smtp_password. Logs a single success/failure line
    (no secrets) so operators can confirm delivery from application logs.
    """
    if not settings.smtp_host:
        raise RuntimeError(
            "SMTP_HOST is not configured — cannot send the daily digest email."
        )
    if not settings.digest_email_to:
        raise RuntimeError(
            "DIGEST_EMAIL_TO is not configured — cannot send the daily digest email."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.digest_email_from or settings.smtp_username or "noreply@localhost"
    msg["To"] = settings.digest_email_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    except Exception:
        logger.exception(
            "daily_digest: failed to send digest email to %s via %s:%s",
            settings.digest_email_to,
            settings.smtp_host,
            settings.smtp_port,
        )
        raise

    logger.info(
        "daily_digest: digest email sent to %s via %s:%s",
        settings.digest_email_to,
        settings.smtp_host,
        settings.smtp_port,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def send_daily_digest(
    system_b_session: Session,
    system_a_session: Session | None = None,
) -> str:
    """Aggregate all metrics, render the digest, and send it. Returns the body.

    ``system_b_session`` MUST be a System B (fdnwlcomuddzmluvbylg) session.
    ``system_a_session``, if provided, MUST be a System A (ejxrbxoncsgglrqvjulg)
    session -- never the same session as ``system_b_session``.
    """
    if system_a_session is not None:
        outbox = _aggregate_outbox(system_a_session)
    else:
        outbox = OutboxStats(available=False)
        logger.warning(
            "daily_digest: no System A session provided — outbox stats will "
            "render as N/A, not zero"
        )

    bills = _aggregate_bills(system_b_session)
    exception_queue = _aggregate_exception_queue(system_b_session)
    aivs_status = _aggregate_aivs_chain(system_b_session)
    temporal = _aggregate_temporal_proxy(system_b_session)
    proof_bundle_gaps = _aggregate_proof_bundle_coverage(system_b_session)
    pending_qb_sync = _aggregate_pending_qb_sync(system_b_session)

    report_date = datetime.now(UTC).strftime("%Y-%m-%d")
    body = render_digest_text(
        report_date=report_date,
        outbox=outbox,
        bills=bills,
        exception_queue=exception_queue,
        aivs_status=aivs_status,
        temporal=temporal,
        proof_bundle_gaps=proof_bundle_gaps,
        pending_qb_sync=pending_qb_sync,
    )

    subject = f"STV Integration Health — {report_date}"
    send_digest_email(subject, body)

    return body


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _cli_main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manually trigger the daily STV Integration Health digest email. "
            "No scheduler is wired up yet (see module docstring) — this is the "
            "manual / cron-wrapped invocation path."
        )
    )
    parser.add_argument(
        "--system-a-database-url",
        default=None,
        help=(
            "Optional System A (ejxrbxoncsgglrqvjulg) Postgres URL. If omitted, "
            "outbox stats render as N/A in the digest."
        ),
    )
    args = parser.parse_args()

    from app.db import get_session

    system_a_session: Session | None = None
    system_a_engine = None
    if args.system_a_database_url:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        system_a_engine = create_engine(args.system_a_database_url, future=True)
        system_a_session = sessionmaker(bind=system_a_engine, future=True)()

    gen = get_session()
    system_b_session = next(gen)
    try:
        body = send_daily_digest(system_b_session, system_a_session)
        print(body)
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
        if system_a_session is not None:
            system_a_session.close()
        if system_a_engine is not None:
            system_a_engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
