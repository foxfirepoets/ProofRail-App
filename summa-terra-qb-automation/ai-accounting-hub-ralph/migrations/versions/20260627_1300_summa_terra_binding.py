"""summa_terra_binding — dimensioned canonical model (SPEC_SUMMA_TERRA_BINDING.md §6/§13).

Adds the QuickBooks dimensions the binding needs: accounts, classes, cost_codes,
customer_jobs, draw_packages, intercompany_links, fee_entries, bill_lines; new columns on
companies and bills; and the v_intercompany_net reconciliation view.

`companies.role` is added NULLABLE with NO blanket default on purpose — a DEFAULT
'partnership' would silently mis-tag the existing parent row, and the loader/assertions
would then reject the parent's own commission/income accounts. The catalog bootstrap sets
role explicitly on the company rows it creates.

Revision ID: 20260627_1300
Revises: 20260626_1200
Create Date: 2026-06-27 13:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260627_1300"
down_revision: str | None = "20260626_1200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- companies / bills column additions ---
    op.execute(
        """
        ALTER TABLE companies
            ADD COLUMN role VARCHAR(16),
            ADD COLUMN qb_entity_code VARCHAR(16),
            ADD COLUMN expense_dev_fee BOOLEAN NOT NULL DEFAULT false;
        """
    )

    # --- catalogs (no cross-deps first) ---
    op.execute(
        """
        CREATE TABLE accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            number VARCHAR(8) NOT NULL,
            name VARCHAR(128) NOT NULL,
            acct_type VARCHAR(32) NOT NULL,
            statement CHAR(2) NOT NULL,
            is_cip_bucket BOOLEAN NOT NULL DEFAULT false,
            parent_only BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_accounts_company_number UNIQUE (company_id, number)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE classes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            code VARCHAR(8) NOT NULL,
            name VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_classes_company_code UNIQUE (company_id, code)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE cost_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            code VARCHAR(20) NOT NULL,
            name VARCHAR(128) NOT NULL,
            maps_to_account VARCHAR(8) NOT NULL,
            default_class_code VARCHAR(8),
            kind VARCHAR(16) NOT NULL,
            fee_role VARCHAR(24),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_cost_codes_company_code UNIQUE (company_id, code)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE customer_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            path VARCHAR(128) NOT NULL,
            parent_path VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_customer_jobs_company_path UNIQUE (company_id, path)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE draw_packages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id),
            draw_number VARCHAR(32) NOT NULL,
            customer_job VARCHAR(128) NOT NULL,
            package_total DECIMAL(14,2) NOT NULL
                CONSTRAINT ck_draw_pkg_total_nonneg CHECK (package_total >= 0),
            status VARCHAR(16) NOT NULL DEFAULT 'submitted',
            approved_by VARCHAR(64),
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_draw_pkg_company_number UNIQUE (company_id, draw_number)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE intercompany_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            partnership_company_id UUID NOT NULL REFERENCES companies(id),
            parent_company_id UUID NOT NULL REFERENCES companies(id),
            partnership_account VARCHAR(8) NOT NULL,
            parent_account VARCHAR(8) NOT NULL,
            amount DECIMAL(14,2) NOT NULL,
            source_ref VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE fee_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            draw_package_id UUID NOT NULL REFERENCES draw_packages(id),
            book_company_id UUID NOT NULL REFERENCES companies(id),
            fee_role VARCHAR(24) NOT NULL,
            percent NUMERIC(5,4) NOT NULL,
            amount DECIMAL(14,2) NOT NULL,
            dr_account VARCHAR(8) NOT NULL,
            cr_account VARCHAR(8) NOT NULL,
            intercompany_link_id UUID REFERENCES intercompany_links(id),
            proof_bundle_id UUID REFERENCES proof_bundles(id),
            qb_txn_id VARCHAR(128),
            status VARCHAR(16) NOT NULL DEFAULT 'drafted',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_fee_entries_draw_role UNIQUE (draw_package_id, fee_role)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE bill_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bill_id UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
            cost_code_id UUID NOT NULL REFERENCES cost_codes(id),
            account_number VARCHAR(8) NOT NULL,
            class_code VARCHAR(8) NOT NULL,
            customer_job VARCHAR(128) NOT NULL,
            amount DECIMAL(14,2) NOT NULL,
            is_retainage BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # --- bills column additions (after draw_packages exists for the FK) ---
    op.execute(
        """
        ALTER TABLE bills
            ADD COLUMN draw_package_id UUID REFERENCES draw_packages(id),
            ADD COLUMN net_amount_due DECIMAL(14,2),
            ADD COLUMN approval_id VARCHAR(64);
        """
    )

    # --- indexes ---
    op.execute("CREATE INDEX idx_accounts_company ON accounts(company_id);")
    op.execute("CREATE INDEX idx_costcodes_company ON cost_codes(company_id);")
    op.execute("CREATE INDEX idx_drawpkg_company ON draw_packages(company_id);")
    op.execute("CREATE INDEX idx_feeentries_draw ON fee_entries(draw_package_id);")
    op.execute("CREATE INDEX idx_billlines_bill ON bill_lines(bill_id);")

    # --- reconciliation view: net per (partnership, parent) pair; close gate targets $0 ---
    op.execute(
        """
        CREATE VIEW v_intercompany_net AS
        SELECT partnership_company_id,
               parent_company_id,
               SUM(amount) AS net
        FROM intercompany_links
        GROUP BY partnership_company_id, parent_company_id;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_intercompany_net;")
    op.execute(
        """
        DROP TABLE IF EXISTS
            bill_lines, fee_entries, intercompany_links, draw_packages,
            cost_codes, customer_jobs, classes, accounts CASCADE;
        """
    )
    op.execute(
        """
        ALTER TABLE bills
            DROP COLUMN IF EXISTS draw_package_id,
            DROP COLUMN IF EXISTS net_amount_due,
            DROP COLUMN IF EXISTS approval_id;
        """
    )
    op.execute(
        """
        ALTER TABLE companies
            DROP COLUMN IF EXISTS role,
            DROP COLUMN IF EXISTS qb_entity_code,
            DROP COLUMN IF EXISTS expense_dev_fee;
        """
    )
