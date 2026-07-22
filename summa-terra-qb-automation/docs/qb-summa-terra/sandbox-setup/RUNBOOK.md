# Sandbox Environment Build Runbook

Operator runbook for `spec-qb-sandbox-environment-2026-07-01.md`. **Every step below requires a human operator
inside the Rightworks-hosted QuickBooks Desktop Enterprise session.** No AI agent or automated script can execute
these steps — QuickBooks Desktop has no API for company-file creation, list import, or Web Connector
registration; all of it is GUI-driven. This runbook exists to make that manual work as fast and error-proof as
possible, not to replace it.

**Status of this runbook: artifacts prepared, NOT yet executed.** Do not mark any checklist item below complete
until the operator has actually performed it inside the hosted QuickBooks session and can point to the resulting
state in QuickBooks itself (a screenshot or a live query result) as evidence — per the spec's own Section 9/16
evidence requirements. A checklist item marked complete without that evidence is exactly the "checkpoint theater"
failure mode HKO-truth-audit is designed to catch.

---

## Prerequisite artifacts (already prepared, this repo)

| Artifact | Path | Purpose |
|---|---|---|
| Cost-code Items (Partnership) | `ai-accounting-hub-ralph/tests/fixtures/import_files/CSV_Items_Partnership.csv` | Items 001–069 + FEE-DEV + RETAINAGE-HELD, mapped to CIP bucket + default Class, per `docs/qb-summa-terra/Cost_Codes_and_Items.md` |
| Fee/commission Items (Parent) | `ai-accounting-hub-ralph/tests/fixtures/import_files/CSV_Items_Parent.csv` | FEE-DEV-INC, FEE-CEO, FEE-PRES — parent-file-only per §4b of the binding cost-code doc |
| Customer:Jobs | `ai-accounting-hub-ralph/tests/fixtures/import_files/CSV_Customers_Jobs.csv` | Hunter's Landing + 4 sub-jobs (Acquisition/Sitework/Vertical/Disposition) |
| Vendors (Partnership / Parent) | `ai-accounting-hub-ralph/tests/fixtures/import_files/CSV_Vendors_Partnership.csv`, `CSV_Vendors_Parent.csv` | Test vendor records |
| Chart of Accounts (Partnership / Parent) | `ai-accounting-hub-ralph/tests/fixtures/import_files/CSV_Chart_of_Accounts_Partnership.csv`, `CSV_Chart_of_Accounts_Parent.csv` | Reference only — New Company from Existing Company File clones the COA natively; these confirm what the cloned COA should contain |
| Class list (IIF, NEW) | `docs/qb-summa-terra/sandbox-setup/classes_sandbox.iif` | The 10 phase Classes — **converted to IIF format** because QuickBooks' native CSV import wizard does not support the Class list (confirmed in prior research) |
| Sandbox `.qwc` registration (NEW) | `docs/qb-summa-terra/sandbox-setup/summa_terra_sandbox.qwc` | Web Connector registration with freshly generated, unique `OwnerID`/`FileID` GUIDs — see collision-check step below |
| Seed opening-balance JE (NEW) | `docs/qb-summa-terra/sandbox-setup/seed_opening_balance_je.md` | The one synthetic journal entry to enter manually |

**Note on the existing CSV fixtures:** these were originally built as test fixtures for `ai-accounting-hub-ralph`'s
Python import-parsing logic. They are also directly usable as real QuickBooks CSV import files — the data is
correct and sourced from `docs/qb-summa-terra/Cost_Codes_and_Items.md` (the authoritative cost-code catalog) — but
they have not previously been run through QuickBooks' actual Import wizard. Treat that as unverified until the
operator does it for real (Step 4 below).

---

## Steps (operator-executed, per spec Section 5 / 18)

**Step 1 — Select source company file.** Pick whichever of the 10 existing STV production files is fastest/
simplest to clone (any file works as a starting point — CSV/IIF import corrects the structure afterward per spec
§14). Record which file was chosen and why, in one sentence, in this runbook's Execution Log below.
`[ ] Not yet executed`
Picked Orion Investing LLC- It was the smallest file

**Step 2 — Clone via New Company from Existing Company File.** `File > New Company from Existing Company File...`
→ name the new file `Summa Terra SANDBOX - DO NOT USE FOR REAL WORK.QBW`. Confirm the `SANDBOX` marker is in the
filename exactly as shown — this is the guard against ever restoring/importing over a production filename by
accident (spec §7).
`[ ] Not yet executed`

**Step 3 — Review cloned users.** Open the Users list in the new sandbox file; remove or reset any credentials
inherited from the source file before anyone else accesses it (spec §7).
`[ ] Not yet executed`

**Step 4 — Import Items (CSV).** `File > Utilities > Import > Excel Files` → import
`CSV_Items_Partnership.csv`, then `CSV_Items_Parent.csv`. Verify count = 69 numbered cost-code Items
(001–069, accounting for the intentional gaps in the real GC continuation-sheet numbering) + `RETAINAGE-HELD` +
`FEE-DEV` + `FEE-DEV-INC` + `FEE-CEO` + `FEE-PRES`, each mapped to exactly one CIP bucket, 0 orphans.
`[ ] Not yet executed`

**Step 5 — Import Customer:Jobs (CSV).** Same Import wizard, `CSV_Customers_Jobs.csv`. Verify Hunter's Landing +
4 sub-jobs appear.
`[ ] Not yet executed`

**Step 6 — Import Classes (IIF).** `File > Utilities > Import > IIF Files` → `classes_sandbox.iif`. Verify all 10
Classes appear in the Class list.
`[ ] Not yet executed`

**Step 7 — Import Vendors (CSV, optional but recommended).** `CSV_Vendors_Partnership.csv` /
`CSV_Vendors_Parent.csv`, so Spec B's test BillAdd has a real vendor to reference.
`[ ] Not yet executed`

**Step 8 — Enter seed opening-balance JE.** Per `seed_opening_balance_je.md`. Confirm trial balance and
`Verify Data` clean afterward.
`[ ] Not yet executed`

**Step 9 — Confirm Rightworks File Manager visibility.** Per Rightworks' 2026-07-01 written confirmation this
requires no support ticket. Confirm the sandbox file is visible/accessible in File Manager.
`[ ] Not yet executed`

**Step 10 — GUID collision check (CRITICAL — do not skip).** Before registering `summa_terra_sandbox.qwc` in Web
Connector, the operator must confirm the `OwnerID` (`{dc6bc214-5f52-447b-84e7-bf741f57f738}`) and `FileID`
(`{6ca052fa-84fa-4fa9-b42a-604d06e92fad}`) generated for this file do NOT match any of the `FileID`/`OwnerID`
values already registered for the 10 production `.qwc` apps on the Rightworks machine. These GUIDs were generated
fresh (via `uuid.uuid4()`) specifically for this file and are astronomically unlikely to collide, but this repo
has no visibility into what is actually registered on the live Rightworks Web Connector instance — **this check
can only be performed by the operator, on the hosted machine, and must not be skipped or assumed.**
`[ ] Not yet executed`

**Step 11 — Fill in `AppURL`/`AppSupport` and register `.qwc`.** Once Spec B's `/qbwc` SOAP endpoint is deployed,
replace `REPLACE_WITH_SPEC_B_SOAP_ENDPOINT_URL` and `REPLACE_WITH_SUPPORT_CONTACT_URL` in
`summa_terra_sandbox.qwc`, then register it in QuickBooks Web Connector on the Rightworks machine.
`[ ] Not yet executed — blocked on Spec B endpoint deployment`

**Step 12 — Isolation proof (per spec §9 — the mandatory security test).**
1. Run one no-op qbXML `HostQuery`/`CompanyQuery` through the registered sandbox `.qwc` app. Confirm the response
   identifies the sandbox company, never a production company. Save the response as evidence.
2. Attempt to run the sandbox `.qwc` app while a production file is the active/open file. Confirm Web Connector
   refuses or errors. Save the error/log as evidence.
`[ ] Not yet executed — blocked on Step 11`

**Step 13 — Ben structural sign-off.** Ben reviews the sandbox structure against `SPEC_SUMMA_TERRA_BINDING.md`
and this runbook's evidence, and signs off per spec §3 acceptance criteria.
`[ ] Not yet executed — blocked on Steps 1–12`

**Step 14 — Before/after production file check.** Capture account counts and last-modified timestamps for all 10
production files both before Step 1 and after Step 13, and confirm no production file changed.
`[ ] Not yet executed`

---

## Execution Log

*(Operator: fill in as each step is actually performed. Do not pre-fill or mark steps done in advance.)*

- Step 1 source file chosen: _______________ — reason: _______________
- Date sandbox build started: _______________
- Evidence artifacts saved to: _______________

## Cost-code count reconciliation

`Cost_Codes_and_Items.md` §2 lists numbered cost codes 001–069 with intentional gaps in the real GC continuation-
sheet numbering (e.g., 006, 029, 038–039, 044–045, 051, 054–055, 064, 066 do not appear — this matches the real
document Draw #29 is drawn from, not an error). The actual count of numbered draw-line Items is 58, plus 8
non-draw lifecycle Items (100, 101, 110, 120, 121, 122, 200, 201) = **66 numbered Items total**, plus the 5
non-numbered Items (`RETAINAGE-HELD`, `FEE-DEV`, `FEE-DEV-INC`, `FEE-CEO`, `FEE-PRES`). Verify against this exact
count during Step 4 — do not expect exactly 69 rows; expect 66 numbered + 5 special-purpose = 71 total Item rows
across both CSV files.
