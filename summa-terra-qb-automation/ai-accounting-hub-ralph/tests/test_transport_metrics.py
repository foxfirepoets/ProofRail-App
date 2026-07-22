"""PollMetrics tests: poll cadence, max queue depth, and error backoff (CRUX)."""
from __future__ import annotations

from app.transport.metrics import PollMetrics


def test_mean_cadence_needs_two_polls():
    m = PollMetrics()
    assert m.mean_cadence_seconds is None
    m.record_poll(queue_depth=2, now=0.0)
    assert m.mean_cadence_seconds is None


def test_cadence_and_max_queue_depth():
    m = PollMetrics()
    m.record_poll(queue_depth=2, now=0.0)
    m.record_poll(queue_depth=1, now=300.0)
    m.record_poll(queue_depth=0, now=600.0)
    assert m.poll_count == 3
    assert m.max_queue_depth == 2
    assert m.mean_cadence_seconds == 300.0


def test_backoff_grows_then_resets():
    m = PollMetrics(backoff_base=2.0)
    assert m.backoff_seconds() == 0.0
    assert m.record_error("locked") == 2.0
    assert m.record_error("locked again") == 4.0
    m.record_success()
    assert m.backoff_seconds() == 0.0


def test_backoff_is_capped():
    m = PollMetrics(backoff_base=2.0, backoff_cap=10.0)
    for _ in range(10):
        m.record_error("boom")
    assert m.backoff_seconds() == 10.0


def test_snapshot_shape():
    m = PollMetrics()
    m.record_poll(queue_depth=2, now=0.0)
    m.record_poll(queue_depth=2, now=120.0)
    snap = m.snapshot()
    assert snap["poll_count"] == 2
    assert snap["max_queue_depth"] == 2
    assert snap["mean_cadence_seconds"] == 120.0
    assert snap["backoff_seconds"] == 0.0
    assert set(snap) == {
        "poll_count",
        "max_queue_depth",
        "mean_cadence_seconds",
        "error_count",
        "backoff_seconds",
        "last_error",
    }
