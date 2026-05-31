"""Dons et libéralités — evidence + registre OING

Revision ID: 0010_dons_liberalites
Revises: 0009_recon_cache
Create Date: 2026-05-25

CGI Cameroun, Art. 7 — dons et libéralités:
  - Principle : non-deductible.
  - Exception : versements aux œuvres d'intérêt général situées au Cameroun,
                plafonnés à 5‰ du CA HT.

Two tables:
  - donation_evidence            : per-GL-line justificatifs + verdict
  - registre_organismes_agrees   : shared master data of beneficiary orgs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM


revision = "0010_dons_liberalites"
down_revision = "0009_recon_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums (guard with DO/EXISTS — see migration 0007 for rationale) ───────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'donationdockind') THEN
                CREATE TYPE donationdockind AS ENUM (
                    'RECU','CONVENTION','STATUTS','AGREMENT','VIREMENT','AUTRE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'donationverdict') THEN
                CREATE TYPE donationverdict AS ENUM (
                    'ELIGIBLE','NON_ELIGIBLE','A_REINSTRUIRE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'donationverdictsource') THEN
                CREATE TYPE donationverdictsource AS ENUM (
                    'AUTO_GL','DOC_EXTRACTED','MANUAL_OVERRIDE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orgnature') THEN
                CREATE TYPE orgnature AS ENUM (
                    'PHILANTHROPIQUE','EDUCATIF','SPORTIF','SCIENTIFIQUE',
                    'SOCIAL','CULTUREL','FAMILIAL','RECHERCHE','AUTRE'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orgstatut') THEN
                CREATE TYPE orgstatut AS ENUM (
                    'AGREE','EN_INSTRUCTION','REFUSE','EXPIRE','INCONNU'
                );
            END IF;
        END $$;
    """)

    doc_kind = ENUM(name="donationdockind", create_type=False)
    verdict = ENUM(name="donationverdict", create_type=False)
    verdict_source = ENUM(name="donationverdictsource", create_type=False)
    org_nature = ENUM(name="orgnature", create_type=False)
    org_statut = ENUM(name="orgstatut", create_type=False)

    # ── registre_organismes_agrees : shared org master data ───────────────────
    op.create_table(
        "registre_organismes_agrees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("nom", sa.String(512), nullable=False, index=True),
        sa.Column("niu", sa.String(32), unique=True),
        sa.Column("pays", sa.String(8), nullable=False, server_default="CM"),
        sa.Column("adresse", sa.String(1024)),
        sa.Column("nature", org_nature, nullable=False, server_default="AUTRE"),
        sa.Column("agrement_num", sa.String(128)),
        sa.Column("agrement_date", sa.Date),
        sa.Column("agrement_autorite", sa.String(256)),
        sa.Column("statut", org_statut, nullable=False, server_default="INCONNU"),
        sa.Column("notes", sa.String(2048)),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── donation_evidence : one row per uploaded document, linked to GL line ─
    op.create_table(
        "donation_evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # journal_entry_lines.id — keep nullable so a verdict can be recorded
        # against a logical "line key" (piece+line_number) when the GL is
        # re-imported (line UUID changes but business key stays).
        sa.Column("gl_line_id", UUID(as_uuid=True),
                  sa.ForeignKey("journal_entry_lines.id", ondelete="SET NULL")),
        sa.Column("piece_number", sa.String(64), nullable=False, index=True),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("slip_id", sa.String(64), index=True),     # DJP tracker
        sa.Column("doc_kind", doc_kind, nullable=False, server_default="AUTRE"),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("extracted", JSONB),                        # Claude output
        sa.Column("organisme_id", UUID(as_uuid=True),
                  sa.ForeignKey("registre_organismes_agrees.id", ondelete="SET NULL")),
        sa.Column("verdict", verdict, nullable=False, server_default="A_REINSTRUIRE"),
        sa.Column("verdict_reason", sa.String(2048)),
        sa.Column("verdict_source", verdict_source, nullable=False,
                  server_default="AUTO_GL"),
        sa.Column("verdict_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verdict_at", sa.DateTime(timezone=True)),
        sa.Column("uploaded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_donation_evidence_case_piece_line",
        "donation_evidence",
        ["audit_case_id", "piece_number", "line_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_donation_evidence_case_piece_line", table_name="donation_evidence")
    op.drop_table("donation_evidence")
    op.drop_table("registre_organismes_agrees")
    op.execute("DROP TYPE IF EXISTS donationdockind")
    op.execute("DROP TYPE IF EXISTS donationverdict")
    op.execute("DROP TYPE IF EXISTS donationverdictsource")
    op.execute("DROP TYPE IF EXISTS orgnature")
    op.execute("DROP TYPE IF EXISTS orgstatut")
