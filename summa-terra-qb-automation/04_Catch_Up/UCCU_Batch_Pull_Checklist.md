# UCCU Batch Pull — Download Checklist (Q2 2026 Catch-Up)

**Goal:** get the missing bank transactions into a form Claude can process, so we can build the Q2 (Apr–Jun 2026) catch-up entries for QuickBooks.

**Why this is needed:** our transaction dataset is solid for the Mountain America (MACU) and STDG accounts through ~March 31, 2026, but the **UCCU transaction downloads are largely missing** — we only have the monthly reconciliation PDFs, not the line-by-line data. UCCU is the single biggest gap.

---

## HOW TO PULL (do this once, then repeat per account)

1. Log into **UCCU online banking** (uccu.com).
2. Open an account → **Download / Export transactions**.
3. **Date range:** **March 1, 2026 → June 25, 2026** (today). Overlap is fine — Claude de-dupes automatically.
4. **Format — pick in this order of preference:**
   - **QuickBooks (.QBO / "Web Connect")** ← best (imports straight to QB *and* Claude reads it)
   - **Quicken (.QFX)** ← also great
   - **CSV / Excel** ← fine if the above aren't offered
   - Also grab the **PDF statement** for each (that's the reconciliation source of truth).
5. **Save every file to this folder** (already created for you):
   `I:\My Drive\ACCOUNTING - PC FILES\QB-MISC\Q2_2026_Catchup_Intake`
   Name them clearly, e.g. `STVE-UCCU-Checking_Mar-Jun2026.qbo`.
6. Tell me when files are in the folder — I'll parse, dedupe, and reconcile them against the books.

---

## UCCU ACCOUNTS TO PULL (the "batch")

Pull both the **Checking** and **Money Market (MM)** for each entity that has them:

- [ ] **STVE — UCCU Checking** (STV Entitlement Services)  *(P0)*
- [ ] **STVE — UCCU Money Market**  *(P0)*
- [ ] **HLN — UCCU Checking**  *(P0 — see fraud note below)*
- [ ] **HLN — UCCU Money Market**  *(P0)*
- [ ] **Summa Elite — UCCU Checking**  *(P0)*
- [ ] **Summa Elite — UCCU Money Market**  *(P0)*
- [ ] **Union (Union Walk) — UCCU**  *(P0)*
- [ ] **STDG — UCCU Checking**  *(P0)*
- [ ] **STDG — UCCU Money Market**  *(P0)*
- [ ] **12SB (Hunters Landing) — UCCU**  *(P0 — confirm this is the right bank when you log in)*
- [ ] **AW1 — UCCU Checking + MM**  *(important — AW1 is the furthest behind, since Oct 2025)*
- [ ] **Quincy — UCCU**
- [ ] **Ledges at Moab — UCCU**
- [ ] **Freeman Ranch — UCCU**
- [ ] **Vic — UCCU**
- [ ] **Lazarus — UCCU**

> ⚠️ **HLN fraud note:** HLN's old account ending **…92090** was closed **12/05/2025** after a fraud event and replaced by **…48560**. Pull the **new …48560** account. (Separately, the old account still needs a ~$118,750 write-off/receivable entry — tracked on the "for Mike" list.)

## NON-UCCU P0 accounts (different banks — pull these too while you're at it)

- [ ] **STVE — Mountain America (MACU)** Checking + Sweep (acct 2215) — we have through 3/31; need **Apr 1 → Jun 25**
- [ ] **STDG — Mountain America (MACU)** 2212 Checking + Sweep — we have through ~3/31; need **Apr 1 → Jun 25**
- [ ] **STDG — Granite Credit Union** — ~$730K unreconciled; pull **Mar 1 → Jun 25**
- [ ] **Madison — Central Bank** (Madison Central Checking + MM) — we have May only; need **Mar 1 → Jun 25**

---

## What happens after you drop the files

1. I parse every file, tag duplicates, and merge into the master dataset.
2. I reconcile each account: bank balance vs. the books, and list every transaction that needs to be entered.
3. I produce a **ready-to-post entry sheet per account** (same clean format as the variance booking sheet) — you review, then key them into QuickBooks.
4. We tick each account off the worklist until Q2 is current.

_Created 2026-06-25. Intake folder confirmed to exist. Date ranges chosen to safely cover the unposted period (QB current only ~through Jan–Feb; reconciliation PDFs exist through May but the line-level data isn't in the books)._
