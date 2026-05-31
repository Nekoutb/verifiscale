"""Add audit_type + scope to AuditCase; add period_year + bank_account_code + new kinds to Dataset.

Revision ID: 0004_audit_scope_and_dataset_period
Revises: 0003_tax_returns
Create Date: 2026-05-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_audit_scope"
down_revision: Union[str, None] = "0003_tax_returns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# New DatasetKind values to add to the existing enum
NEW_DATASET_KINDS = [
    "ACCOUNTS_PAYABLE_AGING",
    "ACCOUNTS_RECEIVABLE_AGING",
    "FIXED_ASSETS_REGISTER",
    "BANK_STATEMENT",
]


def upgrade() -> None:
    # ── audit_type enum ──────────────────────────────────────────────────
    audit_type = postgresql.ENUM(
        "VGC", "VP", "CSP", "CI", "CT", "EF",
        name="audittype", create_type=False,
    )
    audit_type.create(op.get_bind(), checkfirst=True)

    # ── AuditCase columns ────────────────────────────────────────────────
    op.add_column(
        "audit_cases",
        sa.Column("audit_type", audit_type, nullable=False, server_default="VGC"),
    )
    op.add_column("audit_cases", sa.Column("starting_year", sa.Integer, nullable=True))
    op.add_column(
        "audit_cases",
        sa.Column("number_of_years", sa.Integer, nullable=True, server_default="1"),
    )

    # Backfill from existing fiscal_year so existing rows have a sane scope
    op.execute(
        "UPDATE audit_cases SET starting_year = fiscal_year WHERE starting_year IS NULL"
    )

    # ── Extend DatasetKind enum ──────────────────────────────────────────
    for value in NEW_DATASET_KINDS:
        op.execute(f"ALTER TYPE datasetkind ADD VALUE IF NOT EXISTS '{value}'")

    # ── Dataset columns ──────────────────────────────────────────────────
    op.add_column("datasets", sa.Column("period_year", sa.Integer, nullable=True))
    op.add_column("datasets", sa.Column("bank_account_code", sa.String(32), nullable=True))
    op.create_index("ix_datasets_period_year", "datasets", ["audit_case_id", "kind", "period_year"])


def downgrade() -> None:
    op.drop_index("ix_datasets_period_year", table_name="datasets")
    op.drop_column("datasets", "bank_account_code")
    op.drop_column("datasets", "period_year")
    op.drop_column("audit_cases", "number_of_years")
    op.drop_column("audit_cases", "starting_year")
    op.drop_column("audit_cases", "audit_type")
    sa.Enum(name="audittype").drop(op.get_bind(), checkfirst=True)
