"""Taxpayer.sector_code — structured sector for specific tax regimes (Tier A)

Revision ID: 0018_taxpayer_sector_code
Revises: 0017_chgfin_capital_libere
Create Date: 2026-06-28

Adds a structured sector code driving sector-aware control branching
(petroleum IS, mining/forestry royalties, COBAC/CIMA provisions, etc.).
Kept as VARCHAR (not enum) so Tier B/C sectors can be added without an
ALTER TYPE migration. Defaults to 'DROIT_COMMUN'.
"""
from alembic import op
import sqlalchemy as sa


revision = "0018_taxpayer_sector_code"
down_revision = "0017_chgfin_capital_libere"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "taxpayers",
        sa.Column("sector_code", sa.String(length=32), nullable=False,
                  server_default="DROIT_COMMUN"),
    )


def downgrade() -> None:
    op.drop_column("taxpayers", "sector_code")
