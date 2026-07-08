"""qbo_read_report_by_location.py — READ-ONLY report fetch: Balance Sheet / P&L by Location.

Usage:
    python scripts/qbo_read_report_by_location.py --realm A [--report BalanceSheet|ProfitAndLoss]

Renders the report summarized by Location (QBO API column group 'Departments').
This is the 'birth certificate' check: one column per legal entity, all zeros
until transactions post. Safe to run at any time — makes no writes.
"""
import json
import sys

from qbo_common import Realm, load_env


def main():
    if "--realm" not in sys.argv:
        sys.exit("usage: qbo_read_report_by_location.py --realm A|B [--report BalanceSheet]")
    realm_key = sys.argv[sys.argv.index("--realm") + 1].upper()
    report = "BalanceSheet"
    if "--report" in sys.argv:
        report = sys.argv[sys.argv.index("--report") + 1]
    realm = Realm(realm_key, load_env())
    rep = realm.get(f"reports/{report}", {"summarize_column_by": "Departments"})
    cols = [c.get("ColTitle", "") for c in rep.get("Columns", {}).get("Column", [])]
    print(f"{report} by Location — {realm.label}")
    print(f"Columns ({len(cols)}): {cols}")

    def walk(rows, depth=0):
        for r in rows.get("Row", []):
            header = r.get("Header", {}).get("ColData", [{}])[0].get("value", "")
            cells = [c.get("value", "") for c in r.get("ColData", [])]
            if header:
                print("  " * depth + header)
            elif cells:
                print("  " * depth + " | ".join(cells))
            if "Rows" in r:
                walk(r["Rows"], depth + 1)

    walk(rep.get("Rows", {}))


if __name__ == "__main__":
    main()
