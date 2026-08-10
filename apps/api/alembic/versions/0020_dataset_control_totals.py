"""Ingest — per-dataset control totals (file rows/cols vs read rows/cols)

Revision ID: 0020_dataset_control_totals
Revises: 0019_dataset_pending_mapping
Create Date: 2026-08-10

Every upload now records how many rows/columns the FILE contains versus how
many the tool actually READ (+ excluded-with-reason + structural context
rows), so the auditor can verify at a glance that nothing was silently
dropped. Stored as JSONB for flexibility across dataset kinds.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0020_dataset_control_totals"
down_revision = "0019_dataset_pending_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("control_totals", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "control_totals")
