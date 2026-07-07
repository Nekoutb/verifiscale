"""Charges financières — capital_libere flag (Art. 7 B, T2)

Revision ID: 0017_chgfin_capital_libere
Revises: 0016_dons_ai_groups
Create Date: 2026-06-28

T2 (Art. 7 B) requires BOTH a registered loan convention AND fully-released
share capital for interest to be deductible. Adds a case-level boolean so the
auditor can flag when the capital is not entirely paid up. Defaults to true to
preserve existing verdicts.
"""
from alembic import op
import sqlalchemy as sa


revision = "0017_chgfin_capital_libere"
down_revision = "0016_dons_ai_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "charges_fin_case_params",
        sa.Column("capital_libere", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("charges_fin_case_params", "capital_libere")
