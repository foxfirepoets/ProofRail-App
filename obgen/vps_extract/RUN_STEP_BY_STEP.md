# Step-by-Step: Pull the QuickBooks balances on the VPS

This walks you through running the extract on the **Rightworks VPS**, one company file at a time,
until all 18 are done. It is **read-only** — it cannot change anything in QuickBooks. Total time:
roughly 3-5 minutes per file once you've done the first one.

Everything you produce lands on the **J: drive** and syncs back to your PC automatically, where
Co-work finishes the QBO load.

---

## PART 1 - One-time setup (do this once, at the start)

### Step 1 - Log in to the Rightworks VPS
Open your Rightworks cloud desktop the way you normally do.

### Step 2 - Find the folder on the VPS
1. On the VPS, open **File Explorer** (the yellow folder icon on the taskbar).
2. Go to your **Google Drive** there. Look under **My Drive** for:
   `2 Areas` -> `QuickBooks & VPS Operations` -> `QB_Enterprise_Extract`
3. You should see two files: `Extract-QBEnterprise.ps1` and the README/guides.
   *(If the folder isn't there yet, wait a minute for Google Drive to sync, then refresh.)*
4. Click once in the **address bar** at the top of that window, so the full path highlights
   (it will look like `G:\My Drive\2 Areas\QuickBooks & VPS Operations\QB_Enterprise_Extract`,
   but the drive letter on the VPS may be different). **Copy it** (Ctrl+C). You'll paste it in a moment.

### Step 3 - Open a Command Prompt
1. Click the **Start** button, type **cmd**, and press Enter. A black window opens.
2. Leave it open - you'll type one command per company file into it.

---

## PART 2 - Run it once per company file (repeat 18 times)

### Step 4 - Open the company file in QuickBooks
In QuickBooks on the VPS, **open the entity's company file** (File -> Open or Restore Company).
QODBC reads whatever file is currently open, so only one at a time.

> **Which file for which key?** Use the table in Part 3. Example: for Hunter's Landing (12SB),
> open the `12SB` company file, and you'll type `-Entity 12SB`.

### Step 5 - Run the extract command
In the Command Prompt window, type the command below **on one line**, then press Enter.
Replace two things:
- `PASTE_FOLDER_PATH` -> the folder path you copied in Step 2
- `12SB` -> the entity key for the file you have open (see Part 3)

```
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "PASTE_FOLDER_PATH\Extract-QBEnterprise.ps1" -Entity 12SB
```

Real example (your drive letter may differ):
```
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "G:\My Drive\2 Areas\QuickBooks & VPS Operations\QB_Enterprise_Extract\Extract-QBEnterprise.ps1" -Entity 12SB
```

> **Why that long `SysWOW64` path?** That's the **32-bit** PowerShell, which QODBC usually needs.
> If you get **"Could not connect to QODBC DSN"**, QuickBooks probably isn't open, OR your QODBC
> is 64-bit - in that case run the exact same command but change `SysWOW64` to `System32`:
> `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe ...`

### Step 6 - Read the result
After a few seconds you'll see lines like:
```
  -> trial_balance.csv  (142 rows)
  -> open_ap.csv  (18 rows)
  ...
  Trial balance: DR 1,234,567.00  CR 1,234,567.00  (delta 0.00)
  BALANCED. Extract complete for '12SB'.
```
- **BALANCED (green)** = success. Move to the next file.
- **"WARNING: trial balance came back EMPTY"** = the wrong file was open, or the date is before the
  file has data. Open the correct file and run again.
- **"NOT BALANCED"** = note it down and tell Ben/Co-work; run the rest anyway.

### Step 7 - Repeat
Close the current company file (or just open the next one) and repeat Steps 4-6 with the next
entity key, until all 18 in the checklist are done.

---

## PART 3 - The 18 files and their keys (your checklist)

Open each file, run with the matching key, and tick it off. (Book nicknames are there to help you
find the right file.)

| Done | Type this `-Entity` | Company file to open (nickname) |
|---|---|---|
| [ ] | `12SB`         | 12SB, LLC - "Hunter's Landing" |
| [ ] | `HLN`          | Hunter's Landing North, LLC - "HLN" |
| [ ] | `Union`        | Union Station, LLC - "Union Walk" |
| [ ] | `Madison`      | Madison Park, LLC (legacy QB name may read "Sunset Village") |
| [ ] | `Quincy`       | Quincy Partners, LLC |
| [ ] | `Vic`          | Vic Partners, LLC - "The Vic" |
| [ ] | `SummaElite`   | Summa Elite, LLC - the "Rock Creek" project |
| [ ] | `Ventura`      | Ventura Landing, LLC |
| [ ] | `Freeman`      | Freeman Ranch, LLC |
| [ ] | `Carlo`        | Carlo @ Washington, LLC - "The Carlo" |
| [ ] | `Ledges`       | Ledges at Moab, LLC |
| [ ] | `RMTexas`      | RM Texas Partners, LLC |
| [ ] | `ElephantRock` | Elephant Rock, LLC |
| [ ] | `EJH`          | EJH Development, LLC |
| [ ] | `Dominus`      | Dominus Data, LLC |
| [ ] | `RockCreek`    | Rock Creek Acquisitions, LLC (the land entity, NOT Summa Elite) |
| [ ] | `Camden`       | Camden Crossing, LLC (Lazarus line) |
| [ ] | `Ensign`       | Ensign Partners, LLC (SOLD - wind-down) |

> These keys must be typed **exactly** as shown (capitalization matters). They match
> `obgen\config\entities.yaml`. If a company file doesn't exist or you're unsure which one an entity
> is, skip it and tell Ben - don't guess.
>
> The corporate/parent side (STVE, STDG, etc. - "Realm B") is a **separate later step** in the
> migration; it is NOT part of these 18.

---

## PART 4 - After all 18 are done

### Step 8 - Confirm they synced back to your PC
On your **work PC** (not the VPS), the results appear under the same Google Drive folder:
`...\2 Areas\QuickBooks & VPS Operations\QB_Enterprise_Extract\_output\` - one folder per entity,
each containing 6 CSVs + a `_meta.json`. Give Google Drive a couple of minutes to sync.

### Step 9 - Hand off to Co-work
Tell Co-work: **"the QB extracts are in the _output folder - run the obgen build."**
Co-work will copy each entity's files into `obgen\cache\`, run `python obgen\run.py build`, and
generate the QBO Advanced opening balances - with the penny-tie gates. **Nothing posts to QBO
without your approval.**

---

## Troubleshooting (quick answers)

| You see | What it means | Do this |
|---|---|---|
| "Could not connect to QODBC DSN 'QuickBooks Data'" | QuickBooks/the file isn't open, or wrong bitness | Make sure QB is open with the file loaded; if still failing, swap `SysWOW64` -> `System32` in the command (or vice-versa) |
| "Available DSNs:" lists things but not QuickBooks | QODBC isn't seen at this bitness | Try the other PowerShell path (System32 vs SysWOW64) |
| "trial balance came back EMPTY" | Wrong file open, or cutover date too early | Open the correct company file; confirm the file has data on/before 6/30/2026 |
| An error mentioning a table/column name | QODBC version names a table differently | Copy the exact red text and send it to Ben/Co-work - the other files still saved fine |
| "running scripts is disabled on this system" | Execution policy | The command already includes `-ExecutionPolicy Bypass` - make sure you copied the whole line |

## Is this safe? (yes)
The script only **reads** QuickBooks (SELECT queries) and **writes CSV files** to the Google Drive
folder. It has no ability to post, pay, void, delete, or edit anything in QuickBooks. You can run it
as many times as you want; re-running just overwrites that entity's CSVs.
