"""build_invoiceproof_packet.py — build (and optionally send) a SwarmSync InvoiceProof scan packet.

Usage (local checks only — no network by default):
    python scripts/build_invoiceproof_packet.py --vendor "GC - Elite Construction USA (TX)" \
        --invoice-no INV-1001 --amount 12500.00 [--po PO-77] [--line-items-total 12500.00] \
        [--bank-routing 124000054] [--project "Madison West"] [--location "04 Madison Park"] \
        [--class "40 Vertical"] [--item "003 Concrete"] [--source "gmail:msgid123"] [--send]

Local pre-checks (run always): duplicate vs logs/invoice_ledger.jsonl, line-item math,
bank-change risk vs last known routing, missing coding (project/Location/Class/Item),
missing support. Local verdict: PASS / FLAG / FAIL.

--send POSTs to SwarmSync InvoiceProof (https://api.swarmsync.ai/invoice-proof/scan)
using SWARMSYNC_API_KEY (or INVOICEPROOF_API_KEY) as Bearer key. SwarmSync riskLevel
maps LOW->PASS, MEDIUM->FLAG, HIGH/CRITICAL->FAIL; the STRICTER of local/remote wins.
The packet JSON is written to invoiceproof_packets/ for the approval workflow.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qbo_common import ROOT, audit, load_env, redact  # noqa: E402

LEDGER = os.path.join(ROOT, "logs", "invoice_ledger.jsonl")
PACKET_DIR = os.path.join(ROOT, "invoiceproof_packets")
SWARMSYNC_BASE = "https://api.swarmsync.ai"
RISK_TO_VERDICT = {"LOW": "PASS", "MEDIUM": "FLAG", "HIGH": "FAIL", "CRITICAL": "FAIL"}
VERDICT_RANK = {"PASS": 0, "FLAG": 1, "FAIL": 2}


def load_ledger():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def local_checks(inv, ledger):
    findings = []
    for old in ledger:
        if old.get("vendor") == inv["vendor"] and old.get("invoiceNo") == inv["invoiceNo"]:
            findings.append(("FAIL", "duplicate_invoice",
                             f"vendor+invoiceNo already seen on {old.get('ts', '?')}"))
        elif (old.get("vendor") == inv["vendor"] and old.get("amount") == inv["amount"]
              and old.get("invoiceNo") != inv["invoiceNo"]):
            findings.append(("FLAG", "possible_modified_duplicate",
                             f"same vendor+amount under different invoiceNo {old.get('invoiceNo')}"))
        if (inv.get("bankRouting") and old.get("vendor") == inv["vendor"]
                and old.get("bankRouting") and old["bankRouting"] != inv["bankRouting"]):
            findings.append(("FAIL", "bank_change_risk",
                             "routing differs from last known — BEC red flag, out-of-band verify"))
    if inv.get("lineItemsTotal") is not None and round(inv["lineItemsTotal"], 2) != round(inv["amount"], 2):
        findings.append(("FAIL", "line_item_math_error",
                         f"lines {inv['lineItemsTotal']:.2f} != total {inv['amount']:.2f}"))
    for field, code in [("project", "missing_project"), ("location", "missing_location"),
                        ("class", "missing_class"), ("item", "missing_item")]:
        if not inv.get(field):
            findings.append(("FLAG", code, f"{field} not coded — PR-043 never guess"))
    if not inv.get("source"):
        findings.append(("FLAG", "missing_support", "no source email/file reference"))
    if inv["amount"] <= 0:
        findings.append(("FAIL", "invalid_amount", "amount must be positive"))
    if inv["amount"] == round(inv["amount"], -2) and inv["amount"] >= 5000:
        findings.append(("FLAG", "round_dollar_amount", "large round-dollar amount"))
    verdict = "PASS"
    for sev, _, _ in findings:
        if VERDICT_RANK[sev] > VERDICT_RANK[verdict]:
            verdict = sev
    return verdict, findings


def send_to_swarmsync(inv, key):
    body = {"invoices": [{k: v for k, v in {
        "vendor": inv["vendor"], "invoiceNo": inv["invoiceNo"], "amount": inv["amount"],
        "po": inv.get("po"), "bankRouting": inv.get("bankRouting"),
        "lineItemsTotal": inv.get("lineItemsTotal")}.items() if v is not None}]}
    req = urllib.request.Request(
        f"{SWARMSYNC_BASE}/invoice-proof/scan", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", required=True)
    ap.add_argument("--invoice-no", required=True)
    ap.add_argument("--amount", type=float, required=True)
    ap.add_argument("--po", default=None)
    ap.add_argument("--line-items-total", type=float, default=None)
    ap.add_argument("--bank-routing", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--location", default=None)
    ap.add_argument("--class", dest="klass", default=None)
    ap.add_argument("--item", default=None)
    ap.add_argument("--source", default=None, help="source email/file citation, e.g. gmail:<msgid>")
    ap.add_argument("--send", action="store_true", help="also send to SwarmSync InvoiceProof")
    args = ap.parse_args()

    inv = {"vendor": args.vendor, "invoiceNo": args.invoice_no, "amount": args.amount,
           "po": args.po, "lineItemsTotal": args.line_items_total,
           "bankRouting": args.bank_routing, "project": args.project,
           "location": args.location, "class": args.klass, "item": args.item,
           "source": args.source}
    ledger = load_ledger()
    verdict, findings = local_checks(inv, ledger)
    packet = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "invoice": {k: v for k, v in inv.items() if k != "bankRouting"},
        "bank_routing_last4": args.bank_routing[-4:] if args.bank_routing else None,
        "local_verdict": verdict,
        "local_findings": [{"severity": s, "code": c, "detail": d} for s, c, d in findings],
        "swarmsync": None,
        "final_verdict": verdict,
        "recommended_next_action": {
            "PASS": "route to approval packet (05_Pending_Approval)",
            "FLAG": "human review required — override_reason mandatory to approve",
            "FAIL": "QUARANTINE — do not approve, do not post; investigate findings",
        }[verdict],
        "source_citation": args.source or "MISSING — every recommendation must cite its source",
    }
    fail_reason = None
    if args.send:
        env = load_env()
        key = env.get("SWARMSYNC_API_KEY") or env.get("INVOICEPROOF_API_KEY")
        if not key:
            fail_reason = "no SWARMSYNC_API_KEY/INVOICEPROOF_API_KEY in .env"
        else:
            try:
                scan = send_to_swarmsync(inv, key)
                remote = RISK_TO_VERDICT.get(scan.get("riskLevel", "").upper(), "FLAG")
                packet["swarmsync"] = {"scanId": scan.get("scanId"),
                                       "riskLevel": scan.get("riskLevel"),
                                       "findingCount": scan.get("findingCount"),
                                       "findings": scan.get("findings", [])[:20],
                                       "mapped_verdict": remote}
                if VERDICT_RANK[remote] > VERDICT_RANK[packet["final_verdict"]]:
                    packet["final_verdict"] = remote
            except Exception as e:  # noqa: BLE001
                fail_reason = f"SwarmSync call failed: {e}"
        if fail_reason:
            # FAIL CLOSED (PR-003): proof service unavailable -> no PASS allowed
            packet["swarmsync"] = {"error": redact(str(fail_reason))}
            if packet["final_verdict"] == "PASS":
                packet["final_verdict"] = "FLAG"
                packet["recommended_next_action"] = ("proof service unavailable — fail closed: "
                                                     "human review required (PR-003)")
    os.makedirs(PACKET_DIR, exist_ok=True)
    fname = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{args.vendor[:20]}_{args.invoice_no}.json"
    fname = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
    path = os.path.join(PACKET_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(packet, f, indent=2)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": packet["ts"], "vendor": inv["vendor"],
                            "invoiceNo": inv["invoiceNo"], "amount": inv["amount"],
                            "bankRouting": inv.get("bankRouting"),
                            "verdict": packet["final_verdict"]}) + "\n")
    audit({"event": "invoiceproof_packet", "vendor": inv["vendor"], "invoiceNo": inv["invoiceNo"],
           "amount": inv["amount"], "verdict": packet["final_verdict"],
           "packet_file": fname, "sent_to_swarmsync": bool(args.send and not fail_reason)})
    print(json.dumps({k: packet[k] for k in
                      ("final_verdict", "local_findings", "recommended_next_action", "source_citation")},
                     indent=2))
    print(f"packet written: {path}")


if __name__ == "__main__":
    main()
