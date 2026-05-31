"""Charges financières — associés prêteurs + params + BEAC cache

Revision ID: 0012_charges_financieres
Revises: 0011_primes_assurance
Create Date: 2026-05-29

CGI Cameroun, Art. 7 B — intérêts servis aux associés :
  T1 taux ≤ TIAO BEAC + 2 pts · T2 convention enregistrée + capital libéré
  T3 avances ≤ 1,5 × capitaux propres (associés ≥ 25 %)
  T4 intérêts ≤ 25 % EBITDA fiscal (associés ≥ 25 %)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM


revision = "0012_charges_financieres"
down_revision = "0011_primes_assurance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chgfinverdict') THEN
                CREATE TYPE chgfinverdict AS ENUM ('ELIGIBLE','NON_ELIGIBLE','A_REINSTRUIRE');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chgfinverdictsource') THEN
                CREATE TYPE chgfinverdictsource AS ENUM ('AUTO','MANUAL_OVERRIDE');
            END IF;
        END $$;
    """)
    verdict = ENUM(name="chgfinverdict", create_type=False)
    verdict_src = ENUM(name="chgfinverdictsource", create_type=False)

    # BEAC rate cache (append-only; latest row wins)
    op.create_table(
        "beac_rate_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tiao_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("marginal_lending_pct", sa.Numeric(6, 3)),
        sa.Column("deposit_pct", sa.Numeric(6, 3)),
        sa.Column("fetched_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("source_url", sa.String(256)),
    )

    # Per-case parameters (capitaux propres, EBITDA fiscal, rate choice)
    op.create_table(
        "charges_fin_case_params",
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("capitaux_propres_xaf", sa.Numeric(20, 2)),
        sa.Column("ebitda_fiscal_xaf", sa.Numeric(20, 2)),
        # 'TIAO' (default) or 'MARGINAL' — which BEAC rate is the basis for T1
        sa.Column("rate_basis", sa.String(16), server_default="TIAO"),
        # taux effectivement retenu (snapshot) + son uplift
        sa.Column("taux_beac_pct", sa.Numeric(6, 3)),
        sa.Column("notes", sa.String(2048)),
        sa.Column("updated_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Shareholder-lender lines
    op.create_table(
        "charges_fin_associe",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("nom", sa.String(512), nullable=False),
        sa.Column("niu", sa.String(32)),
        sa.Column("pct_detention", sa.Numeric(6, 2)),     # % capital/droits de vote
        sa.Column("is_resident", sa.Boolean, server_default=sa.true()),
        sa.Column("avance_moyenne_xaf", sa.Numeric(20, 2)),   # sommes mises à disposition
        sa.Column("interet_servi_xaf", sa.Numeric(20, 2)),    # intérêts comptabilisés
        sa.Column("compte_gl", sa.String(16)),                # 6713 / 6741 / 6742
        # T2 — conditions de forme
        sa.Column("convention_enregistree", sa.Boolean, server_default=sa.false()),
        sa.Column("convention_filename", sa.String(512)),
        sa.Column("convention_storage_path", sa.String(1024)),
        # Verdict (computed, overridable)
        sa.Column("verdict", verdict, nullable=False, server_default="A_REINSTRUIRE"),
        sa.Column("verdict_reason", sa.String(2048)),
        sa.Column("verdict_source", verdict_src, nullable=False, server_default="AUTO"),
        sa.Column("verdict_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verdict_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("charges_fin_associe")
    op.drop_table("charges_fin_case_params")
    op.drop_table("beac_rate_cache")
    op.execute("DROP TYPE IF EXISTS chgfinverdict")
    op.execute("DROP TYPE IF EXISTS chgfinverdictsource")
