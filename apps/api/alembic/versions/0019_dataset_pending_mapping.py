"""Ingest-v2 — DatasetStatus.PENDING_MAPPING

Revision ID: 0019_dataset_pending_mapping
Revises: 0018_taxpayer_sector_code
Create Date: 2026-06-28

GL/TB uploads now land in PENDING_MAPPING: stored but NOT ingested until the
auditor confirms the column mapping. Postgres enums need an explicit ADD VALUE.

Note: ALTER TYPE ... ADD VALUE is allowed inside a transaction on PG 12+ as
long as the new value is not *used* in the same transaction — we only declare
it here, so this is safe.
"""
from alembic import op


revision = "0019_dataset_pending_mapping"
down_revision = "0018_taxpayer_sector_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE datasetstatus ADD VALUE IF NOT EXISTS 'PENDING_MAPPING'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value. Removing it would require
    # recreating the type and rewriting every dependent column — not worth it
    # for a purely additive, backwards-compatible state.
    pass
