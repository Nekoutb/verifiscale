"""Petit matériel — 3e base de réintégration (1/3 déductible, 2/3 réintégré)

Revision ID: 0014_petitmat_third_basis
Revises: 0013_petit_materiel
Create Date: 2026-05-29
"""
from alembic import op


revision = "0014_petitmat_third_basis"
down_revision = "0013_petit_materiel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 16 supports ADD VALUE inside a transaction.
    op.execute("ALTER TYPE petitmatbasis ADD VALUE IF NOT EXISTS 'THIRD'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value; no-op.
    pass
