"""Multi-company read-sync tests (CHUNK_8_SCALE) — DB-free, mock adapter.

Happy path: all 10 company files sync; a cross-company search returns results from
every entity. Also covers per-file sync-lag + poll-cadence health and error backoff.
"""
from __future__ import annotations

from typing import Any

from app.scale.sync import DEFAULT_COMPANY_FILES, MultiCompanySync
from app.transport.adapter import AccountingAdapter


class MockAdapter(AccountingAdapter):
    """Returns canonical-shaped rows per company without touching a DB."""

    def __init__(self, by_company: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
        self._by_company = by_company

    def list_vendors(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        return list(self._by_company.get(company_id, {}).get("vendors", []))

    def list_bills(self, session: Any, company_id: str) -> list[dict[str, Any]]:
        return list(self._by_company.get(company_id, {}).get("bills", []))


def _ten_company_dataset() -> dict[str, dict[str, list[dict[str, Any]]]]:
    """One distinctly-named vendor + bill per file across all 10 files."""
    data: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for i, cid in enumerate(DEFAULT_COMPANY_FILES, start=1):
        data[cid] = {
            "vendors": [{"id": f"v{i}", "company_id": cid, "name": f"Acme Partner {i:02d}"}],
            "bills": [{"id": f"b{i}", "company_id": cid, "po_ref": f"PO-{i:04d}", "amount": 100 * i,
                       "status": "synced"}],
        }
    return data


class _Clock:
    """Deterministic monotonic clock: each call advances by ``step`` seconds."""

    def __init__(self, step: float = 5.0) -> None:
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def test_all_ten_files_sync_and_search_spans_every_entity():
    adapter = MockAdapter(_ten_company_dataset())
    sync = MultiCompanySync(adapter=adapter, clock=_Clock())

    states = sync.sync_all(session=None, queue_depth=2)

    # All 10 files synced.
    assert len(states) == 10
    assert all(s.last_synced is not None for s in states)
    assert all(s.vendor_count == 1 and s.bill_count == 1 for s in states)

    # Cross-company search spans EVERY entity: each company's vendor is findable.
    hits = sync.search("Acme Partner")
    companies_hit = {h["company_id"] for h in hits if h["kind"] == "vendor"}
    assert companies_hit == set(DEFAULT_COMPANY_FILES)

    # A bill PO match is namespaced by company (disambiguation across files).
    po_hits = sync.search("PO-0001")
    assert po_hits and po_hits[0]["namespaced_id"].endswith(":b1")


def test_company_health_reports_lag_and_cadence_for_all_files():
    adapter = MockAdapter(_ten_company_dataset())
    sync = MultiCompanySync(adapter=adapter, poll_interval_seconds=30.0, clock=_Clock(step=1.0))

    # Two polls per file so an observed cadence exists.
    sync.sync_all(session=None)
    sync.sync_all(session=None)

    health = sync.company_health()
    assert len(health) == 10
    for row in health:
        assert row["synced"] is True
        assert row["sync_count"] == 2
        assert row["poll_interval_seconds"] == 30.0
        assert row["sync_lag_seconds"] is not None and row["sync_lag_seconds"] >= 0.0
        assert row["observed_cadence_seconds"] is not None  # ≥2 polls → cadence known


def test_unsynced_files_report_lag_none():
    sync = MultiCompanySync(company_ids=("file-a", "file-b"))
    health = sync.company_health()
    assert [r["company_id"] for r in health] == ["file-a", "file-b"]
    assert all(r["synced"] is False and r["sync_lag_seconds"] is None for r in health)


def test_sync_error_drives_exponential_backoff():
    sync = MultiCompanySync(company_ids=("file-a",))
    first = sync.record_sync_error("file-a", "QBWC timeout")
    second = sync.record_sync_error("file-a", "QBWC timeout")
    assert first > 0.0 and second > first  # backoff grows with consecutive errors
    health = sync.company_health()[0]
    assert health["backoff_seconds"] > 0.0
    assert health["last_error"] == "QBWC timeout"
