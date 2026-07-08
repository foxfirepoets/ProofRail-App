# QBO_SANDBOX_TEST_PLAN — binary tests; status as of 2026-07-05 (build day)

| # | Test | How | Status (build day) |
|---|---|---|---|
| 1 | Setup count verification | `python scripts/qbo_verify_setup_counts.py` — A: 139/18/5/69/53/64 · B: 109/17/1/3 all present; cross-realm bleed NONE; BS by Location renders | **PASS (executed)** |
| 2 | Sample vendor bill (Realm A) | `qbo_create_sandbox_bill.py` Concord $42,180.55, full 4-dimension coding | **PASS — Bill Id 145, TotalAmt ties, Location column appears on BS** |
| 3 | Sample parent-side transaction (Realm B) | dev-fee invoice leg (below) — Realm B books income under 15 STV CM | **PASS — Invoice Id 145** |
| 4 | Developer fee 5% test | `qbo_create_dev_fee_test.py` Madison base 306,140.60 → both legs 15,307.03, tie check | **PASS — A Bill 146 == B Invoice 145 == 15,307.03** |
| 5 | No-partnership-commission test | (a) verify script asserts `Comm Payable - Watson (2%)` exists ONLY in Realm B; (b) dev-fee audit event has `commissions_booked:false`, status UNRESOLVED | **PASS (both)** |
| 6 | Duplicate invoice test | re-run test 2 same DocNumber+vendor → REFUSED; plus packet-builder duplicate → FAIL verdict | **PASS (both layers)** |
| 7 | Bank-change warning test | `build_invoiceproof_packet.py` with `--bank-routing` differing from ledger history → FAIL `bank_change_risk`; BANK_NOTICE class → out-of-band protocol | **PASS (local check verified); SwarmSync `BANK_ACCOUNT_CHANGE` path untested (needs `ssk_live_` key)** |
| 8 | Historical draw Do-Not-Post test | `classify_attachment.py` on `*HISTORICAL_example*` → `do_not_post:true`, HARD STOP, folder `14_Do_Not_Post` | **PASS (executed)** |
| 9 | Source-file citation test | packet without `--source` → FLAG `missing_support`; `append_audit_log.py` refuses events without `--source` | **PASS (packet check executed; log arg is required=True)** |
| 10 | Audit log test | every QBO write today has `create_attempt`+`create_ok/error` with RequestId; bank masks verified (`****0054`); redaction active | **PASS — 475+ create events, zero secrets in logs (scanned)** |

## Still open (needs Ben / external service)

- T7b: live SwarmSync InvoiceProof scan (`--send`) once `SWARMSYNC_API_KEY` (ssk_live_…) is in `.env`.
- Idempotent re-run of the full seeder against the now-populated realms (expected: all "exists/skip") — safe anytime: `python scripts/qbo_seed_all.py --execute-sandbox`.
- PR-020 partial-pair drill (force a Realm B failure) — verified in code review, not force-tested live.
- Gmail label creation + one full Inbox Run against real mail (needs Co-work session with Gmail connector).
- Drive folder tree creation (16 folders) — one-time manual or first Co-work session.

## Standing regression (run weekly)

Tests 1, 2 (new DocNumber), 4 (new docnumber), 6, 8, 10 — ~5 minutes total.
