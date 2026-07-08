"""qbo_seed_customers_projects.py — seed Customers/Projects (Customer + sub-customer) into Realm A.

Usage:
    python scripts/qbo_seed_customers_projects.py --realm A [--execute-sandbox]

Source: 10_Customers_Projects_REALM_A_API_SEED.csv (64 rows). Colon = hierarchy
('12SB Hunters Landing:Acquisition' -> sub-customer under '12SB Hunters Landing').
CSV is parent-before-child ordered (verified). Sub-customers are created with
Job=true + BillWithParent=false. Idempotent by FullyQualifiedName.
"""
import sys

from qbo_common import QboError, bootstrap, print_summary_table, read_single_column_csv, run_seed


def build_plan(realm, execute):
    names = read_single_column_csv("10_Customers_Projects_REALM_A_API_SEED.csv")
    existing, id_by_fullname = {}, {}
    if execute:
        for c in realm.query_all("Customer"):
            fq = c.get("FullyQualifiedName", c.get("DisplayName", ""))
            existing[fq] = c
            id_by_fullname[fq] = c["Id"]
    plan = []
    for full in names:
        leaf = full.split(":")[-1].strip()
        parent_full = full.rsplit(":", 1)[0] if ":" in full else None

        def creator(full=full, leaf=leaf, parent_full=parent_full):
            payload = {"DisplayName": leaf}
            if parent_full:
                pid = id_by_fullname.get(parent_full)
                if not pid:
                    raise QboError(0, f"parent customer '{parent_full}' not created yet")
                payload.update({"ParentRef": {"value": pid}, "Job": True,
                                "BillWithParent": False})
            obj = realm.create("Customer", payload, full)
            id_by_fullname[full] = obj["Id"]
            return obj

        plan.append({"key": full, "exists": full in existing,
                     "payload": {"DisplayName": leaf}, "create": creator})
    return plan


def main():
    realm, execute = bootstrap("A")  # customers/projects are Realm A only in this test build
    summary = run_seed(realm, "Customer", build_plan(realm, execute), execute)
    print_summary_table([summary])
    return summary


if __name__ == "__main__":
    main()
