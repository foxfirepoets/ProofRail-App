"""Canonical developer-fee split arithmetic (SPEC_SUMMA_TERRA_BINDING §5.3 / §6.4).

Pure, side-effect-free computation — NO database, NO network, NO write-back. This is the
single source of truth for the 5 / 2 / 1 split that the (future) fee engine will draft and
that the Draw-vs-Fee reconciliation verifies. Keeping it pure lets the fee rule be unit-tested
against Draw #29 without standing up the engine, and guarantees shadow-mode safety.

The load-bearing business rule (confirmed, do not "simplify"):

* The **partnership** books ONLY the 5% developer fee owed to Summa Terra.
* **Summa Terra (parent)** books the mirrored 5% as income/receivable, AND its own
  2% (Mike Watson) + 1% (Porter Christensen) commission expense/payable.
* The base for ALL THREE percentages is the approved Draw Package total.
* No commission line ever lands in a partnership book.

⚠ The 5% appears in BOTH books (partnership obligation + parent receivable) but is ONE
economic transfer. Summing all four lines double-counts it and yields a bogus 13%. The
distinct economic charge is 5% + 2% + 1% = 8%. See `distinct_economic_total` /
`naive_double_counted_sum` and the Draw #29 regression test.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Fee roles — must match app.catalog.parsers._FEE_ROLE_MAP and the fee_entries CHECK set.
ROLE_DEV_PARTNERSHIP = "dev_5_partnership"
ROLE_DEV_INCOME_PARENT = "dev_inc_5_parent"
ROLE_CEO_PARENT = "ceo_2_parent"
ROLE_PRES_PARENT = "pres_1_parent"

# Rates as exact decimals (confirmed in QB SPEC §5.3 / Chart_of_Accounts §0).
RATE_DEV = Decimal("0.05")  # 5% developer fee
RATE_CEO = Decimal("0.02")  # 2% CEO (Mike Watson) commission
RATE_PRES = Decimal("0.01")  # 1% President (Porter Christensen) commission

_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """Round a raw product to cents, half-up (the convention QB uses on memorized txns)."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FeeLine:
    """One drafted fee entry. `book` is the file it lands in; commissions are parent-only."""

    book: str  # "partnership" | "parent"
    fee_role: str
    rate: Decimal
    amount: Decimal


def split_developer_fee(package_total: Decimal) -> list[FeeLine]:
    """Return the four canonical fee lines for an approved Draw Package total.

    One partnership line (5%) + three parent lines (5% income, 2% CEO, 1% President).
    Each amount is computed off the SAME base (`package_total`) and rounded to cents.
    """
    if package_total < 0:
        raise ValueError(f"package_total must be >= 0, got {package_total}")
    dev = _money(package_total * RATE_DEV)
    return [
        FeeLine("partnership", ROLE_DEV_PARTNERSHIP, RATE_DEV, dev),
        FeeLine("parent", ROLE_DEV_INCOME_PARENT, RATE_DEV, dev),
        FeeLine("parent", ROLE_CEO_PARENT, RATE_CEO, _money(package_total * RATE_CEO)),
        FeeLine("parent", ROLE_PRES_PARENT, RATE_PRES, _money(package_total * RATE_PRES)),
    ]


def partnership_total(lines: list[FeeLine]) -> Decimal:
    """The partnership's whole obligation = the 5% only (never includes commissions)."""
    return sum((ln.amount for ln in lines if ln.book == "partnership"), Decimal("0"))


def parent_debit_total(lines: list[FeeLine]) -> Decimal:
    """Parent-side debits = 5% receivable + 2% + 1% = 8% of the base."""
    return sum((ln.amount for ln in lines if ln.book == "parent"), Decimal("0"))


def distinct_economic_total(lines: list[FeeLine]) -> Decimal:
    """The real, once-counted fee charge = 8% (the mirrored 5% counted a single time)."""
    return partnership_total(lines) + sum(
        (ln.amount for ln in lines if ln.fee_role in (ROLE_CEO_PARENT, ROLE_PRES_PARENT)),
        Decimal("0"),
    )


def naive_double_counted_sum(lines: list[FeeLine]) -> Decimal:
    """The BUG value: summing all four rows blindly (13%). Exposed so tests can assert the
    correct total differs from it — the regression guard against re-introducing the leak."""
    return sum((ln.amount for ln in lines), Decimal("0"))
