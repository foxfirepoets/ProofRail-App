"""qbo_verify_setup_counts.py — acceptance-count verification (READ-ONLY, safe anytime).

Usage:
    python scripts/qbo_verify_setup_counts.py [--realm A|B]

The counts ARE the acceptance test (0_SETUP_RUNBOOK.md section 4):
  Realm A: 139 accounts (+QBO singletons) · 18 Locations · 5 Classes · 69 Items · 53 Vendors · 64 Customers
  Realm B: 109 accounts (+1 auto-created 'Land Held for Sale' parent) · 17 Locations · 1 Class · 3 Vendors

Because Intuit sandboxes ship pre-seeded with sample data, verification checks that
EVERY EXPECTED NAME EXISTS (matched against the seed CSVs), not raw totals. Extras
(sample data) are reported separately. Also renders Balance Sheet by Location per
realm and asserts realm separation (no cross-realm bleed of realm-specific names).
"""
import sys

from qbo_common import (Realm, audit, load_env, read_csv, read_single_column_csv)

EXPECT = {
    "A": {
        "Account": [r["Account Name"].strip() for r in read_csv("1_COA_Partnership_REALM_A.csv")],
        "Department": read_single_column_csv("6_Locations_REALM_A_API_SEED.csv"),
        "Class": read_single_column_csv("8_Classes_REALM_A_API_SEED.csv"),
        "Item": [r["Product/Service Name"].strip() for r in read_csv("3_Products_Services_REALM_A.csv")],
        "Vendor": read_single_column_csv("4_Vendors_REALM_A.csv"),
        "Customer": read_single_column_csv("10_Customers_Projects_REALM_A_API_SEED.csv"),
    },
    "B": {
        "Account": [r["Account Name"].strip() for r in read_csv("2_COA_Parent_REALM_B.csv")],
        "Department": read_single_column_csv("7_Locations_REALM_B_API_SEED.csv"),
        "Class": read_single_column_csv("9_Classes_REALM_B_API_SEED.csv"),
        "Vendor": read_single_column_csv("5_Vendors_REALM_B.csv"),
    },
}

# names that must exist in exactly one realm — the cross-realm bleed canaries
REALM_ONLY = {
    "A": {"Vendor": ["GC - Elite Construction USA (TX)"], "Class": ["00 Acquisition"],
          "Account": ["Developer Fee Expense"]},
    "B": {"Vendor": ["EXEC - Mike Watson", "EXEC - Porter Christensen"],
          "Account": ["Developer Fee Income", "Comm Payable - Watson (2%)"]},
}

FETCH_NAME = {
    "Account": lambda o: o.get("FullyQualifiedName", o.get("Name", "")),
    "Department": lambda o: o.get("Name", ""),
    "Class": lambda o: o.get("Name", ""),
    "Item": lambda o: o.get("Name", ""),
    "Vendor": lambda o: o.get("DisplayName", ""),
    "Customer": lambda o: o.get("FullyQualifiedName", o.get("DisplayName", "")),
}


def verify_realm(realm):
    print(f"\n===== VERIFY {realm.label} (realm {realm.realm_id}) =====")
    ok_all = True
    results = []
    live = {}
    for entity in EXPECT[realm.key]:
        live[entity] = {FETCH_NAME[entity](o) for o in realm.query_all(entity)}
    for entity, expected in EXPECT[realm.key].items():
        found = [n for n in expected if n in live[entity]]
        missing = [n for n in expected if n not in live[entity]]
        extras = len(live[entity]) - len(found)
        status = "PASS" if not missing else "FAIL"
        ok_all &= not missing
        results.append((entity, len(expected), len(found), len(missing), extras, status))
        if missing:
            print(f"  MISSING {entity} ({len(missing)}): {missing[:10]}{' ...' if len(missing) > 10 else ''}")
    # account-number spot check
    acct_by_fq = {FETCH_NAME["Account"](a): a for a in realm.query_all("Account")}
    src = "1_COA_Partnership_REALM_A.csv" if realm.key == "A" else "2_COA_Parent_REALM_B.csv"
    num_mismatch = [r["Account Name"] for r in read_csv(src)
                    if r["Account Name"].strip() in acct_by_fq
                    and (acct_by_fq[r["Account Name"].strip()].get("AcctNum") or "") != r["Account Number"].strip()]
    # realm-separation canaries: this realm's exclusives must exist; the OTHER realm's must not
    other = "B" if realm.key == "A" else "A"
    bleed = []
    for entity, names in REALM_ONLY[other].items():
        pool = live.get(entity) or {FETCH_NAME[entity](o) for o in realm.query_all(entity)}
        bleed += [n for n in names if n in pool]
    # Balance Sheet by Location must render
    bs_ok, bs_cols = False, 0
    try:
        rep = realm.get("reports/BalanceSheet", {"summarize_column_by": "Departments"})
        cols = rep.get("Columns", {}).get("Column", [])
        bs_cols = max(0, len(cols) - 2)  # minus label + total columns
        bs_ok = len(cols) > 1
    except Exception as e:  # noqa: BLE001
        print(f"  Balance Sheet by Location FAILED to render: {e}")
    print(f"\n{'Entity':<12}{'Expected':>9}{'Found':>7}{'Missing':>9}{'Extras*':>9}  Status")
    for row in results:
        print(f"{row[0]:<12}{row[1]:>9}{row[2]:>7}{row[3]:>9}{row[4]:>9}  {row[5]}")
    print("  (*extras = Intuit sandbox sample data / QBO-created singletons — expected, reviewed not deleted)")
    print(f"AcctNum mismatches: {len(num_mismatch)}" + (f" -> {num_mismatch[:5]}" if num_mismatch else ""))
    print(f"Cross-realm bleed: {'NONE' if not bleed else 'FAIL ' + str(bleed)}")
    print(f"Balance Sheet by Location: {'renders (' + str(bs_cols) + ' location columns)' if bs_ok else 'FAIL'}")
    ok_all = ok_all and not bleed and bs_ok
    audit({"event": "verify_counts", "realm": realm.key, "pass": ok_all,
           "results": [dict(zip(["entity", "expected", "found", "missing", "extras", "status"], r))
                       for r in results],
           "acctnum_mismatches": num_mismatch, "bleed": bleed, "bs_by_location_ok": bs_ok})
    print(f"\n{realm.label}: {'ALL CHECKS PASS' if ok_all else 'CHECKS FAILED — see above'}")
    return ok_all


def main():
    env = load_env()
    keys = ["A", "B"]
    if "--realm" in sys.argv:
        keys = [sys.argv[sys.argv.index("--realm") + 1].upper()]
    results = [verify_realm(Realm(k, env)) for k in keys]  # list, not generator: never skip a realm
    overall = all(results)
    print(f"\n========== VERIFICATION {'PASS' if overall else 'FAIL'} ==========")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
