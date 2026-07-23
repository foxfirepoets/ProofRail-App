"""Unit tests for the QBE posting service (qbe_qbxml / qbe_duplicate_gate /
qbe_post / qbe_post_catchup).

Run:  python -m pytest scripts/test_qbe_posting_service.py -v

Every test is offline: no QuickBooks, no COM, no network. The split and routing
tests use the REAL pack CSVs (read-only) so the assertions bind to production data,
not toy fixtures.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from qbe_qbxml import (
    JournalLine,
    NormalizedEntry,
    QbeAssemblyError,
    assemble_and_validate,
    build_gje_request,
    to_amount,
    validate_qbxml,
)
from qbe_duplicate_gate import (
    DuplicateGate,
    ExistingTxn,
    PASS,
    SKIP_DUPLICATE,
    find_match,
    parse_transaction_query,
)
from qbe_post import (
    BalanceTracker,
    BatchHalt,
    CONFIRMED,
    INTENT,
    PostError,
    PostingClient,
    assert_read_back,
    _parse_add_response,
)
import qbe_post as qbe_post_mod
import qbe_post_catchup as driver

_DOCS = Path(__file__).resolve().parent.parent / "docs" / "final_issue_resolution"
_LOGS = Path(__file__).resolve().parent.parent / "logs"


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _simple_entry(**over) -> NormalizedEntry:
    kw = dict(
        entity="Elephant Rock, LLC",
        txn_date="2026-03-12",
        bank_account="Checking at UCCU",
        memo="Ricks and Co. (CPA) - 2025 K-1 Filing",
        gate="READY",
        seq="1",
    )
    kw.update(over)
    amt = to_amount("1100.00")
    return NormalizedEntry(
        lines=[
            JournalLine("Professional Fees", amt, "debit", kw["memo"]),
            JournalLine("Checking at UCCU", amt, "credit", kw["memo"]),
        ],
        **kw,
    )


def _hln_draw_seq34() -> NormalizedEntry:
    """The real 28-line HLN Arixa draw (pack Seq 34) via the driver's builder."""
    cm = driver.CompanyMap()
    pack = {r["Seq"]: r for r in driver._read_csv(_DOCS / "FINAL_QBE_CATCHUP_POSTING_PACK.csv")}
    row = pack["34"]
    groups = driver.load_split_groups()
    key = (driver._norm_acct(row["Entity"]), row["Date"].strip(), to_amount(row["Amount"]))
    entry, _warn = driver.build_split_entry(row, cm.resolve(row["Entity"]), groups[key])
    return entry


# --------------------------------------------------------------------------- #
# 1. qbXML assembly
# --------------------------------------------------------------------------- #


def test_ready_entry_produces_schema_valid_gje():
    entry = _simple_entry()
    xml, ok, errs = assemble_and_validate(entry)
    assert ok, errs

    cleaned = xml.split("?>")[-1].strip()  # drop PIs for parsing
    doc = etree.fromstring(cleaned.encode())
    add = doc.find(".//JournalEntryAdd")
    assert add.findtext("TxnDate") == "2026-03-12"

    debit = add.find("JournalDebitLine")
    credit = add.find("JournalCreditLine")
    assert debit.findtext("AccountRef/FullName") == "Professional Fees"
    assert debit.findtext("Amount") == "1100.00"
    assert debit.findtext("Memo").startswith("Ricks and Co")
    assert credit.findtext("AccountRef/FullName") == "Checking at UCCU"
    assert credit.findtext("Amount") == "1100.00"


def test_debits_precede_credits_and_one_request():
    entry = _simple_entry()
    doc = etree.fromstring(build_gje_request(entry).split("?>")[-1].strip().encode())
    assert len(doc.findall(".//JournalEntryAddRq")) == 1  # atomic: one request
    add = doc.find(".//JournalEntryAdd")
    kinds = [child.tag for child in add if child.tag.endswith("Line")]
    assert kinds == sorted(kinds, key=lambda k: 0 if "Debit" in k else 1)


def test_unbalanced_entry_refused():
    with pytest.raises(QbeAssemblyError):
        build_gje_request(
            NormalizedEntry(
                entity="X",
                txn_date="2026-01-01",
                bank_account="Bank",
                lines=[
                    JournalLine("A", to_amount("100.00"), "debit"),
                    JournalLine("Bank", to_amount("90.00"), "credit"),
                ],
            )
        )


def test_negative_line_amount_rejected_at_line_level():
    with pytest.raises(QbeAssemblyError):
        JournalLine("A", to_amount("-5.00"), "debit")


# --------------------------------------------------------------------------- #
# 2. Atomic split -- real 28-line HLN draw
# --------------------------------------------------------------------------- #


def test_atomic_split_28_line_hln_draw_one_balanced_request():
    entry = _hln_draw_seq34()
    # 28 detail legs (one is a -$500 contra flipped to the opposite side) => 28 leg
    # lines + 1 bank line.
    assert len(entry.lines) == 29
    assert entry.bank_account == "Central Bank - Checking"

    xml, ok, errs = assemble_and_validate(entry)
    assert ok, errs

    doc = etree.fromstring(xml.split("?>")[-1].strip().encode())
    # ONE request, ONE JournalEntryAdd -> QuickBooks commits atomically.
    assert len(doc.findall(".//JournalEntryAddRq")) == 1
    add = doc.find(".//JournalEntryAdd")

    debit = sum(Decimal(a.text) for a in add.findall("JournalDebitLine/Amount"))
    credit = sum(Decimal(a.text) for a in add.findall("JournalCreditLine/Amount"))
    assert debit == credit                     # debits equal credits
    # Gross total includes the $500 Arixa draw-fee contra leg; the net cash that
    # actually hit the bank (and that the duplicate gate matches on) is the pack
    # total. Both are exact to the cent -- no plug, no rounding.
    assert debit == to_amount("1155163.00")        # gross debits == gross credits
    assert entry.match_amount() == to_amount("1154663.00")  # net bank movement
    bank_amt = to_amount(
        add.xpath("(.//JournalDebitLine[AccountRef/FullName='Central Bank - Checking']/Amount)[1]")[0].text
    )
    assert bank_amt == to_amount("1154663.00")


# --------------------------------------------------------------------------- #
# 3. Duplicate gate
# --------------------------------------------------------------------------- #


def test_duplicate_gate_skips_match_and_passes_nonmatch():
    entry = _simple_entry()
    gate = DuplicateGate()

    match = ExistingTxn(
        txn_id="TXN-500",
        txn_date="2026-03-13",  # within +/-5 days
        amount=to_amount("1100.00"),
        accounts=("Checking at UCCU", "Professional Fees"),
        memo="Ricks and Co CPA K-1",
    )
    res = gate.check(entry, [match])
    assert res.decision == SKIP_DUPLICATE
    assert res.matched_txn_id == "TXN-500"

    non_match_amount = ExistingTxn(
        txn_id="TXN-501", txn_date="2026-03-12",
        amount=to_amount("2200.00"), accounts=("Checking at UCCU",))
    non_match_date = ExistingTxn(
        txn_id="TXN-502", txn_date="2026-04-30",
        amount=to_amount("1100.00"), accounts=("Checking at UCCU",))
    non_match_account = ExistingTxn(
        txn_id="TXN-503", txn_date="2026-03-12",
        amount=to_amount("1100.00"), accounts=("Some Other Bank",))
    assert gate.check(entry, [non_match_amount]).decision == PASS
    assert gate.check(entry, [non_match_date]).decision == PASS
    assert gate.check(entry, [non_match_account]).decision == PASS


def test_duplicate_gate_prefers_high_confidence_on_ref_match():
    entry = _simple_entry(ref_number="480")
    e_med = ExistingTxn("A", "2026-03-12", to_amount("1100.00"),
                        ("Professional Fees",), memo="unrelated")
    e_high = ExistingTxn("B", "2026-03-12", to_amount("1100.00"),
                         ("Professional Fees",), ref_number="480")
    res = find_match(entry, [e_med, e_high])
    assert res.decision == SKIP_DUPLICATE
    assert res.matched_txn_id == "B"
    assert res.confidence == "high"


# --------------------------------------------------------------------------- #
# 4. Held-list wins
# --------------------------------------------------------------------------- #


def test_held_list_entry_never_emitted(tmp_path):
    held = tmp_path / "held.json"
    held.write_text(json.dumps([{"seq": "1"}, {"seq": "2"}]), encoding="utf-8")
    cm = driver.CompanyMap()
    routed, _notes = driver.route_pack(cm, held_path=held)
    for seq in ("1", "2"):
        row = next(r for r in routed if r.seq == seq)
        assert row.bucket == driver.HELD_LIST
        assert row.entry is None  # never assembled into a postable entry


# --------------------------------------------------------------------------- #
# 5. Idempotency
# --------------------------------------------------------------------------- #


def test_idempotency_two_phase_intent_confirm(tmp_path):
    log = tmp_path / "qbe_posted.jsonl"
    client = PostingClient(posted_log=log)
    e1 = _simple_entry(seq="1")
    e2 = _simple_entry(seq="2", txn_date="2026-03-20", memo="different")

    assert not client.already_posted(e1)
    assert not client.has_intent_orphan(e1)

    # Two-phase: INTENT written before the (simulated) write, CONFIRMED after.
    client._write_intent(e1, e1.entry_id)
    assert client.has_intent_orphan(e1)     # intent with no confirm => orphan
    assert not client.already_posted(e1)
    client._confirm(e1, "TXN-1")
    assert client.already_posted(e1)        # confirmed
    assert not client.has_intent_orphan(e1)  # resolved

    # A fresh client reading the same log still skips e1 (persisted idempotency).
    client2 = PostingClient(posted_log=log)
    emit = [e for e in [e1, e2] if not client2.already_posted(e)]
    assert [e.seq for e in emit] == ["2"]   # zero duplicate posts of e1


def test_intent_orphan_blocks_until_resolved(tmp_path):
    log = tmp_path / "qbe_posted.jsonl"
    client = PostingClient(posted_log=log)
    e = _simple_entry(seq="1")
    client._write_intent(e, e.entry_id)     # crash simulated: never confirmed
    assert client.has_intent_orphan(e)
    # A FAILED record (clean rejection) resolves the intent so it no longer blocks.
    client._mark_failed(e, "QB rejected")
    assert not client.has_intent_orphan(e)


# --------------------------------------------------------------------------- #
# 6. Negative-balance halt
# --------------------------------------------------------------------------- #


def test_negative_balance_halt():
    tracker = BalanceTracker()
    tracker.set_opening("Vic Partners LLC", "UCCU Checking", "1000.00")

    # An entry that credits (drains) the bank by 1500 would overdraw.
    overdraw = NormalizedEntry(
        entity="Vic Partners LLC", txn_date="2026-05-01", bank_account="UCCU Checking",
        lines=[
            JournalLine("Professional Fees", to_amount("1500.00"), "debit"),
            JournalLine("UCCU Checking", to_amount("1500.00"), "credit"),
        ],
    )
    assert tracker.would_overdraw(overdraw) is True

    # A safe draining entry does not.
    safe = NormalizedEntry(
        entity="Vic Partners LLC", txn_date="2026-05-01", bank_account="UCCU Checking",
        lines=[
            JournalLine("Professional Fees", to_amount("400.00"), "debit"),
            JournalLine("UCCU Checking", to_amount("400.00"), "credit"),
        ],
    )
    assert tracker.would_overdraw(safe) is False

    # Unknown opening balance -> None ("requires live balance"), never a false safe.
    unknown = NormalizedEntry(
        entity="Vic Partners LLC", txn_date="2026-05-01", bank_account="Mystery Bank",
        lines=[
            JournalLine("Professional Fees", to_amount("10.00"), "debit"),
            JournalLine("Mystery Bank", to_amount("10.00"), "credit"),
        ],
    )
    assert tracker.would_overdraw(unknown) is None


# --------------------------------------------------------------------------- #
# 7. Gate routing (pure, with an EMPTY held list to isolate the routing rule)
# --------------------------------------------------------------------------- #


def test_gate_routing_counts(tmp_path):
    empty_held = tmp_path / "empty.json"
    empty_held.write_text("[]", encoding="utf-8")
    cm = driver.CompanyMap()
    routed, _notes = driver.route_pack(cm, held_path=empty_held)

    from collections import Counter
    buckets = Counter(r.bucket for r in routed)
    # 357 READY + 1 correction all route to the post queue.
    assert buckets[driver.POST_QUEUE] == 358
    # 17 SPLIT REQUIRED all held (never in the post queue).
    assert buckets[driver.HELD_SPLIT] == 17
    # 16 UNCODED never posted.
    assert buckets[driver.NEVER_UNCODED] == 16
    assert buckets[driver.MALFORMED] == 0
    assert buckets[driver.UNMAPPED_ENTITY] == 0

    # No SPLIT/UNCODED row ever lands in the post queue.
    for r in routed:
        if r.bucket == driver.POST_QUEUE:
            assert r.entry is not None and r.entry.gate.startswith("READY")


# --------------------------------------------------------------------------- #
# 8. Read-back assertion (requirement 1d)
# --------------------------------------------------------------------------- #


def _readback_xml(date_="2026-03-12", debit_acct="Professional Fees",
                  credit_acct="Checking at UCCU", amount="1100.00"):
    return (
        '<?qbxml version="13.0"?>'
        '<QBXML><QBXMLMsgsRs><JournalEntryQueryRs statusCode="0" statusSeverity="Info">'
        '<JournalEntryRet><TxnID>TXN-9</TxnID>'
        f"<TxnDate>{date_}</TxnDate>"
        f'<JournalDebitLine><AccountRef><FullName>{debit_acct}</FullName></AccountRef>'
        f"<Amount>{amount}</Amount></JournalDebitLine>"
        f'<JournalCreditLine><AccountRef><FullName>{credit_acct}</FullName></AccountRef>'
        f"<Amount>{amount}</Amount></JournalCreditLine>"
        "</JournalEntryRet></JournalEntryQueryRs></QBXMLMsgsRs></QBXML>"
    )


def test_read_back_matches_and_detects_mismatch():
    entry = _simple_entry()
    ok, detail = assert_read_back(entry, _readback_xml())
    assert ok, detail

    ok_date, _ = assert_read_back(entry, _readback_xml(date_="2026-03-13"))
    assert not ok_date
    ok_amt, _ = assert_read_back(entry, _readback_xml(amount="999.00"))
    assert not ok_amt
    ok_acct, _ = assert_read_back(entry, _readback_xml(debit_acct="Wrong Account"))
    assert not ok_acct


def test_all_post_queue_requests_schema_valid(tmp_path):
    empty_held = tmp_path / "empty.json"
    empty_held.write_text("[]", encoding="utf-8")
    cm = driver.CompanyMap()
    routed, _notes = driver.route_pack(cm, held_path=empty_held)
    invalid = [r for r in routed if r.bucket == driver.POST_QUEUE and r.schema_valid is False]
    assert invalid == []


# --------------------------------------------------------------------------- #
# 9. LIVE-PATH integration (stubbed COM bridge -- still no real QuickBooks).
#    Proves the safety modules are WIRED INTO post_entry, not merely callable.
# --------------------------------------------------------------------------- #


class _StubGate:
    """Stands in for DuplicateGate: returns a fixed existing-txn set and reuses
    the real find_match logic, so the wiring (load_existing -> check) is exercised."""

    def __init__(self, existing=None, window_days=5):
        self._existing = existing or []
        self.window_days = window_days
        self.load_calls = 0

    def load_existing(self, working_copy_path, from_date, to_date):
        self.load_calls += 1
        return self._existing

    def check(self, entry, existing):
        return find_match(entry, existing, window_days=self.window_days)


def _add_response(txn_id="TXN-9", severity="Info", message="Status OK"):
    return (
        '<?qbxml version="13.0"?>'
        '<QBXML><QBXMLMsgsRs>'
        f'<JournalEntryAddRs statusCode="0" statusSeverity="{severity}" '
        f'statusMessage="{message}">'
        f"<JournalEntryRet><TxnID>{txn_id}</TxnID><TxnDate>2026-03-12</TxnDate>"
        "</JournalEntryRet></JournalEntryAddRs>"
        "</QBXMLMsgsRs></QBXML>"
    )


def _install_stub_bridge(client, add_resp, readback_resp):
    """Replace client._run_bridge with a stub; return a calls recorder."""
    calls = {"write": 0, "read": 0, "requests": []}

    def _stub(working_copy_path, request_xml, *, read_only, write):
        calls["requests"].append(("write" if write else "read", request_xml))
        if write:
            calls["write"] += 1
            return add_resp
        calls["read"] += 1
        return readback_resp

    client._run_bridge = _stub  # type: ignore[assignment]
    return calls


def _live_client_and_wc(tmp_path):
    """A PostingClient with tmp log/backup roots and a real (dummy) working copy."""
    wc = tmp_path / "wc.qbw"
    wc.write_bytes(b"dummy company file bytes")
    client = PostingClient(
        posted_log=tmp_path / "qbe_posted.jsonl",
        backup_root=tmp_path / "backups",
    )
    return client, str(wc)


def _funded_tracker(entry, opening="100000.00"):
    tracker = BalanceTracker()
    tracker.set_opening(entry.entity, entry.bank_account, opening)
    return tracker


def test_live_happy_path_posts_once_and_logs_confirmed(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    client.prepare_pre_open_backup(entry.entity, wc)   # pre-open backup (file closed)
    calls = _install_stub_bridge(client, _add_response("TXN-77"), _readback_xml())
    gate = _StubGate(existing=[])            # no duplicate
    tracker = _funded_tracker(entry)

    res = client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=tracker)
    assert res.status == "POSTED"
    assert res.txn_id == "TXN-77"
    assert res.read_back_ok is True
    assert calls["write"] == 1 and calls["read"] == 1
    assert gate.load_calls == 1              # gate was actually consulted

    # Log shows INTENT then CONFIRMED (two-phase, in order); backup was taken.
    recs = [json.loads(l) for l in (tmp_path / "qbe_posted.jsonl").read_text().splitlines()]
    assert [r["status"] for r in recs] == [INTENT, CONFIRMED]
    assert (tmp_path / "backups" / "qbe_backup_manifest.jsonl").exists()

    # Re-run is idempotent: CONFIRMED entry is skipped, no second write.
    calls2 = _install_stub_bridge(client, _add_response("TXN-99"), _readback_xml())
    res2 = client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=tracker)
    assert res2.status == "SKIPPED_IDEMPOTENT"
    assert calls2["write"] == 0


def test_live_duplicate_skips_and_never_writes(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    calls = _install_stub_bridge(client, _add_response(), _readback_xml())
    dup = ExistingTxn("TXN-DUP", "2026-03-12", to_amount("1100.00"),
                      ("Professional Fees", "Checking at UCCU"))
    gate = _StubGate(existing=[dup])
    tracker = _funded_tracker(entry)

    res = client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=tracker)
    assert res.status == "SKIPPED_DUPLICATE"
    assert res.txn_id == "TXN-DUP"
    assert calls["write"] == 0               # the gate blocked the write
    # nothing logged as INTENT/CONFIRMED
    assert not (tmp_path / "qbe_posted.jsonl").exists() or \
        (tmp_path / "qbe_posted.jsonl").read_text().strip() == ""


def test_live_overdraw_halts_and_never_writes(tmp_path):
    entry = _simple_entry()                  # credits bank 1100
    client, wc = _live_client_and_wc(tmp_path)
    calls = _install_stub_bridge(client, _add_response(), _readback_xml())
    gate = _StubGate(existing=[])
    tracker = _funded_tracker(entry, opening="500.00")   # 500 - 1100 < 0

    with pytest.raises(BatchHalt):
        client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=tracker)
    assert calls["write"] == 0


def test_live_unknown_balance_halts_unless_confirmed(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    _install_stub_bridge(client, _add_response(), _readback_xml())
    gate = _StubGate(existing=[])
    empty_tracker = BalanceTracker()         # no opening balance -> would_overdraw None

    with pytest.raises(BatchHalt):
        client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=empty_tracker)

    # With explicit human-confirm, it proceeds and posts.
    client.prepare_pre_open_backup(entry.entity, wc)   # pre-open backup required
    calls = _install_stub_bridge(client, _add_response("TXN-OK"), _readback_xml())
    res = client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=empty_tracker,
                            allow_unknown_balance=True)
    assert res.status == "POSTED"
    assert calls["write"] == 1


def test_live_intent_orphan_on_rerun_blocks(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    # Simulate a prior crash: INTENT written, never confirmed.
    client._write_intent(entry, entry.entry_id)
    calls = _install_stub_bridge(client, _add_response(), _readback_xml())
    gate = _StubGate(existing=[])
    tracker = _funded_tracker(entry)

    res = client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=tracker)
    assert res.status == "BLOCKED_INTENT_ORPHAN"
    assert calls["write"] == 0               # never auto-reposts an orphan


def test_live_requires_gate_and_tracker(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    _install_stub_bridge(client, _add_response(), _readback_xml())
    with pytest.raises(PostError):
        client.post_entry(entry, wc, live=True)  # no gate/tracker -> refuse


def test_parse_transaction_query_realistic_shape():
    # Two TransactionRet: one with AccountRef/FullName, one with repeated
    # AccountName elements the way QB report-style responses can emit them.
    xml = (
        '<?qbxml version="13.0"?>'
        '<QBXML><QBXMLMsgsRs>'
        '<TransactionQueryRs statusCode="0" statusSeverity="Info">'
        "<TransactionRet>"
        "<TxnID>TXN-1</TxnID><TxnType>Check</TxnType><TxnDate>2026-01-07</TxnDate>"
        "<RefNumber>480</RefNumber><Amount>-7247.08</Amount>"
        "<AccountRef><FullName>UCCU Checking #81900</FullName></AccountRef>"
        "<Memo>Check 480</Memo>"
        "</TransactionRet>"
        "<TransactionRet>"
        "<TxnID>TXN-2</TxnID><TxnType>Deposit</TxnType><TxnDate>2026-03-23</TxnDate>"
        "<Amount>1482696.66</Amount>"
        "<DataExtRet><AccountName>UCCU - Checking **8560</AccountName></DataExtRet>"
        "<DataExtRet><AccountName>Construction in Progress</AccountName></DataExtRet>"
        "</TransactionRet>"
        "</TransactionQueryRs>"
        "</QBXMLMsgsRs></QBXML>"
    )
    txns = parse_transaction_query(xml)
    assert len(txns) == 2

    t1 = txns[0]
    assert t1.txn_id == "TXN-1"
    assert t1.txn_date == "2026-01-07"
    assert t1.amount == to_amount("7247.08")          # abs of -7247.08
    assert t1.accounts == ("UCCU Checking #81900",)
    assert t1.ref_number == "480"

    t2 = txns[1]
    assert t2.txn_id == "TXN-2"
    assert t2.amount == to_amount("1482696.66")
    assert set(t2.accounts) == {"UCCU - Checking **8560", "Construction in Progress"}


def test_gate_matches_when_existing_has_no_account_names():
    # Conservative guard: if the live record carries no account names, the gate
    # still matches on amount+date (prefer false-skip over false-post).
    entry = _simple_entry()
    no_accounts = ExistingTxn("TXN-X", "2026-03-12", to_amount("1100.00"), accounts=())
    res = find_match(entry, [no_accounts])
    assert res.decision == SKIP_DUPLICATE


# --------------------------------------------------------------------------- #
# 10. REAL QuickBooks element names (BUG 1). The service must emit JournalEntry*
#     (NOT General...), matching the golden fixtures captured from a live post.
# --------------------------------------------------------------------------- #


def _smoke_entry():
    """The exact $1 wash entry the live smoke test posted (see golden fixtures)."""
    memo = "QBE SMOKE TEST - delete after verification"
    return NormalizedEntry(
        entity="Elephant Rock, LLC", txn_date="2026-07-22",
        bank_account="Ask My Accountant",
        lines=[
            JournalLine("Ask My Accountant", to_amount("1.00"), "debit", memo),
            JournalLine("Ask My Accountant", to_amount("1.00"), "credit", memo),
        ],
    )


def test_build_emits_correct_qbxml_element_name():
    xml = build_gje_request(_simple_entry())
    assert "<JournalEntryAddRq" in xml
    assert "<JournalEntryAdd>" in xml
    assert "GeneralJournalEntry" not in xml     # the bug that QB rejected
    ok, errs = validate_qbxml(xml)              # XSD now matches real QB too
    assert ok, errs


def test_golden_add_response_parses():
    # Real QuickBooks add response. Element is <JournalEntryAddRs>/<JournalEntryRet>.
    add = (_LOGS / "smoke_add_response.xml").read_text(encoding="utf-8")
    assert "<JournalEntryAddRs" in add and "<JournalEntryRet>" in add
    txn_id, severity, message = _parse_add_response(add)
    assert txn_id == "1F3-1784747287"
    assert severity == "Info"


def test_golden_readback_asserts_against_real_response():
    # Real QuickBooks read-back response validates against the sent entry.
    rb = (_LOGS / "smoke_readback_response.xml").read_text(encoding="utf-8")
    assert "<JournalEntryQueryRs" in rb and "<JournalEntryRet>" in rb
    ok, detail = assert_read_back(_smoke_entry(), rb)
    assert ok, detail


def test_emitted_names_match_golden_response_family():
    # The names the builder emits belong to the same JournalEntry* family that
    # real QuickBooks returned -- proving request and response are consistent.
    req = build_gje_request(_smoke_entry())
    add = (_LOGS / "smoke_add_response.xml").read_text(encoding="utf-8")
    assert "JournalEntryAdd" in req and "JournalEntryAddRs" in add
    assert "JournalEntryRet" in add
    for xml in (req, add):
        assert "GeneralJournalEntry" not in xml


# --------------------------------------------------------------------------- #
# 11. Bridge write invocation (BUG 2). The driver's write path must pass a bare
#     -Write switch (read-only FALSE) and NEVER "-ReadOnly:$false".
# --------------------------------------------------------------------------- #


def test_driver_write_invocation_sets_read_only_false(monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = list(args)
        out = args[args.index("-OutputFile") + 1]
        Path(out).write_text("<QBXML/>", encoding="utf-8")
        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    monkeypatch.setattr(qbe_post_mod.subprocess, "run", fake_run)
    client = PostingClient()

    # WRITE invocation -> bare -Write, no -ReadOnly:$false footgun.
    client._run_bridge("C:/wc.qbw", "<QBXML/>", read_only=False, write=True)
    write_args = captured["args"]
    assert "-Write" in write_args
    assert "-IUnderstandThisWrites" in write_args
    assert "-ReadOnly:$false" not in write_args   # the form that fails under -File
    assert "-ReadOnly" not in write_args
    assert "-File" in write_args                    # invoked via -File (the failing mode)

    # READ invocation -> no -Write => read-only session (bridge default).
    client._run_bridge("C:/wc.qbw", "<QBXML/>", read_only=True, write=False)
    read_args = captured["args"]
    assert "-Write" not in read_args
    assert "-ReadOnly" not in read_args


# --------------------------------------------------------------------------- #
# 11b. BUG 6 -- OpenConnection2 must use a stable (non-blank) appID. The bridge
#      opens one brand-new connection per qbXML request, so a batch of a few
#      entries can open 4+ separate connections; a blank appID gives QuickBooks
#      no stable identity to key a persisted "always allow" grant to, and the
#      certificate dialog re-prompted on every single connection during the
#      first live post (2026-07-23). A changed/regressed appID silently forces
#      re-approval on every entity's canonical file all over again.
# --------------------------------------------------------------------------- #


def test_bridge_uses_stable_nonblank_app_id():
    bridge_path = Path(__file__).parent / "qbe_com_bridge.ps1"
    text = bridge_path.read_text(encoding="utf-8")
    assert 'OpenConnection2("", $AppName' not in text, (
        "OpenConnection2 must not be called with a blank appID -- "
        "see BUG 6 in MEMORY.md (2026-07-23)"
    )
    assert "$stableAppId" in text
    import re

    match = re.search(r'\$stableAppId\s*=\s*"([0-9A-Fa-f-]{36})"', text)
    assert match, "expected a fixed 36-char GUID literal assigned to $stableAppId"
    assert match.group(1) == "6F3A9E12-8B44-4C1D-9A2E-5D7F1B3C8E60", (
        "the stable appID changed -- QuickBooks will treat this as a brand-new "
        "application and force re-approval on every entity's canonical file"
    )
    assert "OpenConnection2($stableAppId, $AppName" in text


# --------------------------------------------------------------------------- #
# 12. BUG A -- account-name resolution (pack short name -> exact QB FullName).
# --------------------------------------------------------------------------- #

from qbe_account_resolver import AccountResolver, AccountResolutionError
from qbe_duplicate_gate import parse_transaction_query_page
from qbe_post import BackupError


_FREEMAN_ACCOUNTS = [
    "Central Bank - Checking",
    "UCCU Checking",
    "Freeman Ranch:Arixa Loan Closing Costs",
    "Freeman Ranch:Development/Improvement Costs",
    "Freeman Ranch:Land",
    "Professional Fees",
    "Freeman Ranch:Bank Service Charges",
]


def test_account_resolver_maps_pack_name_to_full_name():
    r = AccountResolver(_FREEMAN_ACCOUNTS)
    # The exact live bug: pack "Development/Improvement" -> QB FullName with parent
    # path + " Costs" suffix. Resolves via containment, uniquely.
    assert r.resolve("Development/Improvement") == "Freeman Ranch:Development/Improvement Costs"
    # exact FullName and exact bank name both pass through.
    assert r.resolve("UCCU Checking") == "UCCU Checking"
    assert r.resolve("Freeman Ranch:Land") == "Freeman Ranch:Land"
    # leaf-exact match.
    assert r.resolve("Land") == "Freeman Ranch:Land"


def test_account_resolver_fails_loudly_on_ambiguous_or_missing():
    r = AccountResolver(_FREEMAN_ACCOUNTS + ["Other:Land"])
    with pytest.raises(AccountResolutionError):
        r.resolve("Land")                       # now ambiguous across two parents
    with pytest.raises(AccountResolutionError):
        r.resolve("Nonexistent Account")        # no match at all


def test_account_resolver_from_account_query_xml():
    xml = (
        '<?qbxml version="13.0"?><QBXML><QBXMLMsgsRs>'
        '<AccountQueryRs statusCode="0" statusSeverity="Info">'
        "<AccountRet><ListID>1</ListID><FullName>Freeman Ranch:Development/Improvement Costs</FullName></AccountRet>"
        "<AccountRet><ListID>2</ListID><FullName>UCCU Checking</FullName></AccountRet>"
        "</AccountQueryRs></QBXMLMsgsRs></QBXML>"
    )
    r = AccountResolver.from_account_query_xml(xml)
    assert r.resolve("Development/Improvement") == "Freeman Ranch:Development/Improvement Costs"


def test_resolve_entry_accounts_rewrites_lines_and_bank():
    r = AccountResolver(_FREEMAN_ACCOUNTS)
    entry = NormalizedEntry(
        entity="Freeman Ranch Partners LLC", txn_date="2026-02-10",
        bank_account="UCCU Checking",
        lines=[
            JournalLine("Development/Improvement", to_amount("5000.00"), "debit"),
            JournalLine("UCCU Checking", to_amount("5000.00"), "credit"),
        ],
    )
    resolved = driver.resolve_entry_accounts(entry, r)
    accts = {ln.account for ln in resolved.lines}
    assert "Freeman Ranch:Development/Improvement Costs" in accts
    assert resolved.bank_account == "UCCU Checking"
    assert resolved.is_balanced()


# --------------------------------------------------------------------------- #
# 13. BUG B -- gate iterator pagination (accumulate ALL pages).
# --------------------------------------------------------------------------- #


def _txn_query_page(txn_ids, iterator_id="", remaining=0):
    rets = "".join(
        f"<TransactionRet><TxnID>{t}</TxnID><TxnType>Check</TxnType>"
        f"<TxnDate>2026-01-0{i+1}</TxnDate><Amount>-{100+i}.00</Amount>"
        f"<AccountRef><FullName>UCCU Checking</FullName></AccountRef>"
        f"</TransactionRet>"
        for i, t in enumerate(txn_ids)
    )
    attrs = 'statusCode="0" statusSeverity="Info"'
    if iterator_id:
        attrs += f' iteratorID="{iterator_id}" iteratorRemainingCount="{remaining}"'
    return (
        '<?qbxml version="13.0"?><QBXML><QBXMLMsgsRs>'
        f"<TransactionQueryRs {attrs}>{rets}</TransactionQueryRs>"
        "</QBXMLMsgsRs></QBXML>"
    )


def test_parse_transaction_query_page_reads_iterator_attrs():
    page = _txn_query_page(["A", "B"], iterator_id="{abc}", remaining=5)
    rets, iterator_id, remaining = parse_transaction_query_page(page)
    assert [r.txn_id for r in rets] == ["A", "B"]
    assert iterator_id == "{abc}"
    assert remaining == 5


def test_load_existing_paginates_until_remaining_zero(monkeypatch):
    gate = DuplicateGate(page_size=2)
    # Page 1: 2 txns, 3 remaining. Page 2 (Continue): 3 txns, 0 remaining.
    pages = [
        _txn_query_page(["A", "B"], iterator_id="{it}", remaining=3),
        _txn_query_page(["C", "D", "E"], iterator_id="{it}", remaining=0),
    ]
    sent = []

    def fake_run_query(self, working_copy_path, request_xml):
        sent.append(request_xml)
        return pages[len(sent) - 1]

    monkeypatch.setattr(DuplicateGate, "_run_query", fake_run_query)
    txns = gate.load_existing("C:/wc.qbw", "2026-01-01", "2026-12-31")
    assert [t.txn_id for t in txns] == ["A", "B", "C", "D", "E"]   # all pages accumulated
    assert len(sent) == 2
    assert 'iterator="Start"' in sent[0]
    assert 'iterator="Continue"' in sent[1] and "{it}" in sent[1]
    # Cached: a second call does not re-query.
    txns2 = gate.load_existing("C:/wc.qbw", "2026-01-01", "2026-12-31")
    assert len(sent) == 2 and [t.txn_id for t in txns2] == ["A", "B", "C", "D", "E"]


# --------------------------------------------------------------------------- #
# 14. BUG C -- backup runs PRE-OPEN; post_entry refuses without a recorded backup.
# --------------------------------------------------------------------------- #


def test_post_entry_refuses_without_pre_open_backup(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    _install_stub_bridge(client, _add_response(), _readback_xml())
    gate = _StubGate(existing=[])
    tracker = _funded_tracker(entry)
    # No prepare_pre_open_backup call -> verify must refuse (BackupError), no write.
    with pytest.raises(BackupError):
        client.post_entry(entry, wc, live=True, gate=gate, balance_tracker=tracker)


def test_prepare_pre_open_backup_then_verify_passes(tmp_path):
    entry = _simple_entry()
    client, wc = _live_client_and_wc(tmp_path)
    result = client.prepare_pre_open_backup(entry.entity, wc)
    assert Path(result.backup_path).is_file()
    assert result.source_sha256 == result.backup_sha256
    # verify now finds the manifest row (does not copy the possibly-open file).
    row = client.verify_pre_open_backup(wc)
    assert row["path"].casefold() == str(Path(wc)).casefold()
