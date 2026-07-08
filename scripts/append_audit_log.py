"""append_audit_log.py — append one structured event to the Co-work audit log (JSONL source of truth).

Usage:
    python scripts/append_audit_log.py --actor cowork --event-type invoice_reviewed \
        --source "gmail:18c2f4a" --summary "INV-1001 Elite Construction 12,500.00 PASS" \
        [--classification INVOICE] [--invoiceproof-verdict PASS] [--recommendation "approve"] \
        [--approver ben@summaterra.com] [--qbo-request-id abc123] [--qbo-result "Bill Id 42"] \
        [--final-status PENDING_APPROVAL] [--json '{"extra": "fields"}']

Schema: docs/AUDIT_LOG_SPEC.md. Log file: logs/cowork_audit_YYYYMMDD.jsonl (append-only).
Secrets and full bank account/routing numbers are refused/redacted — never store raw
bank data (masked last-4 only).
"""
import argparse
import json
import re
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qbo_common import LOG_DIR, redact  # noqa: E402

BANK_PATTERN = re.compile(r"\b\d{9}\b|\b\d{10,17}\b")  # routing / account shapes


def mask_bank_numbers(text):
    return BANK_PATTERN.sub(lambda m: "****" + m.group(0)[-4:], text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", required=True, help="cowork | ben | script name")
    ap.add_argument("--event-type", required=True)
    ap.add_argument("--source", required=True, help="source email/file citation (gmail:<id>, drive:<path>)")
    ap.add_argument("--summary", required=True)
    ap.add_argument("--classification", default=None)
    ap.add_argument("--sender", default=None)
    ap.add_argument("--attachment", default=None)
    ap.add_argument("--invoiceproof-verdict", default=None, choices=["PASS", "FLAG", "FAIL", None])
    ap.add_argument("--recommendation", default=None)
    ap.add_argument("--approver", default=None)
    ap.add_argument("--approval", default=None, choices=["approved", "rejected", "escalated", None])
    ap.add_argument("--qbo-request-id", default=None)
    ap.add_argument("--qbo-result", default=None)
    ap.add_argument("--final-status", default=None)
    ap.add_argument("--json", default=None, help="extra fields as a JSON object")
    args = ap.parse_args()

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": args.actor,
        "event_type": args.event_type,
        "source_ref": args.source,
        "summary": mask_bank_numbers(args.summary),
        "classification": args.classification,
        "sender": args.sender,
        "attachment": args.attachment,
        "invoiceproof_verdict": args.invoiceproof_verdict,
        "recommendation": args.recommendation,
        "approval": args.approval,
        "approver": args.approver,
        "qbo_request_id": args.qbo_request_id,
        "qbo_result": args.qbo_result,
        "final_status": args.final_status,
    }
    if args.json:
        extra = json.loads(args.json)
        for k, v in extra.items():
            if isinstance(v, str):
                extra[k] = mask_bank_numbers(v)
        event["extra"] = extra
    event = {k: v for k, v in event.items() if v is not None}
    line = redact(mask_bank_numbers(json.dumps(event, ensure_ascii=False)))
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"cowork_audit_{datetime.now(timezone.utc):%Y%m%d}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"audit event appended -> {path}")


if __name__ == "__main__":
    main()
