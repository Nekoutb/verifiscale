"""Primes d'assurance — contrats + registre assureurs agréés

Revision ID: 0011_primes_assurance
Revises: 0010_dons_liberalites
Create Date: 2026-05-27

CGI Cameroun, Art. 7, A (4) — Primes d'assurance.
SYSCOHADA Révisé : comptes 625X (Primes d'assurance) et 668X (Assurances personnel).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM


revision = "0011_primes_assurance"
down_revision = "0010_dons_liberalites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums (guarded with DO/EXISTS)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insurancebeneftype') THEN
                CREATE TYPE insurancebeneftype AS ENUM (
                    'ENTREPRISE','DIRIGEANT','FAMILLE_DIRIGEANT','PERSONNEL','MIXTE','INCONNU'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insurancetype') THEN
                CREATE TYPE insurancetype AS ENUM (
                    'MULTIRISQUE','MATERIEL_TRANSPORT','RISQUES_EXPLOITATION',
                    'RESP_PRODUCTEUR','INSOLVABILITE_CLIENT','TRANSPORT_VENTES',
                    'SANTE_PERSONNEL','RETRAITE_FIN_CARRIERE','VIE_HOMME_CLE',
                    'VIE_DIRIGEANT','RC','AUTRE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insuranceverdict') THEN
                CREATE TYPE insuranceverdict AS ENUM (
                    'ELIGIBLE','NON_ELIGIBLE','A_REINSTRUIRE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insuranceverdictsource') THEN
                CREATE TYPE insuranceverdictsource AS ENUM (
                    'AUTO_CONTRACT','MANUAL_OVERRIDE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insurerstatut') THEN
                CREATE TYPE insurerstatut AS ENUM (
                    'AGREE','EXPIRE','REFUSE','INCONNU'
                );
            END IF;
        END $$;
    """)

    benef_type    = ENUM(name="insurancebeneftype", create_type=False)
    ins_type      = ENUM(name="insurancetype", create_type=False)
    verdict       = ENUM(name="insuranceverdict", create_type=False)
    verdict_src   = ENUM(name="insuranceverdictsource", create_type=False)
    insurer_stat  = ENUM(name="insurerstatut", create_type=False)

    # registre_assureurs_agrees — shared master data (ASAC)
    op.create_table(
        "registre_assureurs_agrees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("nom", sa.String(512), nullable=False, index=True),
        sa.Column("niu", sa.String(32), unique=True),
        sa.Column("pays", sa.String(8), nullable=False, server_default="CM"),
        sa.Column("agrement_asac", sa.String(128)),
        sa.Column("statut", insurer_stat, nullable=False, server_default="INCONNU"),
        sa.Column("notes", sa.String(2048)),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # contrats_assurance — per uploaded policy
    op.create_table(
        "contrats_assurance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # File reference
        sa.Column("dataset_id", UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="SET NULL")),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("size_bytes", sa.BigInteger),
        # Extracted contract fields
        sa.Column("numero_police", sa.String(128), index=True),
        sa.Column("assureur_nom", sa.String(512), index=True),
        sa.Column("assureur_niu", sa.String(32)),
        sa.Column("assureur_pays", sa.String(8), server_default="CM"),
        sa.Column("assureur_local", sa.Boolean, server_default=sa.false()),
        sa.Column("assureur_id", UUID(as_uuid=True),
                  sa.ForeignKey("registre_assureurs_agrees.id", ondelete="SET NULL")),
        sa.Column("souscripteur", sa.String(512)),
        sa.Column("beneficiaire_nom", sa.String(512)),
        sa.Column("beneficiaire_type", benef_type, nullable=False, server_default="INCONNU"),
        sa.Column("type_assurance", ins_type, nullable=False, server_default="AUTRE"),
        sa.Column("date_debut", sa.Date),
        sa.Column("date_fin", sa.Date),
        sa.Column("prime_annuelle_ttc", sa.Numeric(20, 2)),
        sa.Column("prime_exercice", sa.Numeric(20, 2)),  # prorata temporis
        sa.Column("compte_syscohada", sa.String(8)),     # 6251 / 6685 / 6686 / 6911 / ...
        # Verdict
        sa.Column("verdict", verdict, nullable=False, server_default="A_REINSTRUIRE"),
        sa.Column("verdict_reason", sa.String(2048)),
        sa.Column("verdict_source", verdict_src, nullable=False,
                  server_default="AUTO_CONTRACT"),
        sa.Column("verdict_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verdict_at", sa.DateTime(timezone=True)),
        # Audit trail
        sa.Column("extracted", JSONB),
        sa.Column("uploaded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_contrats_assurance_case_compte",
        "contrats_assurance",
        ["audit_case_id", "compte_syscohada"],
    )


def downgrade() -> None:
    op.drop_index("ix_contrats_assurance_case_compte", table_name="contrats_assurance")
    op.drop_table("contrats_assurance")
    op.drop_table("registre_assureurs_agrees")
    op.execute("DROP TYPE IF EXISTS insurancebeneftype")
    op.execute("DROP TYPE IF EXISTS insurancetype")
    op.execute("DROP TYPE IF EXISTS insuranceverdict")
    op.execute("DROP TYPE IF EXISTS insuranceverdictsource")
    op.execute("DROP TYPE IF EXISTS insurerstatut")
