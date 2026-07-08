"""qbo_create_sandbox_bill.py — create ONE fully-coded test vendor bill in Realm A (sandbox).

Usage (DRY RUN default; nothing posts without --execute-sandbox):
    python scripts/qbo_create_sandbox_bill.py \
        --vendor "GC - Elite Construction USA (TX)" \
        --item "003 Concrete" --amount 12500.00 \
        --location "04 Madison Park" --class "40 Vertical" \
        --customer "Madison West:Vertical" \
        --docnumber INV-TEST-001 [--txndate 2026-07-05] [--execute-sandbox]

Dimensional law enforced: every bill line carries Location (header DepartmentRef),
Class, Customer(project), and Item (cost code). Refuses to post if any ref is
missing — never guesses (PR-043). Duplicate DocNumber+Vendor is refused (dedup).
Deterministic RequestId prevents API-level double-posting.
"""
import argparse
import sys
from datetime import date

from qbo_common import QboError, audit, bootstrap


def find_one(realm, entity, name, field="Name"):
    safe = name.replace("'", "\\'")
    rows = realm.query(f"SELECT * FROM {entity} WHERE {field} = '{safe}'") \
        .get("QueryResponse", {}).get(entity, [])
    return rows[0] if rows else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", required=True)
    ap.add_argument("--item", required=True)
    ap.add_argument("--amount", type=float, required=True)
    ap.add_argument("--location", required=True)
    ap.add_argument("--class", dest="klass", required=True)
    ap.add_argument("--customer", required=True, help="project or project:phase (FullyQualifiedName)")
    ap.add_argument("--docnumber", required=True, help="vendor invoice number")
    ap.add_argument("--txndate", default=str(date.today()))
    ap.add_argument("--execute-sandbox", action="store_true")
    args = ap.parse_args()

    realm, execute = bootstrap("A")  # vendor bills post to Realm A in this test build
    if args.amount <= 0:
        sys.exit("REFUSED: amount must be positive.")
    if len(args.docnumber) > 21:
        sys.exit(f"REFUSED: DocNumber '{args.docnumber}' is {len(args.docnumber)} chars — QBO max is 21.")

    refs = {}
    lookups = [("Vendor", args.vendor, "DisplayName"), ("Item", args.item, "Name"),
               ("Department", args.location, "Name"), ("Class", args.klass, "Name"),
               ("Customer", args.customer, "FullyQualifiedName")]
    for entity, name, field in lookups:
        obj = find_one(realm, entity, name, field)
        if not obj:
            sys.exit(f"REFUSED (PR-043 never guess): {entity} '{name}' not found in {realm.label}. "
                     "Fix the coding or seed the missing record first.")
        refs[entity] = obj

    dupes = realm.query(
        "SELECT * FROM Bill WHERE DocNumber = '{d}'".format(d=args.docnumber.replace("'", "\\'"))
    ).get("QueryResponse", {}).get("Bill", [])
    if any(b.get("VendorRef", {}).get("value") == refs["Vendor"]["Id"] for b in dupes):
        sys.exit(f"REFUSED (duplicate): Bill DocNumber '{args.docnumber}' already exists for "
                 f"vendor '{args.vendor}'. No duplicate bills.")

    bill = {
        "VendorRef": {"value": refs["Vendor"]["Id"]},
        "TxnDate": args.txndate,
        "DocNumber": args.docnumber,
        "DepartmentRef": {"value": refs["Department"]["Id"]},
        "Line": [{
            "DetailType": "ItemBasedExpenseLineDetail",
            "Amount": round(args.amount, 2),
            "Description": f"Sandbox test bill {args.docnumber}",
            "ItemBasedExpenseLineDetail": {
                "ItemRef": {"value": refs["Item"]["Id"]},
                "Qty": 1,
                "UnitPrice": round(args.amount, 2),
                "ClassRef": {"value": refs["Class"]["Id"]},
                "CustomerRef": {"value": refs["Customer"]["Id"]},
                "BillableStatus": "NotBillable",
            },
        }],
    }
    natural_key = f"bill|{args.vendor}|{args.docnumber}|{args.amount}"
    if not execute:
        print("[DRY RUN] would create Bill in", realm.label)
        print(f"  vendor={args.vendor} doc={args.docnumber} amount={args.amount:.2f}")
        print(f"  location={args.location} class={args.klass} customer={args.customer} item={args.item}")
        print("Run again with --execute-sandbox to post to the sandbox.")
        audit({"event": "test_bill_dry_run", "realm": "A", "doc": args.docnumber,
               "vendor": args.vendor, "amount": args.amount})
        return
    ok, name = realm.assert_company()
    if not ok:
        sys.exit("REFUSED: company-name sanity check failed — not writing.")
    try:
        obj = realm.create("Bill", bill, natural_key)
        print(f"Created Bill Id {obj['Id']} DocNumber {args.docnumber} for {args.amount:.2f} "
              f"in {realm.label}. TotalAmt={obj.get('TotalAmt')}")
    except QboError as e:
        sys.exit(f"Bill create failed: HTTP {e.status} — see logs/qbo_seed_*.jsonl")


if __name__ == "__main__":
    main()
