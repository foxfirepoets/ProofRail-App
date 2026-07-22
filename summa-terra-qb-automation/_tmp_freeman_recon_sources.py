"""Pull Freeman Ranch loan / cash / bid source emails for recon sheet."""
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
        return re.sub(r"<[^>]+>", " ", parts[0][1])
    return ""


def list_attachments(payload: dict, out=None, prefix=""):
    if out is None:
        out = []
    filename = payload.get("filename") or ""
    body = payload.get("body", {})
    if filename and (body.get("attachmentId") or body.get("data")):
        out.append({"filename": filename, "mime": payload.get("mimeType"), "size": body.get("size"), "attId": body.get("attachmentId")})
    for child in payload.get("parts") or []:
        list_attachments(child, out)
    return out


def show(gmail, query, maxn=8, body_chars=3500):
    print(f"\n{'='*80}\nQUERY: {query}\n{'='*80}")
    r = gmail.users().messages().list(userId="me", q=query, maxResults=maxn).execute()
    for m in r.get("messages", []):
        full = gmail.users().messages().get(userId="me", id=m["id"], format="full").execute()
        hdrs = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
        atts = list_attachments(full.get("payload", {}))
        print(f"\n--- {m['id']} | {hdrs.get('Date')} | {hdrs.get('From')}")
        print(f"Subject: {hdrs.get('Subject')}")
        if atts:
            print("Attachments:", [a["filename"] for a in atts])
        body = decode_body(full.get("payload", {}))
        print(body[:body_chars])


def main():
    gmail = build("gmail", "v1", credentials=creds())
    queries = [
        "Freeman (Meritus OR Tommy) (bid OR budget OR proposal OR payapp OR VE) newer_than:90d",
        "Freeman (Arixa) (loan OR balance OR reserve OR draw OR statement) newer_than:120d",
        "subject:(Freeman Ranch) (invoice OR bid OR budget) newer_than:90d",
        "from:zach Freeman (bid OR Tommy OR Meritus OR VE) newer_than:60d",
        "Freeman Ranch cash OR checking OR UCCU newer_than:30d",
        "has:attachment Freeman (bid OR budget OR schedule OR reconcil) newer_than:90d",
    ]
    for q in queries:
        show(gmail, q)


if __name__ == "__main__":
    main()
