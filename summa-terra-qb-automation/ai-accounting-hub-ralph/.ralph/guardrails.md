# Guardrails — Known Risks and Scope Exclusions

ralph: before taking any action, scan this file. If your action matches a SIGN, stop and report.

## Pre-Loaded Risks (from spec §14)

### SIGN: One-file-per-session physics
QB Desktop opens one company file per session (30–120s file switch); concurrency = licensed RDS sessions, not code threads. Write-back throughput to QB cannot be manufactured by the canonical store.
Mitigation: Postgres is the system of record; QB Desktop is an eventually-consistent batch sink. Never make QB the scaling endpoint.

### SIGN: Rightworks persistent-poller permission (most-likely-fatal)
A long-running QBWC poller may require Rightworks support/AppHub approval; there is NO inbound fallback on the host.
Mitigation: Phase 1 measures poll cadence and files the support ticket before building the write path. QBWC outbound poll only — never an inbound listener on the Rightworks box.

### SIGN: Thin adapter unproven
"Thin swappable adapter" is unproven until a second backend exists.
Mitigation: keep transport thin and QB semantics in a separate fat layer with raw_extensions sidecar; CHUNK_8 QBO stub validates <20% mapping delta.

### SIGN: CoA drift breaks qbXML writes silently
Chart-of-accounts drift across differently-configured files can silently break qbXML writes.
Mitigation: VerifyAPI catches CoA mismatch pre-write (COA_DRIFT 422); never a silent failure.

### SIGN: Gates must fail closed
Proof-service outage or invalid proof must BLOCK writes, never fail open on money/books.
Mitigation: every gate (InvoiceProof, AuditProof chain, VerifyAPI) fails closed; no write without a valid proof.

### SIGN: EditSequence optimistic-lock conflict
QB write-back can conflict on stale EditSequence.
Mitigation: re-read from QB, re-base canonical record, retry once, else route to human.

## Scope Exclusions — Do Not Build

- DO NOT BUILD: 1000-company QB Desktop operation (physics wall — out of scope; scale path is API adapters).
- DO NOT BUILD: live QBO/Intacct/NetSuite/Xero/Dynamics adapters — only the QBO STUB seam in CHUNK_8.
- DO NOT BUILD: payroll, tax filing, bank-feed ingestion, vendor portals, document management (future phases).
- DO NOT BUILD: any inbound connection/listener on the Rightworks box (architecturally forbidden — outbound QBWC poll only).
- DO NOT BUILD: any paid third-party integration above $5–10/mo (proof layer is owner-operated SwarmSync = $0).
- DO NOT BUILD (yet): intercompany allocation engine + cross-property fee automation, reconciliation automation, full-scale month-end close (deferred Phase 2+).

## Standing Guardrails (always active)

- DO NOT add pip dependencies without updating AGENTS.md / requirements.txt.
- DO NOT skip the validation gate, even for trivial changes.
- DO NOT commit with --no-verify.
- DO NOT generate code for a future chunk's domain.
- DO NOT modify files outside the current task's scope.
- DO NOT hard-code secrets, API keys, or credentials (use .env). Never log raw bank fields or proof secrets.
- DO NOT merge payment/proof logic (CHUNK_7) with another chunk — payment state must be atomic.

## Accumulation Instructions

When ralph encounters a new failure pattern, append below:

### Learned: (none yet)

## DASHBOARD lessons
- Project convention: NO httpx/TestClient (not installed). Test FastAPI routes by calling endpoint funcs directly with a minimal starlette Request + monkeypatched service. (see test_canonical_router.py)
- fastapi Form(...) needs python-multipart; to avoid a 2nd dep, parse urlencoded via `await request.form()` (Starlette handles urlencoded natively).
- Jinja2Templates needs jinja2 installed IN the venv; autoescape turns apostrophes into &#39; — assert on escaped-safe substrings.
- Jinja2 TemplateResponse is not an HTMLResponse subtype — annotate handlers `-> Response` for mypy.
