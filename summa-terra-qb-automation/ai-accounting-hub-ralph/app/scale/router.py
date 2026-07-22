"""FastAPI router for CHUNK_8_SCALE — firm-wide multi-company sync health.

Exposes a NEW read path ``GET /sync/companies`` (per-file sync lag + poll cadence for
all 10 files). It deliberately does NOT redefine CHUNK_2's ``GET /sync/health`` (the
single-poller CRUX metric) — that path stays owned by ``app.transport.router``.

This module only *defines* ``router``; per the isolation contract it must be
registered in app/main.py by the orchestrator (do not wire it here).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.scale.sync import MultiCompanySync

router = APIRouter()

# Process-wide orchestrator for the 10 company files. Real syncs run on the QBWC poll
# cadence with a live DB session; until then each file reports lag=None (never synced).
multi_sync = MultiCompanySync()


@router.get("/sync/companies")
def sync_companies() -> dict:
    """Per-file sync lag + poll cadence + queue depth for every company file."""
    health = multi_sync.company_health()
    return {
        "data": {"companies": health, "count": len(health)},
        "error": None,
        "meta": {"source": "multi_company_sync"},
    }
