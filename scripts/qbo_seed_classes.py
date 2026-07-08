"""qbo_seed_classes.py — seed Classes (cost phases) into one sandbox realm.

Usage:
    python scripts/qbo_seed_classes.py --realm A [--execute-sandbox]   # 5 cost phases
    python scripts/qbo_seed_classes.py --realm B [--execute-sandbox]   # 1 (90 Parent Overhead)

Class tracking must be ON (one to each row) in company settings first.
Idempotent by Name.
"""
import sys

from qbo_common import bootstrap, print_summary_table, read_single_column_csv, run_seed

CSV_BY_REALM = {"A": "8_Classes_REALM_A_API_SEED.csv", "B": "9_Classes_REALM_B_API_SEED.csv"}


def build_plan(realm, execute):
    names = read_single_column_csv(CSV_BY_REALM[realm.key])
    existing = set()
    if execute:
        existing = {c["Name"] for c in realm.query_all("Class")}
    return [{"key": n, "exists": n in existing, "payload": {"Name": n}} for n in names]


def main():
    if "--realm" not in sys.argv:
        sys.exit("usage: qbo_seed_classes.py --realm A|B [--execute-sandbox]")
    realm_key = sys.argv[sys.argv.index("--realm") + 1].upper()
    realm, execute = bootstrap(realm_key)
    summary = run_seed(realm, "Class", build_plan(realm, execute), execute)
    print_summary_table([summary])
    return summary


if __name__ == "__main__":
    main()
