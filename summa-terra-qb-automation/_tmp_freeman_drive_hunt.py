"""Search Drive + Gmail for Freeman bid / loan / cash docs; download key attachments."""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

sys.stdout.reconfigure(encoding="utf-8")
ENV = Path(r"C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra Gmail Automation\.env")
OUT = Path(r"C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra QB Automation\_tmp_freeman_recon_docs")
OUT.mkdir(parents=True, exist_ok=True)


def load_env(path: Path) -> dict:
    vals = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def creds(scopes=None):
    env = load_env(ENV)
    c = Credentials(
        token=None,
        refresh_token=env["STONE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env["GOOGLE_CLIENT_ID"],
        client_secret=env["GOOGLE_CLIENT_SECRET"],
        scopes=scopes,
    )
    c.refresh(Request())
    return c


def drive_search(drive, q, page_size=20):
    r = drive.files().list(
        q=q,
        pageSize=page_size,
        fields="files(id,name,mimeType,modifiedTime,owners,webViewLink,size)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
        orderBy="modifiedTime desc",
    ).execute()
    return r.get("files", [])


def main():
    # Drive often needs broader scopes already on the token
    c = creds()
    drive = build("drive", "v3", credentials=c)
    gmail = build("gmail", "v1", credentials=c)

    queries = [
        "name contains 'Freeman' and (name contains 'bid' or name contains 'Bid' or name contains 'budget' or name contains 'Budget' or name contains 'Meritus' or name contains 'Tommy' or name contains 'VE' or name contains 'SOV' or name contains 'reconcil') and trashed=false",
        "fullText contains 'Freeman Ranch' and (fullText contains 'Meritus' or fullText contains 'Tommy') and trashed=false",
        "name contains 'Arixa' and name contains 'Freeman' and trashed=false",
        "name contains 'Freeman' and (name contains 'UCCU' or name contains 'statement' or name contains 'Statement') and trashed=false",
        "fullText contains 'Freeman Ranch' and (name contains 'GC' or name contains 'Bid Review' or name contains 'Notice') and trashed=false",
    ]
    seen = set()
    print("===== DRIVE HITS =====")
    for q in queries:
        print(f"\n-- {q[:90]}...")
        try:
            files = drive_search(drive, q)
        except Exception as e:
            print("ERROR:", e)
            continue
        for f in files:
            if f["id"] in seen:
                continue
            seen.add(f["id"])
            owners = ",".join(o.get("emailAddress", "") for o in f.get("owners", []) or [])
            print(f"{f.get('modifiedTime')} | {f['id']} | {f.get('name')} | {f.get('mimeType')} | {owners}")
            print("  ", f.get("webViewLink"))

    # Pull Gmail attachments from likely bid threads
    print("\n===== GMAIL ATTACHMENT SCAN =====")
    for q in [
        "Freeman (Meritus OR Tommy OR bid OR budget OR VE OR SOV) has:attachment newer_than:120d",
        "subject:(Freeman Ranch) has:attachment newer_than:90d",
        "from:zach@summaterraventures.com Freeman has:attachment newer_than:90d",
    ]:
        print(f"\nQ: {q}")
        r = gmail.users().messages().list(userId="me", q=q, maxResults=15).execute()
        for m in r.get("messages", []):
            full = gmail.users().messages().get(userId="me", id=m["id"], format="full").execute()
            hdrs = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            atts = []

            def walk(p):
                fn = p.get("filename") or ""
                body = p.get("body", {})
                if fn and body.get("attachmentId"):
                    atts.append((fn, body["attachmentId"], body.get("size"), p.get("mimeType")))
                for ch in p.get("parts") or []:
                    walk(ch)

            walk(full.get("payload", {}))
            if not atts:
                continue
            print(f"{m['id']} | {hdrs.get('Date')} | {hdrs.get('From')} | {hdrs.get('Subject')}")
            for fn, att_id, size, mime in atts:
                print(f"  ATT: {fn} ({size}) {mime}")
                # download non-image useful files
                low = fn.lower()
                if any(x in low for x in (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".xlsm")) and "image" not in low:
                    data = gmail.users().messages().attachments().get(userId="me", messageId=m["id"], id=att_id).execute()
                    raw = base64.urlsafe_b64decode(data["data"])
                    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in fn)[:120]
                    path = OUT / f"{m['id'][:8]}_{safe}"
                    path.write_bytes(raw)
                    print(f"    -> saved {path} ({len(raw)} bytes)")


if __name__ == "__main__":
    main()
