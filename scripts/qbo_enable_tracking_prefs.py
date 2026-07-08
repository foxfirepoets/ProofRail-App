"""qbo_enable_tracking_prefs.py — enable Location + per-line Class tracking via the Preferences API.

Usage:
    python scripts/qbo_enable_tracking_prefs.py [--execute-sandbox]

Replaces the manual QBO UI step (Gear -> Account and settings -> Advanced -> Categories) for
both sandbox realms:
  * TrackDepartments = true, DepartmentTerminology = "Location"
  * ClassTrackingPerTxnLine = true (one class to each row)
Without these, QBO SILENTLY DROPS DepartmentRef on transactions — the dimensional law dies
quietly. Verified live: bills posted before this fix lost their Location.

Still to check by hand in the UI (not exposed via API): "Warn me when a transaction isn't
assigned" for classes/locations, and Projects ON (Realm A).
"""
import sys

from qbo_common import Realm, audit, load_env, resolve_execute

WANT = {"TrackDepartments": True, "DepartmentTerminology": "Location",
        "ClassTrackingPerTxnLine": True}


def fix_realm(realm, execute):
    prefs = realm.get("preferences")["Preferences"]
    ai = prefs.get("AccountingInfoPrefs", {})
    delta = {k: v for k, v in WANT.items() if ai.get(k) != v}
    if not delta:
        print(f"  {realm.label}: tracking prefs already correct")
        return True
    print(f"  {realm.label}: needs {delta}")
    if not execute:
        return True
    body = {"Id": prefs["Id"], "SyncToken": prefs["SyncToken"], "sparse": True,
            "AccountingInfoPrefs": {**{k: ai.get(k) for k in WANT}, **delta}}
    realm._request("POST", "preferences", {"operation": "update"}, body)
    after = realm.get("preferences")["Preferences"].get("AccountingInfoPrefs", {})
    ok = all(after.get(k) == v for k, v in WANT.items())
    audit({"event": "tracking_prefs_update", "realm": realm.key, "delta": delta, "verified": ok})
    print(f"  {realm.label}: updated -> verified {'OK' if ok else 'FAILED'}")
    return ok


def main():
    env = load_env()
    execute = resolve_execute()
    print(f"[{'EXECUTE-SANDBOX' if execute else 'DRY RUN'}] enabling Location/Class tracking prefs")
    ok = all([fix_realm(Realm(k, env), execute) for k in ("A", "B")])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
