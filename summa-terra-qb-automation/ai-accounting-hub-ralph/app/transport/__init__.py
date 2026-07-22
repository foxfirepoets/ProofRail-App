"""CHUNK_2 transport layer: thin, swappable QBWC/qbXML adapter.

The canonical Postgres store is the system of record; QuickBooks Desktop is an
eventually-consistent batch sink reached ONLY via the QBWC outbound poll. This
package holds the SOAP endpoint, the qbXML codec, the stable ``AccountingAdapter``
interface (read-only ``QBDesktopAdapter``), the poll-cadence/queue-depth metric,
and the Phase 6 write-back path (gated BillAdd behind the proof boundary).
"""
from __future__ import annotations

from app.transport.adapter import AccountingAdapter, QBDesktopAdapter
from app.transport.metrics import PollMetrics
from app.transport.qbwc import QBWCSession, QBWCSessionManager, WritebackConfig
from app.transport.qbwc_resolution import (
    EntityResolutionError,
    resolve_bill_add_fields,
)
from app.transport.qbwc_writeback import (
    BillAddFields,
    BillWriteDriver,
    ProofBoundaryRefused,
    mark_bill_exception,
    select_pending_bills,
    sync_bill_to_qb,
    verify_proof_boundary,
)
from app.transport.qbxml import QBXMLError, parse_bills, parse_vendors

__all__ = [
    "AccountingAdapter",
    "QBDesktopAdapter",
    "PollMetrics",
    "QBWCSession",
    "QBWCSessionManager",
    "WritebackConfig",
    "QBXMLError",
    "parse_bills",
    "parse_vendors",
    "BillAddFields",
    "BillWriteDriver",
    "ProofBoundaryRefused",
    "mark_bill_exception",
    "select_pending_bills",
    "sync_bill_to_qb",
    "verify_proof_boundary",
    "EntityResolutionError",
    "resolve_bill_add_fields",
]
