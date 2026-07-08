"""qbo_create_dev_fee_test.py — the 5% developer-fee two-realm sandbox test.

Usage (DRY RUN default):
    python scripts/qbo_create_dev_fee_test.py --entity Madison --base 306140.60 \
        --location-a "04 Madison Park" --class-a "40 Vertical" \
        --customer-a "Madison West" [--docnumber DEVFEE-TEST-001] [--execute-sandbox]

What it does (business rules from the frozen spec + owner prompt):
  REALM A (partnership): posts a Bill to vendor 'IC - STV CM' using item 'FEE-DEV'
    for exactly 5% of --base. The partnership owes ONLY the 5% developer fee.
  REALM B (parent): posts an Invoice booking 5% Developer Fee Income (account 40200)
    under Location '15 STV CM'. Sandbox-only fixtures (customer 'SBX TEST - {entity} (IC)'
    and item 'SBX TEST Dev Fee Income') are created idempotently and clearly prefixed.
  COMMISSIONS: NOT booked. Rates/recipients (Watson 2% / Christensen 1% reserved in
    the parent COA vs. worksheet practice Zach 3%) are UNRESOLVED — commission
    accrual requires explicit owner approval. This script refuses to book them.
  GUARD: refuses --entity 12SB or 'Summa Elite' for the capitalized-fee path
    (COA law: CIP - Dev Fee Capitalized is NEVER for 12SB / Summa Elite).

The pair must tie: Realm A bill total == Realm B invoice total == round(base*0.05, 2).
"""
import argparse
import sys
from datetime import date

from qbo_common import QboError, Realm, audit, load_env, resolve_execute
from qbo_create_sandbox_bill import find_one

FEE_RATE = 0.05
NO_CAPITALIZED_FEE = {"12SB", "SUMMA ELITE"}


def ensure_fixture(realm, entity, payload, key, execute):
    field = "DisplayName" if entity in ("Customer", "Vendor") else "Name"
    obj = find_one(realm, entity, payload[field], field)
    if obj:
        return obj
    if not execute:
        print(f"  [DRY RUN] would create {entity} fixture: {payload[field]}")
        return {"Id": "DRYRUN"}
    return realm.create(entity, payload, key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity", required=True, help="short entity name, e.g. Madison")
    ap.add_argument("--base", type=float, required=True, help="fee base per OAEA (varies per entity)")
    ap.add_argument("--location-a", required=True, help="Realm A Location name, e.g. '04 Madison Park'")
    ap.add_argument("--class-a", required=True, help="Realm A Class, e.g. '40 Vertical'")
    ap.add_argument("--customer-a", required=True, help="Realm A project customer (FullyQualifiedName)")
    ap.add_argument("--docnumber", default=None)
    ap.add_argument("--execute-sandbox", action="store_true")
    args = ap.parse_args()

    if any(t in args.entity.upper() for t in NO_CAPITALIZED_FEE):
        sys.exit("REFUSED: capitalized dev fee is NEVER booked for 12SB / Summa Elite (COA law). "
                 "Owner + CPA must rule on expensed treatment before any posting.")
    fee = round(args.base * FEE_RATE, 2)
    doc = args.docnumber or f"DEVFEE-{args.entity.upper()}"
    if len(doc) > 21:
        sys.exit(f"REFUSED: DocNumber '{doc}' is {len(doc)} chars — QBO max is 21.")
    env = load_env()
    execute = resolve_execute()
    realm_a, realm_b = Realm("A", env), Realm("B", env)
    mode = "EXECUTE-SANDBOX" if execute else "DRY RUN"
    print(f"[{mode}] Developer fee test — entity {args.entity}, base {args.base:,.2f}, "
          f"5% fee = {fee:,.2f}")
    audit({"event": "dev_fee_test_start", "mode": mode, "entity": args.entity,
           "base": args.base, "fee": fee, "doc": doc})

    # ---------- REALM A: Bill (partnership owes ONLY the 5% fee) ----------
    a_refs = {}
    for entity, name, field in [("Vendor", "IC - STV CM", "DisplayName"),
                                ("Item", "FEE-DEV", "Name"),
                                ("Department", args.location_a, "Name"),
                                ("Class", args.class_a, "Name"),
                                ("Customer", args.customer_a, "FullyQualifiedName")]:
        obj = find_one(realm_a, entity, name, field) if execute else {"Id": "DRYRUN"}
        if execute and not obj:
            sys.exit(f"REFUSED (PR-043): {entity} '{name}' not found in Realm A.")
        a_refs[entity] = obj
    bill = {
        "VendorRef": {"value": a_refs["Vendor"]["Id"]},
        "TxnDate": str(date.today()),
        "DocNumber": doc,
        "DepartmentRef": {"value": a_refs["Department"]["Id"]},
        "Line": [{
            "DetailType": "ItemBasedExpenseLineDetail",
            "Amount": fee,
            "Description": f"5% developer fee — {args.entity} — base {args.base:,.2f} (sandbox test)",
            "ItemBasedExpenseLineDetail": {
                "ItemRef": {"value": a_refs["Item"]["Id"]},
                "Qty": 1, "UnitPrice": fee,
                "ClassRef": {"value": a_refs["Class"]["Id"]},
                "CustomerRef": {"value": a_refs["Customer"]["Id"]},
                "BillableStatus": "NotBillable",
            },
        }],
    }

    # ---------- REALM B: Invoice (parent books 5% Developer Fee Income) ----------
    b_income = find_one(realm_b, "Account", "Developer Fee Income", "Name") if execute else {"Id": "DRYRUN"}
    b_loc = find_one(realm_b, "Department", "15 STV CM", "Name") if execute else {"Id": "DRYRUN"}
    b_class = find_one(realm_b, "Class", "90 Parent Overhead", "Name") if execute else {"Id": "DRYRUN"}
    if execute and not (b_income and b_loc and b_class):
        sys.exit("REFUSED: Realm B needs account 'Developer Fee Income', location '15 STV CM', "
                 "class '90 Parent Overhead'. Seed Realm B first.")
    fixture_item = ensure_fixture(realm_b, "Item", {
        "Name": "SBX TEST Dev Fee Income", "Type": "Service",
        "Description": "SANDBOX TEST fixture — dev fee income item (safe to ignore in reports)",
        "IncomeAccountRef": {"value": b_income["Id"]},
    }, "fixture|item|devfee", execute)
    fixture_cust = ensure_fixture(realm_b, "Customer", {
        "DisplayName": f"SBX TEST - {args.entity} (IC)",
    }, f"fixture|customer|{args.entity}", execute)
    invoice = {
        "CustomerRef": {"value": fixture_cust["Id"]},
        "TxnDate": str(date.today()),
        "DocNumber": doc,
        "DepartmentRef": {"value": b_loc["Id"]},
        "Line": [{
            "DetailType": "SalesItemLineDetail",
            "Amount": fee,
            "Description": f"5% developer fee income — {args.entity} — base {args.base:,.2f} (sandbox test)",
            "SalesItemLineDetail": {
                "ItemRef": {"value": fixture_item["Id"]},
                "Qty": 1, "UnitPrice": fee,
                "ClassRef": {"value": b_class["Id"]},
            },
        }],
    }

    if not execute:
        print(f"  [DRY RUN] Realm A: Bill 'IC - STV CM' item FEE-DEV {fee:,.2f} "
              f"@ {args.location_a} / {args.class_a} / {args.customer_a}")
        print(f"  [DRY RUN] Realm B: Invoice 'Developer Fee Income' {fee:,.2f} "
              f"@ 15 STV CM / 90 Parent Overhead")
        print("  COMMISSIONS: not booked — rates/recipients unresolved; owner approval required.")
        print("Run again with --execute-sandbox to post both sides.")
        return

    for r in (realm_a, realm_b):
        ok, _ = r.assert_company()
        if not ok:
            sys.exit("REFUSED: company sanity check failed — not writing.")
    try:
        a_obj = realm_a.create("Bill", bill, f"devfee|A|{doc}")
        print(f"  Realm A Bill Id {a_obj['Id']} TotalAmt={a_obj.get('TotalAmt')}")
    except QboError as e:
        sys.exit(f"Realm A bill failed (HTTP {e.status}) — pair NOT attempted in Realm B (atomic-or-nothing).")
    try:
        b_obj = realm_b.create("Invoice", invoice, f"devfee|B|{doc}")
        print(f"  Realm B Invoice Id {b_obj['Id']} TotalAmt={b_obj.get('TotalAmt')}")
    except QboError as e:
        audit({"event": "dev_fee_pair_partial", "doc": doc, "realm_a_bill": a_obj.get("Id"),
               "error": "Realm B invoice failed — VOID REALM A BILL MANUALLY IN QBO UI (PR-020)"})
        sys.exit(f"Realm B invoice failed (HTTP {e.status}). PAIR IS PARTIAL — void Realm A "
                 f"Bill Id {a_obj.get('Id')} manually in the QBO UI (PR-020 compensating action).")
    tie = (a_obj.get("TotalAmt") == b_obj.get("TotalAmt") == fee)
    audit({"event": "dev_fee_test_done", "doc": doc, "fee": fee, "tie": tie,
           "realm_a_bill": a_obj.get("Id"), "realm_b_invoice": b_obj.get("Id"),
           "commissions_booked": False,
           "commission_status": "UNRESOLVED — owner approval required before any accrual"})
    print(f"  PAIR TIE CHECK: {'PASS' if tie else 'FAIL'} (A bill == B invoice == {fee:,.2f})")
    print("  COMMISSIONS: not booked — unresolved, owner approval required (by design).")


if __name__ == "__main__":
    main()
