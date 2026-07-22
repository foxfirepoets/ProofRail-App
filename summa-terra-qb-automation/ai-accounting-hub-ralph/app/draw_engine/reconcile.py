"""Three canonical reconciliation reports (binding §ops / Month_End_Checklist §B/§F).

All three are queries over draw_packages ⨝ fee_entries — always current, no batch job. Each
returns a list of per-draw row dicts with an explicit `ok` flag so a caller can render the
report and an exception engine can act on the failures.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.fee_math import (
    ROLE_CEO_PARENT,
    ROLE_DEV_INCOME_PARENT,
    ROLE_DEV_PARTNERSHIP,
    ROLE_PRES_PARENT,
)
from app.draw_engine.policy import COMMISSION_ROLES
from app.models import DrawPackage, FeeEntry

_LIVE = FeeEntry.status != "void"


def _live_entries_by_draw(session: Session, company_id: str) -> dict[str, list[FeeEntry]]:
    """All live fee entries booked into `company_id`, grouped by draw_package_id."""
    rows = session.scalars(
        select(FeeEntry).where(FeeEntry.book_company_id == company_id, _LIVE)
    ).all()
    out: dict[str, list[FeeEntry]] = {}
    for r in rows:
        out.setdefault(r.draw_package_id, []).append(r)
    return out


def _approved_draws(session: Session, company_id: str) -> list[DrawPackage]:
    return list(
        session.scalars(
            select(DrawPackage).where(
                DrawPackage.company_id == company_id,
                DrawPackage.status == "approved_for_accounting",
            )
        ).all()
    )


def partnership_draw_vs_fee(session: Session, partnership_company_id: str) -> list[dict[str, Any]]:
    """Verifies the 5% only: each approved draw has exactly one partnership 5% entry and
    zero commission entries on the partnership book."""
    booked = _live_entries_by_draw(session, partnership_company_id)
    report: list[dict[str, Any]] = []
    for draw in _approved_draws(session, partnership_company_id):
        entries = booked.get(draw.id, [])
        dev = [e for e in entries if e.fee_role == ROLE_DEV_PARTNERSHIP]
        commissions = [e for e in entries if e.fee_role in COMMISSION_ROLES]
        report.append({
            "draw_number": draw.draw_number,
            "package_total": str(draw.package_total),
            "dev_fee_count": len(dev),
            "dev_fee_amount": str(dev[0].amount) if dev else None,
            "commission_count": len(commissions),
            "ok": len(dev) == 1 and len(commissions) == 0,
        })
    return report


def parent_commission_register(session: Session, parent_company_id: str) -> list[dict[str, Any]]:
    """Verifies Mike 2% + Porter 1%: each parent-side developer-fee income has its matching
    CEO and President commission accruals."""
    booked = _live_entries_by_draw(session, parent_company_id)
    report: list[dict[str, Any]] = []
    for draw_id, entries in booked.items():
        by_role = {e.fee_role: e for e in entries}
        if ROLE_DEV_INCOME_PARENT not in by_role:
            continue  # not a fee draw on this book
        draw = session.get(DrawPackage, draw_id)
        ceo = by_role.get(ROLE_CEO_PARENT)
        pres = by_role.get(ROLE_PRES_PARENT)
        report.append({
            "draw_number": draw.draw_number if draw else draw_id,
            "dev_income_amount": str(by_role[ROLE_DEV_INCOME_PARENT].amount),
            "ceo_2pct_amount": str(ceo.amount) if ceo else None,
            "pres_1pct_amount": str(pres.amount) if pres else None,
            "ok": ceo is not None and pres is not None,
        })
    return report


def cross_book_reconciliation(
    session: Session, partnership_company_id: str, parent_company_id: str
) -> list[dict[str, Any]]:
    """Verifies all three fees exist in the correct books per Draw #, counting the mirrored
    5% only once (distinct economic charge = 8%, not the 13% double-count)."""
    part = _live_entries_by_draw(session, partnership_company_id)
    parent = _live_entries_by_draw(session, parent_company_id)
    report: list[dict[str, Any]] = []
    draw_ids = set(part) | set(parent)
    for draw_id in draw_ids:
        draw = session.get(DrawPackage, draw_id)
        p_roles = {e.fee_role: e for e in part.get(draw_id, [])}
        q_roles = {e.fee_role: e for e in parent.get(draw_id, [])}
        has_part_5 = ROLE_DEV_PARTNERSHIP in p_roles
        has_parent_5 = ROLE_DEV_INCOME_PARENT in q_roles
        has_ceo = ROLE_CEO_PARENT in q_roles
        has_pres = ROLE_PRES_PARENT in q_roles
        # no commission ever on the partnership book
        no_part_commission = not (COMMISSION_ROLES & set(p_roles))
        distinct = None
        if has_part_5 and has_ceo and has_pres:
            distinct = str(
                Decimal(str(p_roles[ROLE_DEV_PARTNERSHIP].amount))
                + Decimal(str(q_roles[ROLE_CEO_PARENT].amount))
                + Decimal(str(q_roles[ROLE_PRES_PARENT].amount))
            )
        report.append({
            "draw_number": draw.draw_number if draw else draw_id,
            "partnership_5pct": has_part_5,
            "parent_5pct_income": has_parent_5,
            "ceo_2pct": has_ceo,
            "pres_1pct": has_pres,
            "no_partnership_commission": no_part_commission,
            "distinct_economic_total_8pct": distinct,
            "ok": has_part_5 and has_parent_5 and has_ceo and has_pres and no_part_commission,
        })
    return report
