"""init_canonical — multi-entity canonical store (SPEC §6 / §13).

Creates companies, vendors, bills, proof_bundles, audit_rows with all FKs,
CHECK constraints, and indexes (incl. the pg_trgm GIN index for unified search).
Idempotent extension creation; clean DROP ... CASCADE down-path.

Revision ID: 20260626_1200
Revises:
Create Date: 2026-06-26 12:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260626_1200"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions (safe to re-run).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    op.execute(
        """
        CREATE TABLE companies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            legal_name VARCHAR(255) NOT NULL,
            qb_file_id VARCHAR(128) UNIQUE,
            entity_type VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE vendors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
            qb_list_id VARCHAR(128),
            qb_edit_sequence VARCHAR(64),
            name VARCHAR(255) NOT NULL,
            bank_fingerprint VARCHAR(256),
            swarmscore INT,
            raw_extensions JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE proof_bundles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind VARCHAR(24) NOT NULL,
            vcap_state VARCHAR(24),
            proof_hash CHAR(64),
            proof_signature TEXT,
            passed BOOLEAN NOT NULL DEFAULT false,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE bills (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id),
            vendor_id UUID NOT NULL REFERENCES vendors(id),
            qb_txn_id VARCHAR(128),
            qb_edit_sequence VARCHAR(64),
            po_ref VARCHAR(128),
            amount DECIMAL(14,2) NOT NULL CONSTRAINT ck_bills_amount_nonneg CHECK (amount >= 0),
            status VARCHAR(24) NOT NULL DEFAULT 'drafted',
            invoiceproof_bundle_id UUID REFERENCES proof_bundles(id),
            raw_extensions JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE audit_rows (
            row_id BIGSERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            action_type VARCHAR(48) NOT NULL,
            tool_name VARCHAR(64),
            inputs_json JSONB,
            outputs_json JSONB,
            actor VARCHAR(64) NOT NULL,
            prev_hash CHAR(64) NOT NULL,
            row_hash CHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute("CREATE INDEX idx_vendors_company ON vendors(company_id);")
    op.execute("CREATE INDEX idx_bills_company ON bills(company_id);")
    op.execute("CREATE INDEX idx_bills_vendor ON bills(vendor_id);")
    op.execute("CREATE INDEX idx_bills_status ON bills(status);")
    op.execute("CREATE INDEX idx_audit_session ON audit_rows(session_id);")
    op.execute(
        "CREATE INDEX idx_vendors_name_trgm ON vendors USING gin (name gin_trgm_ops);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_rows, bills, proof_bundles, vendors, companies CASCADE;")
