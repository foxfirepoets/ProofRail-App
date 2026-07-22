"""Summa Terra shadow draw engine (CHUNK_6, SPEC_SUMMA_TERRA_BINDING §5.3).

Takes an approved GC draw package and drafts the 5 / 2 / 1 accounting entries into the
canonical store — partnership 5% only, parent 5% income + 2% + 1% — with proof bundles,
reconciliation reports, and an exception engine. SHADOW MODE: nothing here writes to
QuickBooks, queues a QBWC message, or moves money. Drafts land in the canonical store with
status='drafted' and never advance to a transport.
"""
from app.draw_engine.engine import (
    ENGINE_TRIGGER_STATUS,
    DraftResult,
    DrawEngineError,
    invalidate_drafts,
    is_fee_eligible,
    process_draw,
)

__all__ = [
    "ENGINE_TRIGGER_STATUS",
    "DraftResult",
    "DrawEngineError",
    "is_fee_eligible",
    "invalidate_drafts",
    "process_draw",
]
