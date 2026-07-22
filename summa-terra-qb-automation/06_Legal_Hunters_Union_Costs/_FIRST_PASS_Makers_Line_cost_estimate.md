# FIRST PASS — "What we paid Makers Line" & "Extra cost from Makers Line's bad materials"

**Prepared:** 2026-06-25 · **Status:** FIRST PASS / management estimate — NOT audited, NOT from QuickBooks.

> ⚠️ **SOURCE & RELIABILITY — READ FIRST.**
> These figures are built from STV's **construction project documents** (pay applications, draw packages, budget-tracking spreadsheets, change-order logs, and a payment-tracking sheet). They are **NOT pulled from QuickBooks**, which is currently ~4 months behind. Makers Line figures are amounts **BILLED (requested on pay apps)**, which is **not the same as cash actually paid** — actual paid is reduced by retainage and by pay apps left unpaid when ML was terminated. The only figure here labeled as truly "paid" is the Rich Development total (from a sheet titled "how much we *paid* Rich Development"). **To get the authoritative "amount actually paid to Makers Line," pull the vendor payment history for "Makers Line" from QuickBooks (via QODBC) or from bank records.**

---

## 1. WHAT WE PAID MAKERS LINE (Hunters Landing) — billed, not confirmed paid

Sum of Makers Line pay applications (amount per signed pay-app PDF in `12SB ...\Maker's Line\`):

| ML Pay App | Amount (billed) |
|---|---:|
| #1 | $469,795.50 |
| #2 | $666,379.73 |
| #3 | $2,227,640.72 |
| #4 | $1,547,156.56 |
| #5 | $2,132,419.31 |
| #6 | $1,456,934.11 |
| #7 | $937,100.85 |
| #8 | $741,868.43 |
| #9 | $787,456.65 |
| #10 | $959,137.51 |
| #11 | $504,387.37 |
| #12 | $1,044,398.60 |
| #13 (final) | $152,247.48 |
| **Subtotal #1–#13** | **$13,626,922.82** |
| #14 (draft "R1" — may be unpaid) | $816,151.82 |
| **Total billed #1–#14** | **~$14,443,074.64** |

**Caveats (why actual paid is likely lower):**
- **Retainage** (typ. 5–10% withheld) → ~$0.7M–$1.4M likely held back.
- ML fired mid-stream → final pay app(s) may be partially/never paid (#13 final was reduced from ~$460K drafts to $152K; #14 is a draft).
- Periodic-vs-cumulative basis of the pay apps should be confirmed.
- ML's own change-order log nets **$(526,464.17)** against a $561,532 original budget (separate from the pay-app base).

**Union Walk:** **[GAP]** — no Makers Line contract or pay history in these documents. Must come from QB/the original contract.

---

## 2. EXTRA COST CAUSED BY MAKERS LINE'S BAD MATERIALS — first pass build-up

### Hunters Landing
| Component | Amount | Source |
|---|---:|---|
| Exterior rebuild "budget to fix" (ML's incorrect materials) — billed | ~$2,236,471 | `060624 Budget Tracking to Fix Hunter's Landing.xlsx` |
| (same, scheduled value) | (~$2,692,010) | same |
| "Out of scope / done under ML" items (insurance $105,417; electrical $78,072; plumbing redo $87,565; cracked tubs $34,646; etc.) | ~$704,137 | same |
| Less: insurance recovery | −~$105,417 | same / POP $49,944.09 |
| Plus: sub invoices STV had to cover after ML left | **[GAP — not totaled]** | `Invoices Received from Subs After ML\` |
| **Hunters Landing subtotal (rough)** | **~$2.8M–$2.9M** | |

### Union Walk (clearly ML-attributable change orders)
| Component | Amount | Source |
|---|---:|---|
| 25th St sewer line — "replace wrong-sized line installed by ML" | $104,291.12 | `Union Walk Budget Reconciliation wChange Orders` |
| Exterior doors/windows — "replace windows damaged during demolition" | $171,608.58 | same |
| Less: plumbing supply credit from ML | −$28,086.64 | same |
| (Excavation/undocumented fill — attribution unclear) | (+~$144,453) | same |
| **Union Walk subtotal** | **~$248K (up to ~$392K)** | |
| *Excluded:* missed footings/shear walls — flagged as **designer (AE Urbia)** error, not ML | — | |

### Combined first-pass ML-caused extra cost: **~$3.0M – $3.3M** (dominated by the Hunters Landing exterior rebuild)

---

## 3. HOW TO TURN THIS INTO CONFIRMED, ACTUAL-PAID NUMBERS

1. **Pull from QuickBooks (authoritative "paid"):** run a **Vendor QuickReport / Transaction List by Vendor** for **"Makers Line"** and **"Rich Development"** (and the post-ML subs) across all relevant entity files — via QODBC export. That gives checks actually cut (cash paid), not billed.
2. **Confirm retainage** held/released on the ML contract.
3. **Roll up** the `Invoices Received from Subs After ML\` folder to a single total.
4. **Reconcile** the two differing RD contract/CO totals in `HL Final Draw Analysis`.
5. **Get Union Walk's ML contract + pay history** (absent from these files).
6. Have the client/Zach confirm the single "additional cost caused specifically by ML" causation figure.

_Once the QuickBooks catch-up is current (or a QODBC vendor-payment export is run), this first pass can be replaced with confirmed cash-paid figures._
