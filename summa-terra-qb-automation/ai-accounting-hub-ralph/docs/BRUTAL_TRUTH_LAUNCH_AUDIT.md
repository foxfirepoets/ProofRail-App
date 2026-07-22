# BRUTAL TRUTH LAUNCH AUDIT — AI Accounting Hub Dashboard

**Date:** 2026-06-29 · **Mode:** customer-facing-product (scoped to internal tool) · **Branch:** build/ralph-mvp
**Commits in scope:** 5608c39, 3fa6325, c3047c6, 9f0f779, 518128c, ec6bb01, 5e13d70, 445fd5e

## 0. QA / Evals Harness Summary
**QA Verdict:** QA_HARNESS_PARTIAL (in-process route harness; no live URL — see scope). **Tests:** 298 passed / 50 skipped / 0 failed. **Critical gaps:** None. **QA effect:** constrains to CONDITIONAL GO (full paid-customer GO is structurally N/A — no payment/customer journey exists).

## 1. VERDICT
**Final verdict: CONDITIONAL GO — SAFE FOR INTERNAL SHADOW-MODE USE.**
- **Biggest blocker:** None (no CRITICAL, no HIGH).
- **Why this verdict:** Every claimed module is functional and verified; shadow-mode is absolute (no QB/BillAdd/payment path, enforced by an AST test); no raw bank data; audit trail on every action; no secrets committed. Full `GO — SAFE FOR PAID CUSTOMER TEST` does **not** apply because this is an internal operator tool with no customer signup, no payment, and no live deployment — those journeys are N/A by design, not broken.
- **What would change the verdict:** Adding auth + a live deployment (for multi-user/production use) would move scope toward a full customer-product GO; building QB write-back is the separate, gated next phase.

| Severity | Count |
|---|---:|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 2 (disclosed, by-design) |
| LOW | 1 |

## 2. Scope and Access Reality
| Area | Access | Tested? | Limitation |
|---|---|---|---|
| Repo / code | full | yes | — |
| Validation gate | full | yes (ruff/mypy/pytest) | — |
| In-process routes | full | yes (handler-level via test suite) | `httpx` not installed → no out-of-process HTTP smoke; handlers exercised directly |
| Live deployment | none | N/A | runs locally via `uvicorn`; not deployed |
| Payments / Stripe | none | N/A | no payment surface exists (by design) |
| Auth / customer journey | none | N/A | internal localhost tool, no signup/login (by design) |
| DB (Supabase) | via DATABASE_URL | yes (rolled-back live proofs in build) | — |

## 3–5 (Customer journey / Payment / Entitlement)
**N/A — by design.** No customer signup, no Stripe, no entitlement. This is a single-operator internal shadow-mode tool. Not a defect; documented in `OPERATOR_HANDOFF.md`.

## 6. Auth / Security (MEDIUM, disclosed)
No authentication: anyone with access to the localhost host has full dashboard access. **Acceptable for the current single-operator internal use**, but must be addressed before any networked/multi-user deployment. No secrets in repo (`.env` not tracked, gitignored). No raw bank data stored (SHA-256 fingerprints only). No raw SQL/eval/subprocess in `app/dashboard/`.

## 7. Critical/High Findings
**None.**

## 13. Shadow-safety + integration truth (the core promise)
| Claim | Status | Evidence |
|---|---|---|
| 15 functional modules, only qb_sync pending | PROVEN | `modules.MODULES`: 16 total, 15 functional, pending=['qb_sync'] |
| Every module route renders 200 + SHADOW banner | PROVEN | `test_every_module_route_renders_with_banner` (all 16 routes) passes |
| No QB/BillAdd/payment path reachable | PROVEN | `test_dashboard_package_has_no_qb_write_path` AST scan passes; grep clean |
| No raw bank data | PROVEN | `vendor_bills.py:57-59` hashes a local var to SHA-256; `WorkItem.bank_fingerprint` digest-only; no raw column |
| Audit trail on every action | PROVEN | `append_audit_row` at `work_queue.py:113`, `vendor_bills.py:98` |
| Draw #29 never approvable for posting | PROVEN | `service.py:48-57` `is_historical`/`assert_postable`/`ShadowGuardError` wired into approve route |
| Docs match routes | PROVEN | `OPERATOR_HANDOFF.md` routes verified against `router.py` |

## 18. Failure-mode notes (MEDIUM/LOW)
- **MEDIUM** — No auth (above).
- **MEDIUM** — Multi-user concurrency on status transitions not load-tested (single-operator use only today).
- **LOW** — Out-of-process HTTP smoke not run (`httpx` absent); handler-level coverage is strong but not a full live-server probe.

## Owner-deferred (written reason)
The items preventing a full `GO — SAFE FOR PAID CUSTOMER TEST` — customer journey, payment lifecycle, auth/org isolation, live deployment — are **structurally not applicable to an internal, single-operator, localhost, shadow-mode tool**. They are deferred with this written reason until the system is networked or commercialized. The QB write-back module (`qb_sync`) remains intentionally unbuilt, gated on the two open Rightworks spikes (poll cadence; persistent-poller approval).

**Bottom line: CONDITIONAL GO for internal shadow-mode use. No CRITICAL/HIGH blockers.**
