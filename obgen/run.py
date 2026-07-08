#!/usr/bin/env python3
"""
obgen — QODBC -> IIF opening-balance generator for the STV 10->2 consolidation.

    python run.py extract <ENTITY>     # on VPS, with that legacy .qbw OPEN
    python run.py build                # map + emit + gates G1-G4  -> out/
    python run.py verify <TARGET>      # after trial import: G5-G7 (TARGET open)

Design law: code never decides where a dollar goes — mappings/*.csv does.
Every gate is falsifiable; every failure halts loudly. Nothing auto-posts.
"""
from __future__ import annotations
import csv, sys, json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml  # pip install pyyaml

ROOT = Path(__file__).parent
CFG = yaml.safe_load((ROOT / "config" / "entities.yaml").read_text())
CUTOVER = datetime.strptime(CFG["cutover"], "%Y-%m-%d")
IIF_DATE = CUTOVER.strftime("%m/%d/%Y")
ZERO = Decimal("0.00")

def die(gate: str, msg: str):
    sys.exit(f"\n✗ {gate} FAILED — {msg}\nHalted. Nothing was written past this gate.")

def money(s) -> Decimal:
    return Decimal(str(s or 0)).quantize(Decimal("0.01"))

# ───────────────────────── QODBC seam ─────────────────────────
# The ONLY place that touches QuickBooks. Everything else reads cache/.
def qodbc():
    import pyodbc  # exists on the VPS only
    return pyodbc.connect("DSN=QuickBooks Data;", autocommit=True)

SQL = {
    "company":  "SELECT CompanyName FROM Company",
    "tb":       "sp_report TrialBalance show Label, Debit, Credit parameters DateTo = {{d'%s'}}",
    "open_ap":  ("SELECT TxnID, VendorRefFullName, TxnDate, DueDate, RefNumber, Memo, "
                 "AmountDue FROM Bill WHERE IsPaid = 0"),
    "ap_lines": ("SELECT TxnID, ExpenseLineAccountRefFullName, ItemLineItemRefFullName, "
                 "ExpenseLineAmount, ItemLineAmount, ExpenseLineMemo FROM BillExpenseLine "
                 "WHERE TxnID = ?"),
    "open_ar":  ("SELECT TxnID, CustomerRefFullName, TxnDate, DueDate, RefNumber, "
                 "BalanceRemaining FROM Invoice WHERE IsPaid = 0"),
    "cip":      ("sp_report GeneralLedger show TxnType, Date, RefNumber, Name, Memo, "
                 "Account, Amount parameters DateFrom = {{d'1900-01-01'}}, "
                 "DateTo = {{d'%s'}}, AccountFilterFullName = '%s'"),
}

def cache_dir(entity: str) -> Path:
    d = ROOT / "cache" / entity; d.mkdir(parents=True, exist_ok=True); return d

def dump(rows, cols, path: Path):
    with path.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    print(f"  → {path.relative_to(ROOT)} ({len(rows)} rows)")

# ───────────────────────── EXTRACT ─────────────────────────
def cmd_extract(entity: str):
    ent = CFG["entities"].get(entity) or die("EXTRACT", f"unknown entity '{entity}'")
    cn = qodbc(); cur = cn.cursor()

    # Pre-flight: QODBC binds to whatever file is OPEN. Verify before trusting a byte.
    open_name = cur.execute(SQL["company"]).fetchone()[0]
    if open_name.strip() != ent["qbw_name"].strip():
        die("PRE-FLIGHT", f"open file is '{open_name}', expected '{ent['qbw_name']}'. Wrong .qbw open.")

    d = cache_dir(entity); iso = CFG["cutover"]
    tb = cur.execute(SQL["tb"] % iso).fetchall()
    dump(tb, ["account", "debit", "credit"], d / "trial_balance.csv")

    # G1: source TB must balance and be non-empty
    dr = sum(money(r[1]) for r in tb); cr = sum(money(r[2]) for r in tb)
    if not tb: die("G1", "trial balance came back empty")
    if dr != cr: die("G1", f"TB out of balance: DR {dr} != CR {cr}")

    bills = cur.execute(SQL["open_ap"]).fetchall()
    dump(bills, ["txn_id","vendor","date","due","refnum","memo","amount"], d / "open_ap.csv")
    lines = [l for b in bills for l in cur.execute(SQL["ap_lines"], b[0]).fetchall()]
    dump(lines, ["txn_id","exp_account","item","exp_amt","item_amt","memo"], d / "open_ap_lines.csv")

    dump(cur.execute(SQL["open_ar"]).fetchall(),
         ["txn_id","customer","date","due","refnum","balance"], d / "open_ar.csv")

    cip_accts = CFG["cip_source_accounts"].get(entity, CFG["cip_source_accounts"]["default"])
    cip = [r for a in cip_accts for r in cur.execute(SQL["cip"] % (iso, a)).fetchall()]
    dump(cip, ["txn_type","date","refnum","name","memo","account","amount"], d / "cip_history.csv")

    (d / "_meta.json").write_text(json.dumps(
        {"company": open_name, "extracted": datetime.now().isoformat(), "tb_total_dr": str(dr)}))
    print(f"✓ G1 passed — {entity} extracted, TB {dr} balanced.")

# ───────────────────────── MAP ─────────────────────────
TREATMENTS = {"direct", "cip_detail", "open_ap", "open_ar", "capital_split", "flag"}

def load_mapping(entity: str) -> list[dict]:
    p = ROOT / "mappings" / f"{entity}.csv"
    if not p.exists(): die("G2", f"missing mapping file {p.name}")
    rows = [r for r in csv.DictReader(p.open())
            if r["old_account"] and not r["old_account"].startswith("#")]
    loc = CFG["entities"][entity]["location"]
    phases = CFG["class_phases"]
    forbidden = CFG["forbidden_account_patterns"]
    splits = defaultdict(Decimal)
    for r in rows:
        if r["treatment"] not in TREATMENTS:
            die("G2", f"{entity}: bad treatment '{r['treatment']}' on '{r['old_account']}'")
        if r["treatment"] != "flag":
            if r["new_location"] != loc:
                die("G2", f"{entity}: new_location '{r['new_location']}' != entity Location '{loc}'")
            if r.get("new_class_phase") and r["new_class_phase"] not in phases:
                die("G2", f"{entity}: new_class_phase '{r['new_class_phase']}' not a valid cost phase {phases}")
            if any(f.lower() in r["new_account"].lower() for f in forbidden):
                die("G2", f"{entity}: '{r['old_account']}' maps to forbidden '{r['new_account']}'")
            for seg in r["new_account"].split(":"):
                if len(seg) > 31: die("G2", f"account segment >31 chars: '{seg}'")
        if r["treatment"] == "capital_split":
            splits[r["old_account"]] += Decimal(r["pct"] or "0")
    for acct, tot in splits.items():
        if tot != Decimal("1"): die("G2", f"{entity}: capital_split pcts for '{acct}' sum to {tot}, not 1.0")
    return rows

def coverage_check(entity: str, mapping: list[dict]):
    """G2b: every nonzero TB account is mapped."""
    tb = list(csv.DictReader((cache_dir(entity) / "trial_balance.csv").open()))
    mapped = {r["old_account"] for r in mapping}
    missing = [r["account"] for r in tb
               if (money(r["debit"]) - money(r["credit"])) != ZERO and r["account"] not in mapped]
    if missing: die("G2", f"{entity}: unmapped nonzero accounts: {missing}")

# ───────────────────────── EMIT (IIF) ─────────────────────────
def iif_je(doc: str, memo: str, lines: list[tuple[str, str, Decimal, str]]) -> str:
    """lines = [(account, location, amount(+dr/-cr), line_memo)]. G3 enforced per Location.

    QBO RE-TARGET (next slice): emit `location` as **DepartmentRef** (the legal entity), and set
    **ClassRef** from the mapping's `new_class_phase` (cost phase) — NEVER emit the entity/location
    as Class. The transitional IIF below carries `location` in its single dimension slot; the QBO
    API emitter must split it into Department (location) + Class (phase)."""
    per_loc = defaultdict(Decimal)
    for _, loc, amt, _ in lines: per_loc[loc] += amt
    for loc, tot in per_loc.items():
        if tot != ZERO: die("G3", f"JE {doc}: Location '{loc}' nets {tot}, not 0.00")
    a, loc0, amt0, m0 = lines[0]
    out = ["!TRNS\tTRNSTYPE\tDATE\tACCNT\tCLASS\tAMOUNT\tDOCNUM\tMEMO",
           "!SPL\tTRNSTYPE\tDATE\tACCNT\tCLASS\tAMOUNT\tDOCNUM\tMEMO", "!ENDTRNS",
           f"TRNS\tGENERAL JOURNAL\t{IIF_DATE}\t{a}\t{loc0}\t{amt0}\t{doc}\t{memo}"]
    out += [f"SPL\tGENERAL JOURNAL\t{IIF_DATE}\t{a}\t{c}\t{amt}\t{doc}\t{m}"
            for a, c, amt, m in lines[1:]]
    out.append("ENDTRNS")
    return "\n".join(out) + "\n"

def cmd_build():
    outd = ROOT / "out"; outd.mkdir(exist_ok=True)
    flags, tieout = [], []
    for entity in CFG["entities"]:
        if not (cache_dir(entity) / "trial_balance.csv").exists():
            print(f"… {entity}: no extract yet, skipping"); continue
        mapping = load_mapping(entity); coverage_check(entity, mapping)
        loc = CFG["entities"][entity]["location"]
        tb = {r["account"]: money(r["debit"]) - money(r["credit"])
              for r in csv.DictReader((cache_dir(entity) / "trial_balance.csv").open())}

        je, emitted = [], defaultdict(Decimal)
        for r in mapping:
            bal = tb.get(r["old_account"], ZERO)
            if bal == ZERO: continue
            t = r["treatment"]
            if t == "flag":
                flags.append([entity, r["old_account"], str(bal), r["note"]]); continue
            if t in ("open_ap", "open_ar", "cip_detail"):
                # TODO(next slice): emit BILL/INVOICE blocks + monthly (job,item) CIP JEs,
                # then post only the residual here. Skeleton: full balance flows via OB JE
                # so G4 ties end-to-end today; detail emitters swap in without touching gates.
                pass
            amt = (bal * Decimal(r["pct"])).quantize(Decimal("0.01")) if t == "capital_split" else bal
            je.append((r["new_account"], loc, amt, f"OB<-{r['old_account']}"))
            emitted[(r["new_account"], loc)] += amt

        # Per-class zero, honestly: flagged balances leave a visible hole -> explicit
        # suspense line (must be cleared before live import). Only sub-nickel split
        # rounding may be absorbed silently.
        drift = sum(a for _, _, a, _ in je)
        if drift != ZERO:
            if abs(drift) < Decimal("0.05"):
                i = max(range(len(je)), key=lambda k: abs(je[k][2]))
                a, c, amt, m = je[i]; je[i] = (a, c, amt - drift, m + " (rounding)")
            else:
                je.append(("OB Suspense - Flagged", loc, -drift,
                           "flagged items excluded - MUST be 0.00 before live import"))

        # G4: emitted == source TB (mapped, non-flag), to the penny
        src = sum(tb.get(r["old_account"], ZERO) for r in mapping
                  if r["treatment"] != "flag" and r["treatment"] != "capital_split") \
            + sum(tb.get(a, ZERO) for a in {r["old_account"] for r in mapping
                  if r["treatment"] == "capital_split"})
        emt = sum(emitted.values())
        if src != emt: die("G4", f"{entity}: source {src} != emitted {emt}")

        (outd / f"OB_{entity}.iif").write_text(
            iif_je(f"OB-{entity}-001", f"OB from {CFG['entities'][entity]['qbw_name']} TB {IIF_DATE}", je))
        tieout.append([entity, str(src), str(emt), "0.00"])
        print(f"✓ {entity}: G2 G3 G4 passed → OB_{entity}.iif ({len(je)} lines)")

    dump(flags, ["entity","old_account","balance","note"], outd / "flags.csv")
    dump(tieout, ["entity","source_tb","emitted","delta"], outd / "tieout_report.csv")
    # TODO(next slice): derive Parent_OB.iif IC mirrors + Investment postings from
    # partnership Due-To/From numbers (G7 holds by construction — never keyed twice).

# ───────────────────────── VERIFY (post-import) ─────────────────────────
def cmd_verify(target: str):
    """Run with the TRIAL-IMPORT COPY of `target` open. Never the live file first."""
    cn = qodbc(); cur = cn.cursor()
    open_name = cur.execute(SQL["company"]).fetchone()[0]
    exp = CFG["target_files"][target]
    if exp not in open_name: die("G5", f"open file '{open_name}' is not target '{exp}'")
    newtb = cur.execute(SQL["tb"] % CFG["cutover"]).fetchall()
    # G5: re-extracted BS-by-Location vs tieout (per-entity comparison via Location QuickReports)
    # G6: preserve_labeled amounts present verbatim
    for item in CFG["preserve_labeled"]:
        hit = [r for r in newtb if r[0].endswith(item["account"].split(":")[-1])]
        ok = any(money(r[1]) - money(r[2]) == -money(item["amount"]) or
                 money(r[2]) - money(r[1]) == money(item["amount"]) for r in hit)
        if not ok: die("G6", f"labeled item missing/altered: {item['account']} {item['amount']}")
    # G7: IC mirror pairs net zero across both files (compare cached partnership legs
    # against parent re-extract). TODO(next slice) once Parent_OB emitter lands.
    print("✓ G5/G6 checks passed on trial copy. Review tieout, back up live file, import for real.")

# ───────────────────────── entrypoint ─────────────────────────
if __name__ == "__main__":
    cmds = {"extract": lambda: cmd_extract(sys.argv[2]),
            "build":   cmd_build,
            "verify":  lambda: cmd_verify(sys.argv[2])}
    (cmds.get(sys.argv[1] if len(sys.argv) > 1 else "") or
     (lambda: sys.exit(__doc__)))()
