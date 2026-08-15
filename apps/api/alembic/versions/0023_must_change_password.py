"""users.must_change_password — mot de passe provisoire à changer

Revision ID: 0023_must_change_password
Revises: 0022_multi_tenant
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_must_change_password"
down_revision = "0022_multi_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(),
                                     nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
