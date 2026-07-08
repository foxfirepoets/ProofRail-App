"""qbo_seed_locations_departments.py — seed QBO Locations (API object: Department).

Usage:
    python scripts/qbo_seed_locations_departments.py --realm A [--execute-sandbox]  # 18 legal entities
    python scripts/qbo_seed_locations_departments.py --realm B [--execute-sandbox]  # 17 corporate family

QBO's UI 'Location' is the API entity 'Department'. Location tracking must be
enabled in Account and Settings -> Advanced -> Categories first (manual UI step).
Idempotent by Name.
"""
import sys

from qbo_common import bootstrap, print_summary_table, read_single_column_csv, run_seed

CSV_BY_REALM = {"A": "6_Locations_REALM_A_API_SEED.csv", "B": "7_Locations_REALM_B_API_SEED.csv"}


def build_plan(realm, execute):
    names = read_single_column_csv(CSV_BY_REALM[realm.key])
    existing = set()
    if execute:
        existing = {d["Name"] for d in realm.query_all("Department")}
    return [{"key": n, "exists": n in existing, "payload": {"Name": n}} for n in names]


def main():
    if "--realm" not in sys.argv:
        sys.exit("usage: qbo_seed_locations_departments.py --realm A|B [--execute-sandbox]")
    realm_key = sys.argv[sys.argv.index("--realm") + 1].upper()
    realm, execute = bootstrap(realm_key)
    summary = run_seed(realm, "Department", build_plan(realm, execute), execute)
    print_summary_table([summary])
    return summary


if __name__ == "__main__":
    main()
