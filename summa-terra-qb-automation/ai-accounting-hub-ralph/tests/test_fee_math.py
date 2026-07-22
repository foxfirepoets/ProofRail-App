"""Draw #29 fee-arithmetic proof (SPEC_SUMMA_TERRA_BINDING §5.3, §6.4).

Pure arithmetic — no DB, no network. Locks the 5 / 2 / 1 split, the parent-only placement of
commissions, and the anti-13%-double-count guard so the developer-fee leak cannot return.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.catalog.fee_math import (
    ROLE_CEO_PARENT,
    ROLE_DEV_INCOME_PARENT,
    ROLE_DEV_PARTNERSHIP,
    ROLE_PRES_PARENT,
    distinct_economic_total,
    naive_double_counted_sum,
    parent_debit_total,
    partnership_total,
    split_developer_fee,
)

# Real approved Draw #29 total (binding §5.3 worked example).
DRAW_29 = Decimal("962845.68")


@pytest.fixture
def lines():
    return split_developer_fee(DRAW_29)


def test_partnership_books_five_percent_only(lines):
    part = [ln for ln in lines if ln.book == "partnership"]
    assert len(part) == 1
    assert part[0].fee_role == ROLE_DEV_PARTNERSHIP
    assert part[0].amount == Decimal("48142.28")
    # The partnership's entire obligation is the 5% — nothing more.
    assert partnership_total(lines) == Decimal("48142.28")


def test_parent_books_income_and_both_commissions(lines):
    by_role = {ln.fee_role: ln for ln in lines if ln.book == "parent"}
    assert by_role[ROLE_DEV_INCOME_PARENT].amount == Decimal("48142.28")  # 5% income
    assert by_role[ROLE_CEO_PARENT].amount == Decimal("19256.91")  # 2% Mike Watson
    assert by_role[ROLE_PRES_PARENT].amount == Decimal("9628.46")  # 1% Porter Christensen


def test_partnership_has_zero_commission_entries(lines):
    part_roles = {ln.fee_role for ln in lines if ln.book == "partnership"}
    assert ROLE_CEO_PARENT not in part_roles
    assert ROLE_PRES_PARENT not in part_roles


def test_anti_double_count_13_percent_bug_is_guarded(lines):
    # Naive sum of all four rows double-counts the mirrored 5% → 13% ($125,169.93). BUG.
    assert naive_double_counted_sum(lines) == Decimal("125169.93")
    # Correct distinct economic charge counts the 5% once → 8% ($77,027.65).
    assert distinct_economic_total(lines) == Decimal("77027.65")
    # The whole point: the two must differ, or the leak has returned.
    assert naive_double_counted_sum(lines) != distinct_economic_total(lines)


def test_parent_debit_total_is_eight_percent(lines):
    # Parent-side debits = 5% receivable + 2% + 1% = 8%.
    assert parent_debit_total(lines) == Decimal("77027.65")


def test_summa_terra_net_after_commissions_is_two_percent(lines):
    by_role = {ln.fee_role: ln for ln in lines if ln.book == "parent"}
    net = (
        by_role[ROLE_DEV_INCOME_PARENT].amount
        - by_role[ROLE_CEO_PARENT].amount
        - by_role[ROLE_PRES_PARENT].amount
    )
    assert net == Decimal("19256.91")  # 5% − 2% − 1% = 2% of the draw


def test_all_three_percentages_share_the_draw_total_base(lines):
    # Each percentage is computed off the SAME approved Draw Package total.
    for ln in lines:
        assert ln.amount == (DRAW_29 * ln.rate).quantize(Decimal("0.01"))


def test_zero_draw_yields_zero_split():
    assert all(ln.amount == Decimal("0") for ln in split_developer_fee(Decimal("0")))


def test_negative_total_rejected():
    with pytest.raises(ValueError, match="must be >= 0"):
        split_developer_fee(Decimal("-1"))
