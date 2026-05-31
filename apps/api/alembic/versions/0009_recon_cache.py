"""Reconciliation result cache

Revision ID: 0009_recon_cache
Revises: 0008_widen_gl
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "0009_recon_cache"
down_revision = "0008_widen_gl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_cache",
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_cache")
