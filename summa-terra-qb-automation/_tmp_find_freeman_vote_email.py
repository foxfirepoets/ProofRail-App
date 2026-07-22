"""Find Porter/Mike Freeman Ranch vote email in stone@ Gmail."""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.stdout.reconfigure(encoding="utf-8")

ENV = Path(r"C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra Gmail Automation\.env")


def load_env(path: Path) -> dict:
    vals = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def creds():
    env = load_env(ENV)
    c = Credentials(
        token=None,
        refresh_token=env["STONE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env["GOOGLE_CLIENT_ID"],
        client_secret=env["GOOGLE_CLIENT_SECRET"],
    )
    c.refresh(Request())
    return c


def decode_body(payload: dict) -> str:
    parts = []

    def walk(p):
        mime = p.get("mimeType", "")
        body = p.get("body", {})
        data = body.get("data")
        if data and mime in ("text/plain", "text/html"):
            text = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
            parts.append((mime, text))
        for child in p.get("parts") or []:
            walk(child)

    walk(payload)
    for mime, text in parts:
        if mime == "text/plain":
            return text
    if parts:
        html = parts[0][1]
        return re.sub(r"<[^>]+>", " ", html)
    return ""


def main():
    gmail = build("gmail", "v1", credentials=creds())
    prof = gmail.users().getProfile(userId="me").execute()
    print("Authenticated as:", prof.get("emailAddress"))

    queries = [
        "Freeman Ranch (vote OR votes OR VOTE)",
        "from:porter (Freeman OR vote OR Wednesday)",
        "from:mike (Freeman OR vote) newer_than:45d",
        "subject:(Freeman) newer_than:60d",
        "July 22 Freeman",
        "\"Freeman Ranch\" newer_than:30d",
    ]

    seen = set()
    hits = []
    for q in queries:
        print(f"\n=== QUERY: {q} ===")
        r = gmail.users().messages().list(userId="me", q=q, maxResults=15).execute()
        msgs = r.get("messages", [])
        print("count:", len(msgs))
        for m in msgs:
            mid = m["id"]
            if mid in seen:
                continue
            seen.add(mid)
            full = gmail.users().messages().get(userId="me", id=mid, format="full").execute()
            hdrs = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            snippet = full.get("snippet", "")
            print("-", mid, "|", hdrs.get("Date", ""), "|", hdrs.get("From", ""), "|", hdrs.get("Subject", ""))
            print("  snippet:", snippet[:200])
            hits.append((mid, hdrs, full))

    # Prefer vote-related subjects
    print("\n\n===== FULL BODIES (vote-relevant) =====")
    for mid, hdrs, full in hits:
        subj = (hdrs.get("Subject") or "").lower()
        snip = (full.get("snippet") or "").lower()
        if any(k in subj or k in snip for k in ("vote", "wednesday", "july 22", "ballot", "proxy", "consent")):
            body = decode_body(full.get("payload", {}))
            print("\n" + "=" * 80)
            print("ID:", mid)
            print("Date:", hdrs.get("Date"))
            print("From:", hdrs.get("From"))
            print("To:", hdrs.get("To"))
            print("Cc:", hdrs.get("Cc"))
            print("Subject:", hdrs.get("Subject"))
            print("-" * 40)
            print(body[:8000])


if __name__ == "__main__":
    main()
