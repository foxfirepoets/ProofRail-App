"""qbo_seed_accounts.py — seed the chart of accounts into one sandbox realm.

Usage:
    python scripts/qbo_seed_accounts.py --realm A [--execute-sandbox]
    python scripts/qbo_seed_accounts.py --realm B [--execute-sandbox]

Realm A source: 1_COA_Partnership_REALM_A.csv (139 rows)
Realm B source: 2_COA_Parent_REALM_B.csv    (109 rows)

Colon-delimited Account Name creates sub-accounts (parent must exist first; the
CSVs are parent-before-child ordered). Known exception: Realm B's
'Land Held for Sale:HLE' has no parent row — the missing parent is auto-created
(same type, no account number) and loudly logged.

Idempotent: existing accounts are matched by FullyQualifiedName and skipped.
A/R, A/P, Retained Earnings are intentionally absent — QBO creates its own singletons.
"""
import sys

from qbo_common import (ACCOUNT_SUBTYPE_MAP, ACCOUNT_TYPE_MAP, QboError, audit,
                        bootstrap, print_summary_table, read_csv, run_seed)

CSV_BY_REALM = {"A": "1_COA_Partnership_REALM_A.csv", "B": "2_COA_Parent_REALM_B.csv"}


def build_plan(realm, execute):
    rows = read_csv(CSV_BY_REALM[realm.key])
    existing = {}
    if execute:
        for a in realm.query_all("Account"):
            existing[a.get("FullyQualifiedName", a.get("Name", ""))] = a
    id_by_fullname = {fq: a["Id"] for fq, a in existing.items()}
    plan = []

    def ensure_parent(fullname, row):
        """Auto-create a missing parent account (Realm B 'Land Held for Sale' case)."""
        if fullname in id_by_fullname or any(p["key"] == fullname for p in plan):
            return
        audit({"event": "auto_parent_needed", "realm": realm.key, "parent": fullname,
               "reason": "child row present in CSV without a parent row"})
        print(f"  NOTE: parent '{fullname}' not in CSV — will auto-create (no account number)")
        payload = {
            "Name": fullname.split(":")[-1],
            "AccountType": ACCOUNT_TYPE_MAP[row["Type"].strip()],
            "AccountSubType": ACCOUNT_SUBTYPE_MAP.get(row["Detail Type"].strip()),
            "Description": "AUTO-CREATED PARENT (missing from seed CSV) — review in QBO UI",
        }
        plan.append({"key": fullname, "exists": False, "payload": payload, "row": row})

    for row in rows:
        fullname = row["Account Name"].strip()
        leaf = fullname.split(":")[-1].strip()
        parent_full = fullname.rsplit(":", 1)[0] if ":" in fullname else None
        if parent_full:
            ensure_parent(parent_full, row)
        payload = {
            "Name": leaf,
            "AcctNum": row["Account Number"].strip(),
            "AccountType": ACCOUNT_TYPE_MAP[row["Type"].strip()],
            "AccountSubType": ACCOUNT_SUBTYPE_MAP.get(row["Detail Type"].strip()),
            "Description": (row.get("Description") or "").strip() or None,
        }
        payload = {k: v for k, v in payload.items() if v}
        plan.append({"key": fullname, "exists": fullname in existing,
                     "payload": payload, "parent_full": parent_full})

    # wire create closures so children resolve ParentRef AFTER parents are created
    for p in plan:
        if p["exists"]:
            continue
        parent_full = p.get("parent_full")

        def creator(p=p, parent_full=parent_full):
            payload = dict(p["payload"])
            if parent_full:
                pid = id_by_fullname.get(parent_full)
                if not pid:
                    raise QboError(0, f"parent '{parent_full}' was not created; cannot create child")
                payload["ParentRef"] = {"value": pid}
                payload["SubAccount"] = True
            try:
                obj = realm.create("Account", payload, p["key"])
            except QboError as e:
                # ValidationFault on AccountSubType -> retry once without subtype
                if "AccountSubType" in e.body and "AccountSubType" in payload:
                    payload.pop("AccountSubType")
                    audit({"event": "subtype_fallback", "realm": realm.key, "name": p["key"]})
                    obj = realm.create("Account", payload, p["key"] + "|nosub")
                else:
                    raise
            id_by_fullname[p["key"]] = obj["Id"]
            return obj

        p["create"] = creator
    return plan


def main():
    if "--realm" not in sys.argv:
        sys.exit("usage: qbo_seed_accounts.py --realm A|B [--execute-sandbox]")
    realm_key = sys.argv[sys.argv.index("--realm") + 1].upper()
    realm, execute = bootstrap(realm_key)
    plan = build_plan(realm, execute)
    summary = run_seed(realm, "Account", plan, execute)
    print_summary_table([summary])
    return summary


if __name__ == "__main__":
    main()
