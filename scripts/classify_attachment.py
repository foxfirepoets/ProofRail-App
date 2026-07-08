"""classify_attachment.py — offline document classifier for the ProofRail intake taxonomy.

Usage:
    python scripts/classify_attachment.py --file "path/to/attachment.pdf" [--from "sender@x.com"] [--subject "..."]

No network calls. Classifies by filename/subject keywords into the MailOps taxonomy,
suggests the Gmail label + Drive folder + machine-parseable filename, and flags
historical/example documents as DO NOT POST. Appends a JSONL audit event.
Output: one JSON object on stdout (Co-work reads this).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qbo_common import audit  # noqa: E402

RULES = [
    ("DRAW_SHEET", r"draw|g702|g703|pay\s*app|payapp|pci\b|schedule of values|sov\b"),
    ("LIEN_WAIVER", r"lien|waiver"),
    ("INVOICE", r"invoice|inv[\s_\-#]?\d|bill\b|statement of charges"),
    ("BANK_NOTICE", r"bank (change|update|notice)|routing|remit(tance)? (change|update)|ach (change|update)"),
    ("STATEMENT", r"statement|stmt"),
    ("W9", r"w-?9"),
    ("INSURANCE", r"insurance|coi\b|certificate of (liability|insurance)|acord"),
    ("INSPECTION", r"inspection|inspector"),
    ("LENDER_DOC", r"lender|loan|arixa|canyon view|copa|trevian|intercap|granite cu|first state"),
    ("APPROVAL", r"approv"),
]

LABEL_BY_CLASS = {
    "INVOICE": "ProofRail/Invoices", "DRAW_SHEET": "ProofRail/Draws",
    "LIEN_WAIVER": "ProofRail/Draws", "BANK_NOTICE": "ProofRail/Risk-BankChange",
    "STATEMENT": "ProofRail/Statements", "W9": "ProofRail/W9-Insurance",
    "INSURANCE": "ProofRail/W9-Insurance", "INSPECTION": "ProofRail/Docs",
    "LENDER_DOC": "ProofRail/Lender", "APPROVAL": "ProofRail/Approval",
    "OTHER": "ProofRail/Docs",
}
FOLDER_BY_CLASS = {
    "INVOICE": "03_Vendor_Invoices", "DRAW_SHEET": "02_Draw_Packages",
    "LIEN_WAIVER": "02_Draw_Packages", "BANK_NOTICE": "10_Exceptions",
    "STATEMENT": "01_Email_Attachments", "W9": "01_Email_Attachments",
    "INSURANCE": "01_Email_Attachments", "INSPECTION": "02_Draw_Packages",
    "LENDER_DOC": "01_Email_Attachments", "APPROVAL": "05_Pending_Approval",
    "OTHER": "00_Inbox",
}
HISTORICAL = r"historical|example|sample|do[\s_-]?not[\s_-]?post|superseded|void"


def classify(filename, subject="", sender=""):
    hay = f"{filename} {subject} {sender}".lower()
    cls = "OTHER"
    for name, pat in RULES:
        if re.search(pat, hay):
            cls = name
            break
    do_not_post = bool(re.search(HISTORICAL, hay))
    # filename-law check: invoices should be YYYYMMDD_ENTITY_VENDOR_INVno_amount.pdf
    convention_ok = bool(re.match(r"^\d{8}_[A-Za-z0-9]+_.+_(INV|DRAW|stmt)", os.path.basename(filename)))
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "file": os.path.basename(filename),
        "classification": cls,
        "do_not_post": do_not_post,
        "suggested_gmail_label": "ProofRail/DoNotPost" if do_not_post else LABEL_BY_CLASS[cls],
        "suggested_drive_folder": ("14_Do_Not_Post" if do_not_post
                                   else "13_Historical_Examples" if re.search(r"historical|example", hay)
                                   else FOLDER_BY_CLASS[cls]),
        "filename_convention_ok": convention_ok,
        "bank_change_risk": cls == "BANK_NOTICE" or bool(re.search(r"routing|new bank|updated account", hay)),
        "next_action": ("HARD STOP — file to Do Not Post, never process"
                        if do_not_post else
                        "route to InvoiceProof packet builder" if cls == "INVOICE" else
                        "route to draw review" if cls == "DRAW_SHEET" else
                        "OUT-OF-BAND VERIFICATION REQUIRED before any change" if cls == "BANK_NOTICE" else
                        "file and log"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--subject", default="")
    ap.add_argument("--from", dest="sender", default="")
    args = ap.parse_args()
    result = classify(args.file, args.subject, args.sender)
    audit({"event": "classify_attachment", **result})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
