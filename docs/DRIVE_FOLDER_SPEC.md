# DRIVE_FOLDER_SPEC — the 16-folder operating tree (a file's folder IS its status)

Root: the Drive folder mirrored at `GOOGLE_DRIVE_SYNC_ROOT`. Files move FORWARD only
(00→…→09); anything that can't advance goes to `10_Exceptions` with a note. Naming law (all
folders): machine-parseable, sortable — invoices `{YYYYMMDD}_{ENTITY}_{VENDOR}_INV{no}_{amount}.pdf`,
draws `{PROJECT}_DRAW{NN}_{YYYYMMDD}_{LENDER}.pdf`, statements `{YYYYMM}_{ENTITY}_{BANK}_{last4}_stmt.pdf`.

| Folder | Purpose | Writes | Reads | Status meaning | Co-work action on new file |
|---|---|---|---|---|---|
| `00_Inbox` | manual drop zone for anything (bank CSVs, scans, ad-hoc docs) | Ben, humans | Co-work | unclassified | classify (`classify_attachment.py`), rename to convention, move to the right folder, log |
| `01_Email_Attachments` | raw attachments saved from Gmail (deduped msg_id+sha256) | Co-work (Inbox Run) | Co-work | saved, pending routing | route a copy to 02/03/etc.; original stays as evidence |
| `02_Draw_Packages` | draw sheets, pay apps, lien waivers, inspections by project/draw | Co-work | draw review | awaiting draw review | run draw workflow (historical gate → six checks → packet) |
| `03_Vendor_Invoices` | vendor invoices by entity/month (`{entity}/Invoices/{YYYY-MM}/`) | Co-work | invoice review | awaiting InvoiceProof | build InvoiceProof packet |
| `04_InvoiceProof` | packet JSONs + scan results (mirror of `invoiceproof_packets/`) | packet builder | approval session | proofed (PASS/FLAG/FAIL recorded) | PASS/FLAG → approval packet in 05; FAIL → 10_Exceptions |
| `05_Pending_Approval` | approval packets awaiting Ben (invoice, draw, bank/CC, fee) | Co-work | Ben | waiting on Ben | surface in Morning Brief + Approval Session; nothing moves without recorded approval |
| `06_Approved_For_QBO` | Ben-approved packets w/ approval evidence attached | Co-work (after recorded approval only) | handoff | approved, not yet posted | build exact script command → move to 07 |
| `07_QBO_Sandbox_Handoff` | ready-to-run command files (one JSON/MD per posting: command + coding + source citation) | Co-work | Approval Session executor | queued for sandbox posting | execute with `--execute-sandbox` during approval session; record QBO ID |
| `08_QBO_Exports` | report exports (BS by Location, P&L, GL) | report script, Ben | month-end, audits | reference snapshots | file by realm+date; never edit |
| `09_QBO_Results` | posting receipts: QBO ID, RequestId, TotalAmt, audit-log ref | Co-work (after each posting) | month-end, retro | posted & verified | reconcile against 07 queue; any 07 item without a 09 receipt in 24h = exception |
| `10_Exceptions` | anything blocked: FAIL verdicts, unknown coding, mismatches | any workflow | Ben + Co-work weekly cleanup | blocked, needs human | keep an EXCEPTION_NOTE.md per item; clearing REQUIRES a written note |
| `11_Audit_Logs` | Drive mirror of `logs/*.jsonl` (daily upload) + optional Sheet summary | Co-work daily | Ben, Ricks, auditors | immutable history | append-only; never edit or delete |
| `12_Month_End_Close` | close checklists, rec workbooks, close packets by month | month-end workflow | Ben, Ricks | close in progress / closed | follow MONTH_END_CLOSE_SPEC |
| `13_Historical_Examples` | labeled per-GC/per-vendor historical corpus (fixtures for tests + adapter proving) | Ben, Co-work | draw/invoice workflows (read-only) | REFERENCE ONLY — never post | use as fixtures; never route into the live pipeline |
| `14_Do_Not_Post` | duplicates, superseded/voided docs, examples caught in intake | Co-work | nobody (terminal) | TERMINAL HARD STOP | file, log, done. Never process, never revisit |
| `15_Setup_Seed_Files` | the 11 seed CSVs + setup runbook (mirror of `qbo Source Files/`) | Ben (once) | seeding scripts, audits | setup source of truth | read-only after seeding; changes require a new acceptance run |

Rules: no file deleted, ever (supersede into 14) · every move is audit-logged with source
citation · a file in two workflow folders at once is an exception · Drive folder and Gmail
label must always correspond 1:1 (a labeled email whose attachment isn't filed = incomplete
Inbox Run step).
