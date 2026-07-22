● Spec Compliance Audit

  Audited: 2026-06-30
  Spec version: spec-stv-integration-layer-2026-06-29.md v1.0.0, "Ready for Build"
  Build version: ai-accounting-hub-ralph (System B) at git HEAD 1121d66, prior commits 825c4c9/f75ab8a; live schema
  independently verified against Supabase projects fdnwlcomuddzmluvbylg (System B) and ejxrbxoncsgglrqvjulr (System A —
  note: the spec text itself has a typo, ...julg vs the real ...julr)
  Scope: Full audit, Phases 0–5. Critical scope note: This working directory contains only System B (AI Accounting Hub).
  System A (STV Gmail AccountingOS, described in the spec as "live on Railway") has no repository anywhere on this
  machine. Everything the spec assigns to System A (outbox_writer.py, outbox_delivery_job.py, POST
  /integration/bill-synced, approval_signal.py) exists only as a self-labeled "reference implementation" committed
  inside the System B repo — never proven to be deployed to a real System A service. Every finding about System A's
  actual behavior is UNVERIFIABLE and is marked as such below.

  1. Final Verdict

  FAIL. Two business-critical requirements are built as real, well-documented, well-tested code but are never wired into
  the live request path, which breaks the spec's own happy path end-to-end: (1) InvoiceProof Gate 1 — the formal proof
  gate the architecture calls "AP money-movement, fail closed" — is fully implemented but has zero call sites in the
  live POST /intents/bill handler, so no real bill ever gets a proof bundle; and (2) the durable Temporal workflow
  engine the spec repeatedly promises ("Temporal retains state indefinitely — no data loss") is built but unused — every
  live endpoint hardcodes a non-durable, in-memory stand-in instead. Because the approval endpoint correctly fails
  closed when no proof bundle exists, the net effect is not a security hole — it's that no bill can ever be approved
  through the built system today, and all in-flight approval state is lost on every restart. A third business-critical
  break compounds this: the spec's own documented endpoint, POST /approvals/{workflow_id}, is intercepted by a
  pre-existing, unrelated handler, while the correct integration logic actually lives at a different path. Any caller
  following the written API spec gets the wrong code with none of the required guarantees.

  2. Executive Summary

  Database schema (Phase 0), the bank-change block (Phase 3), the draw-fee math and STV CM LLC guard (Phase 4), and the
  payment-confirmed endpoint (Phase 5) are genuinely built, live-verified against the real databases, and covered by a
  large passing test suite (main run: 392 passed / 0 failed; a second run counted 339 passed / 52 skipped / 1 xfailed —
  the difference is test-selection flags, not a contradiction). But the pipeline's two most important safety mechanisms
  are dark in production: InvoiceProof Gate 1 (the formal SwarmSync proof product) is never called from the live
  bill-creation code, and the real Temporal engine is dead code sitting next to a hardcoded in-memory fake that every
  live route actually uses. SILENT GAP: tests/test_integration_e2e.py's "Scenario 1 full flow" test hand-feeds a mocked
  session a pre-populated invoiceproof_bundle_id rather than exercising the real code path that's supposed to create it
  — so the test suite reads green while the feature it's testing is actually broken. SILENT GAP: bills approved through
  the manual UI path skip the AIVS audit-chain append that the JSON API path performs, breaking the "100% AIVS chain
  coverage" guarantee for any bill Ben approves by hand. SILENT GAP: the spec's literal endpoint POST
  /approvals/{workflow_id} is answered by an unrelated pre-existing handler with none of the spec's required checks,
  while the correct logic sits at /intents/approvals/{workflow_id} instead. Separately, Phase 5's "extend Ben's existing
  dashboard" requirement was reinterpreted as building a brand-new, System-B-only page, because no existing dashboard
  artifact exists in this workspace to extend, and the daily-digest email required by Definition of Done #10 does not
  exist at all.

  3. Requirement-by-Requirement Comparison

  Spec Requirement: Migration 001: integration_outbox + 3 tracker columns, System A DB (§6.1, §13)
  Actual Build Evidence: Live SQL query on ejxrbxoncsgglrqvjulr confirms table +
    aihub_workflow_id/aihub_bill_id/aihub_status columns exist
  Status: DONE
  Gap / Difference: Not tracked as a committed migration file anywhere — applied out-of-band via MCP
  Impact: Reproducibility risk only
  Fix Required: Commit the applied SQL as a tracked migration
  ────────────────────────────────────────
  Spec Requirement: Migration 002: bills.gmail_tracker_id, draw_packages.gmail_fee_opportunity_id (§6.3, §13)
  Actual Build Evidence: Live SQL on fdnwlcomuddzmluvbylg confirms both UNIQUE columns exist
  Status: DONE
  Gap / Difference: No matching Alembic file in migrations/versions/
  Impact: Same reproducibility risk
  Fix Required: Add matching Alembic migration for CI/local parity
  ────────────────────────────────────────
  Spec Requirement: Migration 003: anon RLS SELECT-only on bills/draw_packages (§6.4, §13)
  Actual Build Evidence: Live pg_policies query confirms anon_select_bills/anon_select_draw_packages, role anon, cmd
    SELECT; RLS enabled on both tables; no anon write policy exists
  Status: DONE
  Gap / Difference: Same untracked-migration gap
  Impact: —
  Fix Required: Same as above
  ────────────────────────────────────────
  Spec Requirement: POST /intents/bill — validation, 400 bank-change, 422 blocked/validation, idempotent 200, vendor
    fuzzy match ≥0.75 (pg_trgm), 201 response shape
  Actual Build Evidence: app/integration/intents_router.py:435-627 — all behaviors match spec line-by-line; threshold
    hardcoded at _VENDOR_SIMILARITY_THRESHOLD = 0.75
  Status: DONE
  Gap / Difference: None
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: InvoiceProof Gate 1 — VCAP Full Bundle sealed on bill creation (§5 Flow 1 Step 11, §12, Governor
  Gate
    1)
  Actual Build Evidence: app/integration/invoice_proof_gate.py fully implements run_invoice_proof_gate1() (hash, HMAC
    signature, fail-closed, writes proof_bundles, sets bills.invoiceproof_bundle_id). Grepped entire app/ tree: zero
  call
     sites outside its own definition and one unit test that calls it directly with a mocked session. create_bill_intent

    never calls it.
  Status: STUB/MOCK — SILENT GAP
  Gap / Difference: Real code exists but never executes in the live path
  Impact: Business-critical. approve_bill_intent hard-rejects 422 PROOF_BUNDLE_MISSING whenever invoiceproof_bundle_id
  IS
     NULL (intents_router.py:1308-1333), which is always, for every real bill. No bill created via the live  endpoint
  can
     ever be approved. Scenario 1 (spec §5) and DoD condition #1 are broken at the first step.
  Fix Required: Call run_invoice_proof_gate1() synchronously immediately after the bill INSERT in create_bill_intent
  (and
    in the draw-fee-bill loop), before commit
  ────────────────────────────────────────
  Spec Requirement: Temporal Cloud workflow — durable, restart-surviving, 48h escalation timer (§4, §8, §16, Governor
    "Stateful objects")
  Actual Build Evidence: app/workflow/temporal_engine.py implements a real temporalio-backed
    TemporalWorkflowEngine/IntentWorkflow. But intents_router.py:76 and app/workflow/router.py:40 both hardcode
    InMemoryWorkflowEngine() at module scope; grep confirms TemporalWorkflowEngine is instantiated nowhere else in app/,

    only in its own file and a RUN_INTEGRATION-gated test
  Status: DISCONNECTED — SILENT GAP
  Gap / Difference: All approval-gate/workflow state lives in a Python object wiped on every process restart or Railway
    redeploy
  Impact: Business-critical. Directly contradicts the spec's own durability guarantee and the human-approval commit
    boundary described in CLAUDE.md
  Fix Required: Add an env-driven factory (TEMPORAL_HOST set → real engine, else in-memory for dev/test only); deploy a
    Temporal worker; prove restart-survival with a real test
  ────────────────────────────────────────
  Spec Requirement: POST /approvals/{workflow_id} — exact spec path, dual auth, idempotent, note≥10 chars, 404, Gate-1
    check, AIVS row, callback (§6.6, §12)
  Actual Build Evidence: The literal path /approvals/{workflow_id} is answered by a pre-existing, unrelated handler
    (app/workflow/router.py:87, generic CHUNK_5/7 resolve_endpoint) — no proof-gate check, no bank-change independence,
    no callback. The spec-correct integration logic (dual auth, note validation, idempotency, Gate-1 fail-closed check,
    AIVS rows, best-effort callback) is fully implemented but lives at a different path: POST
    /intents/approvals/{workflow_id} (intents_router.py:1175-1411)
  Status: DIFFERENT FROM SPEC — business-critical, changes access/behavior
  Gap / Difference: A caller following the written spec/API doc hits the wrong handler with none of the required safety
    checks
  Impact: Retire or rename the conflicting workflow/router.py route, or rename the integration route to match spec and
    update the spec's own change-control log
  Fix Required:
  ────────────────────────────────────────
  Spec Requirement: Approval signal delivery, System A→B (§5 Flow 1 Steps 12-13)
  Actual Build Evidence: app/integration/approval_signal.py:186 (System A reference impl) POSTs to
    {base_url}/approvals/{workflow_id} — matching the spec's documented path, not the actual implemented route
    (/intents/approvals/{workflow_id})
  Status: DIFFERENT FROM SPEC / route mismatch
  Gap / Difference: If System A ever ships this reference file as-is, every email-approval signal would 404 or hit the
    wrong handler
  Impact: Business-critical — breaks the primary email-approval happy path described in spec §5 Flow 1
  Fix Required: Align approval_signal.py's target URL with whichever path is chosen as canonical in the fix above
  ────────────────────────────────────────
  Spec Requirement: Manual-UI approval path — same Temporal signal / AIVS path as email approval (§5 Flow 2)
  Actual Build Evidence: app/integration/approval_ui.py:165-282 (POST /approve/{workflow_id}) is a separate,
    independently-written handler that only does UPDATE bills SET status='approved' — never calls the AIVS append
    (append_audit_row/proof bundle write) that the JSON API path (intents_router.py:1352-1383) performs. Also gated by a

    different token (APPROVAL_UI_TOKEN) than the API path's BEN_SESSION_TOKEN
  Status: PARTIAL — SILENT GAP
  Gap / Difference: Bills approved via the UI get no AIVS chain entry
  Impact: Breaks DoD condition #3 (AIVS chain valid) for any bill Ben approves by hand — likely the majority of real
    approvals per spec §5 Flow 2
  Fix Required: Route UI approvals through the same code path as /intents/approvals/{workflow_id}, or call the same AIVS

    append helper from approval_ui.py
  ────────────────────────────────────────
  Spec Requirement: Bill-synced callback, System B→A (§6.7, §12)
  Actual Build Evidence: app/integration/callback_sender.py — correct outbound httpx POST, bearer auth, 3×/30s retry,
  4xx
    not retried, logs to reconciliation on exhaustion. Fired synchronously inline inside the approval/payment-confirmed
    request handlers using blocking httpx/time.sleep, not fire-and-forget
  Status: PARTIAL
  Gap / Difference: Worst case blocks the caller's HTTP response up to ~90s if System A is down, contradicting spec §8's

    <2s p95/<5s p99 callback latency target measured from the caller's side
  Impact: Non-critical to correctness, but a real latency-SLA violation
  Fix Required: Move the callback send to a background task/queue instead of the request thread
  ────────────────────────────────────────
  Spec Requirement: System A POST /integration/bill-synced receiver (§6.7)
  Actual Build Evidence: app/integration/callback_router.py is a correct, clearly-labeled reference implementation,
    intentionally unmounted in System B's own main.py (comment confirms this is deliberate)
  Status: UNVERIFIABLE
  Gap / Difference: Cannot confirm this reference module was ever copied to and deployed on the real System A service
  Impact: Business-critical if never deployed — the loop that advances System A's tracker (DoD #1, #9) silently no-ops
  in
    production
  Fix Required: Confirm with System A's owner/deployment whether this file was ever ported over
  ────────────────────────────────────────
  Spec Requirement: POST /intents/bank-block — ATEP block, idempotent, exception-queue scan (§5 Flow 3, §7, §12)
  Actual Build Evidence: intents_router.py:986-1174 — advisory lock, idempotent via fingerprint/ILIKE match,
    bank_fingerprint='BLOCKED:<email>', in-flight bills → status='exception', sender_email SHA-256 hashed before audit
    write (exceeds spec's privacy bar)
  Status: DONE
  Gap / Difference: None
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: outbox_writer.py — bank_change_risk fires BEFORE bill_intent, no bill_intent row (§5 Flow 3,
    must-not-break #2)
  Actual Build Evidence: outbox_writer.py:276-298 — Guard 1 fires before any INSERT, redirects to write_bank_block,
    audit-logs outbox_bank_change_guard
  Status: DONE (reference impl; UNVERIFIABLE on real System A)
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: POST /intents/draw — STV CM LLC 400, FEE_PAYEE_BLOCKED 400, idempotent, 5%/2%/1% math + hard-reject
    on mismatch, 3 fee bills (§5 Flow 4, §7, §12)
  Actual Build Evidence: intents_router.py:635-978 — all guards, math validation (economic_total != 8% → 422
    FEE_MATH_INVALID), and 3-bill creation match spec exactly; STV CM LLC blocked independently on both System A
    (outbox_writer.py:429-499) and System B (intents_router.py:684-708) sides
  Status: DONE
  Gap / Difference: Idempotency check queries raw_extensions->>'gmail_fee_opportunity_id' (JSONB text match) instead of
    the dedicated UNIQUE column Migration 002 created and that is live in the DB; the INSERT never populates that column
  Impact: Functional but not what the migration was built for — slower/weaker dedup guarantee
  Fix Required: Populate draw_packages.gmail_fee_opportunity_id on insert and switch the idempotency lookup to that
    column
  ────────────────────────────────────────
  Spec Requirement: Draw engine "CHUNK_6... activate, not rebuild" (§2, §4, §5)
  Actual Build Evidence: app/draw_engine/engine.py is the real CHUNK_6 module, self-labeled "shadow-mode only" in its
  own
    docstring. create_draw_intent() in intents_router.py does not import or call it at all (zero grep matches) — it
    reimplements bill creation directly with raw SQL, reusing only the shared math primitive
    app.catalog.fee_math.split_developer_fee()
  Status: DIFFERENT FROM SPEC
  Gap / Difference: The math is correct and shared, but the orchestration layer is a parallel reimplementation, not an
    "activation" of the existing engine as required; CHUNK_6 itself remains in shadow mode, unconnected to any live path
  Impact: Non-critical to correctness (numbers are right), but violates the explicit "activate, not rebuild" instruction

    and leaves two implementations to maintain
  Fix Required: Either route /intents/draw through draw_engine.engine for real, or update the spec to reflect that a new

    implementation was intentionally chosen
  ────────────────────────────────────────
  Spec Requirement: POST /intents/payment-confirmed — bill→paid, idempotent, 404 (§5, §7, §12)
  Actual Build Evidence: intents_router.py:1486-1615 — full match: auth, lookup, 404, idempotent 200, status update,
  AIVS
    row, commit-before-callback
  Status: DONE
  Gap / Difference: None
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Approval UI — bill list (status=verified),
    vendor/amount/project/date/mike_email_detected/proof_status, Approve button, note≥10 chars (§5 Flow 2, §18)
  Actual Build Evidence: app/integration/approval_ui.py renders all required fields; proof_status correctly displays
    "Gate 1 pending" for every bill (since Gate 1 never runs — see above), which is at least an honest reflection of the

    broken state
  Status: DONE (UI itself) / downstream of Gate-1 gap
  Gap / Difference: UI is real, but every bill will sit permanently unapprovable through it until Gate 1 is wired
  Impact: Same root cause as Gate 1 finding
  Fix Required: Same fix as Gate 1
  ────────────────────────────────────────
  Spec Requirement: Dashboard — extend Ben's existing dashboard/index.html with a second (aihub) Supabase client,
    read-only bills + draw_packages sections (§4, Governor "Reuse opportunities", Phase 5 checklist)
  Actual Build Evidence: No dashboard/index.html or any pre-existing cross-system dashboard file exists anywhere in this

    workspace (repo-root search performed). Instead, System B's own dashboard app gained a new standalone page
    app/dashboard/templates/system_b.html (app/dashboard/router.py:168-186), correctly injecting
    SUPABASE_URL_AIHUB/SUPABASE_ANON_KEY_AIHUB for read-only client-side Supabase reads
  Status: DIFFERENT FROM SPEC
  Gap / Difference: The spec's stated goal — Ben checks one dashboard instead of two — is not delivered; two separate
    pages still exist
  Impact: Affects DoD condition #8 ("Ben's dashboard loads both...sections") literally, though the underlying read-only
    data delivery is equivalent
  Fix Required: Confirm with Ben/System A owner whether system_b.html is accepted as final, or port it into System A's
    real dashboard file
  ────────────────────────────────────────
  Spec Requirement: RLS enforces SELECT-only for anon, no writes possible (§9, §6.4)
  Actual Build Evidence: Live-verified: only SELECT policies exist for role anon on both tables; no INSERT/UPDATE/DELETE

    anon policy present
  Status: DONE
  Gap / Difference: None
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Daily digest email to Ben (§16, DoD condition #10)
  Actual Build Evidence: Grepped app/ for digest/email-sending mechanisms (smtplib, sendgrid, SMTP, "daily digest") —
    zero real hits; only unrelated cryptographic-hash "digest" substring matches
  Status: MISSING
  Gap / Difference: No implementation attempt anywhere
  Impact: DoD #10 cannot be satisfied as built
  Fix Required: Build a scheduled job aggregating the §16 metrics and an approved email-sending mechanism (check
    CLAUDE.md guardrails before adding a dependency)
  ────────────────────────────────────────
  Spec Requirement: Bearer-token auth on all /intents/* and callback endpoints, fail-closed on missing/invalid token,
  401
    (§9)
  Actual Build Evidence: _check_auth()/_check_integration_auth() (intents_router.py:136-185) — real comparison against
    env-loaded secrets, explicitly treats an empty expected token as non-matching (no fail-open bug); applied first-line

    in every relevant handler; callback_router.py:113-123 does the same for the System A side
  Status: DONE
  Gap / Difference: None
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Env var / credential handling (§9)
  Actual Build Evidence: AIHUB_OUTBOX_TOKEN is a typed Settings field (app/config.py:37-65) that fails app startup if
    empty — stronger than spec. SYSTEM_A_CALLBACK_TOKEN, BEN_SESSION_TOKEN, SUPABASE_ANON_KEY_AIHUB, SYSTEM_A_URL are
    read ad hoc via os.environ.get(..., ""), not part of the typed/validated settings model
  Status: PARTIAL
  Gap / Difference: Inconsistent secret-loading pattern; no fail-fast for the ad hoc ones
  Impact: Low — no security exposure demonstrated, just inconsistency and weaker startup validation
  Fix Required: Move remaining secrets into the typed Settings model
  ────────────────────────────────────────
  Spec Requirement: Payload security — no API keys/bank numbers/raw email body in integration_outbox payloads (§9)
  Actual Build Evidence: outbox_writer.py allowlists raw_extensions keys (lines 62-69); write_bank_block payload limited

    to vendor_name/sender_email/message_id
  Status: DONE
  Gap / Difference: No dedicated automated test asserts this (spec §10 lists it as a security test); enforced only by
    code allowlist, not verified by assertion
  Impact: Low
  Fix Required: Add a test asserting payload keys are a subset of the allowlist
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #1: draft_queue never touched by integration code
  Actual Build Evidence: Grep across app/ for "draft_queue": zero code references, only docstring mentions affirming
    non-access
  Status: DONE
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #2: bank_change_risk guard fires before any bill_intent write
  Actual Build Evidence: outbox_writer.py:276-298
  Status: DONE
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #3: STV CM LLC blocked independently, both systems
  Actual Build Evidence: Confirmed both sides (see draw rows above)
  Status: DONE
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #4: no automated approvals
  Actual Build Evidence: Only POST /intents/approvals/{workflow_id} sets status='approved'; requires explicit human POST

    + ≥10-char note for manual path
  Status: DONE
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #5: System A/B DB clients never confused
  Actual Build Evidence: No file imports both DB configs; independently verified live that the two Supabase projects are

    in fact distinct and correctly targeted by their respective MCP servers
  Status: DONE
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #6: Gate 1 fails closed
  Actual Build Evidence: Approval endpoint correctly 422s when no passed proof bundle exists
  Status: DONE in the narrow sense — but see Gate 1 row above: it fails closed permanently, for every bill, because
    nothing ever produces a passing bundle
  Gap / Difference: The safety property holds; the feature is simply non-functional as a result
  Impact: Same fix as Gate 1
  Fix Required:
  ────────────────────────────────────────
  Spec Requirement: Must-not-break #7: no QB write without proof + approval
  Actual Build Evidence: No QBWC/BillAdd path reachable from this module (correctly out of scope per Phase 6 gating)
  Status: DONE
  Gap / Difference: —
  Impact: —
  Fix Required: —
  ────────────────────────────────────────
  Spec Requirement: CLAUDE.md validation gate: ruff check . && mypy app && pytest -q
  Actual Build Evidence: ruff check . → all clean. pytest → 392 passed / 0 failed (full run); no failures found. mypy
  app
    → 1 error: intents_router.py:542, Argument 1 to "float" has incompatible type "Decimal | None"
  Status: PARTIAL
  Gap / Difference: The mandatory pre-commit gate CLAUDE.md requires is currently failing
  Impact: Low severity but a broken required gate
  Fix Required: Guard the Decimal | None → float cast at line 542 with a None check
  ────────────────────────────────────────
  Spec Requirement: Test environment reproducibility
  Actual Build Evidence: Fresh venv could not import the app until httpx and python-multipart (already in
    requirements.txt) were manually installed
  Status: PARTIAL
  Gap / Difference: pip install -r requirements.txt was evidently not run/synced for the shipped venv, or CI/local
  parity
    is broken
  Impact: Blocks trusting "tests pass" claims without manual intervention
  Fix Required: Re-sync venv from requirements.txt; add a CI dependency-drift check
  ────────────────────────────────────────
  Spec Requirement: Documentation accuracy — intents_router.py module docstring / main.py comment
  Actual Build Evidence: Both explicitly label /intents/draw, /intents/bank-block, /intents/payment-confirmed as "stubs
    (wired in later phases)" — false; all three are fully implemented and tested
  Status: DIFFERENT FROM SPEC-adjacent (stale doc)
  Gap / Difference: Misleads future coders/auditors into underestimating completion
  Impact: Low direct impact, real process risk
  Fix Required: Update the docstring to reflect actual status
  ────────────────────────────────────────
  Spec Requirement: Extra endpoint POST /callbacks/bill-synced on System B (intents_router.py:1419-1478)
  Actual Build Evidence: Updates the bill's own raw_extensions.aihub_status — no basis in the spec
  Status: Not a spec requirement
  Gap / Difference: See Section 7
  Impact: —
  Fix Required: —

  4. Missing Items

  1. Daily digest email to Ben (§16, DoD #10) — business-critical relative to Definition of Done; zero implementation
  found anywhere in the repo.
  2. Alembic migration files for Migrations 002/003 — schema changes are live and correct in the actual database, but no
  versioned migration file exists in source control to reproduce them.

  5. Partially Done Items

  1. POST /intents/approvals/{workflow_id} — logic is correct and complete, but functionally unreachable for real bills
  because Gate 1 never populates its precondition (see Section 3/6).
  2. POST /intents/draw idempotency — uses a JSONB text match instead of the dedicated UNIQUE column the migration
  created for exactly this purpose.
  3. Bill-synced callback delivery — correct retry logic, but fired synchronously on the request thread, risking a ~90s
  worst-case block that violates the spec's own latency target.
  4. Env var / secrets loading — inconsistent between typed Settings and raw os.environ.get() across different files.
  5. CI validation gate — mypy app currently fails with one type error; the mandated ruff && mypy && pytest gate does
  not exit 0 clean.
  6. Test environment reproducibility — fresh install did not work without manual dependency installation already
  declared in requirements.txt.

  6. Wrong or Different Items

  1. POST /approvals/{workflow_id} route collision. Spec §6.6/§12 defines exactly this path for the integration-layer
  approval flow. Build: the literal path is answered by a pre-existing, unrelated handler (app/workflow/router.py:87);
  the correct spec logic lives at /intents/approvals/{workflow_id} instead. The System A reference approval_signal.py
  targets the spec's path, meaning the two halves of this build's own feature would not talk to each other if deployed
  as-is.
  2. Temporal Cloud vs. in-memory engine. Spec repeatedly claims durable, restart-surviving workflow state. Build:
  InMemoryWorkflowEngine is hardcoded into every live route; the real TemporalWorkflowEngine exists but is unused —
  functionally the opposite guarantee.
  3. Dashboard delivery mechanism. Spec: "extend Ben's dashboard HTML... not rebuild." Build: an entirely new,
  System-B-only page, because no existing dashboard artifact is present in this workspace to extend.
  4. Draw engine activation. Spec: "CHUNK_6 (activate, not rebuild)." Build: the CHUNK_6 module (draw_engine/engine.py)
  remains unconnected and self-labeled shadow-mode; /intents/draw reimplements the flow directly in the router, sharing
  only the math primitive.
  5. Manual-UI approval path. Spec says this path is "same Temporal signal path as Flow 1" (i.e., same AIVS append).
  Build: a separate handler that skips the audit-chain write entirely.

  7. Overbuilt / Unrequested Items

  1. POST /callbacks/bill-synced on System B (intents_router.py:1419-1478) — an extra endpoint with no spec basis,
  maintaining a second, parallel "synced" bookkeeping field (raw_extensions.aihub_status) alongside the spec's actual
  System A-side mechanism. Low risk today, but an undocumented surface that can drift from the spec'd semantics.
  2. TemporalWorkflowEngine/IntentWorkflow (app/workflow/temporal_engine.py) — a complete, correct implementation that
  is currently pure dead weight since nothing instantiates it outside its own module and a skipped test. Not unwanted
  (it's exactly what's needed), but as shipped it's inert code adding maintenance surface without providing its
  guarantee.

  8. Verification Evidence

  Fully inspected: ai-accounting-hub-ralph/app/integration/*.py (all 8 files),
  app/workflow/{engine,temporal_engine,router,service}.py, app/dashboard/router.py + templates/system_b.html,
  app/config.py, migrations/versions/*.py (all 6 files), IMPLEMENTATION_PLAN.md, live schema/RLS state on both real
  Supabase projects via direct SQL, full pytest, ruff check ., mypy app, git log/git ls-files.

  Spot-checked: app/catalog/fee_math.py (via call sites), app/audit/* (via call sites),
  app/payments/atep.py/fingerprint.py, app/dashboard/vendor_bills.py, app/models.py (targeted grep, not full read).

  Not reached / correctly out of scope: app/scale/, app/transport/ (QBWC — Phase 6, explicitly out of scope),
  app/canonical/, app/ingestion/, 06_Legal_Hunters_Union_Costs/, 02_Data/, 03_Deliverables/, summa-terra-binding-ralph/.

  Fake-completion-signal checks (explicit, per governing rules):
  - TODO/FIXME/"not implemented": none found in app/integration/.
  - Hardcoded/mock values standing in for real logic: found — InMemoryWorkflowEngine used unconditionally where the real
  Temporal client belongs.
  - Disabled/feature-flagged-off paths: none found — the Gate-1/Temporal disconnections are simple omissions, not flags.
  - Skipped tests: ~52 skips, all RUN_INTEGRATION=1-gated live-DB/staging tests, individually traced — legitimate gates,
  not disguised failures.
  - Tests asserting nothing meaningful / mocked past the point of validity: found — test_integration_e2e.py's
  Scenario-1/Guarantee-6 tests hand-inject invoiceproof_bundle_id into a mocked session rather than exercising the real
  Gate-1 code path, so they pass despite the live path being broken.
  - UI with no working handler: none found — both system_b.html and approve.html wire real Supabase/HTTP calls (not
  rendered in an actual browser — no runtime available in this environment).
  - Routes defined but unreachable/404/500: none among the registered /intents/* and /callbacks/* routes, but the spec's
  documented /approvals/{workflow_id} path is answered by the wrong handler (see Section 6).
  - Env vars referenced but unconfigured: several read via os.environ.get(..., "") with no fail-fast, unlike the one
  that is typed/validated — inconsistent but not exploitable given fail-closed auth comparisons.

  9. Tests and Proof

  Existing and real: test_outbox_writer.py, test_intents_bill.py, test_workflow_integration.py, test_integration_e2e.py,
  test_integration_db.py, test_dashboard.py, test_must_not_break.py, test_audit_verify.py. Full suite: 392 passed, 0
  failed (a second targeted run counted 339 passed / 52 skipped / 1 xfailed — consistent, just different selection
  flags). ruff check . clean; mypy app has 1 outstanding error.

  Critical caveat: test_integration_e2e.py's flagship "Scenario 1 full flow" and "Guarantee 6" tests use a mocked
  SQLAlchemy session pre-loaded with invoiceproof_bundle_id — they validate the approval logic assuming Gate 1 already
  ran, not that Gate 1 actually runs. This is precisely the "tests that prove the mock, not the system" pattern the
  Evidence Bar warns against, and it is why this gap survived a large, otherwise-careful test suite.

  Missing/recommended tests:
  1. An unmocked (or realistically-seeded) test that calls create_bill_intent() then approve_bill_intent() on the same
  bill with no manual injection of invoiceproof_bundle_id — would immediately catch the Gate-1 disconnection.
  2. A test proving TemporalWorkflowEngine (not InMemoryWorkflowEngine) is actually selected under production-like
  config, and a restart-survival test.
  3. A route-path test hitting the literal spec path POST /approvals/{workflow_id} and asserting integration-layer
  behavior (would catch the route collision).
  4. A payload-content test asserting integration_outbox payloads never contain disallowed keys.
  5. Any test for the daily digest email (none possible — feature doesn't exist).

  Skipped tests: ~52, all RUN_INTEGRATION=1/live-DB-gated — legitimate given no staging environment was available to
  this audit; DoD conditions requiring 50 staged commits and staging E2E runs remain UNVERIFIABLE for that reason.

  10. Coder Fix Instructions

  Fix 1: Wire InvoiceProof Gate 1 into the live bill-intent and draw-intent paths

  - Problem: Section 3 — run_invoice_proof_gate1() has zero callers outside its own module.
  - Expected behavior: Spec §5 Flow 1 Step 11 — Gate 1 runs synchronously right after bill creation, before the workflow
  starts, sealing a VCAP bundle and setting bills.invoiceproof_bundle_id.
  - Files: app/integration/intents_router.py (create_bill_intent ~L582-610, create_draw_intent's per-fee-bill loop),
  app/integration/invoice_proof_gate.py.
  - Implementation: After the bill INSERT and before _engine.start_workflow, call run_invoice_proof_gate1(bill_id,
  amount, vendor_name, gmail_invoiceproof, session); catch InvoiceProofGateFailed and leave the bill without a bundle
  rather than raising a raw 500.
  - Acceptance criteria: A bill created via /intents/bill with clean evidence has status='verified' and a proof_bundles
  row with passed=True before the response returns, with no test manually injecting that state.
  - How to verify: Call create_bill_intent() then approve_bill_intent() back-to-back on an unmocked/realistically-seeded
  session; expect 200, not 422 PROOF_BUNDLE_MISSING.

  Fix 2: Connect the real Temporal engine

  - Problem: Section 3 — InMemoryWorkflowEngine hardcoded in every live route; TemporalWorkflowEngine unused.
  - Expected behavior: Spec §4/§8/§16 — durable, restart-surviving workflow state via Temporal Cloud.
  - Files: app/integration/intents_router.py:76, app/workflow/router.py:40, app/workflow/temporal_engine.py.
  - Implementation: Add an env-driven factory (TEMPORAL_HOST set → TemporalWorkflowEngine.connect(), else in-memory for
  dev/test only); deploy a Temporal worker process running IntentWorkflow.
  - Acceptance criteria: A workflow started via /intents/bill is queryable via the real Temporal client and survives an
  app process restart, still signalable afterward.
  - How to verify: Start a bill intent, restart the process, send the approval signal, confirm the bill still advances
  to approved.

  Fix 3: Resolve the /approvals/{workflow_id} route collision

  - Problem: Section 6 — two unrelated handlers answer logically the same spec-named endpoint.
  - Files: app/workflow/router.py:87, app/integration/intents_router.py:1175, app/integration/approval_signal.py:186,
  app/main.py.
  - Implementation: Decide whether the pre-existing generic /approvals/{workflow_id} handler is still needed; if not,
  retire it and rename the integration route to the spec path. If both are needed, give the integration route a distinct
  path and patch the spec (v1.1.0) per its own change-control rule. Update approval_signal.py's target URL to match
  whichever is canonical.
  - Acceptance criteria: Exactly one handler answers POST /approvals/{workflow_id}, behaving per spec §6.6.
  - How to verify: POST /approvals/{wf_id} with a valid token; confirm response includes bill_id/new_status and that the
  proof-bundle gate is actually enforced.

  Fix 4: Route manual-UI approvals through the audited path

  - Problem: Section 3/6 — approval_ui.py's handler skips AIVS append.
  - Files: app/integration/approval_ui.py, app/integration/intents_router.py.
  - Implementation: Call the same approval service function (or the /intents/approvals/{workflow_id} logic) from the UI
  handler instead of a bare UPDATE bills SET status='approved'.
  - Acceptance criteria: A bill approved via the UI has an AIVS audit_rows entry identical in kind to one approved via
  the API.
  - How to verify: Approve a test bill via the UI; query audit_rows for that bill and confirm a bill_approved entry
  exists.

  Fix 5: Build the daily digest email

  - Problem: Section 4 — Missing Items #1; DoD #10 unmet.
  - Files: new module, e.g. app/integration/daily_digest.py, plus a scheduler and an approved email-sending mechanism
  (check CLAUDE.md before adding a new dependency).
  - Implementation: Aggregate the §16 metrics; send to Ben on a daily schedule.
  - Acceptance criteria: Ben receives the specified content in staging.
  - How to verify: Trigger manually in staging; confirm delivery and content.

  Fix 6: Reconcile the dashboard requirement

  - Problem: Section 6 — spec assumed an existing file that doesn't exist in this workspace.
  - Files: app/dashboard/templates/system_b.html, app/dashboard/router.py, and whatever System A's real dashboard file
  is (not present here).
  - Implementation: N/A until Ben/spec owner clarifies whether system_b.html is the accepted final artifact or must be
  merged into System A's real dashboard.
  - Acceptance criteria: Explicit sign-off recorded.
  - How to verify: Direct confirmation, not automatable.

  Fix 7: Confirm System A actually received the reference implementations

  - Problem: Section 3 — outbox_writer.py, outbox_delivery_job.py, callback_router.py, approval_signal.py are all
  self-labeled reference code with no proof of deployment.
  - Implementation: N/A — requires access to System A's actual repo/deployment, outside this workspace.
  - Acceptance criteria: A real integration_outbox row appears in System A's live DB after a real Gmail classify event.
  - How to verify: Check System A's Railway deployment logs/repo directly.

  Fix 8: Cleanup items (non-critical)

  - Populate and use draw_packages.gmail_fee_opportunity_id for idempotency instead of the JSONB fallback
  (intents_router.py:724-827).
  - Move the bill-synced callback send off the request thread.
  - Fix the mypy error at intents_router.py:542 (guard Decimal | None before float() cast).
  - Add Alembic migration files matching the live-applied Migrations 002/003.
  - Re-sync the shipped venv with requirements.txt.
  - Correct the stale "stub" docstring in intents_router.py/main.py.

  11. Final Acceptance Checklist

  - [ ] Gate 1 (run_invoice_proof_gate1) is called from the live /intents/bill and /intents/draw paths (Fix 1)
  - [ ] Real TemporalWorkflowEngine is wired in and deployed; workflow state proven to survive a restart (Fix 2)
  - [ ] /approvals/{workflow_id} route collision resolved — exactly one handler matching spec §6.6 (Fix 3)
  - [ ] Manual-UI approvals write an AIVS audit row identical to API approvals (Fix 4)
  - [ ] Daily digest email built and observed delivering to Ben in staging (Fix 5)
  - [ ] Dashboard requirement resolved with explicit sign-off from Ben (Fix 6)
  - [ ] System A's real deployed service confirmed to run the reference outbox/callback/signal logic (Fix 7)
  - [ ] draw_packages.gmail_fee_opportunity_id used for idempotency; Alembic migrations for 002/003 committed
  - [ ] ruff check . && mypy app && pytest -q exits 0 clean on a fresh clone
  - [ ] test_integration_e2e.py's mocked Scenario-1 test replaced/supplemented with a genuinely unmocked end-to-end test
  - [ ] AIVS chain verify.py run against ≥50 real staging commits per DoD condition #3
  - [ ] Staging E2E run for all 5 scenarios with Ben's manual review of the approval UI and dashboard, per DoD
  conditions #1, #8, #9, #10