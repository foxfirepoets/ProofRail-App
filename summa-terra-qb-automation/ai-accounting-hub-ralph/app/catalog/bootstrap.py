"""Plug-and-play catalog bootstrap (SPEC_SUMMA_TERRA_BINDING §5/§13.4).

One command loads every canonical catalog from the QB Import_Files CSVs for a parent + a
partnership company, runs the hard assertions, prints a GREEN/RED summary, and exits 0/1.
Idempotent: re-running reports 0 changes. Mirrors the "upload to QB and it auto-populates"
experience on the canonical side.

    python -m app.catalog.bootstrap \
        --parent      "STV — Summa Terra Ventures" \
        --partnership "STV — HL Hunter's Landing" \
        --imports     "/path/to/QB Summa Terra/Import_Files" [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import parsers
from app.catalog.assertions import (
    AssertionFailure,
    assert_bucket_invariant,
    assert_no_orphans,
    assert_split_at_file_level,
)
from app.catalog.loader import (
    CatalogError,
    LoadResult,
    load_accounts,
    load_classes,
    load_cost_codes,
    load_customer_jobs,
    load_vendors,
)
from app.models import Company


def _get_or_create_company(session: Session, legal_name: str, role: str) -> str:
    existing = session.scalars(
        select(Company).where(Company.legal_name == legal_name)
    ).one_or_none()
    if existing is not None:
        if existing.role != role:
            existing.role = role
        session.flush()
        return existing.id
    entity_type = "management" if role == "parent" else "partnership"
    c = Company(legal_name=legal_name, entity_type=entity_type, role=role)
    session.add(c)
    session.flush()
    return c.id


def _load_company(
    session: Session,
    company_id: str,
    role: str,
    imports: Path,
    *,
    coa_file: str,
    items_file: str,
    vendors_file: str,
    parent_only_numbers: frozenset[str],
    with_jobs: bool,
) -> dict[str, LoadResult]:
    out: dict[str, LoadResult] = {}
    out["accounts"] = load_accounts(
        session,
        company_id,
        parsers.parse_accounts(imports / coa_file),
        parent_only_numbers=parent_only_numbers,
    )
    out["classes"] = load_classes(
        session, company_id, parsers.parse_classes(imports / "CSV_Classes.csv")
    )
    out["cost_codes"] = load_cost_codes(
        session, company_id, parsers.parse_cost_codes(imports / items_file)
    )
    out["vendors"] = load_vendors(
        session, company_id, parsers.parse_vendors(imports / vendors_file), company_role=role
    )
    if with_jobs:
        out["customer_jobs"] = load_customer_jobs(
            session, company_id, parsers.parse_customer_jobs(imports / "CSV_Customers_Jobs.csv")
        )
    return out


def _summary_line(label: str, loads: dict[str, LoadResult]) -> str:
    parts = [
        f"{cat} {r.inserted}+/{r.updated}~/{r.unchanged}=" for cat, r in loads.items()
    ]
    return f"  {label}: " + "  ".join(parts)


def run(parent: str, partnership: str, imports: Path, *, dry_run: bool) -> int:
    from app.db import get_engine

    # Parent-only account numbers = those in the parent COA but not the partnership COA.
    part_nums = {a.number for a in parsers.parse_accounts(imports / "CSV_Chart_of_Accounts_Partnership.csv")}
    parent_nums = {a.number for a in parsers.parse_accounts(imports / "CSV_Chart_of_Accounts_Parent.csv")}
    parent_only = frozenset(parent_nums - part_nums)

    session = Session(get_engine())
    try:
        parent_id = _get_or_create_company(session, parent, "parent")
        partnership_id = _get_or_create_company(session, partnership, "partnership")

        parent_loads = _load_company(
            session, parent_id, "parent", imports,
            coa_file="CSV_Chart_of_Accounts_Parent.csv",
            items_file="CSV_Items_Parent.csv",
            vendors_file="CSV_Vendors_Parent.csv",
            parent_only_numbers=parent_only,
            with_jobs=False,
        )
        partnership_loads = _load_company(
            session, partnership_id, "partnership", imports,
            coa_file="CSV_Chart_of_Accounts_Partnership.csv",
            items_file="CSV_Items_Partnership.csv",
            vendors_file="CSV_Vendors_Partnership.csv",
            parent_only_numbers=frozenset(),
            with_jobs=True,
        )

        # Hard assertions.
        assert_split_at_file_level(session, partnership_id)
        for cid in (parent_id, partnership_id):
            assert_bucket_invariant(session, cid)
            assert_no_orphans(session, cid)

        print("catalog bootstrap — load summary (inserted+/updated~/unchanged=):")
        print(_summary_line(f"parent      [{parent}]", parent_loads))
        print(_summary_line(f"partnership [{partnership}]", partnership_loads))

        if dry_run:
            session.rollback()
            print("DRY-RUN: rolled back, nothing committed. Assertions GREEN.")
            return 0
        session.commit()
        print("GREEN: catalogs loaded and committed; all assertions passed.")
        return 0
    except (CatalogError, AssertionFailure) as exc:
        session.rollback()
        print(f"RED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Load QB Summa Terra catalogs into the canonical store.")
    ap.add_argument("--parent", required=True, help="parent company legal name (get-or-create)")
    ap.add_argument("--partnership", required=True, help="partnership company legal name (get-or-create)")
    ap.add_argument("--imports", required=True, type=Path, help="QB Import_Files directory")
    ap.add_argument("--dry-run", action="store_true", help="load + assert in a rolled-back txn")
    args = ap.parse_args(argv)
    return run(args.parent, args.partnership, args.imports, dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
