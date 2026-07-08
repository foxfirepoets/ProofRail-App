# GMAIL_AUTOMATION_SPEC — labels, searches, intake, drafting, and send rules

Gmail is Co-work's surface (single-writer law: Gmail belongs to Co-work; QBO belongs to the
scripts). OAuth scopes: read + compose + labels. **The delete scope is never granted.**

## 1. Required labels (create once; `mcp Gmail create_label`)

```
ProofRail/Invoices        ProofRail/Draws           ProofRail/Docs
ProofRail/Action          ProofRail/Quarantined     ProofRail/Risk-BankChange
ProofRail/Missing-Docs    ProofRail/W9-Insurance    ProofRail/Statements
ProofRail/Lender          ProofRail/Replied         ProofRail/DoNotPost
ProofRail/Processed       ProofRail/Archive         ProofRail/Approval
ProofRail/ReadyForQBO
```

## 2. Standing searches (each Inbox Run)

| Purpose | Query |
|---|---|
| New unprocessed mail | `in:inbox newer_than:2d -label:ProofRail/Processed -label:ProofRail/DoNotPost` |
| Invoices w/ attachments | `has:attachment (invoice OR bill OR "amount due") -label:ProofRail/Processed` |
| Draw packages | `has:attachment (draw OR G702 OR G703 OR "pay app" OR "schedule of values")` |
| Bank-change risk | `("new bank" OR "updated account" OR routing OR "remittance change" OR "updated ACH")` |
| Approvals (Mike/Zach replies) | `from:(mike OR zach) (approve OR approved OR "looks good")` |
| Aging follow-ups | `label:ProofRail/Action older_than:3d` |
| Missing docs chase | `label:ProofRail/Missing-Docs older_than:5d` |

## 3. Intake rules (classification → label → action)

| Class | Label | Action |
|---|---|---|
| INVOICE | ProofRail/Invoices | save attachment → extract → InvoiceProof packet → queue |
| DRAW_SHEET | ProofRail/Draws | save → historical/current gate → six checks → packet |
| LIEN_WAIVER | ProofRail/Draws | file to the project's draw folder; link to draw |
| BANK_NOTICE | **ProofRail/Risk-BankChange** | HARD STOP — out-of-band verification task; never update anything from the email |
| STATEMENT | ProofRail/Statements | file to recon workbook statements folder |
| W-9 / COI | ProofRail/W9-Insurance | file; update vendor doc tracking |
| LENDER_DOC | ProofRail/Lender | file to entity's Loans folder |
| APPROVAL | ProofRail/Approval | match to the pending intake/draw/fee; record as gate evidence |
| needs human | ProofRail/Action | appears in Morning Brief until resolved |
| dup/superseded/example | **ProofRail/DoNotPost** | terminal — file to `14_Do_Not_Post`, never process |

`ProofRail/Processed` is **terminal** and applied ONLY after attachment save + Drive filing +
audit log ALL succeed. Partial work never wears the done label. `ProofRail/ReadyForQBO` marks
items whose approval is recorded and whose handoff packet exists.

## 4. Attachment saving

Dedupe by (gmail msg_id, sha256). Land in BOTH places: pipeline folder (Drive operating tree)
and the human-convention folder. Filename law: invoices
`{YYYYMMDD}_{ENTITY}_{VENDOR}_INV{no}_{amount}.pdf` · draws
`{PROJECT}_DRAW{NN}_{YYYYMMDD}_{LENDER}.pdf` · statements
`{YYYYMM}_{ENTITY}_{BANK}_{last4}_stmt.pdf`. Use `scripts/classify_attachment.py` for the
routing decision; log every save.

## 5. Auto-draft rules (always allowed — drafts are reversible)

Missing-doc requests (W-9, COI, lien waiver, invoice copy) · receipt acknowledgments ·
follow-ups on aging Action items · clarification questions on unreadable attachments.
Every draft states facts only, cites nothing confidential, and waits for Ben.

## 6. Auto-SEND rules (narrow whitelist, this test build)

Allowed ONLY when ALL are true: recipient is on Ben's written whitelist · content is a
non-money acknowledgment or doc request from an approved template · the underlying item passed
its proof gate · the send is audit-logged. **This test build starts with an EMPTY whitelist —
everything is a draft until Ben adds names in writing.**

## 7. NEVER auto-send

Anything mentioning amounts, payments, bank details, approvals, legal matters, or lender
correspondence · any reply to a bank-change request (**money-content → never auto-reply, to
anyone**) · anything to Mike, lenders, counsel, or Ricks & Co · anything on a FLAG/FAIL item.

## 8. Approval tracking

Mike's channel is email — permanent mechanism. An APPROVAL-classified reply is matched to its
pending item (invoice/draw/fee), recorded via `append_audit_log.py`
(`--approval approved --approver <email> --source gmail:<msgid>`), and only then may the item
move to `06_Approved_For_QBO`.

## 9. Follow-up tracking

`ProofRail/Action` + `ProofRail/Missing-Docs` are the follow-up queues; aging >3d/>5d surfaces
in the Morning Brief with a drafted (not sent) nudge. Hard rules: never delete email; never
mark unread→read without processing; heartbeat = if intake runs silent for a business day,
Morning Brief must say so loudly.
