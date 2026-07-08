"""qbo_seed_items.py — seed Products/Services (cost-code Service items) into Realm A.

Usage:
    python scripts/qbo_seed_items.py --realm A [--execute-sandbox]

Source: 3_Products_Services_REALM_A.csv (69 rows, all Type=Service, purchase-side
only: 'I purchase this' maps to the listed COA expense account).

MUST run after qbo_seed_accounts.py — every ExpenseAccountRef is resolved against
the live chart of accounts by name (leaf or fully-qualified). Idempotent by Name.
"""
import sys

from qbo_common import bootstrap, print_summary_table, read_csv, run_seed


def build_plan(realm, execute):
    rows = read_csv("3_Products_Services_REALM_A.csv")
    existing, accounts_by_name = {}, {}
    if execute:
        existing = {i["Name"]: i for i in realm.query_all("Item")}
        for a in realm.query_all("Account"):
            accounts_by_name[a.get("FullyQualifiedName", "")] = a
            accounts_by_name.setdefault(a.get("Name", ""), a)
    plan = []
    for row in rows:
        name = row["Product/Service Name"].strip()
        expense_name = row["Expense Account"].strip()
        payload = {
            "Name": name,
            "Type": "Service",
            "Description": (row.get("Description") or "").strip() or None,
            "PurchaseDesc": (row.get("Description") or "").strip() or name,
        }
        payload = {k: v for k, v in payload.items() if v}

        def creator(payload=payload, expense_name=expense_name, name=name):
            acct = accounts_by_name.get(expense_name)
            if not acct:
                from qbo_common import QboError
                raise QboError(0, f"expense account '{expense_name}' not found in realm "
                                  f"{realm.key} — run qbo_seed_accounts.py first")
            payload = dict(payload)
            payload["ExpenseAccountRef"] = {"value": acct["Id"]}
            return realm.create("Item", payload, name)

        plan.append({"key": name, "exists": name in existing,
                     "payload": payload, "create": creator})
    return plan


def main():
    realm, execute = bootstrap("A")  # items are Realm A only in this test build
    plan = build_plan(realm, execute)
    summary = run_seed(realm, "Item", plan, execute)
    print_summary_table([summary])
    return summary


if __name__ == "__main__":
    main()
