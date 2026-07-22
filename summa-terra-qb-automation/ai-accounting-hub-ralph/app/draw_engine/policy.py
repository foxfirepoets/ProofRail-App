"""Account mapping + capitalization policy for the draw engine (binding §5.3 / COA §0).

Pure: no DB, no I/O. The canonical account numbers are fixed by the QB Chart of Accounts;
the only choice is whether the partnership's 5% is capitalized to CIP (15500) or expensed
(60100). Commissions are ALWAYS parent-only and expensed — there is no policy switch that
can move them onto a partnership book.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.catalog.fee_math import (
    RATE_CEO,
    RATE_DEV,
    RATE_PRES,
    ROLE_CEO_PARENT,
    ROLE_DEV_INCOME_PARENT,
    ROLE_DEV_PARTNERSHIP,
    ROLE_PRES_PARENT,
)

# --- Canonical account numbers (QB Summa Terra Chart_of_Accounts.md) ---
ACCT_CIP_DEV_FEE = "15500"  # CIP — Developer Fee Capitalized (partnership Dr, capitalize)
ACCT_DEV_FEE_EXPENSE = "60100"  # Developer Fee Expense (partnership Dr, expense)
ACCT_DUE_TO_SUMMA = "21000"  # Due-To Summa Terra (partnership Cr)
ACCT_DUE_FROM_PARTNERSHIP = "12200"  # Developer Fee Receivable / Due-From (parent Dr)
ACCT_DEV_FEE_INCOME = "40200"  # Developer Fee Income (parent Cr)
ACCT_CEO_COMM_EXPENSE = "60200"  # CEO Commission Expense (parent Dr)
ACCT_CEO_COMM_PAYABLE = "21100"  # Commission Payable — Mike Watson (parent Cr)
ACCT_PRES_COMM_EXPENSE = "60300"  # President Commission Expense (parent Dr)
ACCT_PRES_COMM_PAYABLE = "21200"  # Commission Payable — Porter Christensen (parent Cr)

BOOK_PARTNERSHIP = "partnership"
BOOK_PARENT = "parent"


@dataclass(frozen=True)
class RoleSpec:
    """Static placement of a fee role: which book, which Dr/Cr accounts, which rate."""

    fee_role: str
    book: str
    dr_account: str
    cr_account: str
    rate: Decimal
    is_commission: bool


# The three parent roles + the partnership role's Cr are fixed. The partnership Dr depends on
# the capitalization policy and is filled in by `partnership_dr_account`.
_PARENT_SPECS: tuple[RoleSpec, ...] = (
    RoleSpec(ROLE_DEV_INCOME_PARENT, BOOK_PARENT, ACCT_DUE_FROM_PARTNERSHIP, ACCT_DEV_FEE_INCOME, RATE_DEV, False),
    RoleSpec(ROLE_CEO_PARENT, BOOK_PARENT, ACCT_CEO_COMM_EXPENSE, ACCT_CEO_COMM_PAYABLE, RATE_CEO, True),
    RoleSpec(ROLE_PRES_PARENT, BOOK_PARENT, ACCT_PRES_COMM_EXPENSE, ACCT_PRES_COMM_PAYABLE, RATE_PRES, True),
)

# Roles that must NEVER appear in a partnership book (the structural guard).
PARENT_ONLY_ROLES = frozenset(s.fee_role for s in _PARENT_SPECS)
COMMISSION_ROLES = frozenset(s.fee_role for s in _PARENT_SPECS if s.is_commission)


def capitalize_dev_fee(company_expense_default: bool, override: bool | None) -> bool:
    """Return True if the partnership 5% should be capitalized to CIP (else expensed).

    `override` (per-draw) wins when set; otherwise the company default applies. The stored
    flags are *expense* flags, so capitalize = not expense.
    """
    expense = override if override is not None else company_expense_default
    return not expense


def partnership_dr_account(capitalize: bool) -> str:
    return ACCT_CIP_DEV_FEE if capitalize else ACCT_DEV_FEE_EXPENSE


def partnership_spec(capitalize: bool) -> RoleSpec:
    return RoleSpec(
        ROLE_DEV_PARTNERSHIP,
        BOOK_PARTNERSHIP,
        partnership_dr_account(capitalize),
        ACCT_DUE_TO_SUMMA,
        RATE_DEV,
        False,
    )


def parent_specs() -> tuple[RoleSpec, ...]:
    return _PARENT_SPECS
