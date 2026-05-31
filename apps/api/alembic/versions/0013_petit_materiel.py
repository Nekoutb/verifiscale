"""Petit matériel et outillage — overrides par ligne

Revision ID: 0013_petit_materiel
Revises: 0012_charges_financieres
Create Date: 2026-05-29

CGI Cameroun : seuil d'immobilisation obligatoire 500 000 FCFA.
Outillage à main dit petit outillage amorti à 100 %.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM


revision = "0013_petit_materiel"
down_revision = "0012_charges_financieres"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'petitmatqualif') THEN
                CREATE TYPE petitmatqualif AS ENUM (
                    'HAND_TOOL','IT','REPRO','FURNITURE','EQUIPMENT','OTHER','EXCLUDED'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'petitmatbasis') THEN
                CREATE TYPE petitmatbasis AS ENUM ('DIFFERENTIAL','TOTAL');
            END IF;
        END $$;
    """)
    qualif = ENUM(name="petitmatqualif", create_type=False)
    basis = ENUM(name="petitmatbasis", create_type=False)

    op.create_table(
        "petit_materiel_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("piece_number", sa.String(64), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        # Overrides set by the auditor
        sa.Column("qualification", qualif),
        sa.Column("depreciation_rate_pct", sa.Numeric(6, 2)),
        sa.Column("reintegration_basis", basis, server_default="DIFFERENTIAL"),
        sa.Column("verdict_reason", sa.String(2048)),
        sa.Column("excluded", sa.Boolean, server_default=sa.false()),
        sa.Column("updated_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_petit_materiel_line_key",
        "petit_materiel_line",
        ["audit_case_id", "piece_number", "line_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_petit_materiel_line_key", table_name="petit_materiel_line")
    op.drop_table("petit_materiel_line")
    op.execute("DROP TYPE IF EXISTS petitmatqualif")
    op.execute("DROP TYPE IF EXISTS petitmatbasis")
