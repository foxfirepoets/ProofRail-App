# CHUNK_2_PARSE: Pure CSV/IIF parsers that normalize the QB Import_Files into typed catalog rows

## Summary

Build `app/catalog/parsers.py` — pure functions that read the QB Summa Terra `Import_Files/` CSVs and return
typed dataclasses, with **no database or network access**. This isolates the brittle "match the document
exactly" logic from the DB writes (CHUNK_3/4), so it is unit-testable against the real files. The CSVs are the
plug-and-play source of truth (they are the same files uploaded to QuickBooks); the parser mirrors them 1:1.

## Acceptance Criteria

- [ ] `parse_accounts(path)` reads `CSV_Chart_of_Accounts_{Partnership,Parent}.csv`
      (cols `Number, Account Name, Type, Description`) → `[AccountRow]`. Partnership=36 rows, Parent=22 rows.
- [ ] `parse_classes(path)` reads `CSV_Classes.csv` (`Class Name`) → `[ClassRow]` with `code`/`name` split from
      `"NN Rest of name"` (e.g. `"10 Site & Excavation"` → code `10`, name `Site & Excavation`). 10 rows.
- [ ] `parse_cost_codes(path)` reads `CSV_Items_{Partnership,Parent}.csv`
      (cols `Item Name, Type, Description, Account, Default Class`) → `[CostCodeRow]` carrying the **account
      NAME** (resolution to a number happens in CHUNK_3). Partnership=68 rows, Parent=3 rows.
- [ ] Each `CostCodeRow` derives: `kind` ∈ {draw,lifecycle,fee,retainage} (numbered `001`–`069`=draw;
      `100/101/110/120/121/122/200/201`=lifecycle; `FEE-*`=fee; `RETAINAGE-HELD`=retainage) and `fee_role`
      (`FEE-DEV`→`dev_5_partnership`, `FEE-DEV-INC`→`dev_inc_5_parent`, `FEE-CEO`→`ceo_2_parent`,
      `FEE-PRES`→`pres_1_parent`, else NULL).
- [ ] `parse_vendors(path)` reads `CSV_Vendors_{Partnership,Parent}.csv` (`Vendor Name`) → `[VendorRow]`.
      Partnership=44, Parent=2.
- [ ] `parse_customer_jobs(path)` reads `CSV_Customers_Jobs.csv` (`Customer:Job`) → `[CustomerJobRow]` with
      `path` and `parent_path` (split on the last `:`). 5 rows.
- [ ] Optional `parse_iif(path)` parity helper: extract account/item names from the `.iif` and assert they match
      the CSV-derived set (catches drift between the two upload artifacts). Non-fatal warning on mismatch.
- [ ] Parsers are **pure**: no DB, no env, no network; deterministic on the same files.
- [ ] `ruff check . && mypy app` clean.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

No HTTP endpoints — pure parsing functions returning dataclasses.

## Database Changes

No schema changes in this chunk.

## Test Scenarios

- **Happy path**: parsing all 8 CSVs from the real `Import_Files/` yields the exact row counts above and correct
  `code`/`kind`/`fee_role` derivations (spot-check `003 Concrete`→draw, `068 Construction Profit`→draw/no
  fee_role, `FEE-DEV`→fee/dev_5_partnership, `100 Land Acquisition`→lifecycle).
- **Edge case**: a class/item name with extra spaces or a `&` parses correctly; a `Customer:Job` with no colon
  yields `parent_path=None`.
- **Failure case**: a missing CSV raises a clear `FileNotFoundError` naming the file (not a silent empty list).
- **Integration**: the dataclasses are exactly what CHUNK_3/CHUNK_4 consume for upsert.

## Dependencies

- **Requires**: CHUNK_1_SCHEMA (dataclasses mirror the model fields).
- **Blocks**: CHUNK_3_CATALOG, CHUNK_4_NAMES.

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_2_PARSE</promise>
