"""Add tax_center + contact + legal fields to taxpayers

Revision ID: 0006_tp_audit
Revises: 0005_inventory_summary
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_tp_audit"
down_revision = "0005_inventory_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("taxpayers", sa.Column("tax_center", sa.String(128), nullable=True))
    op.add_column("taxpayers", sa.Column("legal_form", sa.String(32), nullable=True))
    op.add_column("taxpayers", sa.Column("capital_social", sa.Numeric(20, 2), nullable=True))
    op.add_column("taxpayers", sa.Column("activity_start_date", sa.Date(), nullable=True))
    op.add_column("taxpayers", sa.Column("contact_name", sa.String(256), nullable=True))
    op.add_column("taxpayers", sa.Column("contact_phone", sa.String(64), nullable=True))
    op.add_column("taxpayers", sa.Column("contact_email", sa.String(256), nullable=True))
    op.add_column("taxpayers", sa.Column("rccm", sa.String(64), nullable=True))

    # New LPF document kinds — must commit each ALTER TYPE on its own
    # connection in PostgreSQL.
    for v in (
        "AVIS_VERIFICATION",
        "NOTIFICATION_REDRESSEMENT",
        "REPONSE_CONTRIBUABLE",
        "DEBUT_INTERVENTION_PV",
        "FIN_INTERVENTION_PV",
    ):
        op.execute(f"ALTER TYPE datasetkind ADD VALUE IF NOT EXISTS '{v}'")


def downgrade() -> None:
    for c in (
        "rccm", "contact_email", "contact_phone", "contact_name",
        "activity_start_date", "capital_social", "legal_form", "tax_center",
    ):
        op.drop_column("taxpayers", c)
