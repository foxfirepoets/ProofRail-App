"""CHUNK_7B: row-confidence on draw_lines (table-aware extraction).

Adds draw_lines.row_confidence (exact | reconstructed | needs_review | unrecoverable) so the
quality of each reconstructed Builder's Draw Request Summary line is queryable and reportable.

Revision ID: 20260630_1000
Revises: 20260629_1000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260630_1000"
down_revision = "20260629_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "draw_lines",
        sa.Column(
            "row_confidence",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("draw_lines", "row_confidence")
