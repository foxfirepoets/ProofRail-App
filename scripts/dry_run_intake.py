"""dry_run_intake.py — SAFE, READ-ONLY dry run of the ProofRail inbox stage.

Reads the real inbox (read-only), runs the deterministic pre-classifier on each message, and posts
ONE summary to your Space. It does NOT label, archive, trash, draft, send, or touch QBO — nothing is
mutated. This is what you watch during the dry-run window before arming any live switch.

Usage:  python scripts/dry_run_intake.py [--n 15] [--notify]
"""
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gmail_client import GmailClient
from intake_preclassifier import preclassify


def main():
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 15
    notify = "--notify" in sys.argv
    gc = GmailClient()
    ids = gc.search("in:inbox newer_than:7d", max_results=n)
    rows, urg, wf = [], Counter(), Counter()
    p0 = []
    for mid in ids:
        m = gc.get_meta(mid)
        h = m["headers"]
        email = {"sender": h.get("From", ""), "subject": h.get("Subject", ""),
                 "body": m.get("snippet", "")}
        r = preclassify(email)
        urg[r.urgency] += 1
        wf[r.workflow] += 1
        rows.append((r.urgency, r.workflow, r.entity or "-", h.get("From", "")[:32], h.get("Subject", "")[:44]))
        if r.requires_p0:
            p0.append((h.get("From", ""), h.get("Subject", ""), "bank-change" if r.bank_change_risk else "BEC/legal"))

    print(f"DRY-RUN intake — {len(rows)} inbox emails (last 7d), READ-ONLY, nothing modified\n")
    print(f"{'URG':<4}{'WORKFLOW':<24}{'ENTITY':<26}{'FROM':<34}SUBJECT")
    for u, w, e, fr, s in rows:
        print(f"{u:<4}{w:<24}{e:<26}{fr:<34}{s}")
    print(f"\nby urgency: {dict(urg)}")
    print(f"by workflow: {dict(wf)}")
    if p0:
        print(f"\n⚠ P0 items ({len(p0)}): " + "; ".join(f"{s} ({k})" for _, s, k in p0))

    if notify:
        import notify_chat
        summary = (f"Dry-run intake: {len(rows)} inbox emails classified (READ-ONLY, nothing changed).\n"
                   f"Urgency: {dict(urg)}\n"
                   f"P0/bank-change: {len(p0)}" + (" — " + "; ".join(s for _, s, _ in p0) if p0 else " — none"))
        notify_chat.fire_p1(summary)
        for sender, subj, kind in p0:
            notify_chat.fire_p0(f"Dry-run flagged {kind}: {sender} — “{subj}” (read-only; verify manually).")
        print("\n(summary posted to Spaces)")


if __name__ == "__main__":
    main()
