"""Supplier invoices table

Revision ID: 0007_invoices
Revises: 0006_tp_audit
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM


revision = "0007_invoices"
down_revision = "0006_tp_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum via raw SQL so we can guard with DO/EXISTS — SQLAlchemy's
    # checkfirst is unreliable inside an alembic transaction when a previous
    # failed attempt left the type half-committed.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'invoicestatus') THEN
                CREATE TYPE invoicestatus AS ENUM ('PENDING','PROCESSING','PARSED','OCR_ERROR');
            END IF;
        END $$;
    """)
    invoice_status = ENUM(
        "PENDING", "PROCESSING", "PARSED", "OCR_ERROR",
        name="invoicestatus", create_type=False,
    )

    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True), sa.ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", invoice_status, nullable=False, server_default="PENDING"),
        sa.Column("ocr_error", sa.String(2048)),
        sa.Column("supplier_niu", sa.String(32), index=True),
        sa.Column("supplier_name", sa.String(512), index=True),
        sa.Column("supplier_rccm", sa.String(64)),
        sa.Column("supplier_address", sa.String(512)),
        sa.Column("supplier_tax_center", sa.String(128)),
        sa.Column("customer_niu", sa.String(32)),
        sa.Column("customer_name", sa.String(512)),
        sa.Column("invoice_number", sa.String(128), index=True),
        sa.Column("invoice_date", sa.Date, index=True),
        sa.Column("base_ht_xaf", sa.Numeric(20, 2)),
        sa.Column("tva_xaf", sa.Numeric(20, 2)),
        sa.Column("ttc_xaf", sa.Numeric(20, 2)),
        sa.Column("tva_rate_pct", sa.Numeric(5, 2)),
        sa.Column("currency", sa.String(8), server_default="XAF"),
        sa.Column("description", sa.String(2048)),
        sa.Column("control_results", JSONB),
        sa.Column("failed_fond_count", sa.Integer, server_default="0"),
        sa.Column("failed_forme_count", sa.Integer, server_default="0"),
        sa.Column("is_compliant", sa.Boolean, server_default=sa.false(), index=True),
        sa.Column("raw_ocr", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("invoices")
    sa.Enum(name="invoicestatus").drop(op.get_bind(), checkfirst=True)
