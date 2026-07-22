"""FIN-1: generic accounting work-queue table (work_items).

One canonical table behind every non-draw, non-GC-bill shadow module (bank feed, credit card,
loan draws, interest reserve, owner/investor contributions, distributions, intercompany,
developer/management fees, vendor setup, non-GC invoices). Filtered by ``module_key``. Shadow
mode only — no QB txn id column. Bank details are stored ONLY as a SHA-256 ``bank_fingerprint``,
never raw account/routing numbers.

Revision ID: 20260701_1000
Revises: 20260630_1000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260701_1000"
down_revision = "20260630_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("module_key", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=True),
        sa.Column("counterparty", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("txn_date", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'needs_review'"),
            nullable=False,
        ),
        sa.Column("project_ref", sa.String(length=128), nullable=True),
        sa.Column("customer_job", sa.String(length=128), nullable=True),
        sa.Column("class_ref", sa.String(length=64), nullable=True),
        sa.Column("item_cost_code", sa.String(length=20), nullable=True),
        # SHA-256 fingerprint ONLY — never a raw bank account / routing number.
        sa.Column("bank_fingerprint", sa.String(length=256), nullable=True),
        sa.Column(
            "raw_extensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_work_items_company", "work_items", ["company_id"])
    op.create_index("idx_work_items_module", "work_items", ["module_key"])
    op.create_index("idx_work_items_status", "work_items", ["status"])


def downgrade() -> None:
    op.drop_index("idx_work_items_status", table_name="work_items")
    op.drop_index("idx_work_items_module", table_name="work_items")
    op.drop_index("idx_work_items_company", table_name="work_items")
    op.drop_table("work_items")
