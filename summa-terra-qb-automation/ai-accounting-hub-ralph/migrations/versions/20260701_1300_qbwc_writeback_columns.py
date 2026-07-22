"""Migration: QBWC write-back tracking columns on ``bills`` (Phase 6, Spec B).

spec-qbwc-writeback-adapter-2026-07-01.md §13. ``bills.qb_txn_id`` and
``bills.qb_edit_sequence`` already exist (added by the CHUNK_1_INFRA init
migration, 20260626_1200 — see that file's ``bills`` table DDL); this
migration adds the two NEW columns Phase 6 needs plus the partial index that
backs the QBWC adapter's outbox-style query (``bills WHERE status='approved'
AND qb_txn_id IS NULL``, spec §13/§18).

Adds:
  * ``bills.qb_synced_at``      TIMESTAMPTZ, nullable — when the BillAdd
    write-back completed.
  * ``bills.qb_sync_attempts``  INTEGER NOT NULL DEFAULT 0 — incremented on
    each QBWC drain attempt for this bill; used for stale-queue alerting
    (daily digest), NOT a hard retry cap (business-hours polling gaps are
    expected, not failures — spec §7/§8).
  * ``idx_bills_pending_qb_sync`` — partial index on ``bills.status`` WHERE
    ``status='approved' AND qb_txn_id IS NULL``, matching the adapter's exact
    outbox-drain query so the query stays index-only at any real STV volume.

Revision ID: 20260701_1300
Revises: 20260701_1200
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260701_1300"
down_revision = "20260701_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("qb_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bills",
        sa.Column(
            "qb_sync_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "idx_bills_pending_qb_sync",
        "bills",
        ["status"],
        postgresql_where=sa.text("status = 'approved' AND qb_txn_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_bills_pending_qb_sync", table_name="bills")
    op.drop_column("bills", "qb_sync_attempts")
    op.drop_column("bills", "qb_synced_at")
