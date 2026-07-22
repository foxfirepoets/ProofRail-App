"""draw_engine_shadow — approval-trigger + capitalization-policy fields (CHUNK_6).

Adds the columns the shadow draw engine needs on draw_packages:
- widen status to hold 'approved_for_accounting';
- cm_approved / watson_approved — the construction-manager + Mike Watson recognition
  trigger (binding §5.3); the engine drafts fees only when both are true;
- source_doc_ref — source document / file reference for the approved draw;
- expense_dev_fee_override — per-project capitalize-vs-expense override (NULL inherits
  companies.expense_dev_fee); never affects parent-only commissions;
- fee_drafted_total — package_total snapshot at draft time, so the exception engine can
  detect a draw total that changed after its fees were drafted.

No QuickBooks writes; this is canonical-store only (shadow mode).

Revision ID: 20260628_1000
Revises: 20260627_1300
Create Date: 2026-06-28 10:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260628_1000"
down_revision: str | None = "20260627_1300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE draw_packages
            ALTER COLUMN status TYPE VARCHAR(32),
            ADD COLUMN cm_approved BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN watson_approved BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN source_doc_ref VARCHAR(128),
            ADD COLUMN expense_dev_fee_override BOOLEAN,
            ADD COLUMN fee_drafted_total NUMERIC(14, 2);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE draw_packages
            DROP COLUMN fee_drafted_total,
            DROP COLUMN expense_dev_fee_override,
            DROP COLUMN source_doc_ref,
            DROP COLUMN watson_approved,
            DROP COLUMN cm_approved,
            ALTER COLUMN status TYPE VARCHAR(16);
        """
    )
