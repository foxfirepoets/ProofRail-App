"""Typed, frozen rows produced by the pure parsers (app/catalog/parsers.py).

No DB, no behavior — just the normalized shape of each QB list, ready for the loaders.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountRow:
    number: str
    name: str
    acct_type: str  # normalized QB type (Bank/AR/AP/OtherCurrentAsset/...)
    statement: str  # "BS" | "PL"
    is_cip_bucket: bool


@dataclass(frozen=True)
class ClassRow:
    code: str
    name: str


@dataclass(frozen=True)
class CostCodeRow:
    code: str
    name: str
    account_name: str  # resolved to an account NUMBER by the loader (per company)
    default_class_name: str | None
    kind: str  # "draw" | "lifecycle" | "fee" | "retainage"
    fee_role: str | None  # dev_5_partnership | dev_inc_5_parent | ceo_2_parent | pres_1_parent


@dataclass(frozen=True)
class VendorRow:
    name: str


@dataclass(frozen=True)
class CustomerJobRow:
    path: str
    parent_path: str | None
