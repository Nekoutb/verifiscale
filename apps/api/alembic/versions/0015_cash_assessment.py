"""Cash-payments — per-line current-year decision + exclusions override

Revision ID: 0015_cash_assessment
Revises: 0014_petitmat_third_basis
Create Date: 2026-05-30

Suite à la lettre DGI 5333/MINFI/DGI/LC/L du 4 août 2011 :
  - exceptions : salaires, frais de missions, jetons CA
  - pénalités bifurquées : 33 % IS + 16,5 % IRCM si la charge se rattache à
    l'exercice ; 16,5 % IRCM seul sinon.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM


revision = "0015_cash_assessment"
down_revision = "0014_petitmat_third_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cashcurrentyear') THEN
                CREATE TYPE cashcurrentyear AS ENUM ('YES','NO','UNKNOWN');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cashdecisionsrc') THEN
                CREATE TYPE cashdecisionsrc AS ENUM ('AUTO','MANUAL');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cashexclusionkind') THEN
                CREATE TYPE cashexclusionkind AS ENUM (
                    'SALARY','MISSION','ADMIN_FEE','OTHER'
                );
            END IF;
        END $$;
    """)
    cy = ENUM(name="cashcurrentyear", create_type=False)
    src = ENUM(name="cashdecisionsrc", create_type=False)
    ex_kind = ENUM(name="cashexclusionkind", create_type=False)

    op.create_table(
        "cash_payment_assessment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("piece_number", sa.String(64), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("current_year_decision", cy),
        sa.Column("decision_source", src, nullable=False, server_default="AUTO"),
        sa.Column("decision_reason", sa.String(2048)),
        sa.Column("excluded", sa.Boolean, server_default=sa.false()),
        sa.Column("exclusion_kind", ex_kind),
        sa.Column("updated_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_cash_assessment_key",
        "cash_payment_assessment",
        ["audit_case_id", "piece_number", "line_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_cash_assessment_key", table_name="cash_payment_assessment")
    op.drop_table("cash_payment_assessment")
    op.execute("DROP TYPE IF EXISTS cashcurrentyear")
    op.execute("DROP TYPE IF EXISTS cashdecisionsrc")
    op.execute("DROP TYPE IF EXISTS cashexclusionkind")
