# Standardized Cost-Code / Item List — Summa Terra Ventures (Deliverable 5)

Companion to `SPEC.md` §6.4 and §6.7 (Draw Package model). **This list mirrors the actual GC/lender draw
package** (see `Hunters Landing Draw #29.pdf`), so QuickBooks coding maps 1:1 to the document the
construction manager and Mike Watson already approve. The numbered cost codes (`001`–`069`) **are the
QuickBooks Items.** They ship **inside the locked template**, identical in every file.

### The five dimensions (one job each — never overload)
| Dimension | Carries | Example (Draw #29) |
|-----------|---------|--------------------|
| **Vendor (payee)** | *Who* gets paid | `Bronco Fence Company`, `Meraki Steel`, `Rich Development Inc` |
| **Item (cost code)** | *What* was bought — the numbered draw line | `005 Fencing`, `012 Steel`, `068 Construction Profit` |
| **Account (CIP bucket)** | *Which broad GL asset* the cost capitalizes to | `15300 CIP — Hard Costs` |
| **Class (phase)** | *Which development phase* | `10 Site/Excavation` |
| **Customer:Job (project)** | *Which project/property* | `Hunter's Landing` |
| **Draw # (custom field)** | *Which approved draw package* ties it together | `D-2025-29` |

> **Design intent:** the **Chart of Accounts stays clean and broad** — every Item rolls into just **one of
> four CIP buckets**. All cost granularity lives here in the Item, not in the COA. Vendors stay vendors,
> Customer:Job stays the project, Class stays the phase, and the **Draw #** field stitches a whole package
> back to the one approved document.

---

## 1. The four CIP buckets (every construction Item maps to exactly one)

| CIP account (from `Chart_of_Accounts.md`) | What lands here |
|-------------------------------------------|-----------------|
| **15300 CIP — Hard Costs** | Physical construction: concrete, steel, framing, MEP, finishes, exteriors, amenities. |
| **15200 CIP — Soft Costs** | Supervision, general conditions, inspections, temporary facilities, site services, GC profit, contingency. |
| **15400 CIP — Financing Costs** | Loan interest, loan fees, carry — typically *not* on a GC draw (own workflow). |
| **15500 CIP — Developer Fee Capitalized** | The **5% developer fee** owed to Summa Terra (if the CPA confirms capitalization; else expense to `60100`). |

Two-sided Items are not needed for the draw lines — these are **one-sided cost Items** (expense/CIP side only),
because the *billing* side of a construction draw is the loan draw, not a customer invoice. (The fee Items in
§4 are the exception.)

---

## 2. Master Item list — the draw schedule (cost codes 001–069)

Numbered exactly as the GC continuation sheet / budget reallocation. **Class default** follows the draw's own
phase grouping. Set the Item's **Maps-to** account once in the template; it then auto-codes every bill.

| Code · Item | CIP bucket (Maps to) | Class default |
|-------------|----------------------|---------------|
| **— Site / Excavation —** | | **10 Site/Excavation** |
| 001 Survey | 15200 Soft | 10 Site/Excavation |
| 002 Excavation | 15300 Hard | 10 Site/Excavation |
| 003 Concrete (Site Concrete) | 15300 Hard | 10 Site/Excavation |
| 004 UDOT Concrete (12th) | 15300 Hard | 10 Site/Excavation |
| 005 Fencing | 15300 Hard | 10 Site/Excavation |
| **— Structure / Frame / Roof —** | | **20 Structure/Frame/Roof** |
| 007 Turnkey Frame / Garage | 15300 Hard | 20 Structure/Frame/Roof |
| 008 Garage Roof | 15300 Hard | 20 Structure/Frame/Roof |
| 009 Roofing (L&M) | 15300 Hard | 20 Structure/Frame/Roof |
| 010 Deck Coatings / Decking | 15300 Hard | 20 Structure/Frame/Roof |
| 011 Structural Steel — Parking | 15300 Hard | 20 Structure/Frame/Roof |
| 012 Steel — All Other Features | 15300 Hard | 20 Structure/Frame/Roof |
| 013 Garage Door (Trash) | 15300 Hard | 20 Structure/Frame/Roof |
| 014 Store Front (Labor) | 15300 Hard | 20 Structure/Frame/Roof |
| 015 Elevator | 15300 Hard | 20 Structure/Frame/Roof |
| 016 HM Door (Labor / Material) | 15300 Hard | 20 Structure/Frame/Roof |
| **— MEP Trades —** | | **30 MEP Trades** |
| 017 Plumbing | 15300 Hard | 30 MEP Trades |
| 018 HVAC | 15300 Hard | 30 MEP Trades |
| 019 Electrical | 15300 Hard | 30 MEP Trades |
| 020 EV Charging Stations | 15300 Hard | 30 MEP Trades |
| 021 Sprinkler / Fire System | 15300 Hard | 30 MEP Trades |
| 022 Fire Caulk | 15300 Hard | 30 MEP Trades |
| **— Finishes —** | | **40 Finishes** |
| 023 Gypcrete | 15300 Hard | 40 Finishes |
| 024 Insulation | 15300 Hard | 40 Finishes |
| 025 Sheetrock / Drywall | 15300 Hard | 40 Finishes |
| 026 Finish Materials (BFS) | 15300 Hard | 40 Finishes |
| 027 Finish Labor / Trim | 15300 Hard | 40 Finishes |
| 028 Interior Paint | 15300 Hard | 40 Finishes |
| 030 Garage Doors | 15300 Hard | 40 Finishes |
| 031 Floor Prep | 15300 Hard | 40 Finishes |
| 032 Hardware & Install Labor | 15300 Hard | 40 Finishes |
| 033 Fire Extinguishers / Supplies | 15300 Hard | 40 Finishes |
| 034 Mirrors / Shower | 15300 Hard | 40 Finishes |
| 035 Flooring / Wall Tile (M&L) | 15300 Hard | 40 Finishes |
| **— Exteriors & Amenities —** | | **50 Exteriors & Amenities** |
| 036 Brick | 15300 Hard | 50 Exteriors & Amenities |
| 037 Stucco / EFIS / Soffit / Fascia | 15300 Hard | 50 Exteriors & Amenities |
| 040 Roof Hatch | 15300 Hard | 50 Exteriors & Amenities |
| 041 Trash Chute | 15300 Hard | 50 Exteriors & Amenities |
| 042 Pool | 15300 Hard | 50 Exteriors & Amenities |
| 043 Knox Box & Fire Lids | 15300 Hard | 50 Exteriors & Amenities |
| 046 Signage | 15300 Hard | 50 Exteriors & Amenities |
| 047 Amenities | 15300 Hard | 50 Exteriors & Amenities |
| 048 Garden Shed & Pad | 15300 Hard | 50 Exteriors & Amenities |
| 049 Blinds | 15300 Hard | 50 Exteriors & Amenities |
| 069 Exterior Wall Project | 15300 Hard | 50 Exteriors & Amenities |
| **— General Conditions / Supervision / Allowances —** | | **60 General Conditions** |
| 050 Contingency | 15200 Soft | 60 General Conditions |
| 052 Honey Bucket / Porta Potty | 15200 Soft | 60 General Conditions |
| 053 Dumpster / Garbage Haul | 15200 Soft | 60 General Conditions |
| 056 Final Clean / Cleaning | 15200 Soft | 60 General Conditions |
| 057 Street Sweeping | 15200 Soft | 60 General Conditions |
| 058 Concrete Wash Out | 15200 Soft | 60 General Conditions |
| 059 SWPPP | 15200 Soft | 60 General Conditions |
| 060 Temp Power | 15200 Soft | 60 General Conditions |
| 061 Office Trailer / Office Hours | 15200 Soft | 60 General Conditions |
| 062 Security Cameras | 15200 Soft | 60 General Conditions |
| 063 Special Inspections / Testing | 15200 Soft | 60 General Conditions |
| 065 General Conditions / Permits | 15200 Soft | 60 General Conditions |
| 067 Site Supervision | 15200 Soft | 60 General Conditions |
| 068 Construction Profit (GC) | 15200 Soft | 60 General Conditions |

> **Add codes as the schedule grows.** New draw lines = new numbered Items mapped to one of the four CIP
> buckets. Never create a new GL account for a new cost code — the bucket already exists.
>
> **⚠ `068 Construction Profit` is the GC's (Rich Development's) builder profit inside the draw — NOT the 5%
> developer fee to Summa Terra.** The developer fee is a *separate* parent management fee computed **on top of**
> the whole draw total (§4). Keep them distinct: 068 is a project cost line; the 5% is an intercompany fee.

### Non-draw lifecycle Items (costs that never appear on a GC draw)
| Code · Item | CIP bucket | Class default |
|-------------|-----------|---------------|
| 100 Land Acquisition | 15100 CIP — Land | 00 Acquisition |
| 101 Due Diligence / Closing (acq.) | 15100 CIP — Land | 00 Acquisition |
| 110 Entitlements / Architecture / Engineering | 15200 Soft | 00 Acquisition |
| 120 Loan Fees | 15400 Financing | 70 Financing |
| 121 Construction Interest | 15400 Financing | 70 Financing |
| 122 Carry / Property Taxes (project) | 15400 Financing | 70 Financing |
| 200 Marketing (disposition) | 70700 Marketing | 80 Disposition |
| 201 Sales Commission / Closing (sale) | 50200 Closing/Comm. | 80 Disposition |

---

## 3. Retainage on draw lines

The draw package carries a **Retainage (–)** column and an **Amount Due** column (e.g., Lara & Sons: invoice
`$37,720.00`, retainage `–$62,155.30` released, amount due `$99,875.30`). Model retainage **on the same bill**,
not as a separate Item:

- **Holding retainage** (lender withholds from a vendor): add a second bill line — Item `RETAINAGE-HELD`
  (negative) → `20200 GC Retainage Payable`. Bill net = the **Amount Due**.
- **Releasing retainage** (a later draw pays it back): positive line to `20200 GC Retainage Payable`, clearing
  the holdback. The vendor's gross stays in its cost-code Item; only the retainage timing moves.

This keeps each vendor's **cost-code total** intact for budget-vs-actual while the **Amount Due** matches the
check the lender cuts.

---

## 4. FEE & COMMISSION items — corrected split (see SPEC §5.3 / §12.4)

> **The fee base is the Draw Package total** (Draw #29 = **$962,845.68**). All three percentages compute off
> that one number. **But the partnership and the parent book different things** — this is the corrected
> structure:

### 4a. Partnership file — books ONLY the 5% developer fee
| Item | Type | Dr → | Cr → | Notes |
|------|------|------|------|-------|
| **FEE-DEV (5%)** | Service | `15500 CIP — Developer Fee Capitalized` (or `60100` if expensed) | `21000 Due-To Summa Terra` | The partnership records the developer fee **as a project cost**, capitalized to CIP if the CPA confirms capitalization policy; otherwise expensed. **The partnership records NO commissions.** |

Entered as a **bill from vendor `IC — Summa Terra Ventures`**, one line, Item `FEE-DEV`, percentage of the
approved Draw Package total, stamped with the same **Draw #**.

### 4b. Parent file (Summa Terra Ventures) — books the income, the receivable, AND the commissions
| Item / entry | Dr → | Cr → | Notes |
|--------------|------|------|-------|
| **FEE-DEV-INC (5%)** | `12200 Developer Fee Receivable / Due-From <Partnership>` | `40200 Developer Fee Income` | Summa Terra recognizes the 5% as income and a receivable from the partnership. |
| **FEE-CEO (2%)** | `60200 CEO Commission Expense` | `21100 Commission Payable — Mike Watson` | Parent-side only. Summa Terra owes Mike **after it earns the developer fee.** |
| **FEE-PRES (1%)** | `60300 President Commission Expense` | `21200 Commission Payable — Porter Christensen` | Parent-side only. Summa Terra owes Porter. |

The 2%/1% are **the parent's own compensation expense**, paid by Summa Terra out of the fee it earns. They
**never touch a partnership file**, never hit project CIP, and never appear on the lender draw.

> **Net economics:** the partnership bears a 5% project cost; Summa Terra nets 5% − 2% − 1% = **2%** after
> paying Mike and Porter. One draw → one 5% intercompany fee → two parent-side commission accruals.

### How the percentages are entered
Each FEE item is configured as a **percentage Service Item**. Enter the approved Draw Package total **once** on
each side's memorized transaction; QuickBooks computes 5% / 2% / 1% automatically. Because the partnership doc
has a single 5% line and the parent doc carries income + both commissions, **no draw can be booked without its
fee, and no commission can be booked on a partnership by mistake.**

---

## 5. Mapping rules (which dimension carries what)
| Question | Answer |
|----------|--------|
| Who is paid? | **Vendor (payee)** |
| What was bought? | **Item** — the numbered draw cost code (this list) |
| Which broad GL asset? | **Account** — one of four CIP buckets (`Chart_of_Accounts.md`) |
| Which phase? | **Class** (`SPEC.md` §6.3) |
| Which project/property? | **Customer:Job** (`SPEC.md` §6.2) |
| Which approved draw package? | **Draw # custom field** — the tie that binds the package |
| Developer fee owed to Summa Terra? | **5% of Draw Package total** → partnership `FEE-DEV` only (§4a) |
| Executive commissions? | **Parent file only** (§4b) — never on a partnership |

> **Trigger reminder (SPEC §5.3):** fees are generated **only after the construction manager and Mike Watson
> approve the draw** and it is released to accounting — *not* on the GC's first submission.
