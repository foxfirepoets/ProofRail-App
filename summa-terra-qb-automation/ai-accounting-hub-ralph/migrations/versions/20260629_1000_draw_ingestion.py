"""draw_ingestion — real draw-package ingestion tables + header fields (CHUNK_7).

Adds draw_lines (parsed Builder's Draw Request Summary rows, raw text preserved),
vendor_candidates (unmatched payees queued, never auto-created), and draw_packages header
fields (lender, borrower, collateral, draw date, prior total, raw_extensions). Shadow mode:
canonical-store only, no QuickBooks writes.

Revision ID: 20260629_1000
Revises: 20260628_1000
Create Date: 2026-06-29 10:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260629_1000"
down_revision: str | None = "20260628_1000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE draw_packages
            ADD COLUMN lender_ref VARCHAR(128),
            ADD COLUMN borrower VARCHAR(128),
            ADD COLUMN collateral_address VARCHAR(255),
            ADD COLUMN draw_date VARCHAR(32),
            ADD COLUMN total_prior NUMERIC(14, 2),
            ADD COLUMN raw_extensions JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
    )
    op.execute(
        """
        CREATE TABLE draw_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            draw_package_id UUID NOT NULL REFERENCES draw_packages(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL,
            item_code VARCHAR(8),
            invoice_no VARCHAR(64),
            payable_to VARCHAR(255),
            description VARCHAR(255),
            inv_amount NUMERIC(14, 2),
            retainage NUMERIC(14, 2),
            amount_due NUMERIC(14, 2),
            vendor_id UUID REFERENCES vendors(id),
            cost_code_id UUID REFERENCES cost_codes(id),
            needs_review BOOLEAN NOT NULL DEFAULT false,
            raw_text VARCHAR,
            raw_extensions JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_draw_lines_pkg_lineno UNIQUE (draw_package_id, line_no)
        );
        CREATE INDEX idx_draw_lines_pkg ON draw_lines(draw_package_id);
        """
    )
    op.execute(
        """
        CREATE TABLE vendor_candidates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            source_ref VARCHAR(64),
            status VARCHAR(16) NOT NULL DEFAULT 'candidate',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_vendor_cand_company_norm UNIQUE (company_id, normalized_name)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vendor_candidates;")
    op.execute("DROP TABLE IF EXISTS draw_lines;")
    op.execute(
        """
        ALTER TABLE draw_packages
            DROP COLUMN raw_extensions,
            DROP COLUMN total_prior,
            DROP COLUMN draw_date,
            DROP COLUMN collateral_address,
            DROP COLUMN borrower,
            DROP COLUMN lender_ref;
        """
    )
