"""Approval-gated shadow draw engine (binding §5.3).

`process_draw` drafts the four fee entries (partnership 5%; parent 5% income, 2%, 1%) for an
approved draw, wires the intercompany Due-To/Due-From link, attaches a shadow proof bundle,
and snapshots the drafted total. It is idempotent on (draw_package_id, fee_role) and never
touches QuickBooks. The fee engine fires ONLY when the draw is 'approved_for_accounting' with
both the construction-manager and Mike Watson approvals recorded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.fee_math import split_developer_fee
from app.draw_engine import policy
from app.draw_engine.proofs import build_shadow_proof
from app.models import Account, Company, DrawPackage, FeeEntry, IntercompanyLink

ENGINE_TRIGGER_STATUS = "approved_for_accounting"
# Statuses that, once fees are drafted, invalidate them and demand reapproval.
INVALIDATING_STATUSES = frozenset({"revised", "rejected"})


class DrawEngineError(Exception):
    """A draw cannot be processed (missing parent, COA drift, ambiguous mapping)."""


@dataclass
class DraftResult:
    drawn_number: str
    drafted: bool
    idempotent: bool
    reason: str
    fee_entry_ids: list[str] = field(default_factory=list)
    proof_bundle_id: str | None = None
    intercompany_link_id: str | None = None
    amounts: dict[str, str] = field(default_factory=dict)


def is_fee_eligible(draw: DrawPackage) -> tuple[bool, str]:
    """Recognition trigger: approved_for_accounting AND CM + Mike Watson approvals present.

    A draw stamped ``not_for_posting`` (a historical/format fixture, CHUNK_7B) is never eligible —
    a reference document must never generate a payable, payment, or fee event.
    """
    if (draw.raw_extensions or {}).get("not_for_posting"):
        return False, "draw is flagged not_for_posting (historical fixture)"
    if draw.status != ENGINE_TRIGGER_STATUS:
        return False, f"status is {draw.status!r}, not {ENGINE_TRIGGER_STATUS!r}"
    if not draw.cm_approved:
        return False, "construction-manager approval missing"
    if not draw.watson_approved:
        return False, "Mike Watson approval missing"
    return True, "eligible"


def _resolve_parent(session: Session) -> Company:
    parents = session.scalars(select(Company).where(Company.role == "parent")).all()
    if len(parents) != 1:
        raise DrawEngineError(f"expected exactly one parent company, found {len(parents)}")
    return parents[0]


def _require_accounts(session: Session, company_id: str, numbers: set[str]) -> None:
    present = set(
        session.scalars(
            select(Account.number).where(
                Account.company_id == company_id, Account.number.in_(numbers)
            )
        )
    )
    missing = numbers - present
    if missing:
        raise DrawEngineError(
            f"COA drift: company {company_id} is missing accounts {sorted(missing)}"
        )


def _upsert_fee_entry(session: Session, draw_id: str, fee_role: str, values: dict[str, Any]) -> FeeEntry:
    existing = session.scalars(
        select(FeeEntry).where(
            FeeEntry.draw_package_id == draw_id, FeeEntry.fee_role == fee_role
        )
    ).one_or_none()
    if existing is None:
        row = FeeEntry(draw_package_id=draw_id, fee_role=fee_role, **values)
        session.add(row)
        session.flush()
        return row
    for k, v in values.items():
        setattr(existing, k, v)
    existing.status = "drafted"
    session.flush()
    return existing


def _get_or_create_link(
    session: Session, partnership_id: str, parent_id: str, draw_number: str, amount: Decimal
) -> IntercompanyLink:
    existing = session.scalars(
        select(IntercompanyLink).where(
            IntercompanyLink.partnership_company_id == partnership_id,
            IntercompanyLink.parent_company_id == parent_id,
            IntercompanyLink.source_ref == draw_number,
        )
    ).one_or_none()
    if existing is not None:
        # Numeric column round-trips Decimal at runtime (Mapped[float] is the codebase's
        # loose money annotation); keep Decimal for cent-exact money.
        existing.amount = amount  # type: ignore[assignment]
        existing.partnership_account = policy.ACCT_DUE_TO_SUMMA
        existing.parent_account = policy.ACCT_DUE_FROM_PARTNERSHIP
        session.flush()
        return existing
    link = IntercompanyLink(
        partnership_company_id=partnership_id,
        parent_company_id=parent_id,
        partnership_account=policy.ACCT_DUE_TO_SUMMA,
        parent_account=policy.ACCT_DUE_FROM_PARTNERSHIP,
        amount=amount,
        source_ref=draw_number,
    )
    session.add(link)
    session.flush()
    return link


def invalidate_drafts(session: Session, draw_package_id: str) -> int:
    """Void any non-void fee entries for a draw and clear its drafted snapshot.

    Used when a draw is revised/rejected after drafting — the old draft is invalidated and
    reapproval is required before the engine will redraft. Returns the count voided.
    """
    rows = session.scalars(
        select(FeeEntry).where(
            FeeEntry.draw_package_id == draw_package_id, FeeEntry.status != "void"
        )
    ).all()
    for r in rows:
        r.status = "void"
    draw = session.get(DrawPackage, draw_package_id)
    if draw is not None:
        draw.fee_drafted_total = None
    session.flush()
    return len(rows)


def process_draw(
    session: Session,
    draw_package_id: str,
    *,
    parent_company_id: str | None = None,
    actor: str = "draw_engine",
) -> DraftResult:
    """Draft the 5/2/1 entries for an approved draw. Idempotent; shadow-mode only.

    `parent_company_id` names the Summa Terra parent book; when omitted the engine resolves
    the single company with role='parent' (which requires exactly one to exist).
    """
    draw = session.get(DrawPackage, draw_package_id)
    if draw is None:
        raise DrawEngineError(f"draw_package {draw_package_id} not found")

    eligible, reason = is_fee_eligible(draw)
    if not eligible:
        # If a previously-drafted draw regressed to revised/rejected, void the stale draft.
        if draw.status in INVALIDATING_STATUSES:
            voided = invalidate_drafts(session, draw_package_id)
            return DraftResult(draw.draw_number, False, False, f"{reason}; voided {voided} stale draft(s)")
        return DraftResult(draw.draw_number, False, False, reason)

    partnership = session.get(Company, draw.company_id)
    if partnership is None or partnership.role != "partnership":
        raise DrawEngineError(f"draw company {draw.company_id} is not a partnership")
    if parent_company_id is not None:
        parent = session.get(Company, parent_company_id)
        if parent is None or parent.role != "parent":
            raise DrawEngineError(f"company {parent_company_id} is not a parent")
    else:
        parent = _resolve_parent(session)

    base = Decimal(str(draw.package_total))
    fee_lines = {ln.fee_role: ln for ln in split_developer_fee(base)}

    capitalize = policy.capitalize_dev_fee(partnership.expense_dev_fee, draw.expense_dev_fee_override)
    part_spec = policy.partnership_spec(capitalize)
    parent_specs = policy.parent_specs()

    # COA-drift guard: every Dr/Cr account must exist in its target book.
    _require_accounts(session, partnership.id, {part_spec.dr_account, part_spec.cr_account})
    parent_accts = {a for s in parent_specs for a in (s.dr_account, s.cr_account)}
    _require_accounts(session, parent.id, parent_accts)

    # Idempotency: if 4 live entries already exist for an unchanged total, no-op.
    live = session.scalars(
        select(FeeEntry).where(
            FeeEntry.draw_package_id == draw.id, FeeEntry.status != "void"
        )
    ).all()
    unchanged_total = draw.fee_drafted_total is not None and Decimal(str(draw.fee_drafted_total)) == base
    if len(live) == 4 and unchanged_total:
        return DraftResult(
            draw.draw_number, False, True, "already drafted; idempotent no-op",
            fee_entry_ids=[r.id for r in live],
            proof_bundle_id=next((r.proof_bundle_id for r in live if r.proof_bundle_id), None),
            intercompany_link_id=next((r.intercompany_link_id for r in live if r.intercompany_link_id), None),
            amounts={r.fee_role: str(r.amount) for r in live},
        )

    dev_amount = fee_lines[part_spec.fee_role].amount
    link = _get_or_create_link(session, partnership.id, parent.id, draw.draw_number, dev_amount)

    # Build the proof bundle over all four lines (partnership Dr resolved per policy).
    proof_lines = [(part_spec, dev_amount)] + [
        (s, fee_lines[s.fee_role].amount) for s in parent_specs
    ]
    bundle = build_shadow_proof(
        session,
        draw_package_id=draw.id,
        draw_number=draw.draw_number,
        partnership_company_id=partnership.id,
        parent_company_id=parent.id,
        source_doc_ref=draw.source_doc_ref,
        base_total=base,
        lines=proof_lines,
        actor=actor,
    )

    entry_ids: list[str] = []
    amounts: dict[str, str] = {}
    # Partnership 5% (links the Due-To leg).
    p = _upsert_fee_entry(
        session, draw.id, part_spec.fee_role,
        {
            "book_company_id": partnership.id,
            "percent": part_spec.rate,
            "amount": dev_amount,
            "dr_account": part_spec.dr_account,
            "cr_account": part_spec.cr_account,
            "intercompany_link_id": link.id,
            "proof_bundle_id": bundle.id,
        },
    )
    entry_ids.append(p.id)
    amounts[part_spec.fee_role] = str(dev_amount)
    # Parent 5% income (Due-From leg) + 2% + 1%.
    for spec in parent_specs:
        amt = fee_lines[spec.fee_role].amount
        link_id = link.id if spec.fee_role == policy.ROLE_DEV_INCOME_PARENT else None
        e = _upsert_fee_entry(
            session, draw.id, spec.fee_role,
            {
                "book_company_id": parent.id,
                "percent": spec.rate,
                "amount": amt,
                "dr_account": spec.dr_account,
                "cr_account": spec.cr_account,
                "intercompany_link_id": link_id,
                "proof_bundle_id": bundle.id,
            },
        )
        entry_ids.append(e.id)
        amounts[spec.fee_role] = str(amt)

    draw.fee_drafted_total = base  # type: ignore[assignment]
    session.flush()
    return DraftResult(
        draw.draw_number, True, False, "drafted 4 fee entries",
        fee_entry_ids=entry_ids,
        proof_bundle_id=bundle.id,
        intercompany_link_id=link.id,
        amounts=amounts,
    )
