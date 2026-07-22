# AI Accounting Hub — Architecture Decision Record

**Date:** 2026-06-25
**Status:** Decision proposed, build gated pending go/no-go
**Scope:** Integrating QuickBooks Enterprise Desktop (Rightworks-hosted, 10+ company files) with an AI automation platform, architected natively around SwarmSync proof primitives.

---

## 0. The two findings that override conventional wisdom

**Finding 1 — On Rightworks, Web Connector is not "conventional wisdom." It is physically forced.**
Live research confirms Rightworks (Right Networks) is a locked-down multi-tenant Microsoft RDS farm:
- No inbound listener / no per-tenant public port (you don't own the firewall).
- No self-service custom `.exe` or Windows service install (apps come only from the vetted AppHub catalog; bespoke apps require a support/vetting ticket).
- **Background programs are killed on disconnect** — unattended sync requires a Rightworks support ticket to configure QB + Web Connector auto-start at login.

Every credible hosted-QB integrator (Bill.com, Webgility, Conductor, MyWorks) uses **QuickBooks Web Connector polling OUTBOUND to a cloud-hosted SOAP endpoint**. COM/QBFC custom agents, ODBC, direct DB replication, RPA/UI automation, gRPC, local REST gateways — all require something Rightworks forbids (inbound ports, persistent daemons, or self-installed binaries). They are eliminated **on environment grounds, not preference.**

**So the honest answer to "is Web Connector best?" is: as a TRANSPORT on Rightworks, yes — it's the only sanctioned reliable option. The mistake everyone makes is letting that transport define the whole architecture.**

**Finding 2 — InvoiceProof / AuditProof / VerifyAPI are not named in the SwarmSync specs, but their primitives are.** All three map cleanly onto real, citable SwarmSync protocol primitives. We architect against the primitives and treat the product names as the branded surface:

| Product (branded) | Real SwarmSync primitive | What we actually call |
|---|---|---|
| **AuditProof** | **AIVS** (`draft-stone-aivs-01`) — hash-chained, tamper-evident audit archive (`prev_hash`/`row_hash`, optional Ed25519) | Wrap every AI action + human decision as an AIVS audit row |
| **InvoiceProof** | **VCAP** verification rail + escrow (`verification_callback`, `proof_hash`, `proof_signature`) | Pre-payment verification gate producing a proof record |
| **VerifyAPI** | **VCAP** `verification_callback.passed` + **ADRP** `verify_resolution` (offline, deterministic) | Independent validation of autonomous workflow outputs |

Supporting primitives available: **ATEP** trust tiers (gate how much an AI agent may do autonomously), **ATXN** transaction recognition events, **ADRP** dispute/ruling supersession, **AREF** commissions. *Action item: obtain the live InvoiceProof/AuditProof/VerifyAPI platform API docs from SwarmSync — the spec primitives tell us the shape, not the exact HTTP surface.*

---

## 1. The core architectural reframe

> **Demote the transport to a swappable adapter. Put all durable value in a vendor-agnostic platform + proof layer above it.**

```
            AI Orchestration Layer  (MCP server: reads cached, writes gated)
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   InvoiceProof     AuditProof      VerifyAPI
   (VCAP rail)   (AIVS audit chain) (VCAP+ADRP verify)
        └───────────────┼───────────────┘
                        ▼
                 Approval Engine (Temporal: Signals=gates, Timers=escalation)
                        ▼
                 Human Gate (when required)
                        ▼
        Canonical Store (Postgres) ── unified search, cross-company, read cache, write-intent queue
                        ▼
                 Event Bus (NATS JetStream) ── every change is a durable event
                        ▼
        Transport Adapter Layer  ◄── PLUGGABLE, per accounting system
        ├─ QuickBooks Desktop (Rightworks): cloud QBWC SOAP endpoint ⇄ qbXML ⇄ .qwc
        ├─ QuickBooks Online / Xero: REST + official MCP servers
        └─ NetSuite / Sage Intacct / Dynamics: REST adapters (future)
                        ▼
                 Accounting System(s)
```

This matches the desired end-state diagram exactly, and the canonical Postgres store **replaces Google Sheets as the operational database** — solving unified search, cross-company visibility, and month-end close in one move.

---

## 2. FOSS leverage shortlist (only OSI-approved; nothing paid)

| Layer | Pick | License | Why | Verdict |
|---|---|---|---|---|
| QBWC SOAP server | **consolibyte/quickbooks-php** (PHP) or **qbwc/qbwc** (Ruby) | EPL-1.0 / MIT | Only QBWC servers with real 2026 activity | BUILD ON (clear EPL copyleft w/ legal) |
| qbXML build/parse | **QbSync.QbXml** (.NET) or **selfjared1/quickbooks_desktop** (Py) | MIT | Typed qbXML; schema rarely changes | FORK + pin |
| Event bus | **NATS + JetStream** | Apache-2.0 | Single ~20MB Go binary, per-entity isolation via accounts/leaf-nodes, durable at-least-once | BUILD ON |
| Approval/orchestration | **Temporal** (code) or **Flowable** (visual BPMN) | MIT / Apache-2.0 | Durable approval gates + escalation timers | BUILD ON |
| Invoice extraction | **invoice2data** + **PaddleOCR/docTR** fallback | MIT / Apache-2.0 | Template-first, ML for unseen vendors | BUILD ON |
| Canonical store | **Postgres** (Supabase available in this env) | OSI | Operational DB + search | BUILD ON |
| MCP layer | **intuit/quickbooks-online-mcp-server** as *pattern only* | Apache-2.0 | **No FOSS Desktop MCP exists — we write it** | REFERENCE |

**License traps to avoid (flagged NOT FREE / NOT OSI):** QODBC (proprietary), Camunda 8/Zeebe (source-available, paid self-host), n8n (fair-code, no resale), Windmill EE/AGPL viral, Redis core (SSPL → use **Valkey**), Surya/Marker/LayoutLMv3/Donut (weight or NC license traps), `quickbooks-js` (archived). **Genuine green field:** there is no production FOSS MCP server for QuickBooks Desktop — budget to build the LLM-facing layer ourselves.

---

## 3. Options A–E

### Option A — Best overall: Canonical-Store + Proof-Gated Platform, QBWC adapter
Postgres canonical store as the operational brain; NATS event bus; Temporal approvals; AIVS/VCAP/ADRP proof gates native; self-built MCP layer; QBWC outbound adapter on Rightworks. **Why best:** respects the Rightworks constraint, decouples transport from platform (future QBO/NetSuite = new adapter, not new system), makes proof a native rail not an add-on, scales across company files via per-entity NATS accounts, and concentrates durable value in the vendor-agnostic layer — the actual product.

### Option B — Lowest dev effort
QBWC (consolibyte/qbwc) → Postgres mirror → simple approval table + LLM coding suggestions. No NATS/Temporal/MCP initially; cron poll + DB queue. Gets to "AI reads/writes QB + cross-company search" fastest. **Trade-off:** ceiling is low; you'll rebuild as A when scale/proof requirements bite.

### Option C — Highest scalability
Option A plus: one logical QBWC adapter per company file, NATS accounts/leaf-nodes per entity, stateless cloud workers, canonical store partitioned by entity, Temporal namespaces per entity. Scales 10→1000 companies. **Bottleneck:** QBWC poll is serial per company file and QB Desktop opens one file at a time — mitigate with multiple `.qwc` endpoints + parallel workers; at extreme scale, steer entities toward QBO/API tiers where the adapter becomes a REST connector.

### Option D — Most innovative: QuickBooks-as-MCP + event-sourced ledger
Expose every accounting entity & command as an MCP server; event-source the canonical ledger (immutable event log = AuditProof-native, fully replayable); AI agents are first-class MCP clients with ATEP-style capability tokens gating autonomous actions; writes are intents reconciled against QB. **Highest novelty, highest risk** (event-sourcing + two-phase QB reconciliation is hard).

### Option E — Dominant in 5–10 years: Vendor-agnostic verified accounting fabric
Transport adapters (QBWC, QBO, NetSuite, Xero) become commodities; the moat is the canonical model + the proof/verification layer. This is literally **"the verification layer for accounting AI."** Dominant because autonomous AI accounting + regulators will *require* independent verification and tamper-evident audit trails — whoever owns that rail wins. **E is A matured and fully decoupled.** Build A deliberately as step one toward E.

---

## 4. Comparison matrix (1–5, 5 = best)

| Criterion | A | B | C | D | E |
|---|---|---|---|---|---|
| Reliability | 5 | 4 | 5 | 3 | 5 |
| Security | 5 | 3 | 5 | 4 | 5 |
| Performance | 4 | 3 | 5 | 3 | 4 |
| Scalability | 4 | 2 | 5 | 4 | 5 |
| Ease of deployment | 3 | 5 | 2 | 2 | 2 |
| Maintenance | 4 | 3 | 4 | 2 | 4 |
| Dev complexity (5=simplest) | 3 | 5 | 2 | 1 | 2 |
| AI-friendliness | 5 | 2 | 5 | 5 | 5 |
| Approval-workflow support | 5 | 2 | 5 | 4 | 5 |
| Auditability | 5 | 2 | 5 | 5 | 5 |
| Rightworks compatibility | 5 | 5 | 4 | 3 | 5 |
| QB Enterprise compatibility | 5 | 5 | 4 | 4 | 5 |
| Supportability | 4 | 4 | 4 | 2 | 4 |
| Long-term viability | 5 | 2 | 5 | 4 | 5 |
| Vendor lock-in (5=least) | 5 | 4 | 5 | 5 | 5 |
| Disaster recovery | 4 | 3 | 5 | 3 | 5 |
| Cost (5=cheapest) | 4 | 5 | 3 | 3 | 3 |
| Licensing cleanliness | 4 | 4 | 4 | 4 | 4 |
| Future-proofing | 5 | 2 | 5 | 5 | 5 |
| **Total /95** | **83** | **64** | **81** | **62** | **83** |

A and E tie — because they are the same architecture at different maturity. **Build A now as the concrete first instantiation of E.**

---

## 5. Risks (technical)

1. **Rightworks background-kill** — unattended sync needs a support ticket for auto-start; no self-service. Hard dependency on Rightworks cooperation.
2. **QB Desktop single-file-open limit** — one company file per QB session. 10+ entities require sequential file-switching or multiple sessions; this caps adapter throughput.
3. **QBWC serial polling latency** — pull model, scheduled batches; not real-time. Writes are eventually-consistent.
4. **Two-phase write reconciliation** — an approved write can still fail at the qbXML/QB layer after the human gate; need idempotent intents + reconciliation + rollback semantics.
5. **qbXML library staleness** — ecosystem frozen ~2023; budget to fork-and-maintain the QB-side glue.
6. **No FOSS Desktop MCP** — the LLM-facing layer is green-field, built in-house.
7. **Copyleft traps** — EPL-1.0 (consolibyte) and MPL-2.0 (django-qb) are file-level copyleft; clear with legal before embedding in a commercial product.
8. **Proof-product API mismatch** — InvoiceProof/AuditProof/VerifyAPI HTTP surfaces are unconfirmed; we know the primitive shapes, not the exact endpoints.
9. **Duplicate/fraud detection accuracy** — InvoiceProof's value depends on precision/recall of duplicate + bank-change + PO-mismatch detection; false positives erode trust, false negatives let fraud through.
10. **Canonical store vs QB source-of-truth divergence** — QB remains system of record; the canonical store is a cache + intent queue and must reconcile, never silently overwrite.

---

## 6. Unknowns requiring validation

- Will Rightworks configure auto-start QBWC for **multiple** concurrent company files? (Ticket required.)
- Exact transaction volume/month per entity (sizes the poll cadence + worker fleet).
- Live API surface + auth for InvoiceProof / AuditProof / VerifyAPI (contact SwarmSync).
- Legal sign-off on EPL-1.0 / MPL-2.0 for a commercial product.
- Any plan to migrate entities QB Desktop → QBO (would swap the hardest adapter for a REST one).
- Whether Supabase Postgres (available here) is acceptable as the canonical store host, or self-hosted Postgres is required for data residency.

---

## 7. Recommended 90-day MVP

**Phase 1 (wks 1–3) — Prove the pipe (read-only, one entity).** Cloud-hosted QBWC SOAP endpoint (consolibyte or qbwc) + `.qwc` on one company file; Rightworks ticket for auto-start. Sync lists + transactions into Postgres. Unified search over that one file.

**Phase 2 (wks 4–7) — Cross-company + AuditProof.** Add 2–3 more company files; canonical model + cross-company search/reporting; wrap every sync and every AI suggestion as an AIVS hash-chained audit row (AuditProof). Live read cache.

**Phase 3 (wks 8–12) — First gated write, full proof chain.** One narrow high-value workflow: AI-proposed AP bill coding → InvoiceProof verification (duplicate / PO / math) → Temporal approval workflow → human gate → qbXML write-back via QBWC → reconcile. End-to-end with the complete proof chain on a single workflow before generalizing.

---

## 8. Final recommendation

Build **Option A as the deliberate first step toward Option E.** Transport is **QBWC outbound** — not because it's conventional, but because Rightworks forces it; treat it as a thin, swappable adapter and never let it shape the platform. The moat — and the commercial product, *"The AI Operating Layer / verification rail for legacy accounting"* — lives entirely in the vendor-agnostic canonical store + the SwarmSync proof/verification layer above the adapter. That is the one design that is simultaneously buildable on Rightworks today and the thing that wins in 5–10 years.
