# INVOICEPROOF REVIEW — paste to interpret one InvoiceProof result

Packet: **[Ben: paste invoiceproof_packets/<file>.json or the invoice reference]**
Reference: `docs/INVOICEPROOF_ROUTING_SPEC.md`.

1. Show the packet verbatim: final_verdict, every local finding, and (if `--send` was used)
   the SwarmSync scanId, riskLevel, and findings. Remind: stricter of local/remote wins;
   LOW→PASS, MEDIUM→FLAG, HIGH/CRITICAL→FAIL.
2. For each finding, explain in plain English what it means and what evidence would clear it
   (e.g., MODIFIED_DUPLICATE → compare the two invoices side by side; BANK_ACCOUNT_CHANGE →
   out-of-band phone verification to the number on file, the email is never enough).
3. Recommend exactly one next action, citing sources:
   - PASS → move to approval packet.
   - FLAG → what Ben must decide + the override-reason text you'd record if he approves.
   - FAIL → quarantine steps + what to request from the vendor/GC.
4. If the proof service was down (packet shows fail-closed FLAG), say so — the item cannot
   PASS until a successful scan exists (PR-003, no bypass).
5. Log the review outcome. Do not approve, do not post — that's Ben's call in session 06.
