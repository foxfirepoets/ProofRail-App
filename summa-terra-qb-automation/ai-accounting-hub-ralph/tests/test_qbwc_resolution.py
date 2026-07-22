"""Canonical -> QuickBooks entity-resolution tests (Phase 6, task 10/11).

DB-free: the SQLAlchemy session is mocked, branching on the query text exactly
like tests/test_qbwc_writeback.py. Proves that resolve_bill_add_fields turns a
canonical bill into the right QB-native BillAddFields, and - critically - that an
UNRESOLVABLE required reference fails CLOSED (raises EntityResolutionError) rather
than guessing a vendor/account (spec section 7 list-drift / section 9 fail-closed).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.transport.qbwc_resolution import (
    EntityResolutionError,
    resolve_account_and_class,
    resolve_bill_add_fields,
    resolve_customer_job_and_draw,
    resolve_vendor_list_id,
)


def _session(rows: dict) -> MagicMock:
    """A MagicMock session whose execute() returns the staged row per table."""
    session = MagicMock()

    def _execute(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM vendors" in sql:
            result.mappings.return_value.first.return_value = rows.get("vendor")
        elif "FROM cost_codes" in sql:
            result.mappings.return_value.first.return_value = rows.get("cost_code")
        elif "FROM accounts" in sql:
            result.mappings.return_value.first.return_value = rows.get("account")
        elif "FROM classes" in sql:
            result.mappings.return_value.first.return_value = rows.get("class")
        elif "FROM draw_packages" in sql:
            result.mappings.return_value.first.return_value = rows.get("draw")
        else:
            raise AssertionError(f"unexpected query: {sql}")
        return result

    session.execute.side_effect = _execute
    return session


def _bill(**overrides) -> dict:
    base = {
        "id": "b1",
        "vendor_id": "v1",
        "company_id": "c1",
        "draw_package_id": None,
        "raw_extensions": {},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Vendor resolution
# --------------------------------------------------------------------------- #
def test_resolve_vendor_list_id_happy():
    session = _session({"vendor": {"qb_list_id": "80000001-1", "name": "GC"}})
    assert resolve_vendor_list_id(session, _bill()) == "80000001-1"


def test_resolve_vendor_no_vendor_id_fails_closed():
    with pytest.raises(EntityResolutionError, match="no vendor_id"):
        resolve_vendor_list_id(_session({}), _bill(vendor_id=None))


def test_resolve_vendor_not_found_fails_closed():
    session = _session({"vendor": None})
    with pytest.raises(EntityResolutionError) as exc:
        resolve_vendor_list_id(session, _bill())
    assert exc.value.code == "VENDOR_UNRESOLVED"


def test_resolve_vendor_without_qb_list_id_fails_closed_never_guesses():
    """A soft-draft / not-yet-ingested vendor has no ListID: refuse, never guess."""
    session = _session({"vendor": {"qb_list_id": None, "name": "SoftDraft LLC"}})
    with pytest.raises(EntityResolutionError) as exc:
        resolve_vendor_list_id(session, _bill())
    assert exc.value.code == "VENDOR_NOT_IN_QB"


# --------------------------------------------------------------------------- #
# Account + Class resolution (cost code path)
# --------------------------------------------------------------------------- #
def test_resolve_account_and_class_from_cost_code():
    session = _session(
        {
            "cost_code": {"code": "40", "maps_to_account": "15200", "default_class_code": "PH1"},
            "account": {"number": "15200", "name": "CIP Hard Costs"},
            "class": {"name": "Phase 1"},
        }
    )
    account, class_name = resolve_account_and_class(
        session, _bill(raw_extensions={"cost_code": "40"})
    )
    assert account == "15200 CIP Hard Costs"  # QB FullName = "<number> <name>"
    assert class_name == "Phase 1"


def test_resolve_account_unknown_cost_code_fails_closed():
    session = _session({"cost_code": None})
    with pytest.raises(EntityResolutionError) as exc:
        resolve_account_and_class(session, _bill(raw_extensions={"cost_code": "999"}))
    assert exc.value.code == "COST_CODE_UNRESOLVED"


def test_resolve_account_number_not_in_coa_fails_closed_list_drift():
    session = _session(
        {
            "cost_code": {"code": "40", "maps_to_account": "15200", "default_class_code": None},
            "account": None,  # drift: cost code maps to an account not in this file
        }
    )
    with pytest.raises(EntityResolutionError) as exc:
        resolve_account_and_class(session, _bill(raw_extensions={"cost_code": "40"}))
    assert exc.value.code == "ACCOUNT_NOT_IN_COA"


def test_resolve_account_no_hint_no_cost_code_fails_closed():
    session = _session({})
    with pytest.raises(EntityResolutionError) as exc:
        resolve_account_and_class(session, _bill(raw_extensions={}))
    assert exc.value.code == "ACCOUNT_UNRESOLVED"


# --------------------------------------------------------------------------- #
# Fee-bill routing (task 11): fee_role -> fixed policy Dr account
# --------------------------------------------------------------------------- #
def test_resolve_fee_bill_ceo_commission_maps_to_expense_account():
    session = _session(
        {"account": {"number": "60200", "name": "CEO Commission Expense"}}
    )
    account, _ = resolve_account_and_class(
        session, _bill(raw_extensions={"fee_role": "ceo_2_parent"})
    )
    assert account == "60200 CEO Commission Expense"


def test_resolve_fee_bill_president_commission_maps_to_expense_account():
    session = _session(
        {"account": {"number": "60300", "name": "President Commission Expense"}}
    )
    account, _ = resolve_account_and_class(
        session, _bill(raw_extensions={"fee_role": "pres_1_parent"})
    )
    assert account == "60300 President Commission Expense"


def test_resolve_fee_bill_partnership_role_without_cost_code_fails_closed():
    """The partnership 5% is capitalization-policy-dependent; refuse to guess."""
    session = _session({})
    with pytest.raises(EntityResolutionError) as exc:
        resolve_account_and_class(
            session, _bill(raw_extensions={"fee_role": "dev_5_partnership"})
        )
    assert exc.value.code == "FEE_ROLE_UNRESOLVED"


# --------------------------------------------------------------------------- #
# Customer:Job + Draw # resolution (optional dimensions)
# --------------------------------------------------------------------------- #
def test_resolve_customer_job_and_draw_from_draw_package():
    session = _session({"draw": {"draw_number": "7", "customer_job": "Proj A:Job 1"}})
    cj, draw = resolve_customer_job_and_draw(
        session, _bill(draw_package_id="d1")
    )
    assert cj == "Proj A:Job 1"
    assert draw == "7"


def test_resolve_customer_job_missing_draw_package_fails_closed():
    session = _session({"draw": None})
    with pytest.raises(EntityResolutionError) as exc:
        resolve_customer_job_and_draw(session, _bill(draw_package_id="ghost"))
    assert exc.value.code == "DRAW_PACKAGE_UNRESOLVED"


def test_resolve_customer_job_absent_is_valid_none():
    """No draw package and no raw_extensions hint -> optional dims are None (valid)."""
    session = _session({})
    cj, draw = resolve_customer_job_and_draw(session, _bill())
    assert cj is None and draw is None


# --------------------------------------------------------------------------- #
# Full composition
# --------------------------------------------------------------------------- #
def test_resolve_bill_add_fields_full_draw_fee_bill():
    session = _session(
        {
            "vendor": {"qb_list_id": "80000009-1", "name": "Mike Watson"},
            "account": {"number": "60200", "name": "CEO Commission Expense"},
            "draw": {"draw_number": "7", "customer_job": "Proj A:Job 1"},
        }
    )
    fields = resolve_bill_add_fields(
        session,
        _bill(draw_package_id="d1", raw_extensions={"fee_role": "ceo_2_parent"}),
    )
    assert fields.vendor_list_id == "80000009-1"
    assert fields.account_name == "60200 CEO Commission Expense"
    assert fields.customer_job == "Proj A:Job 1"
    assert fields.draw_number == "7"
