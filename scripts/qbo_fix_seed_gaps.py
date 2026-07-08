"""qbo_fix_seed_gaps.py — targeted, one-time fixes for the three known seed gaps (sandbox only).

Usage:
    python scripts/qbo_fix_seed_gaps.py [--execute-sandbox]

Gap 1 (Realm A): 'Accumulated Depreciation' (17900) — QBO API rejects a top-level account
  with subtype AccumulatedDepreciation ("cannot be parent accounts", code 6000). Fix: create
  it with subtype OtherFixedAssets. Per the setup runbook, detail types are QBO-mandatory
  metadata that do not affect the gates — refine in the UI later if Ricks prefers.

Gap 2 (Realm A): 'Partner Capital:EJH-TBD' — the seed CSV assigns AcctNum 30134, which
  duplicates 'Partner Capital:Madison-Outside' (CSV line 99). QBO rejected the duplicate
  (code 2010). Fix: create with the first free number in the partner-capital pattern, 30144.
  DEVIATION FROM CSV — flagged for owner review; renumber in the UI if a different number is
  preferred.

Gap 3 (both realms): 'Insurance' (70400) already exists as Intuit sample data (matched by
  name, so the seeder skipped it). Fix: sparse-update ONLY the AcctNum to 70400 so the COA
  numbering is complete. This is the single sanctioned update in the toolchain; it is
  audit-logged and sandbox-gated like everything else.
"""
import sys

from qbo_common import QboError, Realm, audit, load_env, resolve_execute
from qbo_create_sandbox_bill import find_one


def fix_accumulated_depreciation(realm_a, execute):
    name = "Accumulated Depreciation"
    if find_one(realm_a, "Account", name, "Name"):
        print(f"  [gap1] '{name}' already exists — nothing to do")
        return True
    payload = {"Name": name, "AcctNum": "17900", "AccountType": "Fixed Asset",
               "AccountSubType": "OtherFixedAssets",
               "Description": "If held for rental. Detail type OtherFixedAssets per API limit; refine in UI"}
    if not execute:
        print(f"  [gap1] would create '{name}' (17900) with subtype OtherFixedAssets")
        return True
    realm_a.create("Account", payload, name + "|fixgap")
    audit({"event": "seed_gap_fixed", "gap": 1, "realm": "A", "name": name,
           "deviation": "AccountSubType OtherFixedAssets instead of AccumulatedDepreciation"})
    print(f"  [gap1] created '{name}' (17900, subtype OtherFixedAssets)")
    return True


def fix_ejh_tbd(realm_a, execute):
    full = "Partner Capital:EJH-TBD"
    if find_one(realm_a, "Account", full, "FullyQualifiedName"):
        print(f"  [gap2] '{full}' already exists — nothing to do")
        return True
    parent = find_one(realm_a, "Account", "Partner Capital", "Name")
    if not parent and execute:
        print("  [gap2] FAIL: parent 'Partner Capital' not found")
        return False
    payload = {"Name": "EJH-TBD", "AcctNum": "30144", "AccountType": "Equity",
               "AccountSubType": "PartnersEquity", "SubAccount": True,
               "ParentRef": {"value": parent["Id"] if parent else "DRYRUN"},
               "Description": "EJH capital - partners TBD (confirm OA). Renumbered from dup 30134; owner review"}
    if not execute:
        print(f"  [gap2] would create '{full}' with AcctNum 30144 (CSV 30134 was a duplicate)")
        return True
    realm_a.create("Account", payload, full + "|fixgap")
    audit({"event": "seed_gap_fixed", "gap": 2, "realm": "A", "name": full,
           "deviation": "AcctNum 30144 (CSV value 30134 duplicates Partner Capital:Madison-Outside)"})
    print(f"  [gap2] created '{full}' (30144 — deviation from CSV, owner review)")
    return True


def fix_insurance(realm, execute):
    acct = find_one(realm, "Account", "Insurance", "Name")
    if not acct:
        print(f"  [gap3/{realm.key}] 'Insurance' not found — unexpected; run the seeder first")
        return False
    if acct.get("AcctNum") == "70400":
        print(f"  [gap3/{realm.key}] 'Insurance' already numbered 70400 — nothing to do")
        return True
    if not execute:
        print(f"  [gap3/{realm.key}] would sparse-update 'Insurance' AcctNum -> 70400")
        return True
    body = {"Id": acct["Id"], "SyncToken": acct["SyncToken"], "sparse": True,
            "Name": "Insurance", "AcctNum": "70400"}
    resp = realm._request("POST", "account", {"operation": "update"}, body)
    audit({"event": "seed_gap_fixed", "gap": 3, "realm": realm.key, "name": "Insurance",
           "action": "sparse update AcctNum -> 70400 (sample-data collision)",
           "qbo_id": acct["Id"]})
    print(f"  [gap3/{realm.key}] 'Insurance' AcctNum set to 70400 (Id {acct['Id']})")
    return bool(resp)


def main():
    env = load_env()
    execute = resolve_execute()
    realm_a, realm_b = Realm("A", env), Realm("B", env)
    mode = "EXECUTE-SANDBOX" if execute else "DRY RUN"
    print(f"[{mode}] fixing known seed gaps")
    if execute:
        for r in (realm_a, realm_b):
            ok, _ = r.assert_company()
            if not ok:
                sys.exit("REFUSED: company sanity check failed")
    ok = True
    try:
        ok &= fix_accumulated_depreciation(realm_a, execute)
        ok &= fix_ejh_tbd(realm_a, execute)
        ok &= fix_insurance(realm_a, execute)
        ok &= fix_insurance(realm_b, execute)
    except QboError as e:
        print(f"  FIX FAILED: HTTP {e.status} — see logs/qbo_seed_*.jsonl")
        ok = False
    print("All gaps fixed." if ok else "Some gaps remain — see output above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
