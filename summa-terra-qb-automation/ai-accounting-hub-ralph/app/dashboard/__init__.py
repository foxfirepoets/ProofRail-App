"""Accounting Work Queue / Operator Dashboard (FinalSpec Phase 1).

A read-mostly, server-rendered control center over the canonical store. Every write action
transitions canonical status ONLY — there is no path from this package to QuickBooks, QBWC,
BillAdd, or payment execution. Shadow mode is absolute and surfaced on every page.
"""
from __future__ import annotations

SHADOW_BANNER = "SHADOW MODE — QB WRITE-BACK DISABLED"
SHADOW_SUBTEXT = "Payments, BillAdd, and live QuickBooks write-back are disabled in this build."
