\---

name: Ben-first payment ops

overview: Rebuild STV payment notification/tracking so Ben is the default payer, Aubrey is fallback-only, Mike gets a minimal approval email, and every obligation permanently stores “Can Ben pay?” plus method/access fields—starting from the live Payment Calendar sheet and draft templates, then wiring automation.

todos:

&#x20; - id: sheet-schema

&#x20;   content: Extend Payment Calendar + Method Registry with Ben-can-pay and method/access fields

&#x20;   status: pending

&#x20; - id: seed-methods

&#x20;   content: "First-cycle method review: clear Unknown for all current obligations"

&#x20;   status: pending

&#x20; - id: email-templates

&#x20;   content: Rewrite Mike short approval, Ben pay-task, Aubrey fallback-only drafts

&#x20;   status: pending

&#x20; - id: policy-docs

&#x20;   content: Update CLAUDE.md / AccountingOS docs from Aubrey-always to Ben-first

&#x20;   status: pending

&#x20; - id: pilot-mike

&#x20;   content: Pilot one live Mike approval using the short template

&#x20;   status: pending

&#x20; - id: routing-rules

&#x20;   content: Wire approve→Ben task; method-unavailable→Aubrey in ProofRail/GAS

&#x20;   status: pending

&#x20; - id: truth-audit

&#x20;   content: Verify no auto-send and Aubrey only when Aubrey required=Yes

&#x20;   status: pending

isProject: false

\---



\# Ben-first payment notification and tracking



\## Judgment kernel (pre-action)





| Question        | Answer                                                                                                                                                                                                                    |

| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| Actual problem  | Old ops model hardcodes “Aubrey always pays.” You need Ben-first execution with Aubrey only when access/authority/channel require her—and a tracker that never rediscovers that each month.                               |

| Done looks like | Tracker fields filled; Mike gets short approve emails; after approve, Ben gets a pay-task (not Aubrey); Aubrey only on “method not available” / `Aubrey required=Yes`; first cycle clears `Unknown` → Yes/No permanently. |

| Blast radius    | High for policy (who can move money). Low for Phase 1 sheet+drafts. Irreversible = auto-send / auto-pay (forbidden).                                                                                                      |

| Assumptions     | (1) Ben can or will get entity UCCU access for ACH/bill-pay where legal. (2) Mike still approves sensitive/non-autopay items. (3) Existing sheet is the near-term system of record.                                       |

| Cheapest probe  | Extend \[Payment Calendar](https://docs.google.com/spreadsheets/d/1oRD0CFHBGeTtZhkQC9Pfo\_NLAp3AUqyZ486jPvwQX\_o/edit) + rewrite draft templates before touching GAS/ProofRail state machine.                                |





\*\*Policy conflict to resolve explicitly with Mike (one sentence in kickoff):\*\* Current Gmail AccountingOS docs say “Aubrey executes all payments / never Ben.” This project \*\*replaces\*\* that with Ben-first. Do not ship automation that still always routes to Aubrey.



\*\*Default until Mike sets a dollar threshold:\*\* Mike approval required for every non-autopay cash payment (ACH/bill-pay/wire/check/portal). Autopay verify-only items skip Mike. Replace with a numeric threshold once Mike confirms one number.



\---



\## Target workflow



```mermaid

flowchart TD

&#x20; idPay\[Payment identified]

&#x20; idVerify\[Ben verifies amount due entity support]

&#x20; idMethods\[Ben checks payment methods in order]

&#x20; idCan{Ben can pay directly?}

&#x20; idMike{Mike approval required?}

&#x20; idMikeMail\[Draft Mike short approval CC Porter]

&#x20; idBenTask\[Ben pay task email]

&#x20; idAubrey\[Aubrey pay instruction]

&#x20; idConfirm\[Save confirmation]

&#x20; idClear\[Clears bank]

&#x20; idRec\[Record and reconcile]

&#x20; idPay --> idVerify --> idMethods --> idCan

&#x20; idCan -->|Yes| idMike

&#x20; idCan -->|No| idMike

&#x20; idMike -->|Yes| idMikeMail

&#x20; idMike -->|No autopay only| idBenTask

&#x20; idMikeMail -->|Approved| idCan2{Ben can pay?}

&#x20; idCan2 -->|Yes| idBenTask

&#x20; idCan2 -->|No| idAubrey

&#x20; idBenTask -->|Paid| idConfirm

&#x20; idBenTask -->|Method not available| idAubrey

&#x20; idAubrey --> idConfirm --> idClear --> idRec

```







\*\*Method check order (permanent per obligation):\*\* Direct ACH → bank bill-pay → vendor/lender portal → existing autopay → credit card (fees OK) → Ben-initiated wire → online check → manual check → Aubrey only if credentials/authority unavoidable.



\---



\## Phase 1 — Tracker + email templates (this week, manual drafts)



\*\*System of record:\*\* extend existing sheet  

`https://docs.google.com/spreadsheets/d/1oRD0CFHBGeTtZhkQC9Pfo\_NLAp3AUqyZ486jPvwQX\_o/edit`  

Tabs: keep `Payment Calendar` + `README`; add `Method Registry` (one row per recurring obligation) and `Approval Log`.



\### New / renamed fields on Payment Calendar (or Method Registry joined by Entity+Obligation)





| Field                          | Values / notes                                               |

| ------------------------------ | ------------------------------------------------------------ |

| Primary operator               | Ben (constant)                                               |

| Fallback operator              | Aubrey                                                       |

| Ben can pay directly           | Yes / No / Unknown — \*\*Unknown forbidden after first cycle\*\* |

| Available methods              | multi: ACH, bill pay, wire, check, portal, autopay           |

| Preferred method               | e.g. UCCU bill pay                                           |

| Backup method                  | e.g. lender portal ACH                                       |

| Login/access owner             | Ben / Aubrey / Shared                                        |

| Authorized signer required     | Mike / Aubrey / None                                         |

| Bank access available          | Yes / No                                                     |

| Vendor portal available        | Yes / No                                                     |

| Autopay available              | Yes / No                                                     |

| Payment instructions verified  | Yes / No                                                     |

| Aubrey required                | Yes / No (formula or rule from above)                        |

| Why Aubrey is required         | free text; empty if No                                       |

| Last method review             | date                                                         |

| Approval status                | Needed / Requested / Approved / N-A                          |

| Pay status                     | Pending / Scheduled / Paid / Failed                          |

| Mike approval link / thread id |                                                              |

| Evidence link                  | Drive folder / bank search tip                               |





Deprecate or replace ambiguous columns `Who Pays` / `What YOU (Ben) Do` with the operator + method fields above so the sheet stops implying Aubrey-by-default.



\### Email templates (Gmail drafts only — never auto-send)



1\. \*\*Mike (CC Porter only; never Adam)\*\* — short form only:



```

Subject: Approval Needed — {Entity} — ${Amount} — Due {DueDate}



Mike,



Please approve this payment:



{Entity}

{Payee}

${Amount}

Due {DueDate}



Documents: {link}



Approve: reply "Approved" (or Approve link when built)



Thanks,

Ben

```



No rejection UI, no method debate, no accounting essay unless flagged Unusual.



1\. \*\*After Mike approves — Ben pay task\*\* (stays with Ben if `Ben can pay=Yes`):



```

Subject: APPROVED — {Entity} — ${Amount} — Pay by {PayByDate}

… Preferred method, funding account, docs, approval link

Actions: MARK SCHEDULED | MARK PAID | PAYMENT METHOD NOT AVAILABLE

```



`PAYMENT METHOD NOT AVAILABLE` → immediately create Aubrey draft (same payment, approved).



1\. \*\*Aubrey — only when required\*\* — action-only body (payee, amount, due, docs, approval). Ask confirm when scheduled.



Update Stage-2 draft templates that currently say “route to Aubrey for payment execution” (`\[Summa Terra Gmail Automation/Stage 2 - Live Gmail Automation/src/drafts/templates.py](Summa Terra Gmail Automation/Stage 2 - Live Gmail Automation/src/drafts/templates.py)`) to Ben-first / Aubrey-fallback.



\### First-cycle method review (manual, closes Unknown)



For each July–August obligation on the calendar, fill the method fields once. Priority: HLN Arixa, Union Granite, Selective/Travelers autopays, Freeman, Vic NRG, Quincy FSB. After review, `Ben can pay directly` must be Yes or No.



\---



\## Phase 2 — Light automation (ProofRail / Gmail)



Align with existing consolidation: ProofRail absorbs AccountingOS; drafts-only; no auto-pay.



\- Detect Mike reply containing approval → set Approval status=Approved → create \*\*Ben\*\* pay-task draft (not Aubrey) when `Ben can pay=Yes`.

\- Labels: keep Mike approval labels; change “Needs Aubrey Payment Execution” to fire only when `Aubrey required=Yes` or Ben marks method unavailable.

\- Daily digest: past due (red) + due this week (yellow) from sheet colors/dates.

\- Standing rules already in MEMORY: CC Porter with Mike; never CC Adam; drafts only.



Do \*\*not\*\* implement clickable Approve buttons / Stripe-style links in Phase 1—reply “Approved” is enough. Phase 2 can add a simple Apps Script web app approve link if desired later.



\---



\## Phase 3 — Policy + access checklist (human, blocks “Ben pays” claims)



Before marking any row `Ben can pay=Yes` for wires or large ACH:



\- Confirm Ben has UCCU access to that entity account (or portal credentials).

\- Confirm whether Aubrey remains sole bank signer for wires that require dual control.

\- Get Mike’s written approval-threshold number (replace interim “all non-autopay” rule).

\- Update `\[Summa Terra Gmail Automation/CLAUDE.md](Summa Terra Gmail Automation/CLAUDE.md)` and Architecture docs that still say “never Ben / Aubrey executes all payments.”



\---



\## O2O assignment graph (execution after plan approval)



```mermaid

flowchart TD

&#x20; t1\[task-001 Sheet schema] --> t2\[task-002 Seed method review]

&#x20; t1 --> t3\[task-003 Rewrite email templates]

&#x20; t3 --> t4\[task-004 Update CLAUDE policy docs]

&#x20; t2 --> t5\[task-005 Pilot one live Mike draft]

&#x20; t4 --> t6\[task-006 ProofRail draft routing rules]

&#x20; t5 --> t6

&#x20; t6 --> t7\[task-007 Truth audit]

```









| Task                        | Agent / skill                  | Deliverable                                   |

| --------------------------- | ------------------------------ | --------------------------------------------- |

| task-001 Sheet schema       | google-sheets / generalPurpose | New columns + Method Registry + README legend |

| task-002 Seed method review | Ben + assistant                | Fill Yes/No for current month obligations     |

| task-003 Email templates    | Gmail Automation               | Mike / Ben-task / Aubrey-fallback drafts      |

| task-004 Policy docs        | docs                           | Flip Aubrey-always → Ben-first                |

| task-005 Pilot              | Ben                            | One real Mike approval using short template   |

| task-006 Routing rules      | ProofRail / GAS                | Approve → Ben task; fallback → Aubrey         |

| task-007 Truth audit        | truth-audit                    | No auto-send; Aubrey only when required       |





\*\*Pipeline confidence (uncalibrated):\*\* P(success)≈0.75 | P(self-recovery)≈0.6 | P(escalation)≈0.35 — mainly blocked on Mike threshold + Ben bank access confirmation.





7 To-dos

* Extend Payment Calendar + Method Registry with Ben-can-pay

and method/access fields

* First-cycle method review: clear Unknown for all current

obligations

* Rewrite Mike short approval, Ben pay-task, Aubrey fallback-only drafts



* Update CLAUDE.md / AccountingOS docs from Aubrey-always to

Ben-first



* Pilot one live Mike approval using the short template
* Wire approve-Ben task; method-unavailable-Aubrey in

ProofRail/GAS

* Verify no auto-send and Aubrey only when Aubrey required=Yes

\---



\## Explicit non-goals



\- Auto-sending email or auto-executing ACH/wires

\- Building full Bill.com / bank API pay rails in v1

\- Changing who is legal authorized signer without Mike/Aubrey

\- Keeping “send every approved payment to Aubrey” as default





