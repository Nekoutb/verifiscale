"""Dons & libéralités — cache analyse IA libellé + regroupements par nature

Revision ID: 0016_dons_ai_groups
Revises: 0015_cash_assessment
Create Date: 2026-05-30

Trois ajouts :
  - donation_libelle_analysis : cache de l'analyse Claude par ligne GL
  - donation_group : regroupement de lignes par nature (auditeur)
  - donation_group_line : association group ↔ lignes GL
Extension : donation_evidence.group_id (nullable) pour pièces partagées.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM


revision = "0016_dons_ai_groups"
down_revision = "0015_cash_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enum confidence (réutilisable)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'aiconfidence') THEN
                CREATE TYPE aiconfidence AS ENUM ('HIGH','MEDIUM','LOW');
            END IF;
        END $$;
    """)
    conf = ENUM(name="aiconfidence", create_type=False)

    # 1) Cache Claude par ligne GL
    op.create_table(
        "donation_libelle_analysis",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("piece_number", sa.String(64), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("libelle_hash", sa.String(64), nullable=False),
        sa.Column("verdict_ai", sa.String(32), nullable=False),    # ELIGIBLE / NON_ELIGIBLE / A_REINSTRUIRE
        sa.Column("confidence", conf, nullable=False),
        sa.Column("reason", sa.String(4096)),
        sa.Column("indicators", JSONB),                              # liste de signaux extraits
        sa.Column("model", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_dla_key", "donation_libelle_analysis",
        ["audit_case_id", "piece_number", "line_number"], unique=True,
    )

    # 2) Groupes par nature
    op.create_table(
        "donation_group",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", UUID(as_uuid=True),
                  sa.ForeignKey("audit_cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.String(2048)),
        # verdict applied to ALL member lines unless they have their own evidence
        sa.Column("group_verdict", sa.String(32)),                   # ELIGIBLE / NON_ELIGIBLE / A_REINSTRUIRE
        sa.Column("group_verdict_reason", sa.String(4096)),
        sa.Column("group_verdict_source", sa.String(32), server_default="A_REINSTRUIRE"),  # AUTO_DOC / MANUAL
        sa.Column("ai_confidence", conf),
        sa.Column("ai_indicators", JSONB),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # 3) Association group ↔ ligne GL
    op.create_table(
        "donation_group_line",
        sa.Column("group_id", UUID(as_uuid=True),
                  sa.ForeignKey("donation_group.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("piece_number", sa.String(64), primary_key=True),
        sa.Column("line_number", sa.Integer, primary_key=True),
    )
    op.create_index(
        "ix_dgl_case_lookup",
        "donation_group_line",
        ["piece_number", "line_number"],
    )

    # 4) Extension donation_evidence : permet d'attacher une preuve à un groupe
    op.add_column(
        "donation_evidence",
        sa.Column("group_id", UUID(as_uuid=True),
                  sa.ForeignKey("donation_group.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_column("donation_evidence", "group_id")
    op.drop_index("ix_dgl_case_lookup", table_name="donation_group_line")
    op.drop_table("donation_group_line")
    op.drop_table("donation_group")
    op.drop_index("ix_dla_key", table_name="donation_libelle_analysis")
    op.drop_table("donation_libelle_analysis")
    op.execute("DROP TYPE IF EXISTS aiconfidence")
