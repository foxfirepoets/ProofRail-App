"""Parse 7-15 Meritus proposal + look for VE options and cash."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.stdout.reconfigure(encoding="utf-8")

OUT = Path(r"C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra QB Automation\_tmp_freeman_recon_docs")
ENV = Path(r"C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra Gmail Automation\.env")

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader


def load_env(path: Path) -> dict:
    vals = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def main():
    for name in [
        "7-15-2026_Updated_Construction_Pricing.pdf",
        "Freeman_proposal_and_SOV_7-15-26_Signed.pdf",
        "2025_Pricing_Freeman_Ranch.pdf",
    ]:
        p = OUT / name
        r = PdfReader(str(p))
        text = "\n".join((pg.extract_text() or "") for pg in r.pages)
        print("=" * 80)
        print(name, "pages", len(r.pages))
        # print full for pricing docs
        print(text)
        print()

    # Search Drive for VE / value engineering / June-July bank stmts
    env = load_env(ENV)
    c = Credentials(
        token=None,
        refresh_token=env["STONE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env["GOOGLE_CLIENT_ID"],
        client_secret=env["GOOGLE_CLIENT_SECRET"],
    )
    c.refresh(Request())
    drive = build("drive", "v3", credentials=c)
    gmail = build("gmail", "v1", credentials=c)

    for q in [
        "fullText contains 'Freeman' and (fullText contains 'value engineering' or fullText contains 'VE option' or name contains 'VE ') and trashed=false",
        "name contains 'Freeman' and (name contains '2026.06' or name contains '2026.07' or name contains 'June' or name contains 'July') and (name contains 'UCCU' or name contains 'Bank' or name contains 'Statement' or name contains 'Recon') and trashed=false",
        "name contains 'Freeman' and name contains '2026.06' and trashed=false",
    ]:
        print("\nDRIVE Q:", q[:100])
        files = (
            drive.files()
            .list(
                q=q,
                pageSize=15,
                fields="files(id,name,modifiedTime,webViewLink)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
                orderBy="modifiedTime desc",
            )
            .execute()
            .get("files", [])
        )
        for f in files:
            print(f"{f['modifiedTime']} | {f['name']} | {f['id']}")

    # Payment calendar / UCCU for freeman cash
    print("\n===== Gmail cash mentions =====")
    for q in [
        "Freeman (checking OR UCCU OR balance OR cash) newer_than:45d",
        "subject:(Freeman) (paid OR wire OR balance) newer_than:30d",
    ]:
        r = gmail.users().messages().list(userId="me", q=q, maxResults=8).execute()
        for m in r.get("messages", []):
            full = gmail.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
            hdrs = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            print(m["id"], hdrs.get("Date"), hdrs.get("From"), hdrs.get("Subject"), "|", full.get("snippet", "")[:180])


if __name__ == "__main__":
    main()
