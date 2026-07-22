"""Multi-company read-sync orchestrator (CHUNK_8_SCALE).

Scales CHUNK_2's single-file read sync to ALL 10 company files. It re-uses the
existing :class:`app.transport.adapter.QBDesktopAdapter` (read-only against the
canonical store) — one logical poll per file — and records per-file poll cadence,
queue depth and **sync lag** so the firm-wide health is observable.

Two things fall out of syncing every file into one place:

* a unified, cross-company **search** that spans every entity (vendors + bills);
* per-file lag/cadence exposed via ``GET /sync/companies`` (this module supplies the
  snapshot; the router renders it).

GUARDRAIL: this is the 10-file Desktop wedge, NOT 1000-company operation. The scale
path beyond that is API adapters (see :class:`app.scale.qbo_adapter.QBOAdapter`).
Pure in-memory + injectable clock, so the whole flow is DB-free unit-testable.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.transport.adapter import AccountingAdapter, QBDesktopAdapter
from app.transport.metrics import PollMetrics

# The firm runs 10 QB Desktop company files (one partnership each). Logical handles —
# the real canonical ``company_id`` UUIDs are resolved at sync time from the DB.
DEFAULT_COMPANY_FILES: tuple[str, ...] = tuple(f"company-file-{i:02d}" for i in range(1, 11))

# Default QBWC outbound-poll cadence target (seconds) — the measured CRUX number.
DEFAULT_POLL_INTERVAL_SECONDS = 30.0

Clock = Callable[[], float]


@dataclass
class CompanySyncState:
    """Per-file sync bookkeeping. ``last_synced`` is monotonic; ``None`` until first sync."""

    company_id: str
    poll_interval_seconds: float
    metrics: PollMetrics
    vendor_count: int = 0
    bill_count: int = 0
    last_synced: float | None = None
    sync_count: int = 0


@dataclass
class _Entity:
    """A synced canonical row kept for cross-company search."""

    kind: str
    company_id: str
    id: str | None
    name: str
    po_ref: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class MultiCompanySync:
    """Orchestrates read sync across all company files and exposes firm-wide health."""

    def __init__(
        self,
        company_ids: Iterable[str] = DEFAULT_COMPANY_FILES,
        *,
        adapter: AccountingAdapter | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        self._adapter = adapter or QBDesktopAdapter()
        self._clock = clock
        self._states: dict[str, CompanySyncState] = {
            cid: CompanySyncState(
                company_id=cid,
                poll_interval_seconds=poll_interval_seconds,
                metrics=PollMetrics(),
            )
            for cid in company_ids
        }
        # Synced entities, namespaced by company, for the unified cross-company search.
        self._entities: list[_Entity] = []

    # -- sync ------------------------------------------------------------- #

    def sync_company(
        self, session: Any, company_id: str, *, queue_depth: int = 0
    ) -> CompanySyncState:
        """Read one company file via the adapter into the canonical view; record metrics."""
        state = self._states[company_id]
        vendors = self._adapter.list_vendors(session, company_id)
        bills = self._adapter.list_bills(session, company_id)

        state.metrics.record_poll(queue_depth, now=self._clock())
        state.metrics.record_success()
        state.vendor_count = len(vendors)
        state.bill_count = len(bills)
        state.last_synced = self._clock()
        state.sync_count += 1

        self._index_entities(company_id, vendors, bills)
        return state

    def sync_all(self, session: Any, *, queue_depth: int = 0) -> list[CompanySyncState]:
        """Read-sync every company file. Returns the per-file states."""
        return [
            self.sync_company(session, cid, queue_depth=queue_depth) for cid in self._states
        ]

    def record_sync_error(self, company_id: str, message: str) -> float:
        """Record a failed poll for a file; returns the next backoff delay (seconds)."""
        return self._states[company_id].metrics.record_error(message)

    # -- cross-company search --------------------------------------------- #

    def search(self, q: str) -> list[dict[str, Any]]:
        """Unified substring search over EVERY synced company's vendors and bills.

        DB-free analogue of ``app.canonical.service.search`` proving the synced view
        spans all entities; results are namespaced by ``company_id``.
        """
        needle = q.strip().lower()
        hits: list[dict[str, Any]] = []
        if not needle:
            return hits
        for e in self._entities:
            haystack = " ".join(filter(None, [e.name, e.po_ref or ""])).lower()
            if needle in haystack:
                hits.append(
                    {
                        "kind": e.kind,
                        "company_id": e.company_id,
                        "id": e.id,
                        "namespaced_id": f"{e.company_id}:{e.id}",
                        "name": e.name,
                        "po_ref": e.po_ref,
                    }
                )
        return hits

    # -- health (powers GET /sync/companies) ------------------------------ #

    def company_health(self) -> list[dict[str, Any]]:
        """Per-file sync lag + poll cadence + queue depth for all files."""
        now = self._clock()
        out: list[dict[str, Any]] = []
        for state in self._states.values():
            lag = None if state.last_synced is None else max(0.0, now - state.last_synced)
            snap = state.metrics.snapshot()
            out.append(
                {
                    "company_id": state.company_id,
                    "synced": state.last_synced is not None,
                    "sync_count": state.sync_count,
                    "vendor_count": state.vendor_count,
                    "bill_count": state.bill_count,
                    "sync_lag_seconds": lag,
                    "poll_interval_seconds": state.poll_interval_seconds,
                    "observed_cadence_seconds": snap["mean_cadence_seconds"],
                    "max_queue_depth": snap["max_queue_depth"],
                    "backoff_seconds": snap["backoff_seconds"],
                    "last_error": snap["last_error"],
                }
            )
        return out

    @property
    def company_ids(self) -> list[str]:
        return list(self._states)

    def _index_entities(
        self,
        company_id: str,
        vendors: list[dict[str, Any]],
        bills: list[dict[str, Any]],
    ) -> None:
        """Replace this company's slice of the searchable index with the freshest read."""
        self._entities = [e for e in self._entities if e.company_id != company_id]
        for v in vendors:
            self._entities.append(
                _Entity("vendor", company_id, v.get("id"), str(v.get("name") or ""))
            )
        for b in bills:
            self._entities.append(
                _Entity(
                    "bill",
                    company_id,
                    b.get("id"),
                    str(b.get("po_ref") or ""),
                    po_ref=b.get("po_ref"),
                    extra={"amount": b.get("amount"), "status": b.get("status")},
                )
            )
