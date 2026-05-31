"""Add INVENTORY_LISTING DatasetKind + summary_amount column.

Revision ID: 0005_inventory_summary
Revises: 0004_audit_scope
Create Date: 2026-05-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_inventory_summary"
down_revision: Union[str, None] = "0004_audit_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE datasetkind ADD VALUE IF NOT EXISTS 'INVENTORY_LISTING'")
    op.add_column("datasets", sa.Column("summary_amount", sa.Numeric(20, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "summary_amount")
    # Can't DROP VALUE from a Postgres enum — leave INVENTORY_LISTING in place.
