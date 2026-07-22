"""Canonical → QuickBooks native-reference resolution for the QBWC write-back
adapter (Phase 6, spec-qbwc-writeback-adapter-2026-07-01.md §6, task 10).

Turns a canonical ``bills`` row (which references entities by canonical UUIDs and
Summa Terra codes) into the QB-native ``BillAddFields`` a BillAdd needs:

  * ``vendor_list_id``  — ``bills.vendor_id`` → ``vendors.qb_list_id``.
  * ``account_name``    — cost-code Item → posting ``accounts`` row → the QB
    ``AccountRef.FullName`` (``"{number} {name}"``, the QB Enterprise convention).
  * ``class_name``      — development-phase ``classes.name`` (from the cost code's
    ``default_class_code`` or an explicit ``raw_extensions.class_code``).
  * ``customer_job``    — project/property ``customer_jobs.path`` (from the linked
    ``draw_packages.customer_job`` for draw/fee bills, or an explicit
    ``raw_extensions.customer_job``).
  * ``draw_number``     — ``draw_packages.draw_number`` where the bill is a draw/fee
    bill, else ``raw_extensions.draw_number`` / None.

CRITICAL fail-closed contract (spec §7 "list drift" row + §9): if any *required*
reference (vendor list-id, posting account) cannot be resolved from the canonical
store, this module raises :class:`EntityResolutionError` rather than guessing.
The write stage catches it and marks the bill ``status='exception'`` so a human
reviews it — it NEVER invents a vendor/account/class/Customer:Job in QuickBooks
(list changes are a human decision, spec §7). Optional dimensions (Class,
Customer:Job, Draw #) resolve to ``None`` when genuinely absent, which is a valid
BillAdd (the qbXML builder simply omits the element) — they only hard-fail when a
code is *present but unresolvable* (a dangling reference, i.e. real drift).

DB-free-testable: every read is raw ``session.execute(text(...)).mappings()`` in
the exact style of ``qbwc_writeback.select_pending_bills`` / ``verify_proof_boundary``,
so unit tests mock the session and never need a live DB.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.draw_engine import policy
from app.transport.qbwc_writeback import BillAddFields

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Fee-role → the QB posting (Debit) account number for that fee bill (binding §5.3,
# app.draw_engine.policy). A fee bill posts its expense/CIP leg to this account:
#   dev_5_partnership → 15500/60100 (capitalize vs expense — the partnership Dr is
#     policy-dependent, so it is intentionally NOT hard-coded here; a partnership fee
#     bill must carry an explicit cost_code/account in raw_extensions),
#   ceo_2_parent      → 60200 CEO Commission Expense,
#   pres_1_parent     → 60300 President Commission Expense,
#   dev_inc_5_parent  → 40200 is the *income* Cr leg, never a payable bill Dr.
# Only the commission roles reliably become vendor BillAdds (payable to Mike/Porter);
# they are the ones with a fixed, policy-defined expense Dr account.
_FEE_ROLE_DR_ACCOUNT: dict[str, str] = {
    spec.fee_role: spec.dr_account for spec in policy.parent_specs()
}


class EntityResolutionError(Exception):
    """A required canonical → QB reference could not be resolved (fail closed).

    Carries a human-readable ``reason`` and a machine ``code`` so the write stage
    can mark the bill ``status='exception'`` with a clear, auditable cause rather
    than crash the QBWC session or — worse — guess at a QB entity (spec §7/§9).
    """

    def __init__(self, reason: str, *, code: str, bill_id: str | None = None) -> None:
        self.reason = reason
        self.code = code
        self.bill_id = bill_id
        super().__init__(reason)


def _get(bill: Any, key: str, default: Any = None) -> Any:
    if isinstance(bill, Mapping):
        return bill.get(key, default)
    return getattr(bill, key, default)


def _raw_ext(bill: Any) -> dict[str, Any]:
    raw = _get(bill, "raw_extensions") or {}
    return dict(raw) if isinstance(raw, Mapping) else {}


# --------------------------------------------------------------------------- #
# Individual resolvers — each reads canonical rows, never QuickBooks directly.
# --------------------------------------------------------------------------- #
def resolve_vendor_list_id(session: Session, bill: Any) -> str:
    """``bills.vendor_id`` → ``vendors.qb_list_id`` (required, fail closed).

    A bill with no ``vendor_id``, an unknown vendor, or a vendor that has not yet
    been ingested from QuickBooks (``qb_list_id IS NULL`` — the vendor_query never
    saw it, or it was a soft-draft vendor) cannot be posted: QuickBooks needs a
    real ``ListID`` on the ``VendorRef``. Raise rather than guess.
    """
    vendor_id = _get(bill, "vendor_id")
    if not vendor_id:
        raise EntityResolutionError(
            "bill has no vendor_id — cannot build a VendorRef",
            code="VENDOR_UNRESOLVED",
            bill_id=str(_get(bill, "id", "")),
        )
    row = (
        session.execute(
            text("SELECT qb_list_id, name FROM vendors WHERE id = :vid LIMIT 1"),
            {"vid": str(vendor_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise EntityResolutionError(
            f"vendor {vendor_id} not found in canonical store",
            code="VENDOR_UNRESOLVED",
            bill_id=str(_get(bill, "id", "")),
        )
    qb_list_id = row["qb_list_id"]
    if not qb_list_id:
        raise EntityResolutionError(
            f"vendor {row.get('name') or vendor_id} has no qb_list_id — not yet "
            "ingested from QuickBooks (run the vendor_query first) or is a "
            "soft-draft vendor; refusing to guess a VendorRef",
            code="VENDOR_NOT_IN_QB",
            bill_id=str(_get(bill, "id", "")),
        )
    return str(qb_list_id)


def _cost_code_row(session: Session, company_id: str, code: str) -> Any:
    return (
        session.execute(
            text(
                "SELECT code, maps_to_account, default_class_code "
                "FROM cost_codes WHERE company_id = :cid AND code = :code LIMIT 1"
            ),
            {"cid": str(company_id), "code": str(code)},
        )
        .mappings()
        .first()
    )


def _account_fullname(session: Session, company_id: str, number: str) -> str | None:
    row = (
        session.execute(
            text(
                "SELECT number, name FROM accounts "
                "WHERE company_id = :cid AND number = :num LIMIT 1"
            ),
            {"cid": str(company_id), "num": str(number)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    # QB Enterprise AccountRef.FullName convention: "<number> <name>".
    return f"{row['number']} {row['name']}"


def _class_name(session: Session, company_id: str, code: str) -> str | None:
    row = (
        session.execute(
            text("SELECT name FROM classes WHERE company_id = :cid AND code = :code LIMIT 1"),
            {"cid": str(company_id), "code": str(code)},
        )
        .mappings()
        .first()
    )
    return row["name"] if row is not None else None


def resolve_account_and_class(
    session: Session, bill: Any, *, account_hint: str | None = None
) -> tuple[str, str | None]:
    """Resolve the posting ``account_name`` (required) and ``class_name`` (optional).

    Resolution order for the cost code:
      1. ``account_hint`` (e.g. a fee bill's ``fee_role`` → cost-code ``code``),
      2. ``raw_extensions.cost_code`` on the bill,
    then cost_code → ``maps_to_account`` → ``accounts`` FullName, and
    ``default_class_code`` → ``classes.name``. An explicit
    ``raw_extensions.class_code`` overrides the cost code's default class.

    Fail closed if a cost code is named but not found, or resolves to an account
    number that isn't in the company's chart of accounts (that's real list drift,
    spec §7 — never post to a guessed account).
    """
    company_id = _get(bill, "company_id")
    if not company_id:
        raise EntityResolutionError(
            "bill has no company_id — cannot scope account/class resolution",
            code="ACCOUNT_UNRESOLVED",
            bill_id=str(_get(bill, "id", "")),
        )
    raw = _raw_ext(bill)
    cost_code = account_hint or raw.get("cost_code") or raw.get("item_code")

    class_name: str | None = None
    account_number: str | None = None

    # Fee bill routing (task 11): a draw/fee bill carries a ``fee_role`` in
    # raw_extensions but no cost code. A commission fee bill (CEO 2% / President 1%)
    # posts to a fixed, policy-defined expense Dr account — resolve it directly.
    # The partnership 5% (``dev_5_partnership``) is capitalization-policy-dependent
    # and the income leg (``dev_inc_5_parent``) is a Cr, never a payable Dr, so
    # neither is auto-mapped here: those must supply an explicit cost_code/account
    # (fail closed below if absent) rather than post to a guessed account.
    fee_role = raw.get("fee_role")
    if account_number is None and cost_code is None and fee_role:
        account_number = _FEE_ROLE_DR_ACCOUNT.get(str(fee_role))
        if account_number is None:
            raise EntityResolutionError(
                f"fee_role {fee_role!r} has no fixed posting account "
                "(partnership/income legs need an explicit cost_code) — "
                "refusing to guess",
                code="FEE_ROLE_UNRESOLVED",
                bill_id=str(_get(bill, "id", "")),
            )

    if cost_code:
        cc = _cost_code_row(session, str(company_id), str(cost_code))
        if cc is None:
            raise EntityResolutionError(
                f"cost code {cost_code!r} not found for company {company_id} — "
                "refusing to guess a posting account",
                code="COST_CODE_UNRESOLVED",
                bill_id=str(_get(bill, "id", "")),
            )
        account_number = cc["maps_to_account"]
        default_class_code = cc["default_class_code"]
        if default_class_code:
            class_name = _class_name(session, str(company_id), str(default_class_code))

    # An explicit class_code on the bill overrides the cost code's default class.
    explicit_class_code = raw.get("class_code")
    if explicit_class_code:
        resolved = _class_name(session, str(company_id), str(explicit_class_code))
        if resolved is None:
            raise EntityResolutionError(
                f"class code {explicit_class_code!r} not found for company {company_id}",
                code="CLASS_UNRESOLVED",
                bill_id=str(_get(bill, "id", "")),
            )
        class_name = resolved

    # A bill may also carry a direct account number/name (non-cost-code expense).
    if account_number is None:
        account_number = raw.get("account_number")

    if not account_number:
        # Last resort: a fully pre-resolved account FullName on the bill.
        pre = raw.get("account_name")
        if pre:
            return str(pre), class_name
        raise EntityResolutionError(
            "no cost code, account_number, or account_name resolvable on bill — "
            "cannot build an AccountRef",
            code="ACCOUNT_UNRESOLVED",
            bill_id=str(_get(bill, "id", "")),
        )

    full = _account_fullname(session, str(company_id), str(account_number))
    if full is None:
        raise EntityResolutionError(
            f"account {account_number} not in company {company_id} chart of accounts "
            "(list drift) — refusing to post to a guessed account",
            code="ACCOUNT_NOT_IN_COA",
            bill_id=str(_get(bill, "id", "")),
        )
    return full, class_name


def _draw_row(session: Session, draw_package_id: str) -> Any:
    return (
        session.execute(
            text(
                "SELECT draw_number, customer_job FROM draw_packages "
                "WHERE id = :did LIMIT 1"
            ),
            {"did": str(draw_package_id)},
        )
        .mappings()
        .first()
    )


def resolve_customer_job_and_draw(
    session: Session, bill: Any
) -> tuple[str | None, str | int | None]:
    """Resolve ``customer_job`` and ``draw_number`` (both optional).

    For a draw/fee bill (``bills.draw_package_id`` set), the Customer:Job path and
    Draw # come from the linked ``draw_packages`` row — the single source of truth
    for the project a draw belongs to. For a plain bill they come from
    ``raw_extensions`` (``customer_job`` / ``draw_number``) when present, else None.

    These are optional dimensions: absence is valid (the qbXML builder omits the
    element). A ``draw_package_id`` that points at a missing draw row is treated as
    drift and raised (fail closed), since a fee bill without its draw context would
    silently post to the wrong project.
    """
    raw = _raw_ext(bill)
    draw_package_id = _get(bill, "draw_package_id") or raw.get("draw_package_id")

    if draw_package_id:
        draw = _draw_row(session, str(draw_package_id))
        if draw is None:
            raise EntityResolutionError(
                f"draw_package {draw_package_id} referenced by bill not found — "
                "cannot resolve Customer:Job / Draw #",
                code="DRAW_PACKAGE_UNRESOLVED",
                bill_id=str(_get(bill, "id", "")),
            )
        return draw["customer_job"], draw["draw_number"]

    return raw.get("customer_job"), raw.get("draw_number")


def resolve_bill_add_fields(
    session: Session, bill: Any, *, account_hint: str | None = None
) -> BillAddFields:
    """Resolve a canonical bill into the QB-native ``BillAddFields`` (spec §6).

    Composes the individual resolvers. Raises :class:`EntityResolutionError`
    (fail closed) if any *required* reference (vendor list-id, posting account) is
    unresolvable — the write stage turns that into ``status='exception'`` and skips
    the write. Optional dimensions resolve to ``None`` when absent.

    ``account_hint`` lets a caller (e.g. the fee-bill router) pass the cost-code
    ``code`` derived from the bill's ``fee_role`` when the bill row itself does not
    carry a ``cost_code`` in ``raw_extensions``.
    """
    vendor_list_id = resolve_vendor_list_id(session, bill)
    account_name, class_name = resolve_account_and_class(
        session, bill, account_hint=account_hint
    )
    customer_job, draw_number = resolve_customer_job_and_draw(session, bill)
    return BillAddFields(
        vendor_list_id=vendor_list_id,
        account_name=account_name,
        class_name=class_name,
        customer_job=customer_job,
        draw_number=draw_number,
    )
