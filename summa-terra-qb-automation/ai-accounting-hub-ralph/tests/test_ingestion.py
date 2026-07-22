"""CHUNK_7 draw ingestion — offline parser/validator tests (hermetic fixtures) + live ingest.

Golden fixture = Hunter's Landing Draw #29. Offline tests parse committed text fixtures (no
PDF/poppler/DB). Live tests (gated) ingest the real PDF into the canonical store in a rolled-back
transaction and prove idempotency, cost-code mapping, and the hand-off to the shadow fee engine.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.normalize import normalize_name, parse_money
from app.ingestion.parser import (
    DrawHeader,
    ParsedDraw,
    ParsedLine,
    parse_header,
    parse_summary_lines,
)
from app.ingestion.validate import validate_draw
from app.models import Company, DrawLine, DrawPackage

FIX = Path(__file__).resolve().parent / "fixtures" / "draw29"
# pdftotext can emit non-UTF-8 bytes (e.g. "DÉCOR"); read tolerantly as production does.
HEADER_TEXT = (FIX / "header.txt").read_text(encoding="utf-8", errors="replace")
SUMMARY_TEXT = (FIX / "summary.txt").read_text(encoding="utf-8", errors="replace")
INGEST_DIR = Path(__file__).resolve().parent.parent / "app" / "ingestion"
REAL_PDF = Path(r"C:/Users/Administrator/Desktop/QB Summa Terra/Hunters Landing Draw #29.pdf")

REQUIRED_CODES = {"003", "004", "005", "019", "028", "035", "052", "053", "067", "068"}


# ─────────────────────────── offline: money + names ───────────────────────────

def test_parse_money_signs():
    assert parse_money("$5,949.22") == Decimal("5949.22")
    assert parse_money("-$17,699.18") == Decimal("-17699.18")
    assert parse_money("($ (851.75)") == Decimal("-851.75")  # parens = negative (retention release)
    assert parse_money("($ 3,947.37)") == Decimal("-3947.37")  # outer parens = negative
    assert parse_money("-3,113.05") == Decimal("-3113.05")
    assert parse_money("") is None
    assert parse_money("n/a") is None


def test_normalize_name_strips_suffixes():
    assert normalize_name("RICH DEVELOPMENT INC.") == "RICH DEVELOPMENT"
    assert normalize_name("Altura Cameras LLC") == "ALTURA CAMERAS"
    assert normalize_name("Beazer Lock & Key") == "BEAZER LOCK AND KEY"


def test_no_transport_import_shadow_guard():
    for py in INGEST_DIR.glob("*.py"):
        for line in py.read_text(encoding="utf-8").splitlines():
            s = line.strip().lower()
            if s.startswith(("import ", "from ")):
                assert "transport" not in s and "qbwc" not in s, f"{py.name} breaks shadow mode"


# ─────────────────────────── offline: header (golden) ───────────────────────────

def test_header_golden_values():
    h = parse_header(HEADER_TEXT + "\n" + SUMMARY_TEXT)
    assert h.draw_number == "29"
    assert h.project == "Hunter's Landing"
    assert h.lender == "UFirst Credit Union"
    assert h.borrower == "Summa Terra Ventures"
    assert h.collateral_address.startswith("407 W 12th St Ogden")
    assert h.draw_date == "09.10.2025"
    assert h.total_this_draw == Decimal("962845.68")


def test_summary_totals_row_and_tie_out():
    h = parse_header(HEADER_TEXT + "\n" + SUMMARY_TEXT)
    assert h.summary_inv_total == Decimal("705290.49")
    assert h.summary_retainage_total == Decimal("-257555.19")
    assert h.summary_amount_due_total == Decimal("962845.68")
    # amount_due = inv_amount - retainage  (retainage signed; here a net release)
    assert h.summary_inv_total - h.summary_retainage_total == h.summary_amount_due_total
    # document's summed amount-due column ties to Total This Draw
    assert h.summary_amount_due_total == h.total_this_draw


# ─────────────────────────── offline: lines ───────────────────────────

def test_required_item_codes_parsed():
    lines = parse_summary_lines(SUMMARY_TEXT)
    codes = {ln.item_code for ln in lines if ln.item_code}
    assert REQUIRED_CODES <= codes, f"missing {REQUIRED_CODES - codes}"


def test_vendor_names_extracted():
    lines = parse_summary_lines(SUMMARY_TEXT)
    payees = {normalize_name(ln.payable_to) for ln in lines if ln.payable_to}
    for v in ("RICH DEVELOPMENT", "MERAKI STEEL", "ALTURA CAMERAS"):
        assert v in payees, f"{v} not extracted"


def test_negative_retainage_line_parsed():
    # MERAKI STEEL: inv 120,414.50, retainage -17,699.18, due 138,113.68 (release added back).
    lines = parse_summary_lines(SUMMARY_TEXT)
    meraki = next(ln for ln in lines if ln.payable_to and "MERAKI" in ln.payable_to)
    assert meraki.retainage == Decimal("-17699.18")
    assert meraki.inv_amount - meraki.retainage == meraki.amount_due  # 120414.50 + 17699.18 = 138113.68


def test_raw_text_preserved_for_audit():
    lines = parse_summary_lines(SUMMARY_TEXT)
    assert all(ln.raw_text for ln in lines)


# ─────────────────────────── offline: validation ───────────────────────────

def _line(line_no, item, inv, payee, inv_amt, ret, due, review=False):
    return ParsedLine(line_no, item, inv, payee, None, inv_amt, ret, due, "raw", review)


def test_duplicate_invoice_detected():
    draw = ParsedDraw(DrawHeader(total_this_draw=Decimal("10")), [
        _line(1, "003", "INV-1", "ACME LLC", Decimal("5"), Decimal("0"), Decimal("5")),
        _line(2, "004", "INV-1", "ACME LLC", Decimal("5"), Decimal("0"), Decimal("5")),
    ])
    codes = {e.code for e in validate_draw(draw)}
    assert "DUPLICATE_INVOICE" in codes


def test_missing_invoice_is_warning_not_failure():
    draw = ParsedDraw(DrawHeader(total_this_draw=Decimal("5"), summary_amount_due_total=Decimal("5")), [
        _line(1, "003", None, "ACME", Decimal("5"), Decimal("0"), Decimal("5")),
    ])
    exc = validate_draw(draw)
    missing = [e for e in exc if e.code == "MISSING_INVOICE"]
    assert missing and missing[0].severity == "warning"


def test_malformed_total_triggers_exception():
    # summary column total disagrees with Total This Draw → hard exception.
    draw = ParsedDraw(DrawHeader(total_this_draw=Decimal("100"), summary_amount_due_total=Decimal("999")), [])
    codes = {e.code for e in validate_draw(draw)}
    assert "TOTAL_TIE_OUT_MISMATCH" in codes


def test_line_retainage_mismatch_detected():
    draw = ParsedDraw(DrawHeader(total_this_draw=Decimal("5")), [
        _line(1, "003", "INV-1", "ACME", Decimal("10"), Decimal("2"), Decimal("5")),  # 10-2 != 5
    ])
    codes = {e.code for e in validate_draw(draw)}
    assert "LINE_RETAINAGE_MISMATCH" in codes


# ─────────────────────────── live: ingest into canonical store ───────────────────────────

pytestmark_live = pytest.mark.integration


@pytest.fixture
def live() -> Iterator[dict]:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("set RUN_INTEGRATION=1")
    if not REAL_PDF.is_file():
        pytest.skip("real Draw #29 PDF not present")
    from app.db import get_engine

    s = Session(get_engine())
    try:
        part = s.scalars(select(Company).where(Company.role == "partnership")).one()
        parent = s.scalars(select(Company).where(Company.role == "parent")).one()
        yield {"s": s, "part": part.id, "parent": parent.id}
    finally:
        s.rollback()
        s.close()


FIXTURE_META = {
    "historical_example": True, "already_paid": True, "not_for_posting": True,
    "not_for_payment": True, "source_purpose": "format_fixture",
}


@pytest.mark.integration
def test_live_ingest_header_and_tie_out(live):
    from app.ingestion.service import ingest_draw

    r = ingest_draw(live["s"], REAL_PDF, live["part"])
    assert r.draw_number == "29"
    assert r.authoritative_total == Decimal("962845.68")
    assert r.line_count == 57
    # header reliably ties to the summary column total
    pkg = live["s"].get(DrawPackage, r.draw_id)
    assert Decimal(str(pkg.package_total)) == Decimal("962845.68")
    assert pkg.raw_extensions["summary_amount_due_total"] == "962845.68"


@pytest.mark.integration
def test_live_line_reconstruction_meets_acceptance_threshold(live):
    """CHUNK_7B acceptance: the reconstructed amount-due column ties to the authoritative total."""
    from app.ingestion.service import ingest_draw

    r = ingest_draw(live["s"], REAL_PDF, live["part"])
    assert r.reconstructed_amount_due == Decimal("962845.68")
    assert abs(r.unresolved_delta) < Decimal("0.01")
    assert r.pct_coverage == Decimal("100.00")
    assert r.confidence_breakdown.get("unrecoverable", 0) == 0
    # the CHUNK_7 shortfall is gone — PARSE_INCOMPLETE no longer fires
    assert not any(e.code == "PARSE_INCOMPLETE" for e in r.exceptions)
    # summary pages were located dynamically (not hard-coded)
    assert r.summary_pages == (9, 10)


@pytest.mark.integration
def test_live_invoice_numbers_not_reported_as_cost_code_misses(live):
    from app.ingestion.service import ingest_draw

    r = ingest_draw(live["s"], REAL_PDF, live["part"])
    for tok in ("402", "403", "404"):
        assert tok not in r.mapping.cost_code_misses
    # K Carter invoice tokens live in invoice_no, the real codes in item_code
    kc = live["s"].scalars(
        select(DrawLine).where(DrawLine.draw_package_id == r.draw_id, DrawLine.payable_to.like("K CARTER%"))
    ).all()
    assert {ln.item_code for ln in kc} == {"048", "046", "047", "022"}


@pytest.mark.integration
def test_live_coverage_report(live):
    from app.ingestion.reports import amount_coverage_report
    from app.ingestion.service import ingest_draw

    r = ingest_draw(live["s"], REAL_PDF, live["part"])
    rep = amount_coverage_report(live["s"], r.draw_id)
    assert rep["authoritative_total"] == "962845.68"
    assert rep["reconstructed_amount_due_total"] == "962845.68"
    assert rep["fully_reconciled"] is True
    assert rep["unresolved_delta"] == "0.00"


@pytest.mark.integration
def test_live_cost_codes_mapped(live):
    from app.ingestion.service import ingest_draw

    r = ingest_draw(live["s"], REAL_PDF, live["part"])
    assert r.mapping.cost_code_hits >= 40
    # the required item codes resolved to catalog cost codes
    rows = live["s"].scalars(
        select(DrawLine).where(DrawLine.draw_package_id == r.draw_id, DrawLine.cost_code_id.isnot(None))
    ).all()
    mapped_codes = {ln.item_code for ln in rows}
    assert REQUIRED_CODES <= mapped_codes


@pytest.mark.integration
def test_live_idempotent_no_duplicate_lines(live):
    from app.ingestion.service import ingest_draw

    s = live["s"]
    r1 = ingest_draw(s, REAL_PDF, live["part"])
    n1 = s.scalar(select(func.count()).select_from(DrawLine).where(DrawLine.draw_package_id == r1.draw_id))
    r2 = ingest_draw(s, REAL_PDF, live["part"])
    n2 = s.scalar(select(func.count()).select_from(DrawLine).where(DrawLine.draw_package_id == r2.draw_id))
    assert r1.draw_id == r2.draw_id
    assert n1 == n2  # no duplicate lines


@pytest.mark.integration
def test_live_vendor_candidates_queued(live):
    from app.ingestion.service import ingest_draw
    from app.models import VendorCandidate

    r = ingest_draw(live["s"], REAL_PDF, live["part"])
    assert r.mapping.vendor_hits >= 1
    cand = live["s"].scalar(
        select(func.count()).select_from(VendorCandidate).where(VendorCandidate.company_id == live["part"])
    )
    assert cand == r.mapping.vendor_candidates_queued


@pytest.mark.integration
def test_live_ingested_draw_feeds_shadow_fee_engine(live):
    """Hand-off: an ingested draw, once approved, drafts fees via the existing shadow engine."""
    from app.draw_engine import engine
    from app.ingestion.service import ingest_draw
    from app.models import FeeEntry

    s = live["s"]
    r = ingest_draw(s, REAL_PDF, live["part"])
    pkg = s.get(DrawPackage, r.draw_id)
    # simulate a clean approval (engine fires only on approved_for_accounting + both approvals)
    pkg.status = "approved_for_accounting"
    pkg.cm_approved = True
    pkg.watson_approved = True
    s.flush()
    res = engine.process_draw(s, r.draw_id, parent_company_id=live["parent"])
    assert res.drafted
    assert res.amounts["dev_5_partnership"] == "48142.28"  # 5% of 962,845.68
    drafted = s.scalars(select(FeeEntry).where(FeeEntry.draw_package_id == r.draw_id)).all()
    assert len(drafted) == 4
    for fe in drafted:
        assert fe.qb_txn_id is None  # shadow: no QuickBooks write


@pytest.mark.integration
def test_live_historical_fixture_flags_persisted(live):
    from app.ingestion.service import ingest_draw

    r = ingest_draw(live["s"], REAL_PDF, live["part"], fixture_meta=FIXTURE_META)
    pkg = live["s"].get(DrawPackage, r.draw_id)
    for k, v in FIXTURE_META.items():
        assert pkg.raw_extensions[k] == v


@pytest.mark.integration
def test_live_not_for_posting_fixture_never_fires_fee_engine(live):
    """A historical fixture must never create an active payable/payment/fee event."""
    from app.draw_engine import engine
    from app.ingestion.service import ingest_draw
    from app.models import FeeEntry

    s = live["s"]
    r = ingest_draw(s, REAL_PDF, live["part"], fixture_meta=FIXTURE_META)
    pkg = s.get(DrawPackage, r.draw_id)
    # even fully "approved", a not_for_posting draw is refused by the fee engine
    pkg.status = "approved_for_accounting"
    pkg.cm_approved = True
    pkg.watson_approved = True
    s.flush()
    eligible, reason = engine.is_fee_eligible(pkg)
    assert not eligible and "not_for_posting" in reason
    res = engine.process_draw(s, r.draw_id, parent_company_id=live["parent"])
    assert not res.drafted
    fees = s.scalar(
        select(func.count()).select_from(FeeEntry).where(FeeEntry.draw_package_id == r.draw_id)
    )
    assert fees == 0  # zero fee events from the historical fixture
