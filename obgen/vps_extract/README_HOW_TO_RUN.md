# Pull QuickBooks Enterprise balances → J: drive → QBO Advanced

**You run this ON the Rightworks VPS** (that's where QuickBooks Desktop + QODBC live). It reads
each company file and drops CSVs onto the J: drive, which syncs back to your PC where obgen turns
them into the QBO Advanced opening balances. **It is read-only — it cannot change QuickBooks.**

## One-time check before you start
- **QODBC installed?** QuickBooks → it should have a "QODBC" / "QuickBooks Data" data source. (This
  is what Adam's setup already used.)
- **32-bit vs 64-bit.** QODBC is usually **32-bit**. If so, run the **32-bit** PowerShell:
  `C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`
  (Yes — "SysWOW64" is the *32-bit* one on 64-bit Windows. If the script says it can't find the
  DSN, this bitness mismatch is almost always why — just switch to the other PowerShell.)

## Do this for EACH company file (repeat ~18 times)
1. In **QuickBooks on the VPS, open the entity's company file.** QODBC reads whatever file is open,
   so only one at a time.
2. Open PowerShell (32-bit — see above), `cd` into this `vps_extract` folder (it's on the J: drive,
   so it's visible on the VPS too).
3. Run, passing the matching **entity key** (left column below):
   ```
   powershell -ExecutionPolicy Bypass -File .\Extract-QBEnterprise.ps1 -Entity 12SB
   ```
4. Read the summary. **BALANCED (green)** = good, move on. Empty or NOT BALANCED = note it and
   double-check the right file was open.

That's it — the CSVs land in `_output\<Entity>\` on the J: drive and sync straight back to your PC.

## The 18 entity keys (use these exactly for -Entity)
`12SB · HLN · Union · Madison · Quincy · Vic · SummaElite · Ventura · Freeman · Carlo · Ledges ·
RMTexas · ElephantRock · EJH · Dominus · RockCreek · Camden · Ensign`

(These match `obgen\config\entities.yaml`. The script records the file's real Company Name in
`_meta.json` so obgen's safety check can confirm the right file was open before it loads anything.)

## What you get per entity (in `_output\<Entity>\`)
| File | What it is |
|---|---|
| `trial_balance.csv` | every account + debit/credit as of 6/30/2026 — the spine everything ties to |
| `open_ap.csv` / `open_ap_lines.csv` | unpaid bills + their detail lines (keeps A/P aging) |
| `open_ar.csv` | unpaid invoices (keeps A/R aging) |
| `cip_history.csv` | construction-cost detail (for job/item rebuild) |
| `accounts_list.csv` | the full chart of accounts (catches zero-balance accounts) |
| `_meta.json` | company name, timestamp, and a debit=credit balance check |

## Optional knobs (defaults are already set for STV)
- `-Cutover 2026-06-30` — the as-of date for balances.
- `-CipAccount "Development/Improvements"` — the legacy construction-cost account; override if a
  file spells it differently (e.g. `-CipAccount "Construction in Progress"`).
- `-Dsn "QuickBooks Data"` — the QODBC data-source name, if yours is named differently.
- `-OutRoot "<path>"` — where to write; defaults to `_output` next to the script (already on J:).

## After all 18 are done (this happens on your PC, by Co-work)
Co-work copies each `_output\<Entity>\` folder into `obgen\cache\<Entity>\`, then runs
`python obgen\run.py build` to generate the QBO opening-balance entries — with the penny-tie gates.
Nothing posts to QBO without your approval.

## If something goes wrong
- **"Could not connect to QODBC DSN"** → wrong PowerShell bitness (see top), or QuickBooks/the
  company file isn't open. The script prints the DSNs it can see to help.
- **A query errors on one table** → note the exact message; QODBC table/column names can vary by
  version. Send the message and we'll adjust that one query — the others still wrote fine.
- **Empty trial balance** → the wrong file was open, or the cutover date is before the file has data.
