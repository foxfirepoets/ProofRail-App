"""CHUNK_7B table-aware extraction — hermetic regression tests over the real Draw #29 layout.

``tests/fixtures/draw29/summary_table.txt`` is the committed ``pdftotext -table`` text of the
Builder's Draw Request Summary (pages 9-10). These tests need no PDF/poppler/DB: they parse the
fixture and lock the difficult-row behaviours that broke the CHUNK_7 ``-layout`` parser — the
$278,237.18 shortfall, invoice/item-code confusion, multi-line cells, and retainage sign.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.ingestion.parser import summary_rows_to_lines
from app.ingestion.table_extract import (
    EXACT,
    RECONSTRUCTED,
    UNRECOVERABLE,
    SummaryRow,
    parse_table_page,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "draw29" / "summary_table.txt"
AUTHORITATIVE = Decimal("962845.68")


def _all_rows() -> tuple[list[SummaryRow], list]:
    text = FIX.read_text(encoding="utf-8")
    rows: list[SummaryRow] = []
    totals = None
    for page in (p for p in text.split("\f") if p.strip()):
        page_rows, page_totals = parse_table_page(page)
        rows.extend(page_rows)
        if page_totals.amount_due_total is not None:
            totals = page_totals
    return rows, totals


ROWS, TOTALS = _all_rows()


def _by_vendor(substr: str) -> list[SummaryRow]:
    return [r for r in ROWS if r.payable_to and substr.upper() in r.payable_to.upper()]


def _due(substr: str) -> Decimal:
    return next(r.amount_due for r in _by_vendor(substr) if r.amount_due is not None)


# ─────────────────────────── acceptance threshold ───────────────────────────

def test_reconstructed_total_meets_acceptance_threshold():
    recon = sum((r.amount_due for r in ROWS if r.amount_due is not None), Decimal("0"))
    assert abs(AUTHORITATIVE - recon) < Decimal("0.01"), f"delta {AUTHORITATIVE - recon}"


def test_full_row_count():
    assert len(ROWS) == 57


def test_totals_row_signed():
    assert TOTALS.inv_total == Decimal("705290.49")
    assert TOTALS.retainage_total == Decimal("-257555.19")  # net release
    assert TOTALS.amount_due_total == AUTHORITATIVE
    assert TOTALS.inv_total - TOTALS.retainage_total == TOTALS.amount_due_total


def test_no_unrecoverable_rows():
    assert all(r.row_confidence != UNRECOVERABLE for r in ROWS)
    assert all(r.row_confidence in (EXACT, RECONSTRUCTED) for r in ROWS)


# ─────────────────────────── item# vs invoice# disambiguation ───────────────────────────

def test_item_codes_are_never_invoice_numbers():
    # Every item code is a 3-digit Summa Terra cost code (001-069); invoice tokens like
    # 402/403/404 must never surface as an item code.
    for r in ROWS:
        assert r.item_code and r.item_code.isdigit() and 1 <= int(r.item_code) <= 69


def test_k_carter_402_403_404_are_invoices_not_item_codes():
    kc = _by_vendor("K CARTER")
    assert len(kc) == 4
    item_codes = {r.item_code for r in kc}
    assert item_codes == {"048", "046", "047", "022"}  # real cost codes
    invoices = " ".join(r.invoice_no or "" for r in kc)
    for tok in ("402", "403", "404"):
        assert tok in invoices
    # …and none of 402/403/404 leaked into item codes
    assert not ({"402", "403", "404"} & item_codes)


def test_invoice_numbers_do_not_become_cost_code_misses():
    # The mapping only ever sees item_code; convert to ParsedLines and confirm item codes only.
    lines = summary_rows_to_lines(ROWS)
    for ln in lines:
        assert ln.item_code and ln.item_code.isdigit()
        # an invoice-looking value never appears as the item code
        assert ln.item_code not in {"402", "403", "404", "2257", "697265"}


# ─────────────────────────── retainage sign (withheld vs release) ───────────────────────────

def test_meraki_steel_retainage_release():
    m = _by_vendor("MERAKI STEEL")[0]
    assert m.item_code == "012"
    assert m.inv_amount == Decimal("120414.50")
    assert m.retainage == Decimal("-17699.18")  # negative = release
    assert m.amount_due == Decimal("138113.68")
    assert m.inv_amount - m.retainage == m.amount_due


def test_fox_and_hound_retainage_withheld():
    f = _by_vendor("FOX & HOUND")[0]
    assert f.inv_amount == Decimal("78947.37")
    assert f.retainage == Decimal("3947.37")  # positive = withheld
    assert f.amount_due == Decimal("75000.00")


def test_lara_sons_negative_retainage_split_lines():
    lara = _by_vendor("LARA & SONS")
    assert {r.item_code for r in lara} == {"025", "037"}
    drywall = next(r for r in lara if r.item_code == "025")
    assert drywall.retainage == Decimal("-62155.30")
    assert drywall.amount_due == Decimal("99875.30")
    exteriors = next(r for r in lara if r.item_code == "037")
    assert exteriors.retainage == Decimal("-33845.23")


def test_mc_siding_retention():
    brick = next(r for r in _by_vendor("MC SIDING") if r.item_code == "036")
    assert brick.retainage == Decimal("-22500.00")
    assert brick.amount_due == Decimal("39485.00")


def test_tk_elevator_retention():
    tk = _by_vendor("TK ELEVATOR")[0]
    assert tk.item_code == "015"
    assert tk.retainage == Decimal("-14012.90")
    assert tk.amount_due == Decimal("14012.90")


def test_tst_fire_final_pay_app():
    tst = _by_vendor("TST FIRE")[0]
    assert tst.item_code == "021"
    assert tst.amount_due == Decimal("31124.47")


def test_webbs_windows_retention():
    w = _by_vendor("WEBB")[0]
    assert w.item_code == "014"
    assert w.retainage == Decimal("-3113.05")
    assert w.amount_due == Decimal("3113.05")


# ─────────────────────────── multi-line cells ───────────────────────────

def test_rich_development_split_lines():
    rich = _by_vendor("RICH DEVELOPMENT")
    assert len(rich) == 7  # seven cost categories, one invoice (HL 2508) each
    assert all(r.invoice_no == "HL 2508" for r in rich)
    assert _due("RICH DEVELOPMENT") is not None
    assert sum((r.amount_due for r in rich), Decimal("0")) == Decimal("203959.43")


def test_metro_porcelain_multiline_invoice_and_vendor():
    m = _by_vendor("METRO PORCELAIN")[0]
    assert m.item_code == "017"
    assert m.payable_to == "METRO PORCELAIN & FIBERGLASS"  # wrapped vendor name merged
    for tok in ("836955", "837337", "837276", "837514", "837712"):
        assert tok in (m.invoice_no or "")  # all five wrapped invoice fragments merged
    assert m.row_confidence == RECONSTRUCTED


def test_wasatch_two_distinct_vendors_not_cross_merged():
    w = _by_vendor("WASATCH")
    names = {r.payable_to for r in w}
    assert "WASATCH CONSTRUCTION CLEAN UP" in names
    assert "WASATCH PREMIER HOME SERVICES" in names
    # the "CLEAN UP" / "SERVICES" wraps did not bleed into the neighbouring row
    assert all("WEBB" not in (n or "") for n in names)


def test_altura_cameras_multi_invoice():
    a = _by_vendor("ALTURA CAMERAS")[0]
    assert a.item_code == "062"
    assert "AC25024" in (a.invoice_no or "") and "AC25031" in (a.invoice_no or "")
    assert a.payable_to == "ALTURA CAMERAS LLC"  # not absorbed into the invoice cell


def test_beazer_lock_key_multi_invoice():
    b = _by_vendor("BEAZER")[0]
    assert b.item_code == "032"
    assert "697265" in (b.invoice_no or "") and "697266" in (b.invoice_no or "")


# ─────────────────────────── coverage of every difficult row ───────────────────────────

@pytest.mark.parametrize("vendor", [
    "RICH DEVELOPMENT", "MERAKI STEEL", "LARA & SONS", "MC SIDING", "TK ELEVATOR",
    "TST FIRE", "WEBB", "K CARTER", "ALTURA CAMERAS", "BEAZER", "METRO PORCELAIN",
])
def test_named_difficult_rows_present_and_amounts_tie(vendor):
    rows = _by_vendor(vendor)
    assert rows, f"{vendor} missing"
    for r in rows:
        assert r.amount_due is not None
        if r.inv_amount is not None and r.retainage is not None:
            assert r.inv_amount - r.retainage == r.amount_due
