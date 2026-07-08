"""qbo_seed_vendors.py — seed vendors into one sandbox realm.

Usage:
    python scripts/qbo_seed_vendors.py --realm A [--execute-sandbox]   # 53 vendors
    python scripts/qbo_seed_vendors.py --realm B [--execute-sandbox]   # 3 vendors

Idempotent by DisplayName. NOTE: QBO shares one display-name namespace across
Vendor/Customer/Employee — a 6240 duplicate-name error is logged, not fatal.
"""
import sys

from qbo_common import bootstrap, print_summary_table, read_single_column_csv, run_seed

CSV_BY_REALM = {"A": "4_Vendors_REALM_A.csv", "B": "5_Vendors_REALM_B.csv"}


def build_plan(realm, execute):
    names = read_single_column_csv(CSV_BY_REALM[realm.key])
    existing = set()
    if execute:
        existing = {v["DisplayName"] for v in realm.query_all("Vendor")}
    return [{"key": n, "exists": n in existing, "payload": {"DisplayName": n}} for n in names]


def main():
    if "--realm" not in sys.argv:
        sys.exit("usage: qbo_seed_vendors.py --realm A|B [--execute-sandbox]")
    realm_key = sys.argv[sys.argv.index("--realm") + 1].upper()
    realm, execute = bootstrap(realm_key)
    summary = run_seed(realm, "Vendor", build_plan(realm, execute), execute)
    print_summary_table([summary])
    return summary


if __name__ == "__main__":
    main()
