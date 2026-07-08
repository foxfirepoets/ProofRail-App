# INVOICEPROOF_ROUTING_SPEC — every invoice/payment request goes through InvoiceProof BEFORE approval

**No proof → no completion. Fail closed (PR-003): if the proof service is unreachable, nothing
passes — items wait or get human review; there is no bypass flag.**

## The SwarmSync InvoiceProof service (verified against the SwarmSync repo)

- Base URL: `https://api.swarmsync.ai` · Auth: `Authorization: Bearer <ssk_live_…>` (or
  `X-API-Key`) — one SwarmSync key (`SWARMSYNC_API_KEY` in `.env`) serves InvoiceProof,
  AuditProof, and VerifyAPI. Keys are minted in the SwarmSync dashboard (shown once).
- `POST /invoice-proof/scan` — JSON body `{ "invoices": [{vendor, invoiceNo, amount, po?,
  bank?, bankRouting?, lineItemsTotal?}], poRegister?, vendorMaster?, paymentHistory? }`.
  Response: `{ scanId, riskLevel: LOW|MEDIUM|HIGH|CRITICAL, findings: [{severity, pattern,
  detail, rows}], checks_passed/failed/skipped, coverage_summary }`.
- `POST /invoice-proof/scan-pdf` — multipart `file` (digital/text PDFs only — **no OCR**;
  scanned images must be extracted by Co-work first, then sent as JSON).
- Chain-hashed proof retrieval: `GET /api/proof/:id` and `GET /api/proof/:id/verify`
  (recomputes the sha256 chain hash; `verification_level: signed_hash_chain|hash_chain`).
- Rate limits: scan 60/min; verify 20/min. Tier for this build: Invoice-Proof Verify
  (500 invoices/mo).
- Note: proof IDs are bare cuids (docs cosmetically show `prf_…`).

## Checks (local pre-checks in `scripts/build_invoiceproof_packet.py` + SwarmSync engine)

| Check | Local | SwarmSync pattern |
|---|---|---|
| Duplicate invoice (exact + modified) | vendor+invoiceNo / vendor+amount vs `logs/invoice_ledger.jsonl` | `EXACT_DUPLICATE`, `MODIFIED_DUPLICATE` |
| Vendor match | vendor must exist in Realm A vendor list | vendor-master mismatch, lookalike-domain vendor |
| Invoice number present/valid | required arg | `invoice_number_present` |
| Amount math | lineItemsTotal must equal amount | `Line-item math error` |
| Bank-change risk (BEC) | routing differs from last known → FAIL | `BANK_ACCOUNT_CHANGE` — "do not pay" red flag |
| Missing W-9 | vendor doc tracking (W9-Insurance label) | new-vendor compliance missing |
| Missing support | `--source` citation required | evidence sufficiency score |
| Missing project / Location / Class / Item | any absent → FLAG (PR-043 never guess) | — (local only) |
| Suspicious change | >2× vendor trailing average → WARN on packet | prior-invoice comparison |
| Unsupported payment request | payment requests with no underlying invoice → FAIL | urgency-pressure, approval-authority checks |
| Round-dollar | ≥$5,000 round amounts → FLAG | `ROUND_DOLLAR_AMOUNT` |
| Missing/ghost PO | — | `Missing / ghost PO`, `PO amount exceeded` |

## Verdict mapping and routing

SwarmSync `riskLevel` → verdict: **LOW→PASS · MEDIUM→FLAG · HIGH/CRITICAL→FAIL.**
The STRICTER of (local verdict, SwarmSync verdict) always wins.

| Verdict | Routing |
|---|---|
| **PASS** | approval packet → `05_Pending_Approval`; Ben approves normally |
| **FLAG** | human review; approval REQUIRES a written override reason (PR-002); override surfaces in the nightly/close bundle |
| **FAIL** | `ProofRail/Quarantined` + `10_Exceptions`; never approvable as-is; investigate, resolve findings, re-scan |

## Output packet (written to `invoiceproof_packets/`, mirrored to `04_InvoiceProof`)

`{ ts, invoice{vendor, invoiceNo, amount, po, project, location, class, item, source},
bank_routing_last4, local_verdict, local_findings[], swarmsync{scanId, riskLevel, findings,
mapped_verdict}, final_verdict, recommended_next_action, source_citation }`
— i.e., verdict + proof ID (scanId) + reason + next action + approval-packet link + source
email/file link. Raw bank numbers are never stored (last-4 only).

## Command

```
python scripts/build_invoiceproof_packet.py --vendor "<exact QBO vendor>" \
  --invoice-no <no> --amount <amt> [--line-items-total <amt>] [--po <po>] \
  [--bank-routing <digits>] --project "<cust:job>" --location "<loc>" \
  --class "<class>" --item "<cost code>" --source "gmail:<msgid>" [--send]
```
Without `--send`: local checks only (offline). With `--send`: SwarmSync scan too, and the
packet records the scanId as the proof reference.
