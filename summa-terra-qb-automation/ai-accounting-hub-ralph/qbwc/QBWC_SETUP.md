# QuickBooks Web Connector Setup — STV AI Accounting Hub

This connects the live Hub (`https://ai-accounting-hub-production.up.railway.app`) to your
**test** QuickBooks company files on the Rightworks hosted desktop, via QuickBooks Web Connector (QBWC).

> These steps run **on the Rightworks hosted desktop** (the actual Windows session, not the
> `filemanagerui.rightworks.com` file manager). They require clicking an authorization dialog
> inside QuickBooks Desktop as **Admin** — Intuit requires a human for that grant. There is no
> API that bypasses it. Everything else (the endpoint, the qbXML, the .qwc) is already built.

Test files (from your setup):
- **Parent:** `Test Parent Summa Terra Ventures` (.QBW)
- **Partnership:** `Test File Summa Terra Ventures` (.QBW)

---

## Step 1 — Set the QBWC credentials on the Hub (Railway, System B) **[you]**

The endpoint authenticates the Web Connector against two env vars. Set them on the
`ai-accounting-hub` Railway service (they're currently blank):

```
QBWC_USERNAME=stv-aihub
QBWC_PASSWORD=<choose a strong password>
```

`stv-aihub` matches `<UserName>` in `STV-AIHub.qwc`. The password is **not** stored in the .qwc —
QBWC will prompt you for it once and remember it. Redeploy the service after setting these.

---

## Step 2 — Get the .qwc onto the hosted desktop **[you / me]**

`STV-AIHub.qwc` (in this folder) is ready. Upload it to the hosted environment via
`filemanagerui.rightworks.com` (I can do this part), or copy it through your normal file transfer.
Land it somewhere easy like the hosted Desktop.

---

## Step 3 — Add the app in QuickBooks Web Connector **[you, on the hosted desktop]**

1. On the hosted desktop, open **QuickBooks Desktop** and open the **`Test Parent Summa Terra Ventures`** company file, logged in as **Admin** in **single-user mode**.
2. Open **QuickBooks Web Connector** (Start menu → QuickBooks → Web Connector). If it isn't installed, install it from Intuit (free) — it ships with Enterprise.
3. Click **Add an Application** → select `STV-AIHub.qwc`.
4. QuickBooks pops the **Application Certificate / access** dialog. Choose:
   **"Yes, whenever this QuickBooks company file is open"** → Continue → Done.
   (This is the grant only you can make.)
5. In Web Connector, tick the app's checkbox, and paste the `QBWC_PASSWORD` from Step 1 when prompted.

---

## Step 4 — First sync (read-only proof) **[you]**

1. In Web Connector, click **Update Selected**.
2. Status should show a successful poll. This first version exercises the read path
   (vendor/bill query) — proving the handshake, auth, and company-file access all work end to end.
3. If it errors: `getLastError` text appears in the Web Connector status line — send it to me.

---

## Step 5 — Repeat for the partnership file **[you]**

Close the parent file, open **`Test File Summa Terra Ventures`**, and repeat Steps 3–4 so the app
is authorized against that file too. (QBWC authorizes per company file.)

---

## Step 6 — Enable writes (after my write-stage build lands)

The write path (approved, proof-gated `BillAdd` into QB) is being built now. Once it's deployed,
the same Web Connector app will, on each poll, drain approved bills and post them as `BillAdd`
transactions — no new setup needed on your side beyond keeping a hosted session active during
business hours (per the Rightworks 2‑hour idle constraint).

---

## What stays true (guardrails)
- Only **approved + proof-passed** bills are ever written — the write path re-checks the proof
  boundary directly against the DB, never trusting an upstream claim.
- Nothing writes off-hours; bills queue in Postgres until the next authorized poll.
- These are **test** company files — validate the full flow here before pointing at production entities.
