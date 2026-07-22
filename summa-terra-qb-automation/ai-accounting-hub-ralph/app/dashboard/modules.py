"""Accounting Work Queue module registry.

The dashboard is a modular work queue over all day-to-day real-estate-development accounting
workflows — not just GC draws. ``Draw Review`` is the first FULLY FUNCTIONAL module; the other
modules ship as placeholder/work-queue sections (status ``pending``) under the same shadow
banner. This registry is pure metadata (no DB, no QuickBooks) and drives both the grouped
left-nav and the work-queue landing page.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    group: str
    status: str  # "functional" | "pending"
    route: str
    description: str
    columns: tuple[str, ...]


MODULES: tuple[Module, ...] = (
    Module(
        "draw_review", "Draw Review", "Construction", "functional", "/ui/draws",
        "GC construction draw packages — parse, review, approve/reject, 5/2/1 fee split.",
        ("Draw #", "Project", "Total", "Status", "Confidence"),
    ),
    Module(
        "vendor_bills", "Vendor Bills", "Accounts Payable", "functional", "/ui/vendor-bills",
        "Standard AP vendor bills — intake, vendor match, coding, duplicate + bank-change checks.",
        ("Date", "Vendor", "Bill #", "Amount", "Status"),
    ),
    Module(
        "non_gc_invoices", "Non-GC Invoices", "Accounts Payable", "functional",
        "/ui/m/non_gc_invoices",
        "Non-construction invoices (services, soft costs, professional fees).",
        ("Date", "Vendor", "Invoice #", "Amount", "Status"),
    ),
    Module(
        "bank_feed", "Bank Feed Review", "Banking", "functional", "/ui/m/bank_feed",
        "Bank feed transactions awaiting match and categorization.",
        ("Date", "Account", "Payee", "Amount", "Match"),
    ),
    Module(
        "credit_card", "Credit Card Charges", "Banking", "functional", "/ui/m/credit_card",
        "Credit card charges awaiting receipt match and coding.",
        ("Date", "Card", "Merchant", "Amount", "Receipt"),
    ),
    Module(
        "loan_draws", "Loan Draws", "Financing", "functional", "/ui/m/loan_draws",
        "Construction-loan draw fundings against the lender facility.",
        ("Date", "Lender", "Facility", "Amount", "Status"),
    ),
    Module(
        "interest_reserve", "Interest Reserve Activity", "Financing", "functional",
        "/ui/m/interest_reserve",
        "Interest reserve draws and accruals against the loan facility.",
        ("Date", "Loan", "Type", "Amount", "Balance"),
    ),
    Module(
        "owner_contributions", "Owner/Investor Contributions", "Equity", "functional",
        "/ui/m/owner_contributions",
        "Capital contributions from owners and investors.",
        ("Date", "Entity", "Investor", "Amount", "Status"),
    ),
    Module(
        "distributions", "Distributions", "Equity", "functional", "/ui/m/distributions",
        "Distributions to owners and investors.",
        ("Date", "Entity", "Investor", "Amount", "Status"),
    ),
    Module(
        "intercompany", "Intercompany Reimbursements", "Intercompany", "functional",
        "/ui/m/intercompany",
        "Cross-entity reimbursements and due-to / due-from settlement.",
        ("Date", "From", "To", "Amount", "Status"),
    ),
    Module(
        "developer_fees", "Developer Fees", "Fees", "functional", "/ui/m/developer_fees",
        "Developer fee billing (live 5% calc is shown in the Draw Review fee panel).",
        ("Period", "Entity", "Basis", "5% Fee", "Status"),
    ),
    Module(
        "management_fees", "Management Fees", "Fees", "functional", "/ui/m/management_fees",
        "Recurring management fee billing across entities.",
        ("Period", "Entity", "Basis", "Fee", "Status"),
    ),
    Module(
        "vendor_setup", "Vendor Setup / Bank Changes", "Master Data", "functional",
        "/ui/m/vendor_setup",
        "New vendor setup and vendor bank-detail change review (ATEP gate).",
        ("Date", "Vendor", "Change", "Fingerprint", "Status"),
    ),
    Module(
        "month_end", "Month-End Close Exceptions", "Close", "functional", "/ui/m/month_end",
        "Open exceptions across draws, vendor bills, and work items blocking month-end close.",
        ("Source", "Reference", "Exception", "Amount", "Open"),
    ),
    Module(
        "missing_dimensions", "Missing Customer:Job / Class / Item Cleanup", "Close",
        "functional", "/ui/m/missing_dimensions",
        "Items across modules missing Customer:Job, Class, or Item dimensions.",
        ("Source", "Reference", "Missing", "Amount", "Fix"),
    ),
    # The ONLY remaining pending module: live QuickBooks write-back is intentionally disabled in
    # this shadow build (no QBWC write path exists — see SHADOW banner / AST shadow-safety test).
    Module(
        "qb_sync", "QuickBooks Sync / Write-back", "QuickBooks", "pending",
        "/ui/queue/qb_sync",
        "Live QuickBooks Desktop write-back (QBWC / BillAdd). DISABLED in shadow mode — the "
        "single remaining non-functional module.",
        ("Batch", "Target File", "Items", "Gate", "Status"),
    ),
)

# Display order for groups in the nav and landing page.
GROUP_ORDER: tuple[str, ...] = (
    "Construction", "Accounts Payable", "Banking", "Financing", "Equity",
    "Intercompany", "Fees", "Master Data", "Close", "QuickBooks",
)

_BY_KEY: dict[str, Module] = {m.key: m for m in MODULES}


def get_module(key: str) -> Module | None:
    return _BY_KEY.get(key)


def grouped_modules() -> list[tuple[str, list[Module]]]:
    """Modules grouped by their workflow group, in GROUP_ORDER."""
    buckets: dict[str, list[Module]] = {}
    for m in MODULES:
        buckets.setdefault(m.group, []).append(m)
    return [(g, buckets[g]) for g in GROUP_ORDER if g in buckets]
