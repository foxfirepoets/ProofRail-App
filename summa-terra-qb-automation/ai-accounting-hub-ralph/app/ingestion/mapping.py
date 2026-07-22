"""Map parsed draw lines to canonical cost codes + vendors (CHUNK_7).

Item # → Summa Terra cost code (catalog 001-069). Payee → known vendor by normalized name;
unmatched payees are queued as vendor_candidates (never auto-created as vendors). DB reads +
candidate upserts only; no QuickBooks writes.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.normalize import normalize_name
from app.models import CostCode, Vendor, VendorCandidate


@dataclass
class MappingResult:
    cost_code_hits: int = 0
    cost_code_misses: list[str] = None  # type: ignore[assignment]
    vendor_hits: int = 0
    vendor_candidates_queued: int = 0
    unmatched_payees: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.cost_code_misses = self.cost_code_misses or []
        self.unmatched_payees = self.unmatched_payees or []


def _cost_code_index(session: Session, company_id: str) -> dict[str, str]:
    rows = session.execute(
        select(CostCode.code, CostCode.id).where(CostCode.company_id == company_id)
    ).all()
    return {code: cid for code, cid in rows}


def _vendor_index(session: Session, company_id: str) -> dict[str, str]:
    rows = session.execute(
        select(Vendor.name, Vendor.id).where(Vendor.company_id == company_id)
    ).all()
    return {normalize_name(name): vid for name, vid in rows}


def map_draw_lines(session: Session, company_id: str, lines: list) -> MappingResult:
    """Resolve each line's cost_code_id + vendor_id in place; queue unmatched payees."""
    cc_idx = _cost_code_index(session, company_id)
    v_idx = _vendor_index(session, company_id)
    result = MappingResult()
    queued: set[str] = set()
    for ln in lines:
        if ln.item_code:
            cid = cc_idx.get(ln.item_code)
            if cid:
                ln.cost_code_id = cid
                result.cost_code_hits += 1
            else:
                result.cost_code_misses.append(ln.item_code)
                ln.needs_review = True
                ln.review_reasons.append(f"item {ln.item_code} not a known cost code")
        if ln.payable_to:
            norm = normalize_name(ln.payable_to)
            vid = v_idx.get(norm)
            if vid:
                ln.vendor_id = vid
                result.vendor_hits += 1
            else:
                result.unmatched_payees.append(ln.payable_to)
                if norm and norm not in queued:
                    queued.add(norm)
                    _queue_candidate(session, company_id, ln.payable_to, norm)
                    result.vendor_candidates_queued += 1
    session.flush()
    return result


def _queue_candidate(session: Session, company_id: str, name: str, norm: str) -> None:
    existing = session.scalars(
        select(VendorCandidate).where(
            VendorCandidate.company_id == company_id,
            VendorCandidate.normalized_name == norm,
        )
    ).one_or_none()
    if existing is None:
        session.add(VendorCandidate(
            company_id=company_id, name=name[:255], normalized_name=norm[:255], status="candidate"
        ))
