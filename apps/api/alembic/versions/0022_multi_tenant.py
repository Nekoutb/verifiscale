"""Multi-tenant: organizations, invitations, org scoping, platform superadmin

Revision ID: 0022_multi_tenant
Revises: 0021_ledger_review_and_fs
Create Date: 2026-08-14

* organizations + org_invitations tables
* users.organization_id / users.is_superadmin
* taxpayers.organization_id / audit_cases.organization_id
* seed: platform org « CM-EA — Plateforme », backfill every existing user /
  taxpayer / case to it, create superadmin contact@cm-ea.com (pwd: admin —
  TO BE CHANGED after first login).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_multi_tenant"
down_revision = "0021_ledger_review_and_fs"
branch_labels = None
depends_on = None

SUPERADMIN_EMAIL = "contact@cm-ea.com"
SUPERADMIN_HASH = "$2b$12$Id9wiKxw4fkRZ1yxHLJW7u5EXm5r8LLS79SRMeOOiHF6b03DtUU0m"  # « admin »


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("is_platform", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "org_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="AUDITEUR"),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_org_inv_org", "org_invitations", ["organization_id"])

    for table in ("users", "taxpayers", "audit_cases"):
        op.add_column(table, sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                                       sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                                       nullable=True))
        op.create_index(f"ix_{table}_org", table, ["organization_id"])
    op.add_column("users", sa.Column("is_superadmin", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))

    # ── seed ────────────────────────────────────────────────────────────────
    conn = op.get_bind()
    org_id = conn.execute(sa.text(
        "INSERT INTO organizations (id, name, contact_email, is_platform) "
        "VALUES (gen_random_uuid(), 'CM-EA — Plateforme', :email, true) RETURNING id"
    ), {"email": SUPERADMIN_EMAIL}).scalar()
    for table in ("users", "taxpayers", "audit_cases"):
        conn.execute(sa.text(f"UPDATE {table} SET organization_id = :oid"), {"oid": org_id})
    existing = conn.execute(sa.text("SELECT id FROM users WHERE email = :e"),
                            {"e": SUPERADMIN_EMAIL}).scalar()
    if existing:
        conn.execute(sa.text(
            "UPDATE users SET is_superadmin = true, organization_id = :oid WHERE id = :id"
        ), {"oid": org_id, "id": existing})
    else:
        conn.execute(sa.text(
            "INSERT INTO users (id, email, full_name, password_hash, role, is_active, "
            "is_superadmin, organization_id) VALUES (gen_random_uuid(), :e, "
            "'CM-EA — Administrateur plateforme', :h, 'ADMIN', true, true, :oid)"
        ), {"e": SUPERADMIN_EMAIL, "h": SUPERADMIN_HASH, "oid": org_id})


def downgrade() -> None:
    op.drop_column("users", "is_superadmin")
    for table in ("users", "taxpayers", "audit_cases"):
        op.drop_index(f"ix_{table}_org", table_name=table)
        op.drop_column(table, "organization_id")
    op.drop_index("ix_org_inv_org", table_name="org_invitations")
    op.drop_table("org_invitations")
    op.drop_table("organizations")
