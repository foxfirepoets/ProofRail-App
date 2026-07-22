"""Unit tests for app.integration.daily_digest (spec-stv-integration-layer §16, DoD #10).

No live DB or SMTP server required — all SQLAlchemy I/O and smtplib are
mocked/patched, mirroring tests/test_outbox_writer.py's MagicMock-session
pattern.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.integration import daily_digest as dd
from app.integration.daily_digest import (
    BillStats,
    ExceptionQueueStats,
    OutboxStats,
    PendingQBSyncStats,
    TemporalStats,
    _aggregate_aivs_chain,
    _aggregate_bills,
    _aggregate_exception_queue,
    _aggregate_outbox,
    _aggregate_pending_qb_sync,
    _aggregate_proof_bundle_coverage,
    _aggregate_temporal_proxy,
    render_digest_text,
    send_daily_digest,
    send_digest_email,
)


def _mock_session() -> MagicMock:
    return MagicMock()


def _mock_rows(session: MagicMock, rows: list[dict]) -> None:
    """Configure session.execute(...).mappings().all() to return `rows`."""
    session.execute.return_value.mappings.return_value.all.return_value = rows


# ---------------------------------------------------------------------------
# _aggregate_outbox
# ---------------------------------------------------------------------------


def test_aggregate_outbox_counts():
    session = _mock_session()
    _mock_rows(
        session,
        [
            {"status": "delivered", "n": 12},
            {"status": "pending", "n": 3},
            {"status": "failed", "n": 1},
        ],
    )
    stats = _aggregate_outbox(session)
    assert stats == OutboxStats(delivered=12, pending=3, failed=1, available=True)


def test_aggregate_outbox_missing_status_defaults_zero():
    session = _mock_session()
    _mock_rows(session, [{"status": "delivered", "n": 5}])
    stats = _aggregate_outbox(session)
    assert stats.delivered == 5
    assert stats.pending == 0
    assert stats.failed == 0


# ---------------------------------------------------------------------------
# _aggregate_bills
# ---------------------------------------------------------------------------


def test_aggregate_bills_counts():
    session = _mock_session()
    _mock_rows(
        session,
        [
            {"status": "drafted", "n": 4},
            {"status": "verified", "n": 2},
            {"status": "approved", "n": 7},
        ],
    )
    stats = _aggregate_bills(session)
    assert stats == BillStats(drafted=4, verified=2, approved=7)


# ---------------------------------------------------------------------------
# _aggregate_exception_queue
# ---------------------------------------------------------------------------


def test_aggregate_exception_queue_empty():
    session = _mock_session()
    _mock_rows(session, [])
    stats = _aggregate_exception_queue(session)
    assert stats == ExceptionQueueStats(open_count=0, oldest_age_hours=None)


def test_aggregate_exception_queue_computes_oldest_age():
    session = _mock_session()
    oldest = datetime.now(UTC) - timedelta(hours=30)
    _mock_rows(session, [{"created_at": oldest}, {"created_at": datetime.now(UTC)}])
    stats = _aggregate_exception_queue(session)
    assert stats.open_count == 2
    assert stats.oldest_age_hours is not None
    assert 29.9 < stats.oldest_age_hours < 30.1


# ---------------------------------------------------------------------------
# _aggregate_aivs_chain
# ---------------------------------------------------------------------------


def test_aggregate_aivs_chain_empty_is_valid():
    session = _mock_session()
    _mock_rows(session, [])
    assert _aggregate_aivs_chain(session) == "VALID"


def test_aggregate_aivs_chain_valid_real_chain():
    from app.audit.chain import append_to_chain

    records: list = []
    append_to_chain(
        records,
        row_id=1,
        session_id="11111111-1111-1111-1111-111111111111",
        action_type="tool_call",
        actor="system",
        tool_name="draft_bill",
    )
    append_to_chain(
        records,
        row_id=2,
        session_id="11111111-1111-1111-1111-111111111111",
        action_type="tool_call",
        actor="system",
        tool_name="verify_bill",
    )
    rows = [
        {
            "row_id": r.row_id,
            "session_id": r.session_id,
            "action_type": r.action_type,
            "tool_name": r.tool_name,
            "actor": r.actor,
            "prev_hash": r.prev_hash,
            "row_hash": r.row_hash,
            "inputs_json": r.inputs,
            "outputs_json": r.outputs,
        }
        for r in records
    ]
    session = _mock_session()
    _mock_rows(session, rows)
    assert _aggregate_aivs_chain(session) == "VALID"


def test_aggregate_aivs_chain_broken_row_hash_tamper():
    from app.audit.chain import append_to_chain

    records: list = []
    append_to_chain(
        records,
        row_id=1,
        session_id="11111111-1111-1111-1111-111111111111",
        action_type="tool_call",
        actor="system",
        tool_name="draft_bill",
    )
    rows = [
        {
            "row_id": records[0].row_id,
            "session_id": records[0].session_id,
            "action_type": records[0].action_type,
            "tool_name": records[0].tool_name,
            "actor": records[0].actor,
            "prev_hash": records[0].prev_hash,
            "row_hash": "0" * 64,  # tampered
            "inputs_json": records[0].inputs,
            "outputs_json": records[0].outputs,
        }
    ]
    session = _mock_session()
    _mock_rows(session, rows)
    assert _aggregate_aivs_chain(session) == "BROKEN"


# ---------------------------------------------------------------------------
# _aggregate_temporal_proxy
# ---------------------------------------------------------------------------


def test_aggregate_temporal_proxy_no_escalation():
    session = _mock_session()
    _mock_rows(session, [{"created_at": datetime.now(UTC) - timedelta(hours=1)}])
    stats = _aggregate_temporal_proxy(session)
    assert stats == TemporalStats(active=1, escalated=0)


def test_aggregate_temporal_proxy_with_escalation():
    session = _mock_session()
    _mock_rows(
        session,
        [
            {"created_at": datetime.now(UTC) - timedelta(hours=1)},
            {"created_at": datetime.now(UTC) - timedelta(hours=50)},
        ],
    )
    stats = _aggregate_temporal_proxy(session)
    assert stats == TemporalStats(active=2, escalated=1)


# ---------------------------------------------------------------------------
# _aggregate_proof_bundle_coverage
# ---------------------------------------------------------------------------


def test_aggregate_proof_bundle_coverage_returns_gaps():
    session = _mock_session()
    _mock_rows(session, [{"bill_id": "bill-1"}, {"bill_id": "bill-2"}])
    gaps = _aggregate_proof_bundle_coverage(session)
    assert gaps == ["bill-1", "bill-2"]


def test_aggregate_proof_bundle_coverage_empty_when_all_covered():
    session = _mock_session()
    _mock_rows(session, [])
    assert _aggregate_proof_bundle_coverage(session) == []


# ---------------------------------------------------------------------------
# _aggregate_pending_qb_sync (Phase 6 — spec-qbwc-writeback-adapter-2026-07-01.md §16)
# ---------------------------------------------------------------------------


def test_aggregate_pending_qb_sync_empty():
    session = _mock_session()
    _mock_rows(session, [])
    stats = _aggregate_pending_qb_sync(session)
    assert stats == PendingQBSyncStats(count=0, oldest_age_hours=None)


def test_aggregate_pending_qb_sync_computes_oldest_age():
    session = _mock_session()
    oldest = datetime.now(UTC) - timedelta(hours=80)
    _mock_rows(session, [{"created_at": oldest}, {"created_at": datetime.now(UTC)}])
    stats = _aggregate_pending_qb_sync(session)
    assert stats.count == 2
    assert stats.oldest_age_hours is not None
    assert 79.9 < stats.oldest_age_hours < 80.1


# ---------------------------------------------------------------------------
# render_digest_text
# ---------------------------------------------------------------------------


def _all_clear_kwargs(**overrides) -> dict:
    base = dict(
        report_date="2026-07-01",
        outbox=OutboxStats(delivered=10, pending=2, failed=0),
        bills=BillStats(drafted=3, verified=1, approved=5),
        exception_queue=ExceptionQueueStats(open_count=0, oldest_age_hours=None),
        aivs_status="VALID",
        temporal=TemporalStats(active=1, escalated=0),
        proof_bundle_gaps=[],
    )
    base.update(overrides)
    return base


def test_render_digest_text_all_clear_has_no_action_items():
    body = render_digest_text(**_all_clear_kwargs())
    assert "STV Integration Health — 2026-07-01" in body
    assert "Outbox: 10 delivered, 2 pending, 0 failed" in body
    assert "Bills today: 3 drafted, 1 verified, 5 approved" in body
    assert "Exception queue: 0 open items (oldest: 0 hours)" in body
    assert "AIVS chain: VALID" in body
    assert "Temporal: 1 active workflows, 0 escalated (>48h)" in body
    assert "Dashboard: System B section loading OK" in body
    assert "Action items:" in body
    assert "(none — all systems nominal)" in body


def test_render_digest_text_outbox_pending_over_threshold_flags():
    body = render_digest_text(**_all_clear_kwargs(outbox=OutboxStats(delivered=1, pending=25, failed=0)))
    assert "Outbox pending backlog is 25" in body


def test_render_digest_text_outbox_failed_flags():
    body = render_digest_text(**_all_clear_kwargs(outbox=OutboxStats(delivered=1, pending=0, failed=3)))
    assert "3 outbox delivery failure(s)" in body


def test_render_digest_text_outbox_unavailable_renders_na():
    body = render_digest_text(**_all_clear_kwargs(outbox=OutboxStats(available=False)))
    assert "Outbox: N/A -- System A session not provided" in body
    # Unavailable outbox stats must never be silently treated as zero failures/pending.
    assert "outbox delivery failure" not in body
    assert "pending backlog" not in body


def test_render_digest_text_exception_queue_over_24h_flags():
    body = render_digest_text(
        **_all_clear_kwargs(
            exception_queue=ExceptionQueueStats(open_count=1, oldest_age_hours=30.0)
        )
    )
    assert "Exception queue has an item open 30.0h" in body


def test_render_digest_text_exception_queue_under_24h_does_not_flag():
    body = render_digest_text(
        **_all_clear_kwargs(
            exception_queue=ExceptionQueueStats(open_count=1, oldest_age_hours=5.0)
        )
    )
    assert "needs human resolution" not in body


def test_render_digest_text_aivs_broken_flags_p0():
    body = render_digest_text(**_all_clear_kwargs(aivs_status="BROKEN"))
    assert "AIVS chain: BROKEN" in body
    assert "P0: AIVS hash chain is BROKEN" in body


def test_render_digest_text_temporal_escalated_flags():
    body = render_digest_text(**_all_clear_kwargs(temporal=TemporalStats(active=5, escalated=2)))
    assert "2 approval(s) waiting >48h without a signal" in body


def test_render_digest_text_proof_bundle_gaps_flag():
    body = render_digest_text(**_all_clear_kwargs(proof_bundle_gaps=["bill-1", "bill-2"]))
    assert "2 approved bill(s) missing a passed proof bundle" in body
    assert "bill-1" in body


def test_render_digest_text_pending_qb_sync_line_renders():
    body = render_digest_text(
        **_all_clear_kwargs(pending_qb_sync=PendingQBSyncStats(count=3, oldest_age_hours=5.0))
    )
    assert "QB sync backlog: 3 approved bill(s) awaiting QuickBooks sync (oldest: 5.0 hours)" in body


def test_render_digest_text_pending_qb_sync_omitted_defaults_zero():
    """Backward compat: callers that don't pass pending_qb_sync (e.g. pre-Phase-6
    call sites/tests) render a zero backlog line rather than raising."""
    body = render_digest_text(**_all_clear_kwargs())
    assert "QB sync backlog: 0 approved bill(s)" in body


def test_render_digest_text_pending_qb_sync_under_threshold_does_not_flag():
    body = render_digest_text(
        **_all_clear_kwargs(pending_qb_sync=PendingQBSyncStats(count=2, oldest_age_hours=10.0))
    )
    assert "check the QBWC session" not in body


def test_render_digest_text_pending_qb_sync_over_threshold_flags():
    """>72h (spec §7: 'longer than a normal business-hours gap would explain')."""
    body = render_digest_text(
        **_all_clear_kwargs(pending_qb_sync=PendingQBSyncStats(count=4, oldest_age_hours=96.0))
    )
    assert "4 approved bill(s) awaiting QB sync, oldest 96.0h (> 72h" in body
    assert "check the QBWC session" in body


# ---------------------------------------------------------------------------
# send_digest_email
# ---------------------------------------------------------------------------


def test_send_digest_email_raises_when_smtp_host_missing():
    with patch.object(dd.settings, "smtp_host", ""), patch.object(
        dd.settings, "digest_email_to", "ben@example.com"
    ):
        with pytest.raises(RuntimeError, match="SMTP_HOST"):
            send_digest_email("subject", "body")


def test_send_digest_email_raises_when_recipient_missing():
    with patch.object(dd.settings, "smtp_host", "smtp.example.com"), patch.object(
        dd.settings, "digest_email_to", ""
    ):
        with pytest.raises(RuntimeError, match="DIGEST_EMAIL_TO"):
            send_digest_email("subject", "body")


def test_send_digest_email_sends_via_smtp():
    with (
        patch.object(dd.settings, "smtp_host", "smtp.example.com"),
        patch.object(dd.settings, "smtp_port", 587),
        patch.object(dd.settings, "smtp_use_tls", True),
        patch.object(dd.settings, "smtp_username", "user@example.com"),
        patch.object(dd.settings, "smtp_password", "secret"),
        patch.object(dd.settings, "digest_email_from", "digest@example.com"),
        patch.object(dd.settings, "digest_email_to", "ben@example.com"),
        patch("smtplib.SMTP") as mock_smtp_cls,
    ):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        send_digest_email("STV Integration Health — 2026-07-01", "body text here")

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "secret")
        mock_smtp.send_message.assert_called_once()
        sent_msg = mock_smtp.send_message.call_args[0][0]
        assert sent_msg["To"] == "ben@example.com"
        assert sent_msg["From"] == "digest@example.com"
        assert sent_msg["Subject"] == "STV Integration Health — 2026-07-01"
        assert "body text here" in sent_msg.get_content()


def test_send_digest_email_no_real_network_call_when_mocked():
    """Guard: patched smtplib.SMTP means no real socket is ever opened."""
    with (
        patch.object(dd.settings, "smtp_host", "smtp.example.com"),
        patch.object(dd.settings, "digest_email_to", "ben@example.com"),
        patch("smtplib.SMTP") as mock_smtp_cls,
    ):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        send_digest_email("subject", "body")
        # smtplib.SMTP itself is patched to a MagicMock class for the duration
        # of this test, so constructing it never opens a real socket.
        assert mock_smtp_cls.called
        assert isinstance(mock_smtp_cls, MagicMock)


# ---------------------------------------------------------------------------
# send_daily_digest (end-to-end wiring)
# ---------------------------------------------------------------------------


def test_send_daily_digest_wires_aggregators_and_sends():
    system_b_session = _mock_session()
    system_a_session = _mock_session()

    with (
        patch.object(dd, "_aggregate_outbox", return_value=OutboxStats(1, 2, 0)) as m_outbox,
        patch.object(dd, "_aggregate_bills", return_value=BillStats(1, 2, 3)) as m_bills,
        patch.object(
            dd, "_aggregate_exception_queue", return_value=ExceptionQueueStats(0, None)
        ) as m_exc,
        patch.object(dd, "_aggregate_aivs_chain", return_value="VALID") as m_aivs,
        patch.object(
            dd, "_aggregate_temporal_proxy", return_value=TemporalStats(1, 0)
        ) as m_temporal,
        patch.object(dd, "_aggregate_proof_bundle_coverage", return_value=[]) as m_proof,
        patch.object(
            dd, "_aggregate_pending_qb_sync", return_value=PendingQBSyncStats(0, None)
        ) as m_qb_sync,
        patch.object(dd, "send_digest_email") as m_send,
    ):
        body = send_daily_digest(system_b_session, system_a_session)

    m_outbox.assert_called_once_with(system_a_session)
    m_bills.assert_called_once_with(system_b_session)
    m_exc.assert_called_once_with(system_b_session)
    m_aivs.assert_called_once_with(system_b_session)
    m_temporal.assert_called_once_with(system_b_session)
    m_proof.assert_called_once_with(system_b_session)
    m_qb_sync.assert_called_once_with(system_b_session)

    m_send.assert_called_once()
    subject_arg, body_arg = m_send.call_args[0]
    assert "STV Integration Health" in subject_arg
    assert body_arg == body
    assert "Outbox: 1 delivered, 2 pending, 0 failed" in body
    assert "Bills today: 1 drafted, 2 verified, 3 approved" in body


def test_send_daily_digest_without_system_a_session_shows_na():
    system_b_session = _mock_session()

    with (
        patch.object(dd, "_aggregate_bills", return_value=BillStats()),
        patch.object(dd, "_aggregate_exception_queue", return_value=ExceptionQueueStats(0, None)),
        patch.object(dd, "_aggregate_aivs_chain", return_value="VALID"),
        patch.object(dd, "_aggregate_temporal_proxy", return_value=TemporalStats(0, 0)),
        patch.object(dd, "_aggregate_proof_bundle_coverage", return_value=[]),
        patch.object(dd, "_aggregate_pending_qb_sync", return_value=PendingQBSyncStats(0, None)),
        patch.object(dd, "send_digest_email") as m_send,
    ):
        body = send_daily_digest(system_b_session, system_a_session=None)

    assert "Outbox: N/A -- System A session not provided" in body
    m_send.assert_called_once()
