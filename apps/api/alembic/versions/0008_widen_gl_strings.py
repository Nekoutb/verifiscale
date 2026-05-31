"""Widen GL string columns for long Odoo-style codes

Revision ID: 0008_widen_gl
Revises: 0007_invoices
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_widen_gl"
down_revision = "0007_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # journal_entries
    op.alter_column("journal_entries", "piece_number",
                    type_=sa.String(128), existing_nullable=False)
    op.alter_column("journal_entries", "journal_code",
                    type_=sa.String(64), existing_nullable=False)
    # journal_entry_lines
    op.alter_column("journal_entry_lines", "account_code",
                    type_=sa.String(64), existing_nullable=False)
    op.alter_column("journal_entry_lines", "libelle",
                    type_=sa.String(2048), existing_nullable=True)
    op.alter_column("journal_entry_lines", "lettrage",
                    type_=sa.String(64), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("journal_entry_lines", "lettrage",
                    type_=sa.String(32), existing_nullable=True)
    op.alter_column("journal_entry_lines", "libelle",
                    type_=sa.String(1024), existing_nullable=True)
    op.alter_column("journal_entry_lines", "account_code",
                    type_=sa.String(32), existing_nullable=False)
    op.alter_column("journal_entries", "journal_code",
                    type_=sa.String(16), existing_nullable=False)
    op.alter_column("journal_entries", "piece_number",
                    type_=sa.String(64), existing_nullable=False)
