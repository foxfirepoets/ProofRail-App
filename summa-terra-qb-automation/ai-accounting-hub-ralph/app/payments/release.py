"""Atomic compare-and-swap release of a payment proof bundle (no double-release).

A payment decision must be releasable EXACTLY once. Two mechanisms share one contract:

* In-process: ``ReleaseGuard`` — a thread-safe ledger used by unit tests and the
  default service wiring. The first ``release(id)`` wins; every later call returns False.
* Database: ``sql_cas_release`` — a conditional ``UPDATE ... WHERE vcap_state='PENDING'``
  whose affected-row count is the CAS result. Used on the live-DB / integration path.

Both express the same invariant: PENDING → RELEASED transitions at most once.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from app.payments.vcap import VCAP_STATE_PENDING, VCAP_STATE_RELEASED

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ReleaseGuard:
    """Thread-safe single-release ledger (in-process CAS)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._released: set[str] = set()

    def release(self, bundle_id: str) -> bool:
        """Atomically claim ``bundle_id``. Returns True for the first caller only."""
        with self._lock:
            if bundle_id in self._released:
                return False
            self._released.add(bundle_id)
            return True

    def is_released(self, bundle_id: str) -> bool:
        with self._lock:
            return bundle_id in self._released


def sql_cas_release(session: Session, bundle_id: str) -> bool:
    """Conditional UPDATE flipping PENDING→RELEASED; True iff this call did the flip.

    The ``WHERE vcap_state = PENDING`` predicate makes the swap atomic at the row
    level, so concurrent releasers see exactly one rowcount==1.
    """
    from sqlalchemy import update

    from app.models import ProofBundle

    result = session.execute(
        update(ProofBundle)
        .where(ProofBundle.id == bundle_id, ProofBundle.vcap_state == VCAP_STATE_PENDING)
        .values(vcap_state=VCAP_STATE_RELEASED)
    )
    rowcount: Any = result.rowcount
    return bool(rowcount and rowcount == 1)
