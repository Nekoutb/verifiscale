"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- brigades ---
    op.create_table(
        "brigades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- users ---
    user_role = postgresql.ENUM("AUDITEUR", "SUPERVISEUR", "CHEF_BRIGADE", "ADMIN", name="userrole", create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="AUDITEUR"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("brigade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brigades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # --- taxpayers ---
    tax_regime = postgresql.ENUM("REEL", "SIMPLIFIE", "LIBERATOIRE", "INCONNU", name="taxregime", create_type=False)
    tax_regime.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "taxpayers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("niu", sa.String(32), nullable=False, unique=True),
        sa.Column("raison_sociale", sa.String(512), nullable=False),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("sector", sa.String(128), nullable=True),
        sa.Column("regime", tax_regime, nullable=False, server_default="REEL"),
        sa.Column("fca_active", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_taxpayers_niu", "taxpayers", ["niu"])

    # --- audit_cases ---
    audit_status = postgresql.ENUM("PLANIFICATION", "EN_COURS", "CONTRADICTOIRE", "RAPPORT", "NOTIFIE", "CLOS", name="auditstatus", create_type=False)
    audit_status.create(op.get_bind(), checkfirst=True)
    risk_level = postgresql.ENUM("FAIBLE", "MOYEN", "ELEVE", name="risklevel", create_type=False)
    risk_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "audit_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("reference", sa.String(64), nullable=False, unique=True),
        sa.Column("taxpayer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("taxpayers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("brigade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brigades.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", audit_status, nullable=False, server_default="PLANIFICATION"),
        sa.Column("risk_level", risk_level, nullable=False, server_default="MOYEN"),
        sa.Column("avis_verification_date", sa.Date, nullable=True),
        sa.Column("debut_intervention_date", sa.Date, nullable=True),
        sa.Column("fin_intervention_date", sa.Date, nullable=True),
        sa.Column("notification_date", sa.Date, nullable=True),
        sa.Column("reponse_contribuable_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_cases_reference", "audit_cases", ["reference"])

    # --- datasets ---
    dataset_kind = postgresql.ENUM(
        "TRIAL_BALANCE", "GENERAL_LEDGER", "FEC", "JOURNAL", "SUB_LEDGER_AP", "SUB_LEDGER_AR",
        "MONTHLY_RETURN", "ANNUAL_RETURN", "INVOICE", "CONTRACT", "PAYROLL",
        name="datasetkind", create_type=False,
    )
    dataset_kind.create(op.get_bind(), checkfirst=True)
    dataset_status = postgresql.ENUM("UPLOADED", "PARSING", "PARSED", "PARSE_ERROR", name="datasetstatus", create_type=False)
    dataset_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", dataset_kind, nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("status", dataset_status, nullable=False, server_default="UPLOADED"),
        sa.Column("rows_count", sa.Integer, nullable=True),
        sa.Column("parse_error", sa.String(2048), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB, nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- trial_balance_lines ---
    op.create_table(
        "trial_balance_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_code", sa.String(32), nullable=False),
        sa.Column("account_name", sa.String(512), nullable=False),
        sa.Column("opening_debit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("opening_credit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("period_debit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("period_credit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("closing_debit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("closing_credit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tb_dataset_acct", "trial_balance_lines", ["dataset_id", "account_code"])

    # --- journal_entries ---
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("piece_number", sa.String(64), nullable=False),
        sa.Column("journal_code", sa.String(16), nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_je_dataset_piece", "journal_entries", ["dataset_id", "piece_number"])
    op.create_index("ix_je_dataset_date", "journal_entries", ["dataset_id", "entry_date"])

    # --- journal_entry_lines ---
    op.create_table(
        "journal_entry_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("account_code", sa.String(32), nullable=False, index=True),
        sa.Column("account_name", sa.String(512), nullable=True),
        sa.Column("libelle", sa.String(1024), nullable=True),
        sa.Column("debit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("lettrage", sa.String(32), nullable=True),
    )

    # --- control_runs / control_findings ---
    control_severity = postgresql.ENUM("INFO", "LOW", "MEDIUM", "HIGH", "BLOCKING", name="controlseverity", create_type=False)
    control_severity.create(op.get_bind(), checkfirst=True)
    control_status = postgresql.ENUM("PENDING", "RUNNING", "SUCCESS", "FAILED", name="controlstatus", create_type=False)
    control_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "control_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("audit_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("triggered_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", control_status, nullable=False, server_default="PENDING"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_table(
        "control_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("control_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("control_code", sa.String(16), nullable=False, index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("severity", control_severity, nullable=False),
        sa.Column("legal_reference", sa.String(256), nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
        sa.Column("estimated_impact_xaf", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_ip", postgresql.INET, nullable=True),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=True, index=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("signature", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("control_findings")
    op.drop_table("control_runs")
    op.drop_table("journal_entry_lines")
    op.drop_table("journal_entries")
    op.drop_table("trial_balance_lines")
    op.drop_table("datasets")
    op.drop_table("audit_cases")
    op.drop_table("taxpayers")
    op.drop_table("users")
    op.drop_table("brigades")
    for enum_name in (
        "controlstatus", "controlseverity", "datasetstatus", "datasetkind",
        "risklevel", "auditstatus", "taxregime", "userrole",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
