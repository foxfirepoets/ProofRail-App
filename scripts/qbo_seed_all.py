"""qbo_seed_all.py — orchestrate the full two-realm sandbox seed in runbook order.

Usage:
    python scripts/qbo_seed_all.py                     # DRY RUN (default, no writes)
    python scripts/qbo_seed_all.py --execute-sandbox   # real sandbox writes

Order (0_SETUP_RUNBOOK.md — COA first, items after COA, dimensions, then customers):
   1. Realm A accounts      2. Realm B accounts
   3. Realm A items         4. Realm A vendors       5. Realm B vendors
   6. Realm A locations     7. Realm B locations
   8. Realm A classes       9. Realm B classes
  10. Realm A customers/projects
  11. Verification counts (only after --execute-sandbox)

Row failures are logged and the run continues; the summary lists every failed row.
Never deletes. Never updates. Never touches production (sandbox guard in qbo_common).
"""
import sys

import qbo_seed_accounts
import qbo_seed_classes
import qbo_seed_customers_projects
import qbo_seed_items
import qbo_seed_locations_departments
import qbo_seed_vendors
from qbo_common import Realm, audit, load_env, print_summary_table, resolve_execute, run_seed

STEPS = [
    ("Account", "A", qbo_seed_accounts.build_plan),
    ("Account", "B", qbo_seed_accounts.build_plan),
    ("Item", "A", qbo_seed_items.build_plan),
    ("Vendor", "A", qbo_seed_vendors.build_plan),
    ("Vendor", "B", qbo_seed_vendors.build_plan),
    ("Department", "A", qbo_seed_locations_departments.build_plan),
    ("Department", "B", qbo_seed_locations_departments.build_plan),
    ("Class", "A", qbo_seed_classes.build_plan),
    ("Class", "B", qbo_seed_classes.build_plan),
    ("Customer", "A", qbo_seed_customers_projects.build_plan),
]


def main():
    env = load_env()
    execute = resolve_execute()
    realms = {"A": Realm("A", env), "B": Realm("B", env)}
    audit({"event": "seed_all_start", "mode": "EXECUTE-SANDBOX" if execute else "DRY_RUN"})
    summaries = []
    for entity, rk, builder in STEPS:
        realm = realms[rk]
        try:
            plan = builder(realm, execute)
        except Exception as e:  # noqa: BLE001 — a broken step must not kill later steps
            print(f"\nSTEP FAILED to plan [{rk}/{entity}]: {e}")
            summaries.append({"realm": rk, "entity": entity, "created": 0, "skipped": 0,
                              "errors": [("__plan__", str(e)[:300])]})
            continue
        summaries.append(run_seed(realm, entity, plan, execute))
    errs = print_summary_table(summaries)
    audit({"event": "seed_all_done", "mode": "EXECUTE-SANDBOX" if execute else "DRY_RUN",
           "error_rows": len(errs)})
    if not execute:
        print("\nDRY RUN complete — no API writes were made.")
        print("To execute against the two SANDBOX realms, run exactly:")
        print('    python "scripts/qbo_seed_all.py" --execute-sandbox')
        print("Then verify with:")
        print('    python "scripts/qbo_verify_setup_counts.py"')
    else:
        print("\nExecute complete. Running verification counts...")
        import qbo_verify_setup_counts
        rc = 0
        try:
            qbo_verify_setup_counts.main()
        except SystemExit as e:
            rc = e.code or 0
        sys.exit(rc)


if __name__ == "__main__":
    main()
