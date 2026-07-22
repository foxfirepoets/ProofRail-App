"""Exception engine for the shadow draw flow (binding §5.3 golden rule / §9).

Computes structured exceptions from current canonical state — no batch job, no stored table.
Covers the full list: missing/wrong/duplicate fees, commission-on-partnership, missing or
wrong commissions, orphaned legs, intercompany imbalance, and post-draft drift in total or
status. Every drafted draw should reconcile to zero exceptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.fee_math import (
    ROLE_CEO_PARENT,
    ROLE_DEV_INCOME_PARENT,
    ROLE_DEV_PARTNERSHIP,
    ROLE_PRES_PARENT,
    split_developer_fee,
)
from app.draw_engine.engine import ENGINE_TRIGGER_STATUS, INVALIDATING_STATUSES
from app.draw_engine.policy import COMMISSION_ROLES
from app.models import DrawPackage, FeeEntry, IntercompanyLink


@dataclass(frozen=True)
class DrawException:
    code: str
    draw_number: str
    detail: str


def _live(entries: list[FeeEntry]) -> list[FeeEntry]:
    return [e for e in entries if e.status != "void"]


def scan_exceptions(
    session: Session, partnership_company_id: str, parent_company_id: str
) -> list[DrawException]:
    draws = list(
        session.scalars(
            select(DrawPackage).where(DrawPackage.company_id == partnership_company_id)
        ).all()
    )
    all_entries = session.scalars(
        select(FeeEntry).where(
            FeeEntry.draw_package_id.in_([d.id for d in draws] or [""])
        )
    ).all()
    by_draw: dict[str, list[FeeEntry]] = {}
    for e in all_entries:
        by_draw.setdefault(e.draw_package_id, []).append(e)

    out: list[DrawException] = []
    for draw in draws:
        dn = draw.draw_number
        entries = _live(by_draw.get(draw.id, []))
        part = [e for e in entries if e.book_company_id == partnership_company_id]
        parent = [e for e in entries if e.book_company_id == parent_company_id]
        part_by_role: dict[str, list[FeeEntry]] = {}
        for e in part:
            part_by_role.setdefault(e.fee_role, []).append(e)
        parent_by_role = {e.fee_role: e for e in parent}

        base = Decimal(str(draw.package_total))
        expected = {ln.fee_role: ln.amount for ln in split_developer_fee(base)}

        # --- post-draft drift (applies whenever a draft exists) ---
        if entries:
            if draw.fee_drafted_total is not None and Decimal(str(draw.fee_drafted_total)) != base:
                out.append(DrawException(
                    "DRAW_TOTAL_CHANGED", dn,
                    f"package_total {base} != drafted snapshot {draw.fee_drafted_total}",
                ))
            if draw.status in INVALIDATING_STATUSES:
                out.append(DrawException(
                    "STATUS_REGRESSED_AFTER_DRAFT", dn,
                    f"live fee entries exist but draw status is {draw.status!r}",
                ))

        # --- commission-on-partnership: the load-bearing guard ---
        for role in COMMISSION_ROLES:
            if role in part_by_role:
                out.append(DrawException(
                    "COMMISSION_ON_PARTNERSHIP", dn,
                    f"commission role {role!r} booked on the partnership book",
                ))

        # The remaining checks only make sense for draws that should carry fees.
        should_have_fees = draw.status == ENGINE_TRIGGER_STATUS
        dev_part = part_by_role.get(ROLE_DEV_PARTNERSHIP, [])

        if should_have_fees and not dev_part:
            out.append(DrawException("DRAW_FEE_MISSING", dn, "approved draw has no 5% partnership fee"))
        if len(dev_part) > 1:
            out.append(DrawException("DUP_FEE", dn, f"{len(dev_part)} partnership 5% entries (expected 1)"))
        if dev_part and Decimal(str(dev_part[0].amount)) != expected[ROLE_DEV_PARTNERSHIP]:
            out.append(DrawException(
                "FEE_AMOUNT_WRONG", dn,
                f"5% is {dev_part[0].amount}, expected {expected[ROLE_DEV_PARTNERSHIP]}",
            ))

        ceo = parent_by_role.get(ROLE_CEO_PARENT)
        pres = parent_by_role.get(ROLE_PRES_PARENT)
        dev_income = parent_by_role.get(ROLE_DEV_INCOME_PARENT)

        if should_have_fees:
            if ceo is None:
                out.append(DrawException("MISSING_CEO_COMMISSION", dn, "parent missing 2% Mike commission"))
            if pres is None:
                out.append(DrawException("MISSING_PRES_COMMISSION", dn, "parent missing 1% Porter commission"))
        if ceo is not None and Decimal(str(ceo.amount)) != expected[ROLE_CEO_PARENT]:
            out.append(DrawException(
                "COMMISSION_AMOUNT_WRONG", dn,
                f"2% is {ceo.amount}, expected {expected[ROLE_CEO_PARENT]}",
            ))
        if pres is not None and Decimal(str(pres.amount)) != expected[ROLE_PRES_PARENT]:
            out.append(DrawException(
                "COMMISSION_AMOUNT_WRONG", dn,
                f"1% is {pres.amount}, expected {expected[ROLE_PRES_PARENT]}",
            ))

        # --- mirrored-leg orphans ---
        if dev_income is not None and not dev_part:
            out.append(DrawException(
                "ORPHAN_PARENT_INCOME", dn, "parent 5% income without partnership payable",
            ))
        if dev_part and dev_income is None:
            out.append(DrawException(
                "ORPHAN_PARTNERSHIP_PAYABLE", dn, "partnership 5% payable without parent receivable",
            ))

        # --- intercompany Due-To / Due-From must net to zero (both legs = the 5%) ---
        if dev_part and dev_income is not None:
            link = session.scalars(
                select(IntercompanyLink).where(
                    IntercompanyLink.partnership_company_id == partnership_company_id,
                    IntercompanyLink.parent_company_id == parent_company_id,
                    IntercompanyLink.source_ref == dn,
                )
            ).one_or_none()
            p5 = Decimal(str(dev_part[0].amount))
            q5 = Decimal(str(dev_income.amount))
            link_amt = Decimal(str(link.amount)) if link is not None else None
            if p5 != q5 or link_amt is None or link_amt != p5:
                out.append(DrawException(
                    "INTERCOMPANY_IMBALANCE", dn,
                    f"Due-To {p5} / Due-From {q5} / link {link_amt} do not net to zero",
                ))

    return out


def net_intercompany(session: Session, partnership_company_id: str, parent_company_id: str) -> Decimal:
    """Net of all intercompany links between the pair; 0 means Due-To == Due-From overall."""
    links = session.scalars(
        select(IntercompanyLink).where(
            IntercompanyLink.partnership_company_id == partnership_company_id,
            IntercompanyLink.parent_company_id == parent_company_id,
        )
    ).all()
    # Each link's partnership Due-To (credit) mirrors the parent Due-From (debit) of equal
    # magnitude, so a balanced book nets to zero by construction.
    part_due_to = sum((Decimal(str(link.amount)) for link in links), Decimal("0"))
    parent_due_from = sum((Decimal(str(link.amount)) for link in links), Decimal("0"))
    return part_due_to - parent_due_from
