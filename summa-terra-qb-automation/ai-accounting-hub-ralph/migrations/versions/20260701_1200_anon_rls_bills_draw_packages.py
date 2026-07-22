"""Migration 003 (reproduction): anon RLS SELECT-only policies on bills / draw_packages.

Fix 8 (spec-compliance-audit-stv-integration-layer-2026-06-30.md): reproduces a
migration already applied LIVE to fdnwlcomuddzmluvbylg via the ``supabase-aihub``
MCP ``apply_migration`` tool. Added here for reproducibility / CI parity only —
NOT re-applied live by running this file (the policies already exist there).

Enables row level security on ``bills`` and ``draw_packages`` and grants the
Supabase ``anon`` role SELECT-only access (``USING (true)``, no ``WITH CHECK`` —
i.e. no INSERT/UPDATE/DELETE path for anon). This is what backs the read-only
Ben's-dashboard "second Supabase client, anon RLS" view described in
spec-stv-integration-layer-2026-06-29.md §6.4/§9 — the anon key is safe to
inject as a browser window global because it can never write.

Revision ID: 20260701_1200
Revises: 20260701_1100
"""
from __future__ import annotations

from alembic import op

revision = "20260701_1200"
down_revision = "20260701_1100"
branch_labels = None
depends_on = None

_TABLES = ("bills", "draw_packages")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY anon_select_{table} ON {table} "
            "FOR SELECT TO anon USING (true)"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS anon_select_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
