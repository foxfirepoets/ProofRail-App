"""Migration 002 (reproduction): STV integration layer idempotency columns.

Fix 8 (spec-compliance-audit-stv-integration-layer-2026-06-30.md): this Alembic
file reproduces a migration that was already applied LIVE to the Supabase
canonical store (fdnwlcomuddzmluvbylg) via the ``supabase-aihub`` MCP
``apply_migration`` tool during the STV integration layer build. It is added
here for reproducibility / CI parity — running it against the live database is
a no-op-safe idempotent DDL (``IF NOT EXISTS`` guards), it is NOT expected to
perform first-time provisioning there.

Adds:
  * ``bills.gmail_tracker_id``               UUID, UNIQUE, nullable — the
    idempotency key for POST /intents/bill and POST /intents/payment-confirmed
    (spec §6.3).
  * ``draw_packages.gmail_fee_opportunity_id`` UUID, UNIQUE, nullable — the
    idempotency key for POST /intents/draw (spec §6.3, Fix 8: intents_router.py
    now queries this column directly instead of the raw_extensions->> JSONB
    fallback).

Both models (``app/models.py``) are intentionally NOT updated to map these
columns — they are schema-frozen per CHUNK_1_INFRA, so intents_router.py
accesses them via raw SQL only (see its module docstring).

Revision ID: 20260701_1100
Revises: 20260701_1000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260701_1100"
down_revision = "20260701_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column("gmail_tracker_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_unique_constraint(
        "bills_gmail_tracker_id_key", "bills", ["gmail_tracker_id"]
    )

    op.add_column(
        "draw_packages",
        sa.Column(
            "gmail_fee_opportunity_id", postgresql.UUID(as_uuid=False), nullable=True
        ),
    )
    op.create_unique_constraint(
        "draw_packages_gmail_fee_opportunity_id_key",
        "draw_packages",
        ["gmail_fee_opportunity_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "draw_packages_gmail_fee_opportunity_id_key",
        "draw_packages",
        type_="unique",
    )
    op.drop_column("draw_packages", "gmail_fee_opportunity_id")

    op.drop_constraint("bills_gmail_tracker_id_key", "bills", type_="unique")
    op.drop_column("bills", "gmail_tracker_id")
