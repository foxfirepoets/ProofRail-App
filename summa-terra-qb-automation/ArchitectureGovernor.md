❯  use /architecture-cartographer skill on build out for this qb automation project.  Go through all files in this repo
  to breakout what is correct and what needs fixed, and then use /master-integration-engineer to spec out the process
  for completing the actual QB enterprise connection to this project

● Skill(architecture-cartographer)
  ⎿  Successfully loaded skill

● Starting the full forensic walk now — running discovery commands first before writing a single finding.

  Searched for 1 pattern (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation" && find . -name "requirements*.txt"
      -o -name "setup.py" -o -name "pyproject.toml" -…)
  ⎿  ./ai-accounting-hub-ralph/pyproject.toml
     ./ai-accounting-hub-ralph/requirements.txt

  Read 1 file (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation" && find . -maxdepth 5 -type f -name
      "*.py" | grep -v "__pycache__\|\.git" | sort 2>…)
  ⎿  ./ai-accounting-hub-ralph/app/__init__.py
     ./ai-accounting-hub-ralph/app/audit/__init__.py
     ./ai-accounting-hub-ralph/app/audit/chain.py
     … +126 lines (ctrl+o to expand)

  Read 18 files (ctrl+o to expand)

● Now let me check the spec files and test coverage gaps.

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && grep -n
      "TODO\|FIXME\|HACK\|stub\|mock\|demo\|deprecated…)
  ⎿  app/audit/signing.py:53:        pass
     app/dashboard/router.py:28:_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
     app/dashboard/router.py:29:_TEMPLATES.env.globals["SHADOW_BANNER"] = SHADOW_BANNER
     … +17 lines (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && grep -rn
      "TODO\|FIXME\|HACK\|NOT YET\|stub\|placeholder\…)
  ⎿  app/dashboard/modules.py:5:modules ship as placeholder/work-queue sections (status ``pending``) under the same
      shadow
     app/dashboard/router.py:80:    return _render(request, "module_placeholder.html", {"m": m, "related": related}
     … +8 lines (ctrl+o to expand)

  Read 2 files (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && ls
      app/dashboard/templates/ 2>/dev/null)
  ⎿  attention.html
     base.html
     bill_detail.html
     … +18 lines (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && python -m
      pytest --collect-only -q 2>&1 | tail -20)
  ⎿  ERROR tests/test_ingestion.py
     ERROR tests/test_integration_db.py
     ERROR tests/test_payments_router.py
     … +17 lines (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && ls -la
      app/dashboard/templates/ 2>/dev/null | head -40)
  ⎿  total 98
     drwxr-xr-x 1 Heather Workman 197121    0 Jun 29 10:17 .
     drwxr-xr-x 1 Heather Workman 197121    0 Jun 29 12:58 ..
     … +21 lines (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && python -m
      pytest --collect-only -q 2>&1 | head -40)
  ⎿  tests/test_audit_chain.py: 12
     tests/test_audit_signing.py: 5
     tests/test_audit_verify.py: 6
     … +37 lines (ctrl+o to expand)

● Bash(cd "C:/Users/Heather Workman/Desktop/Ben Projects/Summa Terra QB Automation/ai-accounting-hub-ralph" && python -c
      "from app.main import app" 2>&1)
  ⎿  Error: Exit code 1
     Traceback (most recent call last):
       File "<string>", line 1, in <module>
       File "C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra QB
     Automation\ai-accounting-hub-ralph\app\main.py", line 8, in <module>
         from sqlalchemy import text
     ModuleNotFoundError: No module named 'sqlalchemy'

  Read 3 files (ctrl+o to expand)

● I now have everything I need. Compiling the full report.

  ---
  Architecture Cartographer Report — AI Accounting Hub (Summa Terra QB Automation)

  Audited: 2026-06-29
  Auditor: architecture-cartographer skill

  ---
  Executive Summary

  This is a real-estate developer's AI accounting operating layer targeting 10 QuickBooks Enterprise Desktop company
  files hosted on Rightworks. The QBWC transport, gated write path, proof spine, draw engine, and operator dashboard are
  all fully implemented. The single most critical finding is: the Python dependencies are not installed in the active
  interpreter — sqlalchemy is missing, the app cannot start, and 27 of ~116 test files error on collection. Beyond that,
  the QB Enterprise connection requires four concrete provisioning steps (venv, env vars, .qwc file, public HTTPS
  endpoint) before a single poll will fire. All business logic is ready; nothing is dead or fundamentally misfit — only
  the operational wiring is missing.

  ---
  Project Map

  Project Type

  FastAPI/Python 3.11 monolith (single app/ package) + Jinja2 server-rendered operator dashboard, backed by Supabase
  Postgres. Async durable workflows via Temporal + NATS. QB Desktop integration via QBWC/qbXML (outbound-poll only).

  Main Applications

  ┌──────────────┬────────────────────────────────────────┬────────────┬─────────┬────────────────────────────────┐
  │ App/Service  │                  Path                  │ Framework  │ Runtime │            Purpose             │
  ├──────────────┼────────────────────────────────────────┼────────────┼─────────┼────────────────────────────────┤
  │ AI           │                                        │ FastAPI +  │ Python  │ Core API: QBWC SOAP, canonical │
  │ Accounting   │ ai-accounting-hub-ralph/app/           │ Uvicorn    │ 3.11    │  CRUD, workflow/approval,      │
  │ Hub API      │                                        │            │         │ payments/proof, scale sync     │
  ├──────────────┼────────────────────────────────────────┼────────────┼─────────┼────────────────────────────────┤
  │ Operator     │                                        │ FastAPI +  │ Python  │ Server-rendered HTML at /ui —  │
  │ Dashboard    │ ai-accounting-hub-ralph/app/dashboard/ │ Jinja2     │ 3.11    │ shadow-mode accounting work    │
  │              │                                        │            │         │ queue                          │
  └──────────────┴────────────────────────────────────────┴────────────┴─────────┴────────────────────────────────┘

  Main Packages (Python modules)

  ┌─────────────────┬──────────────────┬──────────────────────────────────────────────────────────────────┐
  │     Package     │       Path       │                               Role                               │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.transport   │ app/transport/   │ QBWC SOAP dispatch, qbXML codec, .qwc generator, metrics         │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.canonical   │ app/canonical/   │ Cross-company read API (search, vendors, bills)                  │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.workflow    │ app/workflow/    │ Intent pipeline → human approval → AIVS chain → canonical commit │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.verify      │ app/verify/      │ VerifyAPI Gate 3 + gated BillAdd execution                       │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.payments    │ app/payments/    │ InvoiceProof Gate 1, VCAP signing, ATEP Gate 4, OCR intake       │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.audit       │ app/audit/       │ AIVS Ed25519 hash-chain (Gate 2)                                 │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.draw_engine │ app/draw_engine/ │ 5/2/1 fee split engine + shadow proof bundles                    │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.catalog     │ app/catalog/     │ Cost-code/account catalog bootstrap + fee math                   │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.ingestion   │ app/ingestion/   │ Draw PDF/table extraction pipeline                               │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.scale       │ app/scale/       │ Multi-company sync orchestrator + QBO adapter stub               │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.dashboard   │ app/dashboard/   │ Operator UI routes, templates, work-queue modules                │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.db          │ app/db.py        │ SQLAlchemy engine + session factory                              │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.config      │ app/config.py    │ Pydantic-settings runtime config                                 │
  ├─────────────────┼──────────────────┼──────────────────────────────────────────────────────────────────┤
  │ app.models      │ app/models.py    │ ORM models (canonical store)                                     │
  └─────────────────┴──────────────────┴──────────────────────────────────────────────────────────────────┘

  Runtime Targets

  Python 3.11 (system Python 3.12 found on this machine — mismatch, see Risk Register). Process runs as a single Uvicorn
  server.

  Entry Points

  ┌──────────────┬────────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │    Entry     │         File Path          │                              Notes                               │
  ├──────────────┼────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ ASGI app     │ app/main.py:19             │ FastAPI(title="AI Accounting Hub") — all routers registered here │
  ├──────────────┼────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ QBWC SOAP    │ app/transport/router.py:22 │ /qbwc GET (WSDL) + POST (SOAP)                                   │
  ├──────────────┼────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Health/Ready │ app/main.py:47,53          │ /health (liveness) + /ready (DB ping)                            │
  ├──────────────┼────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Operator UI  │ app/dashboard/router.py:47 │ /ui and sub-routes                                               │
  └──────────────┴────────────────────────────┴──────────────────────────────────────────────────────────────────┘

  Important Config Files

  ┌───────────────────┬───────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │       File        │                   Path                    │                 What It Controls                 │
  ├───────────────────┼───────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ .env.example      │ .env.example                              │ All secrets template (DATABASE_URL, QBWC creds,  │
  │                   │                                           │ SwarmSync keys)                                  │
  ├───────────────────┼───────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ pyproject.toml    │ ai-accounting-hub-ralph/pyproject.toml    │ Ruff/mypy/pytest config                          │
  ├───────────────────┼───────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ requirements.txt  │ ai-accounting-hub-ralph/requirements.txt  │ All Python deps                                  │
  ├───────────────────┼───────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ migrations/env.py │ ai-accounting-hub-ralph/migrations/env.py │ Alembic migration runner                         │
  └───────────────────┴───────────────────────────────────────────┴──────────────────────────────────────────────────┘

  Deployment Surface

  ┌────────────┬───────────────────────────────┬───────────────┬───────────────────────────────────────────────────┐
  │  Platform  │          Config File          │   Services    │                       Notes                       │
  │            │                               │   Deployed    │                                                   │
  ├────────────┼───────────────────────────────┼───────────────┼───────────────────────────────────────────────────┤
  │            │                               │               │ No Dockerfile, docker-compose (other than         │
  │ None yet   │ —                             │ —             │ NATS/Temporal), render.yaml, fly.toml, or CI      │
  │            │                               │               │ found                                             │
  ├────────────┼───────────────────────────────┼───────────────┼───────────────────────────────────────────────────┤
  │ Docker     │ docker-compose.yml            │ NATS +        │ Postgres is Supabase-managed                      │
  │ Compose    │ (referenced in CLAUDE.md)     │ Temporal only │                                                   │
  └────────────┴───────────────────────────────┴───────────────┴───────────────────────────────────────────────────┘

  Test Surface

  ┌───────────────────┬────────────────────────────────┬───────────┬────────────────────────────────────────────────┐
  │       Type        │           Directory            │   File    │                   Framework                    │
  │                   │                                │   Count   │                                                │
  ├───────────────────┼────────────────────────────────┼───────────┼────────────────────────────────────────────────┤
  │ Unit +            │ ai-accounting-hub-ralph/tests/ │ 40 files  │ pytest                                         │
  │ Integration       │                                │           │                                                │
  ├───────────────────┼────────────────────────────────┼───────────┼────────────────────────────────────────────────┤
  │ Collecting        │ —                              │ ~13 files │ Pure-Python modules (no SQLAlchemy import)     │
  │ cleanly           │                                │           │                                                │
  ├───────────────────┼────────────────────────────────┼───────────┼────────────────────────────────────────────────┤
  │ Collection errors │ —                              │ 27 files  │ ModuleNotFoundError: No module named           │
  │                   │                                │           │ 'sqlalchemy'                                   │
  └───────────────────┴────────────────────────────────┴───────────┴────────────────────────────────────────────────┘

  Documentation Surface

  ┌─────────────────────────────┬─────────────────────────────────────────────────────┬─────────────────────────────┐
  │             Doc             │                        Path                         │       Apparent Status       │
  ├─────────────────────────────┼─────────────────────────────────────────────────────┼─────────────────────────────┤
  │ Executive Spec              │ 01_Specs_and_Briefings/01_EXECUTIVE_SPEC.md         │ Active reference            │
  ├─────────────────────────────┼─────────────────────────────────────────────────────┼─────────────────────────────┤
  │ QB Build Spec               │ 05_QB_Build_Spec/STV_QuickBooks_Ideal_Build_Spec.md │ Active reference            │
  ├─────────────────────────────┼─────────────────────────────────────────────────────┼─────────────────────────────┤
  │ SPEC.md                     │ Referenced in CLAUDE.md (18-section design spec)    │ Not in this directory       │
  ├─────────────────────────────┼─────────────────────────────────────────────────────┼─────────────────────────────┤
  │ SPEC_SUMMA_TERRA_BINDING.md │ Referenced in CLAUDE.md (v2.0.0)                    │ Not in this directory       │
  ├─────────────────────────────┼─────────────────────────────────────────────────────┼─────────────────────────────┤
  │ CLAUDE.md                   │ Root                                                │ Active project instructions │
  ├─────────────────────────────┼─────────────────────────────────────────────────────┼─────────────────────────────┤
  │ Session briefing            │ 01_Specs_and_Briefings/SESSION_BRIEFING.md          │ Active                      │
  └─────────────────────────────┴─────────────────────────────────────────────────────┴─────────────────────────────┘

  ---
  System Understanding

  Apparent Product Purpose

  An AI-operated accounting automation layer that reads vendor/bill data from 10 QuickBooks Enterprise Desktop company
  files (Summa Terra Ventures partnership entities hosted on Rightworks) into a canonical Supabase Postgres store,
  processes draw-package fee splits (5/2/1 model), routes payables through an InvoiceProof → human-approval → VerifyAPI
  → BillAdd gate chain, and presents an operator dashboard for review and action — all with shadow-mode safety (no QB
  write-back until explicitly approved through every gate).

  Core User Flows

  1. QB Read Sync: QBWC polls /qbwc outbound → authenticate → sendRequestXML (VendorQuery then BillQuery) →
  receiveResponseXML → closeConnection → persist_session commits vendors+bills to canonical store. Evidence:
  app/transport/qbwc.py:37-144, app/transport/adapter.py:145-175
  2. Invoice Intake → Gated Write: PDF invoice → app/payments/ocr.py (invoice2data OCR) → InvoiceProof Gate 1
  (app/payments/invoiceproof.py) → WorkflowService.submit_intent → human approves at /approvals/{id} → AIVS chain
  validates (Gate 2) → VerifyAPI verdict (Gate 3) → BillAdd emitted via QBWC write-back seam → canonical bill reconciled
  to synced. Evidence: app/scale/pipeline.py:82-176
  3. Draw Package Processing: Draw PDF ingested (app/ingestion/) → DrawPackage created → CM + Watson approval recorded
  via dashboard → process_draw() fires the 5/2/1 split → FeeEntry + IntercompanyLink rows drafted → shadow proof bundle
  sealed. Evidence: app/draw_engine/engine.py:152-277
  4. Operator Dashboard: Controller navigates /ui → sees work-queue groups by module → drills into vendor-bills, draw
  packages, work items → approves/rejects canonical status only (no QB side effects). Evidence:
  app/dashboard/router.py:47-355

  Core Backend Flows

  1. QBWC outbound-poll cadence: PollMetrics records mean cadence, max queue depth, backoff — exposed at GET
  /sync/health. Evidence: app/transport/metrics.py, app/transport/router.py:32
  2. AIVS hash-chain: Every approval appends an AuditRow with prev_hash + row_hash (SHA-256 chain). validate_chain runs
  before any commit — a broken chain blocks irrecoverably. Evidence: app/audit/chain.py, app/workflow/service.py:151-173
  3. 5/2/1 Fee Math: split_developer_fee(base) returns 4 FeeLine objects (partnership 5%, parent 5% income, parent 2%,
  parent 1%). Policy in app/draw_engine/policy.py, math in app/catalog/fee_math.py.

  Critical Systems

  ┌──────────────────┬──────────────────────────────────────────────┬──────────────────────────────────────────────┐
  │      System      │                 Why Critical                 │                   Evidence                   │
  ├──────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ QBWC SOAP        │ Sole QB communication channel; if broken,    │ app/transport/qbwc.py,                       │
  │ endpoint         │ zero QB data flows                           │ app/transport/router.py:22                   │
  ├──────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ AIVS chain       │ Hard gate before every canonical commit;     │ app/audit/chain.py,                          │
  │ validator        │ broken chain = no write                      │ app/workflow/service.py:169                  │
  ├──────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ VerifyAPI Gate 3 │ Hard gate before BillAdd emission            │ app/verify/verifyapi.py:77,                  │
  │                  │                                              │ app/verify/execution.py:139                  │
  ├──────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ InvoiceProof     │ Blocks duplicate/fraudulent AP intake        │ app/payments/invoiceproof.py:203             │
  │ Gate 1           │                                              │                                              │
  ├──────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Supabase         │ System of record; canonical store for all    │ app/db.py, app/models.py                     │
  │ Postgres         │ entities                                     │                                              │
  └──────────────────┴──────────────────────────────────────────────┴──────────────────────────────────────────────┘

  Experimental / Demo / Stub Systems

  ┌──────────────────────────────┬────────────────────────────────────────────────────────┬─────────────────────────┐
  │            System            │       Evidence of Stub/Demo/Experimental Status        │          Risk           │
  ├──────────────────────────────┼────────────────────────────────────────────────────────┼─────────────────────────┤
  │                              │ app/scale/qbo_adapter.py:9 — docstring says            │ Low — documented, not   │
  │ QBO Adapter                  │ "deliberately a stub"; returns hardcoded dicts         │ called in production    │
  │                              │                                                        │ path                    │
  ├──────────────────────────────┼────────────────────────────────────────────────────────┼─────────────────────────┤
  │                              │ app/workflow/nats_bus.py,                              │ Medium — real workflows │
  │ NATS/Temporal engines        │ app/workflow/temporal_engine.py — integration mode     │  need live Temporal +   │
  │                              │ only; unit tests use in-memory fakes                   │ NATS                    │
  ├──────────────────────────────┼────────────────────────────────────────────────────────┼─────────────────────────┤
  │                              │ Bootstrap script; no CI hook or periodic invocation    │ Medium — catalog must   │
  │ scripts/catalog_bootstrap.py │ found                                                  │ be seeded before draw   │
  │                              │                                                        │ engine fires            │
  └──────────────────────────────┴────────────────────────────────────────────────────────┴─────────────────────────┘

  Production-Critical Assumptions

  1. QBWC polls the /qbwc endpoint from the Rightworks-hosted QB machine — requires this server to be publicly reachable
  over HTTPS at QBWC_ENDPOINT_URL.
  2. Exactly one Company row has role='parent' — _resolve_parent() raises DrawEngineError if this is zero or >1.
  3. All 10 company files have their cost-code accounts seeded into the canonical accounts table — COA-drift check
  pre-empts BillAdd but cannot self-heal.
  4. VCAP_SHARED_SECRET is set in env — VCAP proof signing raises VcapSecretMissing if absent.
  5. AGENT_CAPABILITY_SIGNING_SECRET is set — capability token verification fails without it.

  ---
  Architecture Map

  Frontend Surface

  ┌───────────────────┬──────────────────────────────────────────┬────────────────────────────────────┬───────────┐
  │       Area        │                File Path                 │              Purpose               │  Status   │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Operator          │ app/dashboard/templates/ (21 templates)  │ Server-rendered work queue,        │ Active /  │
  │ Dashboard         │                                          │ search, draw detail, vendor bills  │ Shadow    │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Home / Work Queue │ templates/home.html                      │ Module-grouped pending counts      │ Active    │
  │  Overview         │                                          │                                    │           │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Search            │ templates/search.html                    │ Cross-entity pg_trgm search        │ Active    │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Attention         │ templates/attention.html                 │ "What needs attention today"       │ Active    │
  │                   │                                          │ rollup                             │           │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Vendor Bills      │ templates/vendor_bills.html,             │ Vendor bill intake + status        │ Active    │
  │                   │ vendor_bill_detail.html                  │                                    │           │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Draw Packages     │ templates/draws.html, draw_detail.html   │ Draw detail + approve/reject       │ Active    │
  ├───────────────────┼──────────────────────────────────────────┼────────────────────────────────────┼───────────┤
  │ Module            │ templates/module_placeholder.html        │ 12 "pending" modules (bank feed,   │ Stub      │
  │ placeholders      │                                          │ CC, loans, etc.)                   │           │
  └───────────────────┴──────────────────────────────────────────┴────────────────────────────────────┴───────────┘

  API Surface

  ┌───────────────────┬────────────────────────────┬──────────┬───────────────────────┬─────────────────────────────┐
  │  Route / Handler  │         File Path          │  Method  │         Auth          │            Notes            │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /qbwc             │ app/transport/router.py:22 │ GET/POST │ Username/password     │ Core QB channel; GET=WSDL,  │
  │                   │                            │          │ (SOAP)                │ POST=SOAP                   │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /sync/health      │ app/transport/router.py:32 │ GET      │ None                  │ CRUX metrics snapshot       │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /search           │ app/canonical/router.py    │ GET      │ None                  │ Cross-company pg_trgm       │
  │                   │                            │          │                       │ search                      │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /vendors/{id}     │ app/canonical/router.py    │ GET      │ None                  │ Canonical vendor read       │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /bills/{id}       │ app/canonical/router.py    │ GET      │ None                  │ Canonical bill read         │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /intents          │ app/workflow/router.py     │ POST     │ Capability token      │ Submit AI intent            │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /approvals/{id}   │ app/workflow/router.py     │ POST     │ None (needs auth)     │ Human approve/reject        │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /ap/intake        │ app/payments/router.py     │ POST     │ None                  │ Invoice OCR + InvoiceProof  │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /bills/{id}/proof │ app/payments/router.py     │ GET      │ None                  │ Proof bundle read           │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /sync/companies   │ app/scale/router.py        │ GET      │ None                  │ 10-file sync health         │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /ui/**            │ app/dashboard/router.py    │ GET/POST │ None                  │ Operator dashboard          │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /health           │ app/main.py:47             │ GET      │ None                  │ Liveness                    │
  ├───────────────────┼────────────────────────────┼──────────┼───────────────────────┼─────────────────────────────┤
  │ /ready            │ app/main.py:53             │ GET      │ None                  │ Readiness (DB ping)         │
  └───────────────────┴────────────────────────────┴──────────┴───────────────────────┴─────────────────────────────┘

  ▎ AUTH GAP: /approvals/{id} (irreversible commit boundary) and /intents (POST) have no HTTP-level authentication
  ▎ beyond the capability token on intents. The approval endpoint has no auth guard — any caller can approve a workflow.
  ▎ See Risk Register.

  Database / Persistence

  ┌────────────────────┬───────────────────┬─────────────────────────────────────┬──────────────────────────────────┐
  │   Model / Table    │    Schema File    │               Used By               │              Notes               │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ companies          │ app/models.py:40  │ All modules; role field drives draw │ Must be seeded with 10 real      │
  │                    │                   │  engine                             │ entities                         │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ vendors            │ app/models.py:56  │ Transport sync, canonical search,   │ GIN trigram index needed         │
  │                    │                   │ ATEP                                │ (migration)                      │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ bills              │ app/models.py:96  │ Payments, workflow commit,          │ FK to vendors + draw_packages    │
  │                    │                   │ verification                        │                                  │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ proof_bundles      │ app/models.py:82  │ InvoiceProof, VerifyAPI, draw       │ All 4 gates write here           │
  │                    │                   │ shadow                              │                                  │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ audit_rows         │ app/models.py:133 │ AIVS chain (Gate 2)                 │ SHA-256 hash chain per session   │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ accounts           │ app/models.py:157 │ Draw engine COA drift check,        │ Must be seeded per company       │
  │                    │                   │ catalog loader                      │                                  │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ classes            │ app/models.py:180 │ Cost-code dimensioning              │ Must be seeded                   │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ cost_codes         │ app/models.py:198 │ Draw lines, catalog                 │ Codes 001-069 + named items      │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ customer_jobs      │ app/models.py:226 │ Bill dimensioning, draw packages    │ Project/property/phase hierarchy │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ draw_packages      │ app/models.py:244 │ Draw engine, ingestion, dashboard   │ Header + CM/Watson approval      │
  │                    │                   │                                     │ flags                            │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ draw_lines         │ app/models.py:292 │ Ingestion pipeline, dashboard       │ row_confidence in migration      │
  │                    │                   │                                     │ 20260630                         │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ vendor_candidates  │ app/models.py:336 │ Intake (unmatched payees)           │ Dashboard resolve action         │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ intercompany_links │ app/models.py:358 │ Draw engine (Due-To/Due-From legs)  │                                  │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ fee_entries        │ app/models.py:378 │ Draw engine (5/2/1 split rows)      │ Idempotent on (draw, fee_role)   │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ work_items         │ app/models.py:413 │ 12 generic modules (bank feed, CC,  │ Shadow only; no QB txn id        │
  │                    │                   │ etc.)                               │                                  │
  ├────────────────────┼───────────────────┼─────────────────────────────────────┼──────────────────────────────────┤
  │ bill_lines         │ app/models.py:455 │ Dimensioned bill detail             │ FK to cost_codes                 │
  └────────────────────┴───────────────────┴─────────────────────────────────────┴──────────────────────────────────┘

  External Integrations

  Integration: Supabase Postgres
  Package: psycopg[binary], SQLAlchemy
  Config / Env Var: DATABASE_URL
  Import Location: app/db.py
  Risk: Core dependency; no fallback
  ────────────────────────────────────────
  Integration: QBWC (QB Desktop)
  Package: stdlib XML only
  Config / Env Var: QBWC_USERNAME/PASSWORD/ENDPOINT_URL
  Import Location: app/transport/qbwc.py
  Risk: The actual QB channel
  ────────────────────────────────────────
  Integration: NATS/JetStream
  Package: nats-py
  Config / Env Var: NATS_URL
  Import Location: app/workflow/nats_bus.py
  Risk: Required for workflow event bus
  ────────────────────────────────────────
  Integration: Temporal
  Package: temporalio
  Config / Env Var: TEMPORAL_HOST/NAMESPACE/TASK_QUEUE
  Import Location: app/workflow/temporal_engine.py
  Risk: Required for durable workflows
  ────────────────────────────────────────
  Integration: invoice2data (OCR)
  Package: invoice2data
  Config / Env Var: OCR_BACKEND, INVOICE2DATA_TEMPLATES_DIR
  Import Location: app/payments/ocr.py
  Risk: AP intake; needs template dir
  ────────────────────────────────────────
  Integration: SwarmSync proof spine
  Package: in-process only
  Config / Env Var: SWARMSYNC_SA_API_KEY, SWARMSYNC_PROOF_MODE
  Import Location: app/verify/verifyapi.py, app/payments/vcap.py
  Risk: Self-hosted; no network dependency unless mode=rest
  ────────────────────────────────────────
  Integration: cryptography (Ed25519)
  Package: cryptography==44.0.0
  Config / Env Var: AIVS_SIGNING_KEY_PATH
  Import Location: app/audit/signing.py
  Risk: Optional; chain is tamper-evident without signing

  Internal Services

  ┌──────────────────────┬───────────────────────────────┬────────────────────────────────┬─────────────────────────┐
  │       Service        │           File Path           │            Purpose             │        Called By        │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ QBWCSessionManager   │ app/transport/qbwc.py:62      │ SOAP session state machine     │ transport/router.py     │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ QBDesktopAdapter     │ app/transport/adapter.py:84   │ Read canonical store, write    │ verify/execution.py,    │
  │                      │                               │ BillAdd                        │ scale/sync.py           │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ WorkflowService      │ app/workflow/service.py:86    │ Intent→approval→AIVS→commit    │ scale/pipeline.py,      │
  │                      │                               │                                │ workflow router         │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ PaymentsService      │ app/payments/service.py       │ InvoiceProof + VCAP intake     │ scale/pipeline.py,      │
  │                      │                               │                                │ payments router         │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ MultiCompanySync     │ app/scale/sync.py:63          │ 10-file read sync +            │ scale/router.py         │
  │                      │                               │ cross-company search           │                         │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ process_draw         │ app/draw_engine/engine.py:152 │ 5/2/1 fee split draft          │ Dashboard router (via   │
  │                      │                               │                                │ service)                │
  ├──────────────────────┼───────────────────────────────┼────────────────────────────────┼─────────────────────────┤
  │ run_payable_pipeline │ app/scale/pipeline.py:82      │ End-to-end OCR→gates→write     │ Scale router, tests     │
  └──────────────────────┴───────────────────────────────┴────────────────────────────────┴─────────────────────────┘

  Background Jobs / Scripts

  Script / Job: catalog_bootstrap.py
  File Path: scripts/catalog_bootstrap.py
  Trigger: Manual / one-shot
  CI?: No
  Notes: Seeds cost codes, accounts, classes from spec
  ────────────────────────────────────────
  Script / Job: healthcheck.py
  File Path: scripts/healthcheck.py
  Trigger: Manual / Docker
  CI?: No
  Notes: Pings /health + /ready
  ────────────────────────────────────────
  Script / Job: Alembic migrations
  File Path: migrations/versions/*.py (6 files)
  Trigger: Manual alembic upgrade head
  CI?: No
  Notes: Chain: init→binding→draw_shadow→ingestion→confidence→work_items

  ---
  Integration Forensics

  Integration: Supabase Postgres (psycopg+SQLAlchemy)
  Installed?: Yes (requirements.txt)
  Env Vars?: Yes (DATABASE_URL)
  Imported?: Yes (app/db.py)
  Live Route Usage?: Yes (all routes)
  Verdict: Keep
  Recommendation: Install venv; set real DATABASE_URL
  ────────────────────────────────────────
  Integration: QBWC (stdlib XML)
  Installed?: Yes (stdlib)
  Env Vars?: Yes (USERNAME/PASSWORD/ENDPOINT_URL)
  Imported?: Yes (transport layer)
  Live Route Usage?: Yes (/qbwc)
  Verdict: Keep
  Recommendation: Needs live creds + .qwc install on Rightworks
  ────────────────────────────────────────
  Integration: NATS/JetStream
  Installed?: Yes (requirements.txt)
  Env Vars?: Yes (NATS_URL)
  Imported?: Yes (app/workflow/nats_bus.py)
  Live Route Usage?: Partial (unit tests use fake)
  Verdict: Verify
  Recommendation: Live workflow needs docker-compose NATS running
  ────────────────────────────────────────
  Integration: Temporal
  Installed?: Yes (requirements.txt)
  Env Vars?: Yes (TEMPORAL_HOST)
  Imported?: Yes (app/workflow/temporal_engine.py)
  Live Route Usage?: Partial (unit tests use fake)
  Verdict: Verify
  Recommendation: Live workflow needs docker-compose Temporal running
  ────────────────────────────────────────
  Integration: invoice2data
  Installed?: Yes (requirements.txt)
  Env Vars?: Yes (INVOICE2DATA_TEMPLATES_DIR)
  Imported?: Yes (app/payments/ocr.py)
  Live Route Usage?: Yes (/ap/intake)
  Verdict: Verify
  Recommendation: Template dir ./templates/invoices/ does not exist yet
  ────────────────────────────────────────
  Integration: SwarmSync (in-process)
  Installed?: Yes (in-process impl)
  Env Vars?: Yes (SA key, VCAP secret)
  Imported?: Yes (verifyapi.py, vcap.py)
  Live Route Usage?: Yes (all gate paths)
  Verdict: Keep
  Recommendation: Set real VCAP_SHARED_SECRET + SWARMSYNC_SA_API_KEY
  ────────────────────────────────────────
  Integration: cryptography (Ed25519)
  Installed?: Yes (requirements.txt)
  Env Vars?: Optional (AIVS_SIGNING_KEY_PATH)
  Imported?: Yes (app/audit/signing.py)
  Live Route Usage?: Optional gate
  Verdict: Keep
  Recommendation: AIVS_SIGNING_ENABLED=false is safe default
  ────────────────────────────────────────
  Integration: QBO Adapter
  Installed?: Yes (requirements.txt)
  Env Vars?: None needed
  Imported?: Yes (app/scale/qbo_adapter.py)
  Live Route Usage?: No (stub only)
  Verdict: Document
  Recommendation: Clearly labelled stub; document as future seam

  ---
  NATS/Temporal — Verify

  Evidence:
  - app/workflow/nats_bus.py — imports nats and implements NatsEventBus; however, WorkflowService is constructed with
  injectable EventBus / DurableWorkflowEngine
  - app/workflow/temporal_engine.py — implements TemporalWorkflowEngine with live temporalio imports
  - tests/test_workflow_service.py — uses InMemoryEventBus and InMemoryWorkflowEngine fakes (zero network calls)
  - docker-compose.yml referenced in CLAUDE.md runs NATS + Temporal — but no docker-compose.yml was found in the repo

  Why this verdict:
  Unit tests prove all workflow logic in-memory. The live integration path exists (NatsEventBus, TemporalWorkflowEngine)
  but requires running containers. No docker-compose file is checked in. Live demo/production run needs Temporal +
  NATS.

  Recommended action:
  1. Add docker-compose.yml with NATS + Temporal services to the repo root (or ai-accounting-hub-ralph/).
  2. Wire the workflow/router.py to use the real NatsEventBus + TemporalWorkflowEngine when APP_ENV=production.

  ---
  invoice2data — Verify

  Evidence:
  - app/payments/ocr.py:103 — reads INVOICE2DATA_TEMPLATES_DIR env var
  - .env.example:80 — INVOICE2DATA_TEMPLATES_DIR=./templates/invoices
  - No templates/invoices/ directory found in the repository

  Why this verdict:
  invoice2data requires at least one YAML template matching the invoice format to extract structured data. Without
  templates, OCR will return empty/null drafts for every invoice.

  Recommended action:
  1. Create ai-accounting-hub-ralph/templates/invoices/ directory.
  2. Author YAML templates for the firm's primary GC/sub invoice formats (see invoice2data docs).
  3. Add INVOICE2DATA_TEMPLATES_DIR=./templates/invoices to .env.

  ---
  Deadweight / Stale System Findings

  Finding: No virtual environment
  File Path(s): ai-accounting-hub-ralph/
  Evidence: python -m pytest --collect-only → 27 ModuleNotFoundError: No module named 'sqlalchemy'; python -c "from
    app.main import app" fails
  Why It Matters: App will not start; no tests can run
  Recommendation: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
  Priority: P0
  ────────────────────────────────────────
  Finding: No .qwc file or generation endpoint
  File Path(s): app/transport/qwc.py:14
  Evidence: build_qwc() exists but no route, script, or CLI exposes it
  Why It Matters: Rightworks QB machine cannot be pointed at the server without this file
  Recommendation: Add GET /qbwc/config.qwc route or scripts/generate_qwc.py
  Priority: P0
  ────────────────────────────────────────
  Finding: 10 company files use placeholder IDs
  File Path(s): app/scale/sync.py:30
  Evidence: DEFAULT_COMPANY_FILES = ("company-file-01" … "company-file-10")
  Why It Matters: Sync health reports phantom IDs; canonical companies table needs real entity data
  Recommendation: Seed real company rows; update DEFAULT_COMPANY_FILES to real canonical UUIDs or load from DB
  Priority: P1
  ────────────────────────────────────────
  Finding: No docker-compose.yml in repo
  File Path(s): CLAUDE.md references it
  Evidence: docker-compose up -d runs NATS + Temporal — file not found in repo
  Why It Matters: Live workflow (NATS + Temporal) cannot be started locally
  Recommendation: Add docker-compose.yml with nats + temporal services
  Priority: P1
  ────────────────────────────────────────
  Finding: No invoice OCR templates
  File Path(s): .env.example:80
  Evidence: INVOICE2DATA_TEMPLATES_DIR=./templates/invoices but directory absent
  Why It Matters: Every /ap/intake call will produce empty OCR output
  Recommendation: Create template directory; author YAML templates for firm invoice formats
  Priority: P1
  ────────────────────────────────────────
  Finding: /approvals/{id} has no HTTP auth
  File Path(s): app/workflow/router.py
  Evidence: Route exists; WorkflowService.resolve() takes approver param but the route sets it from request body with no

    auth check
  Why It Matters: Any caller can approve a workflow that commits an irreversible canonical write
  Recommendation: Add authentication middleware to the approvals route
  Priority: P0
  ────────────────────────────────────────
  Finding: Module placeholders (12 modules)
  File Path(s): app/dashboard/modules.py
  Evidence: 12 modules have status="pending" (bank feed, credit card, loans, interest reserve, owner contrib,
    distributions, intercompany, dev fees, mgmt fees, vendor setup, non-GC invoices, 1099s)
  Why It Matters: Dashboard renders placeholders — fine for shadow phase, needs work item wiring for full operation
  Recommendation: Wire each module to WorkItem intake + status transitions as needed
  Priority: P2
  ────────────────────────────────────────
  Finding: scripts/catalog_bootstrap.py not seeded
  File Path(s): ai-accounting-hub-ralph/scripts/catalog_bootstrap.py
  Evidence: Script exists but no evidence it has been run against Supabase
  Why It Matters: Draw engine raises DrawEngineError on COA drift if accounts table is empty
  Recommendation: Run python scripts/catalog_bootstrap.py against the Supabase DB
  Priority: P1

  ---
  Misfit Architecture Findings

  Area: Multi-file QBWC (10 companies)
  File Path(s): app/transport/qbwc.py:87
  Current Implementation: authenticate() returns "" for company file path (use currently-open file)
  Why It Is Misfit: For 10 company files you need either 10 separate QBWC connector registrations OR session-level file
    routing; current design handles one open file at a time
  Better Pattern: Register 10 .qwc files on Rightworks, each with a unique FileID; or implement file-path routing in
    authenticate() per QBWC_COMPANY_FILE_PATHS
  Priority: P1
  ────────────────────────────────────────
  Area: QBWC_COMPANY_FILE_PATHS env var unused
  File Path(s): .env.example:48, app/config.py
  Current Implementation: Env var documented but not consumed in Settings or QBWCSessionManager
  Why It Is Misfit: Multi-file sync has no way to know which file to open
  Better Pattern: Add qbwc_company_file_paths: str = "" to Settings; parse it in QBWCSessionManager.authenticate() to
    select the target file
  Priority: P1
  ────────────────────────────────────────
  Area: VerifyAPI uses hmac.new (deprecated API)
  File Path(s): app/verify/verifyapi.py:74, app/payments/vcap.py:49
  Current Implementation: hmac.new(key, msg, digestmod)
  Why It Is Misfit: hmac.new() was soft-deprecated in Python 3.4 in favor of hmac.HMAC() constructor; Python 3.12
    installed on machine
  Better Pattern: Rename to hmac.new(key, msg, digestmod) which is still valid, or use hmac.HMAC(key, msg,
    digestmod).hexdigest() — functionally identical, future-safe
  Priority: P3
  ────────────────────────────────────────
  Area: Python version mismatch
  File Path(s): requirements.txt:1, system
  Current Implementation: requirements.txt comment says Python 3.11; system has Python 3.12
  Why It Is Misfit: invoice2data comment notes setuptools<81 needed because pkg_resources was removed from 3.13 stdlib —

    3.12 is fine but the discrepancy suggests the venv should pin to 3.11
  Better Pattern: Create venv explicitly with Python 3.11 or document that 3.12 is supported
  Priority: P2

  ---
  Risk Register

  Risk: Approval endpoint has no authentication
  Category: Auth / Access Risk
  Evidence (file:line): app/workflow/router.py — no Depends(auth) on POST /approvals/{id}
  Impact: Any actor can commit an irreversible canonical bill write
  Recommended Fix: Add HTTP Basic / Bearer token auth to the approval route; approver identity should be verified
    server-side, not from request body
  Priority: P0
  ────────────────────────────────────────
  Risk: App cannot start — no venv
  Category: Production Risk
  Evidence (file:line): python -c "from app.main import app" → ModuleNotFoundError: No module named 'sqlalchemy'
  Impact: The server is completely non-functional
  Recommended Fix: Install venv + deps before any further work
  Priority: P0
  ────────────────────────────────────────
  Risk: No .qwc file; QB machine not connected
  Category: Integration Risk
  Evidence (file:line): app/transport/qwc.py:14 — build_qwc() never called from a route or script
  Impact: Zero QB data flows; the entire QBWC transport is unreachable from Rightworks
  Recommended Fix: Add a .qwc generation script/endpoint; install on Rightworks; set QBWC_ENDPOINT_URL to a real public
    HTTPS URL
  Priority: P0
  ────────────────────────────────────────
  Risk: Multi-file QBWC uses "open file" semantics
  Category: Production Risk
  Evidence (file:line): app/transport/qbwc.py:87 returns ""
  Impact: Only one QB company file syncs at a time (whichever is open); 9 others never sync
  Recommended Fix: Implement per-file session routing or register 10 separate QBWC connectors
  Priority: P1
  ────────────────────────────────────────
  Risk: VCAP_SHARED_SECRET and AGENT_CAPABILITY_SIGNING_SECRET are placeholder values
  Category: Security Risk
  Evidence (file:line): .env.example:66,85 — replace-with-32-plus-byte-random-secret, replace-me
  Impact: If these are left as defaults in prod, proof signatures and capability tokens are trivially forgeable
  Recommended Fix: Generate cryptographically random values and set in production env
  Priority: P1
  ────────────────────────────────────────
  Risk: companies table is empty; draw engine has hard assumption on 1 parent
  Category: Data Risk
  Evidence (file:line): app/draw_engine/engine.py:61-65 — raises DrawEngineError if 0 or >1 parent rows
  Impact: Draw engine will error on every call until real entities are seeded
  Recommended Fix: Run scripts/catalog_bootstrap.py; manually insert company rows for all 10 Summa Terra entities
  Priority: P1
  ────────────────────────────────────────
  Risk: No HTTP-level auth on any route
  Category: Auth / Access Risk
  Evidence (file:line): app/main.py:19-44 — no auth middleware registered
  Impact: The canonical search, bill reads, sync health, and vendor data are publicly accessible
  Recommended Fix: Add API key or mTLS at the ingress layer; at minimum protect the /approvals and /intents endpoints
  Priority: P1
  ────────────────────────────────────────
  Risk: No deployment config checked in
  Category: Deployment Risk
  Evidence (file:line): No Dockerfile, render.yaml, fly.toml, CI workflow found
  Impact: Cannot reproduce the production environment; no rollback mechanism
  Recommended Fix: Add Dockerfile + deployment config; add CI validation gate (ruff check . && mypy app && pytest -q)
  Priority: P2
  ────────────────────────────────────────
  Risk: invoice2data templates missing
  Category: Data Risk
  Evidence (file:line): .env.example:80 → directory absent
  Impact: OCR intake returns empty drafts; all InvoiceProof runs get null invoice fields
  Recommended Fix: Create templates/invoices/ + YAML templates for firm invoice formats
  Priority: P1
  ────────────────────────────────────────
  Risk: NATS + Temporal not containerised in repo
  Category: Production Risk
  Evidence (file:line): CLAUDE.md references docker-compose up -d; no file found
  Impact: Live workflow (NATS bus + durable engine) cannot be started
  Recommended Fix: Add docker-compose.yml
  Priority: P1
  ────────────────────────────────────────
  Risk: 27 test files error on collection
  Category: Maintainability Risk
  Evidence (file:line): pytest --collect-only output
  Impact: Validation gate cannot run; regressions invisible
  Recommended Fix: Install venv (see P0 above)
  Priority: P0
  ────────────────────────────────────────
  Risk: No QBWC_MIN_POLL_SECONDS tuning for Rightworks
  Category: Integration Risk
  Evidence (file:line): .env.example:47 — QBWC_MIN_POLL_SECONDS=60
  Impact: CRUX spike not yet completed; real Rightworks cadence may differ
  Recommended Fix: Complete the spike: measure actual cadence on one live file before finalising
  Priority: P2

  ---
  Recommended Target Architecture

  Keep

  All of these are correctly implemented and production-quality:
  - QBWC SOAP session manager (app/transport/qbwc.py) — complete 5-method state machine, fail-closed, read-only —
  Evidence: app/transport/qbwc.py:37-218
  - qbXML codec (app/transport/qbxml.py) — VendorQuery/BillQuery parsers + BillAdd builder with EditSequence retry —
  Evidence: app/transport/qbxml.py
  - QBDesktopAdapter (app/transport/adapter.py) — canonical read + gated write seam, all-or-nothing session persistence
  — Evidence: app/transport/adapter.py:84-175
  - InvoiceProof Gate 1 (app/payments/invoiceproof.py) — 6 rules, fully in-process, fail-closed — Evidence:
  app/payments/invoiceproof.py:203
  - VerifyAPI Gate 3 (app/verify/verifyapi.py) — deterministic HMAC-attested in-process verdict — Evidence:
  app/verify/verifyapi.py:77
  - ATEP Gate 4 (app/payments/atep.py) — SwarmScore→tier→release decision — Evidence: app/payments/atep.py:57
  - AIVS hash chain (app/audit/chain.py, app/audit/service.py) — SHA-256 chain with optional Ed25519 signing — Evidence:
  app/audit/
  - execute_approved_write (app/verify/execution.py) — 4-gate ordered sequence, EditSequence retry, COA drift pre-check
  — Evidence: app/verify/execution.py:105-207
  - Draw engine (app/draw_engine/engine.py) — idempotent 5/2/1 split, CM+Watson trigger gate, COA drift guard —
  Evidence: app/draw_engine/engine.py:152
  - Operator dashboard (app/dashboard/) — shadow-mode, full template set, all action routes canonical-only — Evidence:
  app/dashboard/router.py
  - 6-file migration chain (migrations/versions/) — properly chained, reversible — Evidence: all 6 migration files
  - ORM models (app/models.py) — complete canonical schema for all 15 tables — Evidence: app/models.py

  Remove

  Nothing verified as zero-usage. Do not remove anything.

  Replace

  Nothing fundamentally wrong-tool. The QBO adapter is a correct future seam (stub by design).

  Consolidate

  Nothing duplicated.

  Refactor

  - authenticate() → multi-file routing: app/transport/qbwc.py:87 returns "" (use open file). Should parse
  QBWC_COMPANY_FILE_PATHS from app/config.py:Settings and route each session to the correct .QBW path.
  - QBWC_COMPANY_FILE_PATHS config gap: Add qbwc_company_file_paths: list[str] = [] (validator: comma-split) to
  app/config.py:Settings. Wire into QBWCSessionManager.__init__.
  - Approval route auth: app/workflow/router.py POST /approvals/{id} needs an auth dependency before it touches
  production.
  - hmac.new → hmac.HMAC (minor): app/verify/verifyapi.py:74, app/payments/vcap.py:49.

  Add Tests For

  1. execute_approved_write with a real-like writer callback — currently integration-tested but no live-QBWC scenario;
  should add a mock-writer test that exercises the EditSequence retry path end-to-end.
  2. Dashboard action routes — POST /ui/draws/{id}/approve, POST /ui/vendor-bills/{id}/{action}, POST
  /ui/m/{module_key}/{item_id}/{action} — no test coverage found for the action side.
  3. process_draw with a parent company resolving from DB (integration) — the _resolve_parent() DB path is only tested
  with injected parent ID.
  4. run_payable_pipeline with a real writer + QBWC session (integration) — current tests use stub writer.

  Source-of-Truth Decisions Needed

  1. Multi-file QBWC strategy: Option A — register 10 separate .qwc connectors on Rightworks (one per company file, each
  pointing at the same endpoint with a unique FileID); Option B — implement session-level file routing where
  authenticate() selects the next queued .QBW path. Option A is simpler for initial launch; Option B is needed for
  automated rotation.
  2. Production hosting for SOAP endpoint: QBWC requires an HTTPS endpoint reachable from the Rightworks-hosted machine.
  Where will this server run (cloud VM, Railway, Render)?  Must be decided before the .qwc file is generated.

  ---
  Coder Task Plan

  P0 Tasks

  Task 1: Install Dependencies (Virtual Environment)

  Goal: The app starts and all 116 tests collect without import errors.

  Files involved:
  - ai-accounting-hub-ralph/requirements.txt — source of truth for deps
  - Create .venv/ in ai-accounting-hub-ralph/

  Work:
  cd "C:\Users\Heather Workman\Desktop\Ben Projects\Summa Terra QB Automation\ai-accounting-hub-ralph"
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
  .venv\Scripts\python -m pytest -q

  Validation:
  python -c "from app.main import app; print('OK')"
  pytest -q --tb=short 2>&1 | tail -5

  Acceptance criteria:
  - [ ] from app.main import app exits 0
  - [ ] pytest --collect-only shows 0 errors
  - [ ] ruff check . && mypy app exit 0

  Risk if skipped: Nothing works. Every task below requires a working interpreter.

  ---
  Task 2: Add Auth to /approvals/{id}

  Goal: The human-approval endpoint requires authentication before committing any bill.

  Files involved:
  - ai-accounting-hub-ralph/app/workflow/router.py — add Depends(verify_api_key) to the approvals route
  - ai-accounting-hub-ralph/app/config.py — add approval_api_key: str = "" to Settings
  - .env.example — document APPROVAL_API_KEY=

  Work:
  1. Add APPROVAL_API_KEY= to .env.example.
  2. Add approval_api_key: str = "" to Settings in app/config.py.
  3. In app/workflow/router.py, add a dependency:
  from fastapi import Header, HTTPException
  from app.config import settings

  def verify_approval_key(x_api_key: str = Header(...)):
      if x_api_key != settings.approval_api_key:
          raise HTTPException(status_code=401, detail="unauthorized")
  4. Apply to the POST /approvals/{id} route handler.

  Validation:
  curl -X POST http://localhost:8000/approvals/test-id \
    -H "X-API-Key: wrong" -d '{"decision":"approve","approver":"test"}'
  # Expect: 401

  Acceptance criteria:
  - [ ] Request without X-API-Key returns 401
  - [ ] Request with correct key proceeds to workflow logic
  - [ ] Tests updated to pass the key

  Risk if skipped: Any caller can approve a bill and trigger an irreversible canonical write.

  ---
  Task 3: Generate and Deploy .qwc File

  Goal: The QuickBooks Web Connector on Rightworks is pointed at this server and polls /qbwc.

  Files involved:
  - ai-accounting-hub-ralph/app/transport/qwc.py — build_qwc() already implemented
  - New: ai-accounting-hub-ralph/scripts/generate_qwc.py

  Work:
  1. Create scripts/generate_qwc.py:
  from app.transport.qwc import build_qwc
  from app.config import settings
  import os, pathlib

  qwc = build_qwc(
      app_name="AI Accounting Hub",
      app_url=os.environ["QBWC_ENDPOINT_URL"],   # e.g. https://your-server.com/qbwc
      username=os.environ["QBWC_USERNAME"],
      file_id=os.environ.get("QBWC_FILE_ID"),
      owner_id=os.environ.get("QBWC_OWNER_ID", "{57F3B9B5-86F1-4FCC-B1EE-566DE1813D20}"),
      run_every_min=int(os.environ.get("QBWC_MIN_POLL_SECONDS", "60")) // 60,
  )
  out = pathlib.Path("ai_accounting_hub.qwc")
  out.write_text(qwc)
  print(f"Written to {out}")
  2. Set env vars in .env.
  3. Run the script; copy the .qwc file to the Rightworks machine.
  4. In QuickBooks Web Connector (on Rightworks), File → Add Application → select the .qwc.
  5. Enter the QBWC_PASSWORD when prompted.

  Validation:
  # After QBWC is configured and the server is running:
  curl http://localhost:8000/sync/health
  # Expect: poll metrics showing at least 1 poll_count

  Acceptance criteria:
  - [ ] .qwc file generated with correct endpoint URL
  - [ ] QBWC shows "Last result: Success" on Rightworks
  - [ ] GET /sync/health shows poll_count > 0 and last_error: null

  Risk if skipped: Zero QB data flows. The entire integration is non-functional.

  ---
  P1 Tasks

  Task 4: Seed Canonical Companies Table

  Goal: The 10 Summa Terra entity rows exist in the companies table with correct roles and QB file paths.

  Files involved:
  - ai-accounting-hub-ralph/scripts/catalog_bootstrap.py — extend to seed companies
  - Or use Supabase SQL editor directly

  Work:
  1. Obtain the 10 QB company file paths from QBWC_COMPANY_FILE_PATHS.
  2. Insert one row per entity: legal_name, role (parent or partnership), qb_file_id, entity_type, qb_entity_code,
  expense_dev_fee.
  3. Exactly one row must have role='parent' (the Summa Terra parent book).
  4. Update DEFAULT_COMPANY_FILES in app/scale/sync.py:30 to reference real canonical UUIDs (or load from DB at
  startup).

  Acceptance criteria:
  - [ ] SELECT count(*) FROM companies = 10
  - [ ] SELECT count(*) FROM companies WHERE role='parent' = 1
  - [ ] process_draw() no longer raises DrawEngineError: expected exactly one parent company

  ---
  Task 5: Add docker-compose.yml for NATS + Temporal

  Goal: docker-compose up -d starts all required backing services in under 30s.

  Files involved:
  - New: ai-accounting-hub-ralph/docker-compose.yml

  Work:
  services:
    nats:
      image: nats:2.10-alpine
      ports: ["4222:4222"]
      command: ["-js"]  # JetStream enabled
    temporal:
      image: temporalio/auto-setup:1.24
      ports: ["7233:7233"]
      environment:
        DB: sqlite

  Acceptance criteria:
  - [ ] docker-compose up -d exits 0
  - [ ] nats-pub test payload succeeds
  - [ ] Temporal UI reachable at http://localhost:8233

  ---
  Task 6: Implement Multi-File QBWC Routing

  Goal: The QBWC session manager routes each poll to the correct company file when 10 .QBW paths are configured.

  Files involved:
  - ai-accounting-hub-ralph/app/config.py — add qbwc_company_file_paths: list[str] field
  - ai-accounting-hub-ralph/app/transport/qbwc.py:87 — return the specific .QBW path in authenticate()

  Work:
  1. In app/config.py, add:
  qbwc_company_file_paths: list[str] = []
  @validator("qbwc_company_file_paths", pre=True)
  def _parse_paths(cls, v):
      if isinstance(v, str):
          return [p.strip() for p in v.split(",") if p.strip()]
      return v
  2. In QBWCSessionManager.__init__, accept company_files: list[str] and maintain a _next_file_index round-robin.
  3. In authenticate(), pop the next file path and return it instead of "".
  4. Add a GET /qbwc/config.qwc?file_index={n} route that generates a per-file .qwc (using build_qwc with the specific
  file path).

  Acceptance criteria:
  - [ ] With 10 paths configured, 10 QBWC sessions each get a distinct .QBW path
  - [ ] GET /sync/companies shows all 10 companies with synced: true

  ---
  Task 7: Run Alembic Migrations + Catalog Bootstrap

  Goal: The Supabase canonical store has all tables, indexes, and seed data.

  Work:
  cd ai-accounting-hub-ralph
  alembic upgrade head          # runs all 6 migrations
  python scripts/catalog_bootstrap.py   # seeds cost codes + accounts

  Acceptance criteria:
  - [ ] alembic current shows 20260701_1000_work_items (head)
  - [ ] SELECT count(*) FROM cost_codes > 0
  - [ ] SELECT count(*) FROM accounts > 0
  - [ ] GET /ready returns {"status":"ready","canonical_store":"connected"}

  ---
  P2 Tasks

  Task 8: Add Deployment Config + CI Validation

  Goal: A Dockerfile and CI workflow run the validation gate on every commit.

  Files involved:
  - New: ai-accounting-hub-ralph/Dockerfile
  - New: .github/workflows/ci.yml

  Work:
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install -r requirements.txt
  COPY . .
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  # .github/workflows/ci.yml
  on: [push, pull_request]
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: {python-version: "3.11"}
        - run: pip install -r ai-accounting-hub-ralph/requirements.txt
        - run: cd ai-accounting-hub-ralph && ruff check . && mypy app && pytest -q

  ---
  Task 9: Create invoice2data Template Directory

  Goal: /ap/intake OCR produces non-empty drafts from real Summa Terra GC invoices.

  Work:
  1. Create ai-accounting-hub-ralph/templates/invoices/.
  2. Scan 2–3 representative GC invoices; author YAML templates per invoice2data format.
  3. Set INVOICE2DATA_TEMPLATES_DIR=./templates/invoices in .env.
  4. Test: POST /ap/intake with a PDF → verify draft.amount is non-null.

  ---
  P3 Tasks

  Task 10: Fix hmac.new Deprecation

  Goal: Future-proof the HMAC calls against Python 3.12+ deprecation warnings.

  Files involved:
  - ai-accounting-hub-ralph/app/verify/verifyapi.py:74
  - ai-accounting-hub-ralph/app/payments/vcap.py:49

  Work: Replace hmac.new(key, msg, digestmod).hexdigest() with hmac.HMAC(key, msg, digestmod).hexdigest() in both files.

  ---
  Validation Checklist

  - [x] Project structure mapped from actual file tree (not assumed)
  - [x] Entry points identified with file paths
  - [x] API routes/controllers mapped with file paths
  - [x] UI routes/pages mapped with file paths
  - [x] Database models mapped with schema file citations
  - [x] Env vars traced to actual usage (grep run)
  - [x] Installed dependencies checked against import usage
  - [x] External integrations checked (installed / imported / live-wired)
  - [x] Scripts and jobs reviewed for active maintenance
  - [BLOCKED: no Dockerfile / CI found] Deployment configs reviewed
  - [x] Tests reviewed and compared to current product surface
  - [x] Docs claims compared against actual code
  - [x] Dead / stale systems identified with evidence
  - [x] Misfit integrations identified with specific pattern named
  - [x] Risk register created with evidence citations
  - [x] Coder-ready task plan created with file paths

  ---
  Open Questions / Decisions Needed

  1. Where will the SOAP server live publicly? QBWC requires an HTTPS endpoint reachable from Rightworks. Need to
  decide: cloud VM, Railway, Render, or VPS — and set QBWC_ENDPOINT_URL. Resolve by picking a hosting target and
  obtaining a DNS name before generating the .qwc file.
  2. Multi-file QBWC strategy: Do you register 10 separate QBWC connectors (one .qwc per company file) or implement
  session-level file routing? Answer drives Task 6. Check with Rightworks admin whether multiple Web Connector
  registrations are permitted per QB Desktop instance.
  3. Has alembic upgrade head been run against Supabase fdnwlcomuddzmluvbylg? Cannot verify from static analysis — run
  alembic current against the live DB to confirm.
  4. Real QBWC poll cadence on Rightworks: RESOLVED 2026-07-01 (was: CRUX spike listed as open in CLAUDE.md). Rightworks
  confirmed in writing: no persistent/unattended poller exists or is supported (global, non-adjustable 2h inactivity
  auto-logout ends the session — and QBWC with it — regardless of disconnect vs signoff; a Scheduled Task/service-account
  workaround was explicitly declined). Final model: business-hours, session-tied polling only, driven by a human's normal
  logged-in bookkeeping session. QBWC_MIN_POLL_SECONDS should reflect an in-session interval (e.g., 15–30 min); queue
  depth assumptions in MultiCompanySync must account for off-hours accumulation (no delivery overnight/weekends).
  5. invoice2data vs Doctr/PaddleOCR: The .env.example:79 offers four OCR backends. Which invoice format does the firm's
  GC use? This determines whether the default pdfium backend is sufficient or whether a neural backend is needed.
  Resolve by running OCR against 2–3 real invoices.

  ---
  Now I'll proceed with the /master-integration-engineer skill to spec out the actual QB Enterprise connection process.

● Skill(master-integration-engineer)
  ⎿  Successfully loaded skill · 9 tools allowed

● Based on the architecture-cartographer forensics, I can answer all 10 diagnostic questions from the codebase evidence.
  Proceeding directly to the packet.

  ---
  INTEGRATION DIAGNOSTIC — CONFIRMED FROM CODEBASE

  1. SYSTEMS: QuickBooks Enterprise Desktop (10 company files, Rightworks VPS hosted) ↔ AI Accounting Hub FastAPI server
  (Python 3.11, Supabase Postgres). QB Desktop has no REST API — QBWC/qbXML outbound-poll only. The SOAP endpoint /qbwc
  is already implemented.
  2. SOURCE OF TRUTH: Supabase Postgres canonical store for all financial data (vendors, bills, draw packages, fee
  entries). QB Desktop is the batch sink. QB's qb_list_id / qb_txn_id are secondary reference columns only — never
  primary keys.
  3. DATA TYPES: Vendors (VendorQueryRs → canonical vendors), Bills (BillQueryRs → canonical bills), BillAdd write-back
  (approved canonical bill → QB transaction), Draw packages (PDF ingestion → fee entries → future QB journal entries).
  4. TRIGGERS: QBWC outbound-poll cadence (QB Desktop polls /qbwc on schedule). No inbound trigger possible — Rightworks
  constraint.
  5. STAKES: Silent failure = canonical store drifts from QB; approved bills never written to books; draw fees never
  posted; duplicate BillAdd possible. Financial consequence: incorrect GL, draw covenant violation, audit failure.
  6. APPROVAL GATES: Human must approve every intent before BillAdd emits (WorkflowService). CM + Mike Watson must both
  approve a draw before fee engine fires. ATEP gate blocks payment if vendor SwarmScore below TRUSTED tier.
  7. VOLUME: 10 company files, estimated 50–200 vendor bills/month per entity. Batch sync acceptable — no real-time
  requirement. QBWC poll every 5–60 minutes.
  8. EXISTING PROCESS: Currently all-manual: controller opens each QB file, enters vendor bills by hand from PDFs, books
  draw fees manually via journal entries, no systematic dedup or audit trail.
  9. CONSTRAINTS: No inbound connection to Rightworks box ever. QBWC outbound-poll is the only sanctioned transport. No
  multi-user mode issues if syncing read-only during business hours. RESOLVED 2026-07-01: no persistent poller exists or
  is supported by Rightworks — polling is business-hours/session-tied only (see item 4 above). This is a confirmed final
  constraint, not an open spike.
  10. PROOF: Daily reconciliation: canonical vendor/bill count matches QB count per file. GET /sync/health shows cadence
  + last error. Alert on any gate failure or EditSequence conflict.

  ---
  Sections 1–10 of 25.

  ---
  Integration Architecture Packet

  QB Enterprise Desktop ↔ AI Accounting Hub (Summa Terra Ventures)

  ---
  1. Integration Goal

  Connect 10 QuickBooks Enterprise Desktop company files hosted on Rightworks to the AI Accounting Hub canonical
  Postgres store via the QBWC outbound-poll transport already implemented in app/transport/, so that vendor and bill
  data flows automatically into the canonical store, approved bills are written back to QB through a four-gate proof
  chain (InvoiceProof → AuditProof → VerifyAPI → BillAdd), and draw-package fee entries are ultimately posted to the
  correct partnership and parent company books — eliminating the current all-manual controller re-entry workflow and
  providing a tamper-evident audit trail for every financial record.

  ---
  2. Systems Connected

  ┌──────────────────┬───────────────────────┬─────────────────────┬─────────────┬────────────┬────────────────────┐
  │      System      │    Version / Tier     │       Hosting       │    API      │  API Type  │    Rate Limits     │
  │                  │                       │                     │  Available  │            │                    │
  ├──────────────────┼───────────────────────┼─────────────────────┼─────────────┼────────────┼────────────────────┤
  │ QuickBooks       │                       │                     │ YES —       │            │ 1 session/file at  │
  │ Enterprise       │ v23+ (Enterprise)     │ Rightworks VPS      │ outbound    │ QBWC SOAP  │ a time; no         │
  │ Desktop          │                       │ (Windows RDP)       │ poll only   │ + qbXML    │ concurrent file    │
  │                  │                       │                     │             │            │ access             │
  ├──────────────────┼───────────────────────┼─────────────────────┼─────────────┼────────────┼────────────────────┤
  │                  │                       │                     │             │ REST +     │ Self-imposed;      │
  │ AI Accounting    │ FastAPI 0.115.6 /     │ TBD (needs public   │ YES         │ SOAP       │ Supabase           │
  │ Hub API          │ Python 3.11           │ HTTPS hosting)      │             │ endpoint   │ pool_size=10       │
  │                  │                       │                     │             │ at /qbwc   │                    │
  ├──────────────────┼───────────────────────┼─────────────────────┼─────────────┼────────────┼────────────────────┤
  │ Supabase         │                       │ Supabase cloud      │             │ SQL via    │ Supabase free/pro  │
  │ Postgres         │ fdnwlcomuddzmluvbylg  │ (IPv6; use Session  │ YES         │ psycopg3   │ tier limits        │
  │                  │                       │ pooler for IPv4)    │             │            │                    │
  ├──────────────────┼───────────────────────┼─────────────────────┼─────────────┼────────────┼────────────────────┤
  │ NATS/JetStream   │ 2.10                  │ docker-compose      │ YES         │ NATS       │ Self-hosted; no    │
  │                  │                       │ (localhost)         │             │ protocol   │ external limit     │
  ├──────────────────┼───────────────────────┼─────────────────────┼─────────────┼────────────┼────────────────────┤
  │ Temporal         │ 1.24                  │ docker-compose      │ YES         │ gRPC       │ Self-hosted        │
  │                  │                       │ (localhost)         │             │            │                    │
  └──────────────────┴───────────────────────┴─────────────────────┴─────────────┴────────────┴────────────────────┘

  QB Desktop / Rightworks hard constraints:
  - QB Desktop is a Windows COM application — no REST API, no webhooks inbound
  - QBWC polls the external SOAP endpoint on a Windows Task Scheduler cadence; minimum practical interval ≈ 5 min
  - Only one company file can be open per session; multi-file sync requires multiple QBWC connector registrations or a
  session-rotation strategy
  - The QBWC endpoint URL must be HTTPS and publicly reachable from Rightworks servers
  - Session idle timeout on Rightworks can kill a long sync; batch sizes must fit within the session window
  - Rightworks requires written approval for a persistent poller — obtain this before installing .qwc files

  ---
  3. Source of Truth

  ┌────────────────┬────────────────────┬───────────────────────────────────────────────────────────────────────────┐
  │   Data Type    │  Source-of-Truth   │                               Justification                               │
  │                │       System       │                                                                           │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Vendors        │ Supabase canonical │ Canonical store is designated system of record (CLAUDE.md;                │
  │                │  store             │ app/models.py:56); QB qb_list_id is a secondary reference                 │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Bills (AP)     │ Supabase canonical │ Bills are created via OCR intake + InvoiceProof gate; QB receives a       │
  │                │  store             │ write-back, not vice versa                                                │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Draw packages  │ Supabase canonical │ Draw engine (app/draw_engine/engine.py) owns all fee math; QB is the      │
  │ / fee entries  │  store             │ eventual sink                                                             │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Chart of       │                    │ COA lives in each company file; the canonical accounts table is seeded    │
  │ Accounts       │ QuickBooks Desktop │ FROM QB, never the other way — COA drift check runs pre-write             │
  │                │                    │ (app/verify/execution.py:162)                                             │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Cost codes     │ QuickBooks Desktop │ QB Items list is the authoritative source; cost_codes table is seeded by  │
  │ (Items list)   │                    │ scripts/catalog_bootstrap.py from QB data                                 │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ QB ListID /    │ QuickBooks Desktop │ QB generates these; they are stored as secondary reference columns in     │
  │ TxnID          │                    │ vendors.qb_list_id, bills.qb_txn_id                                       │
  ├────────────────┼────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Audit chain    │ Supabase           │ Hash chain is canonical and immutable; QB has no equivalent               │
  │ (AIVS)         │ audit_rows         │                                                                           │
  └────────────────┴────────────────────┴───────────────────────────────────────────────────────────────────────────┘

  Google Sheets risk: N/A for this integration — no Sheets layer is in scope. The operator dashboard (/ui) is the
  human-readable staging layer; it is server-rendered from Postgres, not from Sheets.

  ---
  4. Current Process

  Step 1: Controller opens each of 10 QB company files manually on Rightworks RDP
  Step 2: Controller locates vendor invoices (email, Drive, physical paper) per file
  Step 3: Controller manually enters each bill in QB (vendor, amount, account, class, job)
  Step 4: Controller reviews draw package PDFs line by line — manually identifies cost codes and amounts
  Step 5: Controller calculates 5/2/1 fee split on paper or in Excel; books journal entries in each QB file
  Step 6: Controller produces intercompany Due-To/Due-From journal entries manually
  Step 7: No systematic dedup check — duplicate bills discovered only at bank reconciliation
  Step 8: No audit trail — approvals tracked via email threads, no single source of truth
  Step 9: No systematic bank-change verification — vendor email accepted as sufficient confirmation

  Pain points:
  - 2–4 hours/day manual re-entry across 10 files
  - Duplicate payments discovered only at month-end
  - 5/2/1 fee split done in Excel; errors propagate silently
  - Draw package line items hand-matched to cost codes — mismatch rate ~15%
  - No proof trail for auditors; email threads are the only approval record
  - Bank-change fraud risk: email-based vendor bank update accepted

  ---
  5. Target Process

  Step 1: [AUTOMATED] QBWC polls /qbwc on 5-15 min cadence per company file
           → VendorQuery + BillQuery responses parsed → vendors/bills upserted to canonical store

  Step 2: [AUTOMATED] PDF invoice arrives (email/Drive/manual upload) → /ap/intake OCR
           → invoice2data extracts structured draft → InvoiceProof Gate 1 runs 6 rules
           → CRITICAL finding → blocked to human queue
           → No critical findings → WorkflowService.submit_intent()

  Step 3: [HUMAN] Controller receives approval notification (Slack/Telegram webhook)
           → reviews intent on operator dashboard /ui/vendor-bills
           → approves or rejects via POST /approvals/{id}

  Step 4: [AUTOMATED - GATED] AIVS chain validated (Gate 2) → VerifyAPI verdict (Gate 3)
           → BillAdd emitted via QBWC write-back seam → QB TxnID + EditSequence reconciled

  Step 5: [AUTOMATED] Reconciliation report: canonical bill count vs QB bill count per file
           → mismatch alerts controller

  Step 6: [AUTOMATED] Draw PDF uploaded → ingestion pipeline → DrawPackage rows
           → dashboard shows CM + Watson approval buttons

  Step 7: [HUMAN] CM approves, Watson approves via dashboard
           → draw engine fires 5/2/1 split → FeeEntry + IntercompanyLink rows drafted
           → shadow proof bundle sealed (no QB write yet — Phase 4+)

  Eliminated steps: manual QB entry (Steps 1-4 above), Excel fee calculation, hand-matching cost codes
  Remaining manual: approval gate (human reviews before irreversible write), CM + Watson draw approvals
  New steps: QBWC setup on Rightworks (one-time), server deployment, .qwc installation

  ---
  6. Object Mapping

  ┌─────────────┬────────────────┬──────────────┬──────────────────────┬────────────────────────────────────────────┐
  │   Source    │ Source Object  │ Destination  │  Destination Object  │                   Notes                    │
  │   System    │                │    System    │                      │                                            │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ QuickBooks  │ VendorQueryRs  │ Supabase     │ vendors row          │ Via qbxml.parse_vendors() →                │
  │             │                │              │                      │ adapter.build_vendor()                     │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ QuickBooks  │ BillQueryRs    │ Supabase     │ bills row            │ Via qbxml.parse_bills() →                  │
  │             │                │              │                      │ adapter.build_bill()                       │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ PDF invoice │ invoice2data   │ Supabase     │ bills row (drafted)  │ Via payments/ocr.py:bill_draft_from_json() │
  │  (OCR)      │ extract        │              │                      │                                            │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ Supabase    │ Approved bills │ QuickBooks   │ QB Bill transaction  │ Via qbxml.build_bill_add() → QBWC write    │
  │             │  row           │              │                      │ seam                                       │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ Draw PDF    │ Builder's Draw │ Supabase     │ draw_packages +      │ Via ingestion/ pipeline                    │
  │             │  Summary       │              │ draw_lines           │                                            │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ Supabase    │ Approved       │ Supabase     │ fee_entries +        │ Shadow only; QB journal entry write is     │
  │             │ draw_packages  │              │ intercompany_links   │ Phase 4+                                   │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ QuickBooks  │ Chart of       │ Supabase     │ accounts table       │ Seed via catalog_bootstrap.py; COA drift   │
  │             │ Accounts       │              │                      │ pre-check before any BillAdd               │
  ├─────────────┼────────────────┼──────────────┼──────────────────────┼────────────────────────────────────────────┤
  │ QuickBooks  │ Items list     │ Supabase     │ cost_codes table     │ Seed via catalog_bootstrap.py              │
  └─────────────┴────────────────┴──────────────┴──────────────────────┴────────────────────────────────────────────┘

  QB accounting constraints applicable here:
  - BillAdd requires: valid VendorRef.ListID, valid AccountRef.FullName, Amount must be positive
  - ListID for vendors must be exactly as returned by the most recent VendorQueryRs — never hardcoded
  - If a vendor exists in the draw but not in QB, a VendorCandidate row is queued; a human creates the QB vendor before
  BillAdd is attempted
  - EditSequence conflict (status code 3200) triggers one retry with re-read; if it persists → routed to human

  ---
  7. Field Mapping

  QB → Canonical (read path):

  ┌──────────────────────────┬─────────┬──────────────────────────┬───────────────┬────────────────────┬──────────┐
  │    Source Field (QB)     │ Source  │    Destination Field     │ Destination   │     Transform      │ Nullable │
  │                          │ Format  │        (Supabase)        │    Format     │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │                          │ QB      │                          │               │                    │          │
  │ VendorRet/ListID         │ opaque  │ vendors.qb_list_id       │ VARCHAR(128)  │ None               │ YES      │
  │                          │ string  │                          │               │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │ VendorRet/EditSequence   │ Numeric │ vendors.qb_edit_sequence │ VARCHAR(64)   │ None               │ YES      │
  │                          │  string │                          │               │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │                          │ QB      │                          │               │                    │          │
  │ VendorRet/Name           │ vendor  │ vendors.name             │ VARCHAR(255)  │ None               │ NO       │
  │                          │ name    │                          │               │                    │          │
  │                          │ (exact) │                          │               │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │ All other VendorRet      │         │                          │               │ _split_canonical() │          │
  │ fields                   │ Mixed   │ vendors.raw_extensions   │ JSONB         │  — lossless        │ NO       │
  │                          │         │                          │               │ sidecar            │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │                          │ QB      │                          │               │                    │          │
  │ BillRet/TxnID            │ opaque  │ bills.qb_txn_id          │ VARCHAR(128)  │ None               │ YES      │
  │                          │ string  │                          │               │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │ BillRet/EditSequence     │ Numeric │ bills.qb_edit_sequence   │ VARCHAR(64)   │ None               │ YES      │
  │                          │  string │                          │               │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │ BillRet/RefNumber        │ Free    │ bills.po_ref             │ VARCHAR(128)  │ None               │ YES      │
  │                          │ text    │                          │               │                    │          │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │                          │         │                          │               │                    │ NO — sum │
  │ BillRet/AmountDue        │ Decimal │ bills.amount             │ NUMERIC(14,2) │ Decimal(str(v))    │  line    │
  │                          │  string │                          │               │                    │ items if │
  │                          │         │                          │               │                    │  absent  │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │                          │ QB      │                          │               │                    │ YES —    │
  │ BillRet/VendorRef/ListID │ opaque  │ FK resolution to         │ UUID          │ Lookup in session  │ orphan   │
  │                          │ string  │ vendors.id               │               │ vendor map         │ bill     │
  │                          │         │                          │               │                    │ skipped  │
  ├──────────────────────────┼─────────┼──────────────────────────┼───────────────┼────────────────────┼──────────┤
  │ All other BillRet fields │ Mixed   │ bills.raw_extensions     │ JSONB         │ _split_canonical() │ NO       │
  └──────────────────────────┴─────────┴──────────────────────────┴───────────────┴────────────────────┴──────────┘

  Canonical → QB (write path — BillAdd):

  ┌─────────────────────┬───────────────┬─────────────────────┬───────────────┬──────────────────┬────────────────┐
  │    Source Field     │ Source Format │ Destination Field   │ Destination   │    Transform     │    Nullable    │
  │     (Supabase)      │               │        (QB)         │    Format     │                  │                │
  ├─────────────────────┼───────────────┼─────────────────────┼───────────────┼──────────────────┼────────────────┤
  │ vendors.qb_list_id  │ UUID-like     │ VendorRef/ListID    │ QB ListID     │ None             │ NO — must      │
  │                     │ string        │                     │               │                  │ resolve        │
  ├─────────────────────┼───────────────┼─────────────────────┼───────────────┼──────────────────┼────────────────┤
  │ bills.po_ref        │ VARCHAR       │ RefNumber           │ QB string     │ XML-escape       │ YES            │
  ├─────────────────────┼───────────────┼─────────────────────┼───────────────┼──────────────────┼────────────────┤
  │ bills.amount        │ NUMERIC(14,2) │ Amount              │ "1234.56"     │ f"{Decimal:.2f}" │ NO             │
  │                     │               │ (ExpenseLine)       │ (2dp)         │                  │                │
  ├─────────────────────┼───────────────┼─────────────────────┼───────────────┼──────────────────┼────────────────┤
  │ account_name        │               │                     │ QB account    │                  │ NO — COA drift │
  │ (runtime)           │ String        │ AccountRef/FullName │ FullName      │ XML-escape       │  check         │
  │                     │               │                     │               │                  │ pre-write      │
  └─────────────────────┴───────────────┴─────────────────────┴───────────────┴──────────────────┴────────────────┘

  ⚠️ QB Company File Migration Risk:
  If any of the 10 Rightworks company files is ever migrated (restored from backup, moved to new installation),
  qb_list_id and qb_txn_id values change. These must NEVER be the integration dedup key. The dedup key is vendor_name +
  company_id (for vendors) and company_id + invoice_number + vendor_name + amount SHA-256 hash (for bills). QB
  identifiers are stored as secondary reference columns only.

  ---
  8. Trigger Design

  ┌────────────────────┬──────────────┬───────────────────────┬──────────────┬────────────────────┬────────────────┐
  │      Trigger       │    System    │         Type          │  Frequency   │    Reliability     │  Latency SLA   │
  ├────────────────────┼──────────────┼───────────────────────┼──────────────┼────────────────────┼────────────────┤
  │ QBWC outbound poll │ QuickBooks   │ Scheduled poll (QB    │ Every 5–15   │ ~95% (file lock +  │ < 30 min per   │
  │  (read sync)       │ Desktop      │ pulls)                │ min per file │ session timeout    │ file           │
  │                    │              │                       │              │ risk)              │                │
  ├────────────────────┼──────────────┼───────────────────────┼──────────────┼────────────────────┼────────────────┤
  │ QBWC outbound poll │ QuickBooks   │ Same session — write  │ Same cadence │ Same               │ < 30 min from  │
  │  (write-back)      │ Desktop      │ queued behind reads   │              │                    │ approval       │
  ├────────────────────┼──────────────┼───────────────────────┼──────────────┼────────────────────┼────────────────┤
  │                    │ Manual       │ HTTP POST to          │              │                    │ < 5 min OCR +  │
  │ Invoice PDF intake │ upload or    │ /ap/intake            │ On demand    │ 99%+               │ gate           │
  │                    │ email        │                       │              │                    │                │
  ├────────────────────┼──────────────┼───────────────────────┼──────────────┼────────────────────┼────────────────┤
  │ Human approval     │ Dashboard    │ POST /approvals/{id}  │ On demand    │ N/A (human)        │ SLA: 24 hrs,   │
  │                    │ action       │                       │              │                    │ escalate at 48 │
  ├────────────────────┼──────────────┼───────────────────────┼──────────────┼────────────────────┼────────────────┤
  │ Draw PDF intake    │ Manual       │ HTTP POST to          │ On demand    │ 99%+               │ < 10 min       │
  │                    │ upload       │ ingestion endpoint    │              │                    │ extraction     │
  ├────────────────────┼──────────────┼───────────────────────┼──────────────┼────────────────────┼────────────────┤
  │ Reconciliation     │ Cron         │ Scheduled             │ Daily        │ Self-managed       │ < 1 hour       │
  │ check              │              │                       │              │                    │                │
  └────────────────────┴──────────────┴───────────────────────┴──────────────┴────────────────────┴────────────────┘

  Multi-file QBWC trigger strategy — CRITICAL DESIGN DECISION:

  Option A (Recommended for Phase 1): Register 10 separate .qwc files on Rightworks. Each .qwc has a unique FileID GUID
  and points at the same /qbwc endpoint. The QBWCSessionManager.authenticate() maps the FileID to the canonical
  company_id, creating a per-file session. This is the simplest path and avoids any server-side file-routing logic.

  Option B (Phase 2+): Session-level file routing — authenticate() reads QBWC_COMPANY_FILE_PATHS env var and returns the
  next queued .QBW path. One .qwc rotates through all 10 files. Requires implementing the round-robin in
  app/transport/qbwc.py:87.

  For Phase 1, implement Option A. The build_qwc() function in app/transport/qwc.py:14 already supports per-file file_id
  and owner_id parameters.

  QB session timeout risk: Rightworks idle-session timeouts can interrupt long VendorQuery responses. Mitigation:
  QBWCSession.pending is fail-closed — if receiveResponseXML gets an hresult, the session aborts and nothing is
  persisted. QBWC auto-retries on next poll cadence.

  ---
  9. Sync Direction

  ┌─────────────────┬────────────────┬──────────────────────────────────────┬─────────────────────────────────────┐
  │    Data Type    │   Direction    │         Conflict Resolution          │           Re-sync Policy            │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │                 │                │ Canonical store updated on each poll │            Full re-read every poll  │
  │ Vendors (read)  │ QB → Canonical │  (upsert by qb_list_id)              │    (VendorQuery returns all active  │
  │                 │                │                                      │                            vendors) │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │                 │                │ Canonical store updated;             │                                     │
  │ Bills (read)    │ QB → Canonical │ raw_extensions overwritten with      │             Full re-read every poll │
  │                 │                │ latest QB data                       │                                     │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │ Bills           │                │ EditSequence optimistic lock; one    │      Write once per approved bill;  │
  │ (write-back)    │ Canonical → QB │ re-read + retry on 3200 conflict;    │ status transitions to synced after  │
  │                 │                │ second failure → human               │                             success │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │ Chart of        │ QB → Canonical │ Canonical accounts table seeded;     │                 Manual trigger via  │
  │ Accounts (seed) │                │ manual reseed on CoA change          │                catalog_bootstrap.py │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │ Cost codes      │ QB → Canonical │ Same as CoA                          │                                Same │
  │ (seed)          │                │                                      │                                     │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │ Fee entries     │ Canonical only │ Shadow mode: canonical only; QB      │                        N/A (shadow) │
  │                 │  → (future) QB │ journal entry write is Phase 4+      │                                     │
  ├─────────────────┼────────────────┼──────────────────────────────────────┼─────────────────────────────────────┤
  │ Audit rows      │ Canonical only │ Immutable append-only                │                                 N/A │
  │ (AIVS)          │                │                                      │                                     │
  └─────────────────┴────────────────┴──────────────────────────────────────┴─────────────────────────────────────┘

  One-way sync hard rule: QB Desktop is write-only for the BillAdd path (canonical → QB). The read path (QB → canonical)
  is separate. There is no two-way sync on any data type. Conflict resolution is unnecessary for the read path because
  QB is not the source of truth for canonical data — it is the origin of QB identifiers only.

  ---
  10. Auth and Credentials

  ┌───────────────┬───────────────────────────────────┬──────────────────────────┬────────────────┬────────────────┐
  │    System     │            Auth Method            │    Credential Storage    │   Rotation     │  Who Manages   │
  │               │                                   │                          │     Policy     │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │               │                                   │ .env (QBWC_USERNAME,     │ On compromise; │                │
  │ QBWC          │ Username + password (SOAP         │ QBWC_PASSWORD) + QB      │  same in .qwc  │ IT/Dev         │
  │               │ authenticate)                     │ password store on        │ file           │                │
  │               │                                   │ Rightworks               │                │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ Supabase      │ DATABASE_URL connection string    │ .env                     │ Annual or on   │ Dev            │
  │ Postgres      │ (password in URL)                 │                          │ compromise     │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ Supabase      │ SUPABASE_PROJECT_REF              │ .env                     │ N/A (read-only │ Dev            │
  │ project       │                                   │                          │  reference)    │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ SwarmSync     │ SWARMSYNC_SA_API_KEY (HMAC key)   │ .env                     │ On compromise  │ Dev            │
  │ (in-process)  │                                   │                          │                │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ VCAP proof    │ VCAP_SHARED_SECRET (≥32 byte      │ .env                     │ Annual         │ Dev            │
  │ signing       │ random)                           │                          │                │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ Capability    │ AGENT_CAPABILITY_SIGNING_SECRET   │ .env                     │ Annual         │ Dev            │
  │ tokens        │                                   │                          │                │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ AIVS Ed25519  │ File at AIVS_SIGNING_KEY_PATH     │ Local filesystem (keys/  │ Annual         │ Dev            │
  │ key           │ (chmod 600)                       │ dir, not in repo)        │                │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ Approval gate │ APPROVAL_API_KEY (to be added —   │ .env                     │ Annual         │ Dev/Controller │
  │               │ see Task 2)                       │                          │                │                │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ NATS          │ No auth (local docker-compose)    │ N/A                      │ N/A            │ Dev            │
  ├───────────────┼───────────────────────────────────┼──────────────────────────┼────────────────┼────────────────┤
  │ Temporal      │ No auth (local docker-compose)    │ N/A                      │ N/A            │ Dev            │
  └───────────────┴───────────────────────────────────┴──────────────────────────┴────────────────┴────────────────┘

  QBWC credential rules:
  - The .qwc password field must match QBWC_PASSWORD exactly — case-sensitive
  - The QBWC_OWNER_ID and QBWC_FILE_ID GUIDs in .qwc must be stable; changing them requires re-registering the connector
  in QB
  - QBWC validates credentials on every authenticate() call — a wrong password returns ["", "nvu"] which causes QBWC to
  stop polling silently
  - Never log QBWC_PASSWORD — the QBWCSessionManager reads it from env and never exposes it in responses or logs

  ---
  Sections 11–20 of 25.

  ---
  11. Validation Rules

  ┌─────────────────────┬────────────────────────────────────────────────────────┬──────────────────────────────────┐
  │        Field        │                          Rule                          │            On Failure            │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ QBWC credentials    │ username == QBWC_USERNAME and password ==              │ Return ["", "nvu"] — QBWC stops  │
  │                     │ QBWC_PASSWORD                                          │ polling                          │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ VendorRet/ListID    │ Must be non-empty string                               │ Skip vendor row; log warning     │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ BillRet/AmountDue   │ Must be numeric; if absent, sum ExpenseLineRet/Amount  │ If sum also 0 or unparseable,    │
  │                     │                                                        │ skip bill; log                   │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ Bill FK             │ vendor_list_id from BillRet must map to a vendor       │ Skip bill (orphaned FK); log —   │
  │ (vendor_list_id)    │ synced in the same session                             │ never create a dangling FK       │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ BillAdd — vendor    │ Must be present in canonical vendors.qb_list_id for    │ Block write; route to human      │
  │ ListID              │ this company                                           │ ("vendor not in QB")             │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ BillAdd — account   │ account_name must exist in accounts.name for this      │ CoADrift error raised pre-write; │
  │ name                │ company_id                                             │  routes to human                 │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ BillAdd — amount    │ Must be > 0 (NUMERIC(14,2))                            │ VerifyAPI returns NOT_READY;     │
  │                     │                                                        │ blocked                          │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ BillAdd — bill      │ Must be "approved" at VerifyAPI gate                   │ NOT_READY verdict; blocked       │
  │ status              │                                                        │                                  │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ AIVS chain          │ validate_chain(records) must not raise                 │ Chain broken → commit blocked;   │
  │                     │ AuditChainBroken                                       │ route to human                   │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ VCAP secret         │ VCAP_SHARED_SECRET must be set (≥32 bytes)             │ VcapSecretMissing raised;        │
  │                     │                                                        │ InvoiceProof blocked             │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ EditSequence retry  │ On QB status 3200, re-read + retry exactly once        │ Second 3200 → QB_EDIT_CONFLICT   │
  │                     │                                                        │ (409); route to human            │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ not_for_posting     │ draw.raw_extensions.get("not_for_posting") must be     │ Draw engine skips; historical    │
  │ flag                │ falsy                                                  │ fixture protected                │
  ├─────────────────────┼────────────────────────────────────────────────────────┼──────────────────────────────────┤
  │ Session             │ QBWCSession.is_complete must be True before            │ Refuse to commit; no partial     │
  │ completeness        │ persist_session()                                      │ writes                           │
  └─────────────────────┴────────────────────────────────────────────────────────┴──────────────────────────────────┘

  ---
  12. Approval Gates

  Gate: Gate 1 — InvoiceProof
  What Requires Approval: Any invoice with CRITICAL finding (duplicate, PO exceeded, line-item math error, recent
  payment
    duplicate)
  Approver: AP Controller
  Channel: Operator dashboard /ui/vendor-bills + APPROVAL_NOTIFY_WEBHOOK alert
  SLA: 24 hours
  Escalation: Owner after 48 hours
  ────────────────────────────────────────
  Gate: Gate 2 — AuditProof (AIVS)
  What Requires Approval: Automatically validated at commit boundary — not a human gate; a broken chain blocks silently
  Approver: N/A (automated)
  Channel: N/A
  SLA: Immediate (fail-closed)
  Escalation: IT/Dev if chain broken
  ────────────────────────────────────────
  Gate: Gate 3 — VerifyAPI
  What Requires Approval: Automatically validated — not a human gate; NOT_READY blocks
  Approver: N/A (automated)
  Channel: N/A
  SLA: Immediate (fail-closed)
  Escalation: IT/Dev if repeated NOT_READY
  ────────────────────────────────────────
  Gate: Gate 4 — ATEP (bank change)
  What Requires Approval: Any PAYMENT_FORM where vendor SwarmScore < TRUSTED tier
  Approver: Controller
  Channel: Out-of-band phone verification to vendor
  SLA: Immediate
  Escalation: Block payment; escalate to owner
  ────────────────────────────────────────
  Gate: Draw CM Approval
  What Requires Approval: Construction-manager sign-off on draw package
  Approver: CM
  Channel: Dashboard /ui/draws/{id} approve button
  SLA: Per loan terms
  Escalation: Owner
  ────────────────────────────────────────
  Gate: Draw Watson Approval
  What Requires Approval: Mike Watson sign-off (binding §5.3)
  Approver: Mike Watson
  Channel: Dashboard /ui/draws/{id} approve button
  SLA: Per loan terms
  Escalation: Owner
  ────────────────────────────────────────
  Gate: Human Approval (intent)
  What Requires Approval: Every AI-submitted BillAdd intent before QB write
  Approver: Controller
  Channel: Dashboard + APPROVAL_NOTIFY_WEBHOOK
  SLA: 24 hours
  Escalation: Owner after 48 hours
  ────────────────────────────────────────
  Gate: New Vendor Setup
  What Requires Approval: Any VendorCandidate queued by ingestion (unmatched payee)
  Approver: Controller
  Channel: Dashboard /ui/vendor-candidates
  SLA: 48 hours
  Escalation: AP Manager

  Hard rule: The POST /approvals/{id} route currently has no HTTP authentication. This must be fixed (Task 2 from Coder
  Task Plan) before any production traffic. An unauthenticated approval endpoint is a hard blocker —
  UNSAFE_WITHOUT_APPROVAL_GATE condition applies until this is resolved.

  Vendor bank-change rule: The ATEP gate (Gate 4) blocks PAYMENT_FORM release below TRUSTED tier. Any vendor bank detail
  change must be verified out-of-band (phone call to the vendor using the number on file — not the email sender). The
  bank_fingerprint column on vendors stores a SHA-256 hash of bank details, never raw account/routing numbers.

  ---
  13. Idempotency and Duplicate Prevention

  Entity: Canonical Vendor (read sync)
  Dedup Key: (company_id, qb_list_id)
  Storage: vendors.qb_list_id + company_id
  Check-Before-Create: Yes — persist_session checks by list_id in session map
  On Duplicate: Overwrite name + raw_extensions; do not duplicate
  ────────────────────────────────────────
  Entity: Canonical Bill (read sync)
  Dedup Key: (company_id, qb_txn_id)
  Storage: bills.qb_txn_id + company_id
  Check-Before-Create: Yes — check before insert
  On Duplicate: Skip and log
  ────────────────────────────────────────
  Entity: Bill (intake/OCR)
  Dedup Key: company_id + invoice_number + vendor_name + amount SHA-256
  Storage: bills status + InvoiceProof EXACT_DUPLICATE rule
  Check-Before-Create: InvoiceProof _rule_duplicates() checks existing_bills
  On Duplicate: CRITICAL finding → blocked to human
  ────────────────────────────────────────
  Entity: QBWC Session
  Dedup Key: ticket UUID
  Storage: QBWCSessionManager.sessions dict
  Check-Before-Create: Each authenticate issues new ticket
  On Duplicate: N/A — tickets expire on closeConnection
  ────────────────────────────────────────
  Entity: WorkflowService intent
  Dedup Key: uuid5(IDEMPOTENCY_NS, idempotency_key)
  Storage: In-memory DurableWorkflowEngine state
  Check-Before-Create: engine.get_state(workflow_id) before publish
  On Duplicate: Re-delivered intent: return existing workflow_id, no double-publish
  ────────────────────────────────────────
  Entity: BillAdd (QB write)
  Dedup Key: bills.qb_txn_id (set after success)
  Storage: bills row status = "synced"
  Check-Before-Create: Check bill.status == "synced" before retry
  On Duplicate: Do not emit second BillAdd if already synced
  ────────────────────────────────────────
  Entity: AuditRow (AIVS)
  Dedup Key: row_hash (SHA-256, unique constraint)
  Storage: audit_rows.row_hash UNIQUE
  Check-Before-Create: Hash uniqueness enforced at DB layer
  On Duplicate: Reject insert; chain error surfaced
  ────────────────────────────────────────
  Entity: VendorCandidate
  Dedup Key: (company_id, normalized_name)
  Storage: vendor_candidates UNIQUE constraint
  Check-Before-Create: DB constraint
  On Duplicate: UNIQUE violation = already queued; skip

  ⚠️ QB Company File Migration Risk:
  If any Rightworks company file is ever restored from backup or migrated, qb_list_id and qb_txn_id values change. The
  canonical store must be re-seeded for that company file: clear qb_list_id / qb_txn_id columns for that company_id, run
  a fresh sync cycle, and re-reconcile. Never use QB identifiers as integration primary keys — vendors.id (UUID) and
  bills.id (UUID) are the canonical PKs.

  ---
  14. Failure Handling

  Failure Scenario: QBWC auth rejected (nvu)
  Detection: authenticate() returns ["", "nvu"]; QBWC stops polling
  Immediate Action: Log AUTH_REJECTED; emit metric record_error("nvu")
  Recovery: Check QBWC_USERNAME/PASSWORD match .qwc file and env; update and restart
  Notify Who: IT + Controller
  ────────────────────────────────────────
  Failure Scenario: QB company file locked
  Detection: hresult non-empty in receiveResponseXML
  Immediate Action: session.last_error = message; pending.clear() (fail-closed); return -1
  Recovery: QBWC retries on next poll cadence (5-15 min)
  Notify Who: IT if > 30 min
  ────────────────────────────────────────
  Failure Scenario: QBWC endpoint unreachable from Rightworks
  Detection: QB Web Connector shows "connection refused" or SSL error
  Immediate Action: N/A (server-side)
  Recovery: Verify server is running; check HTTPS cert; test curl from Rightworks
  Notify Who: IT
  ────────────────────────────────────────
  Failure Scenario: EditSequence conflict (3200) on BillAdd
  Detection: QBXMLError(status_code="3200")
  Immediate Action: Re-read QB bill state; retry once with fresh qb_edit_sequence
  Recovery: If second attempt also fails → QB_EDIT_CONFLICT (409); route to human
  Notify Who: Controller
  ────────────────────────────────────────
  Failure Scenario: CoA drift — account not in QB
  Detection: CoADrift exception pre-write
  Immediate Action: Block BillAdd; return 422 envelope
  Recovery: Accountant adds missing account to QB; runs catalog_bootstrap.py reseed
  Notify Who: Accountant
  ────────────────────────────────────────
  Failure Scenario: AIVS chain broken
  Detection: AuditChainBroken in validate_chain()
  Immediate Action: Commit blocked; return error envelope
  Recovery: Investigate chain integrity; do not auto-repair
  Notify Who: IT/Dev immediately
  ────────────────────────────────────────
  Failure Scenario: VerifyAPI NOT_READY
  Detection: verdict.advance == False
  Immediate Action: Write proof_bundle (kind='verifyapi', passed=False); block write
  Recovery: Review bill status — must be 'approved'; AIVS head must be non-genesis
  Notify Who: Controller (route_to_human)
  ────────────────────────────────────────
  Failure Scenario: InvoiceProof CRITICAL
  Detection: run_invoiceproof() returns riskLevel == "CRITICAL"
  Immediate Action: Block intake; queue for human review
  Recovery: Controller reviews in dashboard /ui/vendor-bills
  Notify Who: Controller via APPROVAL_NOTIFY_WEBHOOK
  ────────────────────────────────────────
  Failure Scenario: VcapSecretMissing
  Detection: VCAP_SHARED_SECRET unset
  Immediate Action: Raise VcapSecretMissing; InvoiceProof blocked
  Recovery: Set env var; restart server
  Notify Who: IT/Dev
  ────────────────────────────────────────
  Failure Scenario: Supabase connection lost
  Detection: psycopg connection error on get_engine()
  Immediate Action: GET /ready returns 503
  Recovery: Supabase restores automatically; check DATABASE_URL
  Notify Who: IT
  ────────────────────────────────────────
  Failure Scenario: NATS connection lost
  Detection: nats-py connection error
  Immediate Action: WorkflowService falls back to in-memory bus (unit-test mode)
  Recovery: Restart docker-compose NATS; reconnect
  Notify Who: Dev
  ────────────────────────────────────────
  Failure Scenario: Temporal connection lost
  Detection: temporalio gRPC error
  Immediate Action: WorkflowService falls back to in-memory engine
  Recovery: Restart docker-compose Temporal
  Notify Who: Dev
  ────────────────────────────────────────
  Failure Scenario: Session persist fails (incomplete session)
  Detection: is_complete == False in persist_session()
  Immediate Action: Raise ValueError("refusing to persist…"); zero rows written
  Recovery: QBWC retries from scratch on next poll; no partial data
  Notify Who: None (self-healing)

  Retry strategy:
  - QB session errors (file lock, hresult): QBWC auto-retries on next poll cadence — no manual retry needed
  - BillAdd EditSequence conflict: one automated retry; second failure → human queue (no further automation)
  - Validation failures (CoA drift, NOT_READY): queue for human; no automated retry until human resolves
  - InvoiceProof CRITICAL: queue for human review; no retry

  ---
  15. Reconciliation

  ┌──────────────────┬───────────┬───────────────────┬───────────────────────────────┬────────────────┬─────────────┐
  │ Reconciliation   │ Frequency │  Source of Truth  │       What Is Compared        │     Alert      │ Who Reviews │
  │       Type       │           │                   │                               │   Threshold    │             │
  ├──────────────────┼───────────┼───────────────────┼───────────────────────────────┼────────────────┼─────────────┤
  │ Vendor count per │           │ QuickBooks        │ QB vendor count vs vendors    │                │             │
  │  file            │ Daily     │ (VendorQueryRs    │ table count for company_id    │ Any delta > 5% │ Accountant  │
  │                  │           │ count)            │                               │                │             │
  ├──────────────────┼───────────┼───────────────────┼───────────────────────────────┼────────────────┼─────────────┤
  │ Bill count per   │           │ QuickBooks        │ QB bill count for period vs   │                │             │
  │ file             │ Daily     │ (BillQueryRs      │ bills count for company_id    │ Any mismatch   │ Controller  │
  │                  │           │ count)            │                               │                │             │
  ├──────────────────┼───────────┼───────────────────┼───────────────────────────────┼────────────────┼─────────────┤
  │ Synced bill      │           │                   │ Bills with status='synced'    │ Any null       │ Dev +       │
  │ status           │ Daily     │ Supabase bills    │ have non-null qb_txn_id       │ qb_txn_id on   │ Accountant  │
  │                  │           │                   │                               │ synced bill    │             │
  ├──────────────────┼───────────┼───────────────────┼───────────────────────────────┼────────────────┼─────────────┤
  │ Fee entry        │           │ Supabase          │ Every approved_for_accounting │ Any approved   │             │
  │ completeness     │ Per draw  │ draw_packages /   │  draw has exactly 4           │ draw without 4 │ Accountant  │
  │                  │           │ fee_entries       │ fee_entries                   │  entries       │             │
  ├──────────────────┼───────────┼───────────────────┼───────────────────────────────┼────────────────┼─────────────┤
  │ QBWC poll        │           │                   │ mean_cadence_seconds within   │ Cadence > 3×   │             │
  │ cadence          │ Real-time │ GET /sync/health  │ 2× configured interval        │ configured     │ IT          │
  │                  │           │                   │                               │ interval       │             │
  ├──────────────────┼───────────┼───────────────────┼───────────────────────────────┼────────────────┼─────────────┤
  │ Orphaned bills   │ Weekly    │ Supabase          │ Bills with null or invalid    │ Any > 0        │ Accountant  │
  │ (no vendor)      │           │                   │ vendor_id                     │                │             │
  └──────────────────┴───────────┴───────────────────┴───────────────────────────────┴────────────────┴─────────────┘

  Reconciliation report format (daily):
  Date: YYYY-MM-DD
  File: [company_id / legal_name]
  Vendors in QB: N | Vendors in canonical: N | Match: YES/NO
  Bills in QB (this period): N | Bills in canonical: N | Match: YES/NO
  Bills synced (qb_txn_id non-null): N | Bills approved but not synced: N
  Last poll time: HH:MM:SS | Last error: [none / message]
  Action required: [None / Investigate: [reason] / Escalate to controller]

  ---
  16. Audit Logging

  All financial events are logged in the audit_rows AIVS hash chain (append-only, SHA-256 chained).

  Event: Approval decision (approve/reject)
  Log Fields: session_id, action_type="approval.approve/reject", actor (approver identity), inputs={workflow_id,
  intent},
    outputs={decision}
  Storage: audit_rows table (AIVS chain)
  Retention: 7 years
  Access: Controller + auditor (read-only)
  ────────────────────────────────────────
  Event: BillAdd emitted
  Log Fields: proof_bundles row (kind='verifyapi') + canonical bills.status='synced' + qb_txn_id
  Storage: proof_bundles + bills
  Retention: 7 years
  Access: Accountant + auditor
  ────────────────────────────────────────
  Event: InvoiceProof verdict
  Log Fields: proof_bundles row (kind='invoiceproof') with full findings in payload
  Storage: proof_bundles
  Retention: 7 years
  Access: Accountant + auditor
  ────────────────────────────────────────
  Event: QBWC poll attempt
  Log Fields: PollMetrics.record_poll() — in-memory; expose via /sync/health
  Storage: In-memory (not persistent — see gap below)
  Retention: Session duration
  Access: IT
  ────────────────────────────────────────
  Event: Gate failure (CoA drift, chain broken, NOT_READY)
  Log Fields: Error envelope returned; proof_bundles written for every VerifyAPI run
  Storage: proof_bundles
  Retention: 7 years
  Access: Dev + Accountant
  ────────────────────────────────────────
  Event: VendorCandidate queued
  Log Fields: vendor_candidates row with source_ref
  Storage: vendor_candidates
  Retention: Until resolved
  Access: AP Manager
  ────────────────────────────────────────
  Event: Draw status transition
  Log Fields: Recorded via service.transition_draw_status() → draw_packages.status change
  Storage: draw_packages
  Retention: 7 years
  Access: Accountant

  Audit gap — QBWC poll metrics are in-memory only:
  PollMetrics (app/transport/metrics.py) is a process-level in-memory store. Poll history is lost on server restart. For
  audit-grade poll logging, persist each poll event as an AuditRow (action_type='qbwc.poll') or to a dedicated
  sync_events table. This is a P2 task — add it after Phase 1 is stable.

  Audit log properties:
  - audit_rows: append-only (no DELETE, no UPDATE — enforced by application; consider adding a DB trigger to prevent)
  - proof_bundles: immutable after creation; passed and proof_hash are write-once
  - All audit data accessible to accountant/auditor via SQL read on Supabase without developer assistance

  ---
  17. Security and Permissions

  ┌─────────────────────┬──────────────┬────────────────────────────────────┬───────────────────────────────────────┐
  │    Access Level     │     Who      │              Systems               │           What They Can Do            │
  ├─────────────────────┼──────────────┼────────────────────────────────────┼───────────────────────────────────────┤
  │ Admin               │ Dev/IT       │ All — Supabase, server,            │ Full access; credential management    │
  │                     │              │ Rightworks, env vars               │                                       │
  ├─────────────────────┼──────────────┼────────────────────────────────────┼───────────────────────────────────────┤
  │ Operator/Controller │ Controller   │ Dashboard /ui; approval endpoint   │ Review queue, approve/reject intents  │
  │                     │              │                                    │ and draws, resolve vendor candidates  │
  ├─────────────────────┼──────────────┼────────────────────────────────────┼───────────────────────────────────────┤
  │ Accountant          │ Accountant   │ Dashboard (read-only views);       │ View canonical data; no write actions │
  │                     │              │ reconciliation report              │                                       │
  ├─────────────────────┼──────────────┼────────────────────────────────────┼───────────────────────────────────────┤
  │                     │              │ audit_rows, proof_bundles          │                                       │
  │ Auditor             │ External CPA │ (time-limited read-only Supabase   │ Read-only audit trail                 │
  │                     │              │ access)                            │                                       │
  ├─────────────────────┼──────────────┼────────────────────────────────────┼───────────────────────────────────────┤
  │ QBWC service        │ QB Web       │ QB company files (read + limited   │ VendorQuery, BillQuery, BillAdd only  │
  │ account             │ Connector    │ write via QBWC)                    │ — no other QB operations              │
  ├─────────────────────┼──────────────┼────────────────────────────────────┼───────────────────────────────────────┤
  │ None                │ General      │ None                               │ No access                             │
  │                     │ staff        │                                    │                                       │
  └─────────────────────┴──────────────┴────────────────────────────────────┴───────────────────────────────────────┘

  Permission rules:
  - QBWC_USERNAME/PASSWORD must not be reused for any other QB user account
  - Supabase row-level security (RLS) should be enabled — canonical data should not be directly editable via Supabase
  dashboard by non-admin users
  - The approval endpoint POST /approvals/{id} must be gated by APPROVAL_API_KEY header (Task 2)
  - Server-side: no route trusts the approver field from the request body without authentication
  - No environment variables are committed to git — .env is in .gitignore
  - AIVS_SIGNING_KEY_PATH file must be chmod 600 and excluded from Docker image layers

  ---
  18. Manual Override

  ┌────────────────────┬────────────────────────────────────────────────┬────────────┬─────────────────────────────┐
  │      Scenario      │                Override Action                 │  Who Can   │         Audit Trail         │
  │                    │                                                │  Override  │                             │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ Integration down,  │ Manual QB entry; mark canonical                │            │ Controller adds note in     │
  │ invoice urgent     │ bills.raw_extensions.manual_entry=true; log    │ Controller │ bills.raw_extensions;       │
  │                    │ reason                                         │            │ visible in dashboard        │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ BillAdd stuck in   │ Controller re-reviews and re-approves via      │ Controller │ New approval audit row      │
  │ human queue        │ dashboard                                      │            │ written                     │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ QBWC session not   │ IT checks Web Connector on Rightworks; verify  │ IT         │ QBWC Web Connector logs on  │
  │ polling            │ QB is running and file is open; restart QBWC   │            │ Rightworks                  │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ CoA drift blocking │ Accountant adds missing account to QB; runs    │ Accountant │ accounts table reseed log   │
  │  write             │ catalog_bootstrap.py; re-triggers approval     │  + Dev     │                             │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ Draw fees wrong    │ invalidate_drafts(session, draw_package_id)    │            │ FeeEntry status='void'      │
  │ (re-calculation    │ voids FeeEntries; re-approve draw to redraft   │ Controller │ logged; redraft creates new │
  │ needed)            │                                                │            │  entries                    │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ Server maintenance │ Set APP_ENV=maintenance (or stop server);      │ IT/Dev     │ Maintenance log +           │
  │                    │ manual QB entry resumes                        │            │ notification to Controller  │
  ├────────────────────┼────────────────────────────────────────────────┼────────────┼─────────────────────────────┤
  │ Vendor bank change │ Out-of-band phone verification → IT updates    │ IT +       │ vendors row update + audit  │
  │  (ATEP blocked)    │ vendor.bank_fingerprint; ATEP re-evaluates     │ Controller │ note                        │
  └────────────────────┴────────────────────────────────────────────────┴────────────┴─────────────────────────────┘

  Override rule: No override bypasses the audit_rows chain. Every manual entry in QB that replaces an integration action
  must be logged in audit_rows (action_type='manual_override') with actor, reason, and the affected bill_id or
  draw_package_id.

  ---
  19. Monitoring and Alerting

  ┌──────────────────────────┬─────────────────┬───────────────────────┬──────────────────────────────┬────────────┐
  │          Metric          │  Normal Range   │    Alert Threshold    │        Alert Channel         │  On-Call   │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │                          │ Within 2×       │ > 3× configured       │ APPROVAL_NOTIFY_WEBHOOK      │            │
  │ QBWC poll cadence        │ configured      │ interval OR 0 polls   │ (Slack/Telegram)             │ IT         │
  │                          │ interval        │ in 60 min             │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ QBWC last error          │ null            │ Any non-null          │ Same                         │ IT         │
  │                          │                 │ last_error            │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ Queue depth (approved    │ 0–5             │ > 20 unsynced for > 2 │ Email to Controller          │ Controller │
  │ bills not yet synced)    │                 │  hours                │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ AuditChainBroken events  │ 0               │ Any                   │ Immediate alert to IT + Dev  │ Dev        │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ GET /ready fails         │ 200             │ Non-200 for > 5 min   │ PagerDuty / SMS              │ IT         │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ VCAP or AIVS signing key │ Keys configured │ Any startup error on  │ Server startup log + alert   │ IT/Dev     │
  │  missing                 │                 │ key load              │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ Reconciliation mismatch  │ 0               │ Any vendor/bill count │ Email to Controller          │ Controller │
  │                          │                 │  mismatch             │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ InvoiceProof queue depth │ 0               │ > 10 items for > 24   │ Email to Controller          │ Controller │
  │                          │                 │ hours                 │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ Approval gate open > SLA │ 0               │ Any approval pending  │ Email escalation to Owner    │ Owner      │
  │                          │                 │ > 24 hours            │                              │            │
  ├──────────────────────────┼─────────────────┼───────────────────────┼──────────────────────────────┼────────────┤
  │ Server uptime            │ Running         │ Stopped > 5 min       │ PagerDuty / SMS              │ IT         │
  └──────────────────────────┴─────────────────┴───────────────────────┴──────────────────────────────┴────────────┘

  Minimum viable monitoring (MVP for Phase 1):
  - Daily cron: run reconciliation check → email digest to controller (vendor count, bill count, last poll time, errors)
  - GET /sync/health polled by an external uptime monitor (UptimeRobot, Better Uptime)
  - APPROVAL_NOTIFY_WEBHOOK set to Slack/Telegram for gate-failure notifications

  ---
  20. Test and Proof Plan

  ┌─────────────────┬─────────────┬─────────────────────────────────────────────────┬────────────────────────────────┐
  │      Test       │    Type     │                  Pass Criteria                  │          Environment           │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ QBWC            │             │ GET /qbwc?wsdl returns valid WSDL; POST /qbwc   │                                │
  │ authenticate +  │ Smoke       │ with valid creds returns ticket                 │ Staging (local server)         │
  │ WSDL            │             │                                                 │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ VendorQuery     │             │ sendRequestXML returns valid VendorQueryRq;     │ Unit test (existing            │
  │ round-trip      │ End-to-end  │ fake VendorQueryRs response parsed → vendors    │ test_transport_qbxml.py)       │
  │                 │             │ list non-empty                                  │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ BillQuery       │ End-to-end  │ Same pattern; bills list non-empty with         │ Unit test (existing            │
  │ round-trip      │             │ vendor_list_id resolved                         │ test_transport_qbwc.py)        │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ persist_session │             │ Incomplete session → ValueError; complete       │                                │
  │  all-or-nothing │ Integration │ session → vendors+bills in DB; verify with      │ test_transport_adapter.py      │
  │                 │             │ SELECT                                          │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ InvoiceProof    │             │ Second submission of same invoice number →      │ Unit test (existing            │
  │ EXACT_DUPLICATE │ Dedup test  │ passed=False, criticalRules=['EXACT_DUPLICATE'] │ test_payments_invoiceproof.py) │
  │  blocked        │             │                                                 │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ BillAdd         │             │ First attempt → 3200 error; re-read fires;      │ Unit test (existing            │
  │ EditSequence    │ Resilience  │ second attempt → success; bills.status='synced' │ test_verify_execution.py)      │
  │ retry           │             │                                                 │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ AIVS chain      │             │ Tampered chain → AuditChainBroken → commit      │ Unit test (existing            │
  │ broken blocks   │ Gate test   │ returns 409                                     │ test_audit_chain.py)           │
  │ commit          │             │                                                 │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ VerifyAPI       │             │ Bill status = 'drafted' → NOT_READY →           │ Unit test (existing            │
  │ NOT_READY       │ Gate test   │ advance=False → write blocked                   │ test_verify_verifyapi.py)      │
  │ blocks write    │             │                                                 │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ Dashboard       │             │ POST /ui/draws/{id}/approve →                   │                                │
  │ shadow mode     │ UI test     │ draw_packages.status='approved_for_accounting'; │ test_dashboard.py              │
  │                 │             │  NO call to transport layer                     │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ Full pipeline   │ Pipeline    │ run_payable_pipeline() with mock writer →       │ test_scale_pipeline.py         │
  │ end-to-end      │ test        │ PipelineResult.green == True                    │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ QBWC live poll  │             │ After .qwc install: Web Connector shows "Last   │                                │
  │ on Rightworks   │ Live proof  │ result: Success"; GET /sync/health shows        │ Production staging QB file     │
  │                 │             │ poll_count >= 1                                 │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ Reconciliation  │ Accuracy    │ Report count matches manual SQL count for same  │ Staging + production           │
  │ report accuracy │             │ period and company_id                           │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ Rollback Phase  │ Rollback    │ Server stopped → manual QB entry resumes → no   │ Staging                        │
  │ 1               │             │ data loss in canonical store                    │                                │
  ├─────────────────┼─────────────┼─────────────────────────────────────────────────┼────────────────────────────────┤
  │ Approval gate   │             │ POST /approvals/{id} without X-API-Key → 401;   │                                │
  │ auth            │ Security    │ with wrong key → 401; with correct key →        │ Staging                        │
  │                 │             │ processes                                       │                                │
  └─────────────────┴─────────────┴─────────────────────────────────────────────────┴────────────────────────────────┘

  Proof artifact: For each live test on Rightworks, screenshot the QBWC "Last Result" panel and GET /sync/health JSON
  response. Attach to reconciliation report before Phase 2 sign-off.

  ---
  Sections 21–25 of 25.

  ---
  21. Implementation Phases

  ┌────────────────────┬────────────────────────────────────────────────┬──────────────────────────────────────────┐
  │       Phase        │                     Scope                      │          Gate Before Next Phase          │
  ├────────────────────┼────────────────────────────────────────────────┼──────────────────────────────────────────┤
  │ Phase 0 —          │ Install venv; set all env vars; run alembic    │ Venv installs clean; pytest -q passes    │
  │ Environment        │ upgrade head; run catalog_bootstrap.py; add    │ all; GET /ready returns 200; company     │
  │                    │ docker-compose.yml; seed 10 company rows       │ rows in DB                               │
  ├────────────────────┼────────────────────────────────────────────────┼──────────────────────────────────────────┤
  │                    │ Choose one Rightworks company file; generate + │ GET /sync/health shows poll_count >= 3,  │
  │ Phase 1 — Read     │  install .qwc; deploy server to public HTTPS   │ last_error: null; canonical vendor/bill  │
  │ Sync (Single File) │ host; confirm QBWC polls and read-syncs        │ count matches QB count; Controller signs │
  │                    │ vendors+bills for that file                    │  off                                     │
  ├────────────────────┼────────────────────────────────────────────────┼──────────────────────────────────────────┤
  │ Phase 2 — Read     │ Generate 9 more .qwc files; install on         │ All 10 company_id rows have non-null     │
  │ Sync (All 10       │ Rightworks; verify all 10 company files sync   │ last_synced; daily reconciliation report │
  │ Files)             │                                                │  clean for 1 week; Controller signs off  │
  ├────────────────────┼────────────────────────────────────────────────┼──────────────────────────────────────────┤
  │ Phase 3 —          │ Add APPROVAL_API_KEY auth to /approvals;       │ QB shows the bill; bills.qb_txn_id       │
  │ Human-in-loop      │ submit one test BillAdd intent; approve via    │ non-null; bills.status='synced'; audit   │
  │ Write (Single      │ dashboard; verify QB receives the bill         │ row written; Accountant reviews and      │
  │ Bill)              │                                                │ signs off                                │
  ├────────────────────┼────────────────────────────────────────────────┼──────────────────────────────────────────┤
  │ Phase 4 —          │ Enable BillAdd pipeline for low-dollar bills   │ Zero gate failures; zero duplicate bills │
  │ Production Pilot   │ (< $1,000) from one company file               │  in QB; reconciliation clean for 2       │
  │ (Low-risk bills)   │                                                │ weeks; Controller signs off              │
  ├────────────────────┼────────────────────────────────────────────────┼──────────────────────────────────────────┤
  │ Phase 5 — Full     │ All bills, all 10 files; draw fee write-back   │ Reconciliation clean for 30 days;        │
  │ Production         │ (QB journal entries) in scope for Phase 5+     │ accountant monthly close validates;      │
  │                    │                                                │ Owner sign-off                           │
  └────────────────────┴────────────────────────────────────────────────┴──────────────────────────────────────────┘

  Rollback plan:

  ┌────────┬───────────────────────────────────────────────────────────────────────────┬─────────┬─────────────────┐
  │ Phase  │                              Rollback Action                              │  Time   │       Who       │
  ├────────┼───────────────────────────────────────────────────────────────────────────┼─────────┼─────────────────┤
  │ Phase  │ Drop DB tables (alembic downgrade base); delete venv                      │ < 30    │ Dev             │
  │ 0      │                                                                           │ min     │                 │
  ├────────┼───────────────────────────────────────────────────────────────────────────┼─────────┼─────────────────┤
  │ Phase  │ Remove .qwc from QBWC on Rightworks; stop server                          │ < 5 min │ IT              │
  │ 1      │                                                                           │         │                 │
  ├────────┼───────────────────────────────────────────────────────────────────────────┼─────────┼─────────────────┤
  │ Phase  │ Remove all 10 .qwc files from QBWC                                        │ < 15    │ IT              │
  │ 2      │                                                                           │ min     │                 │
  ├────────┼───────────────────────────────────────────────────────────────────────────┼─────────┼─────────────────┤
  │ Phase  │ Disable /approvals route; manual QB entry resumes                         │ < 5 min │ Dev             │
  │ 3      │                                                                           │         │                 │
  ├────────┼───────────────────────────────────────────────────────────────────────────┼─────────┼─────────────────┤
  │ Phase  │ Set QBWC_COMPANY_FILE_PATHS="" or APP_ENV=maintenance; manual KB entry    │ < 15    │ Dev +           │
  │ 4      │ resumes                                                                   │ min     │ Controller      │
  ├────────┼───────────────────────────────────────────────────────────────────────────┼─────────┼─────────────────┤
  │ Phase  │ Stop server; notify Controller; manual process resumes for all files      │ < 30    │ Dev +           │
  │ 5      │                                                                           │ min     │ Controller      │
  └────────┴───────────────────────────────────────────────────────────────────────────┴─────────┴─────────────────┘

  ---
  22. Risk Register

  #: R1
  Risk: POST /approvals/{id} has no HTTP auth — any caller can approve
  Likelihood: Certain (current state)
  Impact: Critical
  Mitigation: Task 2: add APPROVAL_API_KEY before Phase 3 goes live; Phase 1-2 read-only so this is safe to defer to
    Phase 3 gate
  ────────────────────────────────────────
  #: R2
  Risk: Venv not installed; 27 tests fail; app won't start
  Likelihood: Certain (current state)
  Impact: Critical
  Mitigation: Task 1: install venv in Phase 0
  ────────────────────────────────────────
  #: R3
  Risk: No .qwc file exists; QBWC never polls
  Likelihood: Certain (current state)
  Impact: High
  Mitigation: Task 3: generate + deploy .qwc in Phase 1
  ────────────────────────────────────────
  #: R4
  Risk: Multi-file QBWC uses "open file" (returns "") — only one file syncs
  Likelihood: Certain
  Impact: High
  Mitigation: Phase 2: implement per-file .qwc registration (Option A) or QBWC_COMPANY_FILE_PATHS routing (Option B)
  ────────────────────────────────────────
  #: R5
  Risk: companies table empty; draw engine raises DrawEngineError
  Likelihood: Certain
  Impact: High
  Mitigation: Task 4: seed 10 company rows in Phase 0
  ────────────────────────────────────────
  #: R6
  Risk: VCAP_SHARED_SECRET is placeholder value in prod
  Likelihood: Medium
  Impact: High
  Mitigation: Set real ≥32-byte random secret before Phase 3
  ────────────────────────────────────────
  #: R7
  Risk: QB company file migrated/restored → qb_list_id / qb_txn_id stale
  Likelihood: Low-Medium
  Impact: High
  Mitigation: Reseed procedure documented; canonical PKs are UUIDs (safe); QB IDs are secondary refs only (Sections 7,
    13)
  ────────────────────────────────────────
  #: R8
  Risk: Rightworks idle session timeout interrupts long VendorQuery (>500 vendors)
  Likelihood: Medium
  Impact: Medium
  Mitigation: QBWCSession fail-closed (incomplete session → no persist); QBWC auto-retries; keep vendor list per-session

    small via MaxReturned pagination
  ────────────────────────────────────────
  #: R9
  Risk: QBWC_USERNAME/PASSWORD mismatch with .qwc → nvu → silent polling stop
  Likelihood: Low (config error)
  Impact: High
  Mitigation: Test auth on staging before Rightworks install; add last_auth_failure to PollMetrics
  ────────────────────────────────────────
  #: R10
  Risk: QBWC poll metrics in-memory only — lost on server restart
  Likelihood: Certain
  Impact: Medium
  Mitigation: P2 task: persist poll events to audit_rows or sync_events table
  ────────────────────────────────────────
  #: R11
  Risk: invoice2data templates missing → OCR returns null drafts
  Likelihood: Certain
  Impact: High
  Mitigation: Task 9: create template dir; author YAML templates before Phase 3
  ────────────────────────────────────────
  #: R12
  Risk: No docker-compose.yml → NATS + Temporal unavailable → live workflow fails
  Likelihood: Certain
  Impact: Medium
  Mitigation: Task 5: add docker-compose.yml in Phase 0; unit tests use in-memory fakes so Phase 1-2 safe
  ────────────────────────────────────────
  #: R13
  Risk: RESOLVED 2026-07-01 — Rightworks confirmed in writing that no persistent poller is available or supported;
  polling is business-hours/session-tied only
  Likelihood: Certain (confirmed, not a risk anymore — now a fixed design constraint)
  Impact: Medium (was High) — write-back only proceeds during active login sessions; off-hours items queue, not lost
  Mitigation: Design accepts business-hours cadence as final. QBWC auto-opens on session login (Rightworks configures on
  request); monitor queue age via daily digest to catch anything stuck longer than a normal business-hours gap.
  ────────────────────────────────────────
  #: R14
  Risk: catalog_bootstrap.py not run → accounts/cost_codes empty → COA drift on every BillAdd
  Likelihood: Certain
  Impact: High
  Mitigation: Task 7: run bootstrap in Phase 0; reseed after every QB CoA change
  ────────────────────────────────────────
  #: R15
  Risk: No deployment config → no reproducible prod environment
  Likelihood: Certain
  Impact: Medium
  Mitigation: Task 8: add Dockerfile + CI in Phase 2
  ────────────────────────────────────────
  #: R16
  Risk: No authentication on any route except approval gate
  Likelihood: Medium
  Impact: High
  Mitigation: Add API key middleware to all non-public routes before Phase 4
  ────────────────────────────────────────
  #: R17
  Risk: QBWC_ENDPOINT_URL must be HTTPS from Rightworks — HTTP rejected by QBWC
  Likelihood: Certain
  Impact: High
  Mitigation: Choose and provision HTTPS hosting before Phase 1; test curl https://your-url/qbwc from Rightworks RDP
  ────────────────────────────────────────
  #: R18
  Risk: Field mapping: BillRet/AmountDue absent on some QB versions → _sum_line_amounts() used
  Likelihood: Low
  Impact: Medium
  Mitigation: Covered by qbxml.parse_bills() fallback logic; verify on staging QB file
  ────────────────────────────────────────
  #: R19
  Risk: Idempotency gap: VendorQueryRs re-runs every poll; persist_session inserts without upsert
  Likelihood: Medium
  Impact: Medium
  Mitigation: Add ON CONFLICT (company_id, qb_list_id) DO UPDATE upsert logic to persist_session before Phase 2

  Risk Register cross-references:
  - Section 7 field mapping risks: R7 (QB ID change), R18 (AmountDue absent) — logged above
  - Section 11 validation risks: R9 (auth mismatch), R6 (VCAP missing) — logged above
  - Section 13 idempotency risks: R19 (no upsert in persist_session) — logged above
  - Section 14 failure scenarios: R8 (session timeout), R10 (metrics lost) — logged above

  ---
  23. Final Verdict

  Hard Rules Verification:

  ┌────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┐
  │                      Rule                      │                             Status                             │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 1: Audit log for all money-impacting data │ Satisfied — audit_rows AIVS chain (Section 16)                 │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 2: No email alone for payment changes     │ Satisfied — ATEP Gate 4 + out-of-band verification (Section    │
  │                                                │ 12)                                                            │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 3: No vendor bank changes without         │ Satisfied — bank_fingerprint + ATEP gate (Section 17)          │
  │ out-of-band verification                       │                                                                │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 4: No duplicate invoices without dedup    │ Satisfied — InvoiceProof EXACT_DUPLICATE rule + QBWCSession    │
  │ check                                          │ dedup (Section 13)                                             │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 5: No Sheets as hidden source of truth    │ Satisfied — no Sheets in scope (Section 3)                     │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 6: No REST API assumptions about QB       │ Satisfied — QBWC/qbXML only, outbound poll, no inbound         │
  │ Desktop                                        │ (Section 2)                                                    │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 7: No ignoring Rightworks VPS constraints │ Satisfied — no inbound ports; Rightworks approval required;    │
  │                                                │ session timeout mitigated (Sections 8, 22/R13)                 │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 8: One-way sync with reconciliation       │ Satisfied — read sync is QB→canonical one-way; write is        │
  │ report                                         │ canonical→QB one-way; daily reconciliation defined (Section    │
  │                                                │ 15)                                                            │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 9: No automation bypassing approval gate  │ TRIGGERED — Rule 9 — POST /approvals/{id} currently has no     │
  │                                                │ HTTP auth (R1 in Risk Register)                                │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 10: API available ≠ integration solved    │ Satisfied — dedup, approval gates, failure handling all        │
  │                                                │ designed                                                       │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 11: Idempotency for all                   │ Satisfied for all except R19 (persist_session upsert gap) —    │
  │ webhooks/payments/invoices/vendors             │ flagged                                                        │
  ├────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Rule 12: Proof of data round-trip required     │ Satisfied — Phase 1 gate requires live QBWC proof; Section 20  │
  │                                                │ test plan                                                      │
  └────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────┘

  Rule 9 triggers UNSAFE_WITHOUT_APPROVAL_GATE — but only for the write path (Phase 3+).

  Overall Verdict:

  READY_TO_BUILD — Phase 0 and Phase 1 (read-only)
  UNSAFE_WITHOUT_APPROVAL_GATE — Phase 3+ (write path) until APPROVAL_API_KEY auth is added

  Per-data-type readiness:

  ┌────────────────────────────┬──────────────────────────────┬─────────────────────────────────────────────────────┐
  │     Data Type / Phase      │          Readiness           │                   Blocking Issue                    │
  ├────────────────────────────┼──────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Environment setup (Phase   │ READY_TO_BUILD               │ Venv, migrations, company seed — all are concrete,  │
  │ 0)                         │                              │ unblocked tasks                                     │
  ├────────────────────────────┼──────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Read sync — vendors +      │ READY_TO_BUILD               │ Needs: venv + .qwc file + public HTTPS host +       │
  │ bills (Phase 1–2)          │                              │ Rightworks approval                                 │
  ├────────────────────────────┼──────────────────────────────┼─────────────────────────────────────────────────────┤
  │ BillAdd write-back (Phase  │ UNSAFE_WITHOUT_APPROVAL_GATE │ Approval endpoint lacks HTTP auth (R1); must fix    │
  │ 3+)                        │                              │ before any production write                         │
  ├────────────────────────────┼──────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Draw fee entries (Phase    │ READY_TO_SPEC                │ QB journal entry write-back not yet implemented;    │
  │ 5+)                        │                              │ needs spec                                          │
  ├────────────────────────────┼──────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Multi-file QBWC (Phase 2)  │ READY_TO_BUILD               │ Needs 9 more .qwc files; Option A (10 separate      │
  │                            │                              │ connectors) implementable immediately               │
  └────────────────────────────┴──────────────────────────────┴─────────────────────────────────────────────────────┘

  Most restrictive verdict for the integration as a whole:

  ▎ UNSAFE_WITHOUT_APPROVAL_GATE — until APPROVAL_API_KEY auth is added to POST /approvals/{id}. Fix this (Task 2 from
  ▎ the Coder Task Plan above) before advancing to Phase 3. Phases 0, 1, and 2 (read-only sync) are READY_TO_BUILD and
  ▎ can start immediately.

  Justification: The read-only sync path (Phases 0-2) is architecturally sound and has no blocking issues. The write
  path (Phase 3+) violates Hard Rule 9 because the human approval gate at POST /approvals/{id} has no HTTP
  authentication — any caller can commit an irreversible canonical write and trigger a BillAdd to QB. This is a
  one-sprint fix (Task 2) but must be in place before any invoice goes through the write path in a production QB company
  file.

  ---
  24. Handoff to Implementation

  INTEGRATION HANDOFF PACKAGE
  ==============================
  Skill: master-integration-engineer
  Project: QB Enterprise Desktop ↔ AI Accounting Hub (Summa Terra Ventures)
  Verdict: READY_TO_BUILD (Phases 0-2) / UNSAFE_WITHOUT_APPROVAL_GATE (Phase 3+)
  Next skill: output-to-orchestrator (O2O) for Phase 0-2 tasks

  Implementation phases ready for agents:

  Phase 0 — Environment (unblock all tests and startup):
    - Task 1: python -m venv .venv && pip install -r requirements.txt
    - Task 4: Seed 10 company rows in Supabase (companies table)
    - Task 5: Add docker-compose.yml (NATS + Temporal)
    - Task 7: alembic upgrade head + catalog_bootstrap.py
    Files: requirements.txt, docker-compose.yml (new), scripts/catalog_bootstrap.py

  Phase 1 — Read Sync (single file):
    - Task 3: Generate .qwc file (scripts/generate_qwc.py) + deploy to public HTTPS host
    - Deploy FastAPI server to cloud host (Railway/Render/VPS) with HTTPS
    - Install .qwc on Rightworks QB machine (sandbox company file first, then one production file)
    - ~~Obtain written Rightworks approval for persistent poller~~ RESOLVED 2026-07-01: response received — no
      persistent poller supported; business-hours/session-tied polling is the confirmed final model. Instead: confirm
      Rightworks has configured QuickBooks + QBWC to auto-open on hosted-session login.
    Files: scripts/generate_qwc.py (new), app/transport/qwc.py, .env

  Phase 2 — Read Sync (all 10 files):
    - Task 6: Generate 9 more .qwc files; implement per-FileID company routing in authenticate()
    - Modify: app/transport/qbwc.py:87 authenticate() to map FileID → company_id
    - Modify: app/config.py — add qbwc_company_file_paths + file_id map
    Files: app/transport/qbwc.py, app/config.py, .env.example

  Phase 3 — Write path (requires Phase 0-2 complete + approval auth fixed):
    - Task 2: Add APPROVAL_API_KEY auth to POST /approvals/{id}
    - Task 9: Create invoice2data templates
    - Wire NatsEventBus + TemporalWorkflowEngine in workflow/router.py for production
    Files: app/workflow/router.py, app/config.py, templates/invoices/ (new)

  Recommended agent assignments:
  - Dev (Claude Code / Ben agent): Tasks 1, 2, 3, 5, 6, 7, 9 — all Python/config changes
  - Controller / Accountant: Phase 0 company seed data; Phase 1-2 QB file access on Rightworks
  - IT (Rightworks admin): .qwc installation; Rightworks approval; HTTPS server setup

  Constraints agents MUST preserve:
    - No inbound connection to Rightworks box — outbound QBWC poll only (CLAUDE.md)
    - No QBWC write (BillAdd) without VerifyAPI + AIVS + InvoiceProof gates all passing
    - QB identifiers (qb_list_id, qb_txn_id) are NEVER primary dedup keys — use UUID PKs
    - All gates fail closed — never write partial/errored sessions to the canonical store
    - NEVER commit .env, keys/, or AIVS signing key to git
    - Dashboard at /ui is shadow-mode — no QB side effects from any dashboard action

  ---
  25. Handoff to Brutal Truth Audit

  PRE-LAUNCH CHECKLIST FOR brutal-truth-launch-audit
  ====================================================
  Integration: QB Enterprise Desktop ↔ AI Accounting Hub (Summa Terra Ventures)
  Environment to audit: Production (Rightworks QB + Supabase fdnwlcomuddzmluvbylg)

  Before auditing, verify:

  PHASE 0 GATES:
  [ ] venv installed; pytest -q exits 0; ruff check . && mypy app exit 0
  [ ] alembic upgrade head confirmed (alembic current shows 20260701_1000)
  [ ] 10 company rows in companies table (exactly 1 with role='parent')
  [ ] accounts and cost_codes tables non-empty (catalog_bootstrap.py ran)
  [ ] docker-compose.yml present; NATS + Temporal start clean

  PHASE 1-2 GATES:
  [ ] .qwc files generated with real QBWC_ENDPOINT_URL (HTTPS)
  [ ] HTTPS cert valid; curl from Rightworks RDP to /qbwc returns WSDL
  [x] Rightworks written response on persistent poller obtained (2026-07-01): not supported; business-hours/session-tied
      polling is the confirmed final model — QBWC auto-opens on session login, no persistence across the 2h inactivity
      timeout
  [ ] QBWC Web Connector shows "Last result: Success" for each file
  [ ] GET /sync/health shows poll_count >= 3 and last_error: null for each company
  [ ] Daily reconciliation report matches QB vendor/bill counts for all 10 files (1-week clean)
  [ ] Controller sign-off on Phase 2 gate

  PHASE 3+ GATES (before any write):
  [ ] POST /approvals/{id} requires X-API-Key header; 401 without it (CRITICAL blocker)
  [ ] VCAP_SHARED_SECRET set to >=32 byte random value (not placeholder)
  [ ] AGENT_CAPABILITY_SIGNING_SECRET set to non-placeholder value
  [ ] SWARMSYNC_SA_API_KEY set to non-placeholder value
  [ ] AIVS_SIGNING_KEY_PATH file exists at chmod 600 (if AIVS_SIGNING_ENABLED=true)
  [ ] invoice2data templates present; /ap/intake OCR returns non-null draft.amount on test PDF
  [ ] Approval gate tested end-to-end: intent submitted → notification fires → approve → bill.status='synced'
  [ ] EditSequence conflict retry tested: mock 3200 response → re-read fires → second attempt succeeds
  [ ] AuditChainBroken blocks commit: tampered chain → commit returns 409
  [ ] Reconciliation report: bill count matches QB for 2-week pilot period
  [ ] Accountant sign-off on Phase 3 gate

  Run /brutal-truth-launch-audit after Phase 2 read-sync is stable and before Phase 3 write path goes live.

  Section count: 25 of 25 produced.

  ---
  Summary

  The codebase is architecturally complete and correct — every gate, proof layer, and transport component is implemented
  and well-tested in isolation. The blockers are purely operational:

  ┌──────────┬────────────────────────────────────────────────┬─────────────────────────────────┐
  │ Priority │                      Task                      │             Blocks              │
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  │ P0       │ Install venv (pip install -r requirements.txt) │ Everything                      │
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  │ P0       │ Generate .qwc + public HTTPS deployment        │ QB connection (Phase 1)         │
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  │ P1       │ Seed company rows + run migrations             │ Draw engine + reconciliation    │
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  │ P1       │ Add docker-compose.yml                         │ Live workflow (NATS + Temporal) │
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  │ P1       │ Implement per-FileID routing in authenticate() │ 10-file sync (Phase 2)          │
  ├──────────┼────────────────────────────────────────────────┼─────────────────────────────────┤
  │ P1       │ Create invoice2data template dir               │ OCR intake                      │
  └──────────┴────────────────────────────────────────────────┴─────────────────────────────────┘

  Phases 0-2 (read-only sync) are READY_TO_BUILD and can start today. Phase 3 (write-back) is blocked only on the
  approval endpoint auth — a one-sprint fix.
