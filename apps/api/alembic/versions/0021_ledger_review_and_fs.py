"""Ledger line review flags + FINANCIAL_STATEMENTS dataset kind

Revision ID: 0021_ledger_review_and_fs
Revises: 0020_dataset_control_totals
Create Date: 2026-08-12

Two additions:
  * ledger_line_review — per-transaction auditor flags (« justification reçue »,
    « masquer, transaction contrepassée ») for the comptes 46XX / 4711 / 4712
    analyses.
  * DatasetKind.FINANCIAL_STATEMENTS — états financiers (Excel / PDF).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0021_ledger_review_and_fs"
down_revision = "0020_dataset_control_totals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE datasetkind ADD VALUE IF NOT EXISTS 'FINANCIAL_STATEMENTS'")

    reviewmodule = postgresql.ENUM("SHAREHOLDER", "SUNDRY", name="reviewmodule",
                                   create_type=False)
    reviewmodule.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ledger_line_review",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module", reviewmodule, nullable=False),
        sa.Column("piece_number", sa.String(128), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(64), nullable=False),
        sa.Column("justified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hidden_offset", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(1024), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("audit_case_id", "module", "piece_number", "line_number",
                            name="uq_ledger_review_line"),
    )
    op.create_index("ix_ledger_review_case", "ledger_line_review", ["audit_case_id"])


def downgrade() -> None:
    op.drop_index("ix_ledger_review_case", table_name="ledger_line_review")
    op.drop_table("ledger_line_review")
    op.execute("DROP TYPE IF EXISTS reviewmodule")
    # datasetkind enum value is additive and left in place.
