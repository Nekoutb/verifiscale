"""Add MonthlyReturn + PaymentProof tables; extend DatasetKind enum.

Revision ID: 0003_tax_returns
Revises: 0002_user_contact_fields
Create Date: 2026-05-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_tax_returns"
down_revision: Union[str, None] = "0002_user_contact_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# New DatasetKind values to add to existing enum
NEW_DATASET_KINDS = ["PAYMENT_PROOF", "DIPE", "PATENTE_AVIS", "FONCIER_AVIS"]


def upgrade() -> None:
    # ── Extend existing datasetkind enum with new values ─────────────────
    for value in NEW_DATASET_KINDS:
        op.execute(f"ALTER TYPE datasetkind ADD VALUE IF NOT EXISTS '{value}'")

    # ── Create new enums ─────────────────────────────────────────────────
    tax_type = postgresql.ENUM(
        "TVA", "IRPP_SALAIRES", "CNPS", "TSR", "PRECOMPTE_LOYERS", "PRECOMPTE_ACHATS",
        "IRCM", "DROIT_TIMBRE", "CFC", "FNE", "RAV",
        "ACOMPTE_IS", "IS_ANNUEL", "PATENTE", "FONCIER",
        name="taxtype", create_type=False,
    )
    tax_type.create(op.get_bind(), checkfirst=True)

    return_status = postgresql.ENUM(
        "PENDING", "FILED", "PAID", "AMENDED", "LITIGATION",
        name="returnstatus", create_type=False,
    )
    return_status.create(op.get_bind(), checkfirst=True)

    payment_method = postgresql.ENUM(
        "VIREMENT", "ESPECES", "CHEQUE", "MOBILE_MONEY", "COMPENSATION",
        name="paymentmethod", create_type=False,
    )
    payment_method.create(op.get_bind(), checkfirst=True)

    # ── monthly_returns ──────────────────────────────────────────────────
    op.create_table(
        "monthly_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tax_type", tax_type, nullable=False, index=True),
        sa.Column("period_year", sa.Integer, nullable=False),
        sa.Column("period_month", sa.Integer, nullable=True),
        sa.Column("period_quarter", sa.Integer, nullable=True),
        sa.Column("filing_date", sa.Date, nullable=True),
        sa.Column("filing_deadline", sa.Date, nullable=False),
        sa.Column("declared_amount", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("base_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_reporte", sa.Numeric(20, 2), nullable=True),
        sa.Column("source_dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB, nullable=True),
        sa.Column("status", return_status, nullable=False, server_default="PENDING"),
        sa.Column("notes", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_monthly_returns_case_tax_period",
        "monthly_returns",
        ["audit_case_id", "tax_type", "period_year", "period_month"],
    )

    # ── payment_proofs ───────────────────────────────────────────────────
    op.create_table(
        "payment_proofs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("monthly_return_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("monthly_returns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("payment_date", sa.Date, nullable=False),
        sa.Column("amount_paid", sa.Numeric(20, 2), nullable=False),
        sa.Column("reference", sa.String(128), nullable=True),
        sa.Column("method", payment_method, nullable=False, server_default="VIREMENT"),
        sa.Column("bank", sa.String(255), nullable=True),
        sa.Column("source_dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payment_proofs")
    op.drop_index("ix_monthly_returns_case_tax_period", table_name="monthly_returns")
    op.drop_table("monthly_returns")
    for enum_name in ("paymentmethod", "returnstatus", "taxtype"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
    # Note: cannot DROP VALUE from an enum in PostgreSQL — DatasetKind values stay.
