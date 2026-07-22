"""Canonical store ORM models (SPEC §6). The system of record — QB Desktop is a batch sink.

Schema is frozen by CHUNK_1_INFRA. Later chunks import these models but must NOT
alter the schema here; schema changes go through new Alembic migrations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CHAR, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    qb_file_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Summa Terra binding (migration 20260627_1300). `role` is nullable in the ORM and
    # DB on purpose — it is backfilled per file (parent vs partnership), never defaulted.
    role: Mapped[str | None] = mapped_column(String(16))
    qb_entity_code: Mapped[str | None] = mapped_column(String(16))
    expense_dev_fee: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))


class Vendor(TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("idx_vendors_company", "company_id"),
        # GIN trigram index for unified search is created in the migration
        # (needs the pg_trgm extension + gin_trgm_ops operator class).
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qb_list_id: Mapped[str | None] = mapped_column(String(128))
    qb_edit_sequence: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_fingerprint: Mapped[str | None] = mapped_column(String(256))
    swarmscore: Mapped[int | None] = mapped_column(Integer)
    raw_extensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ProofBundle(TimestampMixin, Base):
    __tablename__ = "proof_bundles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    vcap_state: Mapped[str | None] = mapped_column(String(24))
    proof_hash: Mapped[str | None] = mapped_column(CHAR(64))
    proof_signature: Mapped[str | None] = mapped_column(String)
    passed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    payload: Mapped[dict | None] = mapped_column(JSONB)


class Bill(TimestampMixin, Base):
    __tablename__ = "bills"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_bills_amount_nonneg"),
        Index("idx_bills_company", "company_id"),
        Index("idx_bills_vendor", "vendor_id"),
        Index("idx_bills_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False
    )
    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("vendors.id"), nullable=False
    )
    qb_txn_id: Mapped[str | None] = mapped_column(String(128))
    qb_edit_sequence: Mapped[str | None] = mapped_column(String(64))
    po_ref: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'drafted'"))
    invoiceproof_bundle_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("proof_bundles.id")
    )
    raw_extensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Summa Terra binding (migration 20260627_1300).
    draw_package_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("draw_packages.id")
    )
    net_amount_due: Mapped[float | None] = mapped_column(Numeric(14, 2))
    approval_id: Mapped[str | None] = mapped_column(String(64))
    # QBWC write-back adapter (migration 20260701_1300, Phase 6 Spec B §13).
    qb_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qb_sync_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class AuditRow(TimestampMixin, Base):
    """AuditProof / AIVS tamper-evident hash chain (SPEC §6.1)."""

    __tablename__ = "audit_rows"
    __table_args__ = (Index("idx_audit_session", "session_id"),)

    row_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    action_type: Mapped[str] = mapped_column(String(48), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(64))
    inputs_json: Mapped[dict | None] = mapped_column(JSONB)
    outputs_json: Mapped[dict | None] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)


# ---------------------------------------------------------------------------
# Summa Terra domain binding (SPEC_SUMMA_TERRA_BINDING.md §6; migration 20260627_1300).
# Dimensioned canonical catalogs + draw-package fee scaffolding. Schema frozen here;
# loaders (app/catalog/) import these but must not alter the schema.
# ---------------------------------------------------------------------------


class Account(TimestampMixin, Base):
    """Canonical chart of accounts, scoped per company file (mirrors Chart_of_Accounts.md)."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_accounts_company_number"),
        Index("idx_accounts_company", "company_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    acct_type: Mapped[str] = mapped_column(String(32), nullable=False)
    statement: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    is_cip_bucket: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    parent_only: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))


class Class(TimestampMixin, Base):
    """Development-phase classes, scoped per company file (SPEC §6.3)."""

    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_classes_company_code"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class CostCode(TimestampMixin, Base):
    """Item / cost-code catalog 001-069 + lifecycle (mirrors Cost_Codes_and_Items.md)."""

    __tablename__ = "cost_codes"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_cost_codes_company_code"),
        Index("idx_costcodes_company", "company_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    # code holds numeric draw codes AND named items (RETAINAGE-HELD=14, FEE-DEV-INC=11).
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    # name is the QB item Description; the FEE-DEV description runs to ~74 chars.
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # The posting account this item maps to (a CIP bucket for draw/lifecycle codes; 20200
    # for retainage; 15500 for FEE-DEV; etc.). NOT always a CIP account — hence the name.
    maps_to_account: Mapped[str] = mapped_column(String(8), nullable=False)
    default_class_code: Mapped[str | None] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # fee_role values up to 'dev_5_partnership' (17 chars).
    fee_role: Mapped[str | None] = mapped_column(String(24))


class CustomerJob(TimestampMixin, Base):
    """Project / property / phase hierarchy (SPEC §6.2)."""

    __tablename__ = "customer_jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "path", name="uq_customer_jobs_company_path"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_path: Mapped[str | None] = mapped_column(String(128))


class DrawPackage(TimestampMixin, Base):
    """The virtual approved draw (SPEC §6.5/§6.7); fee engine fires once per package."""

    __tablename__ = "draw_packages"
    __table_args__ = (
        CheckConstraint("package_total >= 0", name="ck_draw_pkg_total_nonneg"),
        UniqueConstraint("company_id", "draw_number", name="uq_draw_pkg_company_number"),
        Index("idx_drawpkg_company", "company_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False
    )
    draw_number: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_job: Mapped[str] = mapped_column(String(128), nullable=False)
    package_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # Lifecycle: draft | submitted | cm_review | revised | rejected | approved_for_accounting.
    # The fee engine fires ONLY on 'approved_for_accounting' with both approvals true.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'submitted'")
    )
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Summa Terra draw engine (CHUNK_6). Recognition trigger = construction-manager +
    # Mike Watson approval (binding §5.3). Both must be true to draft fees.
    cm_approved: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    watson_approved: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    source_doc_ref: Mapped[str | None] = mapped_column(String(128))
    # Per-project capitalize/expense override; NULL inherits the company default
    # (companies.expense_dev_fee). Never affects commissions (parent-only, always expensed).
    expense_dev_fee_override: Mapped[bool | None] = mapped_column()
    # package_total snapshot captured when fees were drafted; lets the exception engine
    # detect a draw total that changed after drafting.
    fee_drafted_total: Mapped[float | None] = mapped_column(Numeric(14, 2))
    # Real-draw ingestion header (CHUNK_7). package_total holds Total This Draw.
    lender_ref: Mapped[str | None] = mapped_column(String(128))
    borrower: Mapped[str | None] = mapped_column(String(128))
    collateral_address: Mapped[str | None] = mapped_column(String(255))
    draw_date: Mapped[str | None] = mapped_column(String(32))
    total_prior: Mapped[float | None] = mapped_column(Numeric(14, 2))
    raw_extensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class DrawLine(TimestampMixin, Base):
    """One parsed Builder's Draw Request Summary line (CHUNK_7 ingestion).

    Raw source text is preserved for auditability; mappings to vendor/cost_code are nullable
    (unmatched rows are flagged needs_review, never dropped). Idempotent on (draw, line_no).
    """

    __tablename__ = "draw_lines"
    __table_args__ = (
        UniqueConstraint("draw_package_id", "line_no", name="uq_draw_lines_pkg_lineno"),
        Index("idx_draw_lines_pkg", "draw_package_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    draw_package_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("draw_packages.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(8))
    invoice_no: Mapped[str | None] = mapped_column(String(64))
    payable_to: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))
    inv_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    retainage: Mapped[float | None] = mapped_column(Numeric(14, 2))
    amount_due: Mapped[float | None] = mapped_column(Numeric(14, 2))
    vendor_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("vendors.id")
    )
    cost_code_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cost_codes.id")
    )
    needs_review: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    # Table-aware row confidence (CHUNK_7B): exact | reconstructed | needs_review | unrecoverable.
    row_confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'needs_review'")
    )
    raw_text: Mapped[str | None] = mapped_column(String)
    raw_extensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class VendorCandidate(TimestampMixin, Base):
    """A payee from a draw that did not match a known vendor — queued, not auto-created."""

    __tablename__ = "vendor_candidates"
    __table_args__ = (
        UniqueConstraint("company_id", "normalized_name", name="uq_vendor_cand_company_norm"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'candidate'")
    )


class IntercompanyLink(TimestampMixin, Base):
    """A Due-To/Due-From leg pair between a partnership and the parent (SPEC §6.8)."""

    __tablename__ = "intercompany_links"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    partnership_company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False
    )
    parent_company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False
    )
    partnership_account: Mapped[str] = mapped_column(String(8), nullable=False)
    parent_account: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(64))


class FeeEntry(TimestampMixin, Base):
    """One posted leg of the 5/2/1 fee split for a draw (SPEC §6.7)."""

    __tablename__ = "fee_entries"
    __table_args__ = (
        UniqueConstraint("draw_package_id", "fee_role", name="uq_fee_entries_draw_role"),
        Index("idx_feeentries_draw", "draw_package_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    draw_package_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("draw_packages.id"), nullable=False
    )
    book_company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False
    )
    fee_role: Mapped[str] = mapped_column(String(24), nullable=False)
    percent: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    dr_account: Mapped[str] = mapped_column(String(8), nullable=False)
    cr_account: Mapped[str] = mapped_column(String(8), nullable=False)
    intercompany_link_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("intercompany_links.id")
    )
    proof_bundle_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("proof_bundles.id")
    )
    qb_txn_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'drafted'")
    )


class WorkItem(TimestampMixin, Base):
    """Generic accounting work-queue item (FIN-1) — the canonical record behind every
    non-draw, non-GC-bill module (bank feed, credit card, loan draws, interest reserve,
    owner contributions, distributions, intercompany, developer/management fees, vendor
    setup, non-GC invoices). One table, filtered by ``module_key``. Shadow mode only: no QB
    txn id is ever written here. Bank details are stored ONLY as a SHA-256 ``bank_fingerprint``,
    never raw account/routing numbers.
    """

    __tablename__ = "work_items"
    __table_args__ = (
        Index("idx_work_items_company", "company_id"),
        Index("idx_work_items_module", "module_key"),
        Index("idx_work_items_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128))
    counterparty: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    txn_date: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'needs_review'")
    )
    project_ref: Mapped[str | None] = mapped_column(String(128))
    customer_job: Mapped[str | None] = mapped_column(String(128))
    class_ref: Mapped[str | None] = mapped_column(String(64))
    item_cost_code: Mapped[str | None] = mapped_column(String(20))
    # SHA-256 fingerprint only — NEVER a raw bank account / routing number.
    bank_fingerprint: Mapped[str | None] = mapped_column(String(256))
    raw_extensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class BillLine(TimestampMixin, Base):
    """Dimensioned bill detail: cost code + class + customer:job + retainage (SPEC §6.6)."""

    __tablename__ = "bill_lines"
    __table_args__ = (Index("idx_billlines_bill", "bill_id"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    bill_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    cost_code_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cost_codes.id"), nullable=False
    )
    account_number: Mapped[str] = mapped_column(String(8), nullable=False)
    class_code: Mapped[str] = mapped_column(String(8), nullable=False)
    customer_job: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    is_retainage: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
