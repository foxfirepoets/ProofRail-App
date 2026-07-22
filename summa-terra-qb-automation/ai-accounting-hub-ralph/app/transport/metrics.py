"""Poll-cadence and queue-depth metric — the CRUX measurement (SPEC §4.6, §13).

QBWC is an outbound poller; the open question is whether its real-world cadence and
queue depth on the Rightworks box sustain a usable round-trip. This records both so
``GET /sync/health`` can surface a real number and drive the lag/backoff signal.
"""
from __future__ import annotations

import time
from typing import Any


class PollMetrics:
    """Records QBWC poll timestamps, observed queue depth, and error backoff.

    Pure in-memory; no DB. One instance is shared by the live router, but tests
    construct their own so measurements stay isolated.
    """

    def __init__(self, backoff_base: float = 2.0, backoff_cap: float = 300.0) -> None:
        self._poll_times: list[float] = []
        self._max_queue_depth: int = 0
        self._error_count: int = 0
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._last_error: str = ""

    def record_poll(self, queue_depth: int, now: float | None = None) -> None:
        """Record a QBWC poll (a sendRequestXML call) and the queue depth it saw."""
        self._poll_times.append(time.monotonic() if now is None else now)
        if queue_depth > self._max_queue_depth:
            self._max_queue_depth = queue_depth

    def record_error(self, message: str) -> float:
        """Record a sync error and return the next backoff delay (seconds)."""
        self._error_count += 1
        self._last_error = message
        return self.backoff_seconds()

    def record_success(self) -> None:
        """A clean round-trip clears the backoff state."""
        self._error_count = 0
        self._last_error = ""

    def backoff_seconds(self) -> float:
        """Exponential backoff: base * 2**(errors-1), capped. Zero when healthy."""
        if self._error_count == 0:
            return 0.0
        return min(self._backoff_cap, self._backoff_base * (2 ** (self._error_count - 1)))

    @property
    def poll_count(self) -> int:
        return len(self._poll_times)

    @property
    def max_queue_depth(self) -> int:
        return self._max_queue_depth

    @property
    def mean_cadence_seconds(self) -> float | None:
        """Mean wall-clock gap between consecutive polls, or None until 2 polls."""
        if len(self._poll_times) < 2:
            return None
        diffs = [b - a for a, b in zip(self._poll_times, self._poll_times[1:], strict=False)]
        return sum(diffs) / len(diffs)

    def snapshot(self) -> dict[str, Any]:
        """JSON-serialisable view powering GET /sync/health."""
        return {
            "poll_count": self.poll_count,
            "max_queue_depth": self._max_queue_depth,
            "mean_cadence_seconds": self.mean_cadence_seconds,
            "error_count": self._error_count,
            "backoff_seconds": self.backoff_seconds(),
            "last_error": self._last_error,
        }
