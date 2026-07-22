"""Put Next/Recent Due as col A; sort by real calendar date."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ENV = Path(r"C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra Gmail Automation\.env")
SID = "1oRD0CFHBGeTtZhkQC9Pfo_NLAp3AUqyZ486jPvwQX_o"


def load_env(path: Path) -> dict:
    vals = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def creds(env: dict) -> Credentials:
    c = Credentials(
        token=None,
        refresh_token=env["STONE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env["GOOGLE_CLIENT_ID"],
        client_secret=env["GOOGLE_CLIENT_SECRET"],
    )
    c.refresh(Request())
    return c


def extract_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", s)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    m = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", s)
    if m:
        return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s[:20].strip(), fmt)
        except ValueError:
            continue
    return None


def sort_key(date_str: str) -> tuple:
    d = extract_date(date_str)
    if d:
        return (0, d.toordinal(), date_str)
    return (1, 999999, date_str or "")


def main() -> None:
    env = load_env(ENV)
    svc = build("sheets", "v4", credentials=creds(env))

    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=SID, range="'Payment Calendar'!A1:Z50")
        .execute()
    )
    rows = result.get("values") or []
    header = rows[0]
    data = rows[1:]
    print("CURRENT HEADER:", header)

    # Prefer actual next-due column, not "Typical Due Day"
    prefer = ["next / recent due", "next due", "next due date", "due date", "payment date"]
    date_idx = None
    for name in prefer:
        for i, h in enumerate(header):
            if (h or "").strip().lower() == name:
                date_idx = i
                break
        if date_idx is not None:
            break
    if date_idx is None:
        for i, h in enumerate(header):
            hl = (h or "").strip().lower()
            if "next" in hl and "due" in hl:
                date_idx = i
                break
    if date_idx is None:
        raise SystemExit(f"No next-due column in {header}")

    print(f"Using date col {date_idx}: {header[date_idx]!r}")

    # Rename for clarity as first column
    date_header = "Payment / Due Date"

    new_header = [date_header] + [h for i, h in enumerate(header) if i != date_idx]
    new_data = []
    for r in data:
        while len(r) < len(header):
            r.append("")
        date_val = r[date_idx]
        rest = [r[i] for i in range(len(header)) if i != date_idx]
        new_data.append([date_val] + rest)

    new_data.sort(key=lambda row: sort_key(row[0]))

    svc.spreadsheets().values().clear(
        spreadsheetId=SID, range="'Payment Calendar'!A1:Z100"
    ).execute()

    out = [new_header] + new_data
    svc.spreadsheets().values().update(
        spreadsheetId=SID,
        range="'Payment Calendar'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": out},
    ).execute()

    # Freeze header + first column for usability
    meta = svc.spreadsheets().get(spreadsheetId=SID).execute()
    sheet_id = next(
        s["properties"]["sheetId"]
        for s in meta["sheets"]
        if s["properties"]["title"] == "Payment Calendar"
    )
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SID,
        body={
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
                    }
                }
            ]
        },
    ).execute()

    print("NEW HEADER:", new_header[:6], "...")
    print("SORTED ROWS:")
    for r in out[1:]:
        print(f"  {(r[0] or '')[:45]:45} | {(r[1] if len(r)>1 else '')[:28]:28} | {(r[2] if len(r)>2 else '')[:40]}")
    print(f"\nhttps://docs.google.com/spreadsheets/d/{SID}/edit")


if __name__ == "__main__":
    main()
