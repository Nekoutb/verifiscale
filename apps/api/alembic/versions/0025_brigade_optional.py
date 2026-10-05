"""Brigade facultative sur les dossiers d'audit.

La brigade (équipe d'audit, structure héritée de la DGI) était obligatoire
(brigade_id NOT NULL, FK RESTRICT). Résultat : la création d'un dossier
échouait avec « Aucune brigade configurée » pour toute organisation neuve
(aucune brigade par défaut). En multi-tenant les dossiers sont déjà cloisonnés
par organisation ; la brigade ne doit plus conditionner la création.

brigade_id devient nullable et la FK passe en SET NULL (supprimer une brigade
ne doit pas être bloqué par des dossiers qui la référencent).

Revision ID: 0025_brigade_optional
Revises: 0024_multitenant_uniques
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_brigade_optional"
down_revision = "0024_multitenant_uniques"
branch_labels = None
depends_on = None

_FK = "audit_cases_brigade_id_fkey"


def upgrade() -> None:
    op.alter_column("audit_cases", "brigade_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=True)
    op.drop_constraint(_FK, "audit_cases", type_="foreignkey")
    op.create_foreign_key(_FK, "audit_cases", "brigades", ["brigade_id"], ["id"],
                          ondelete="SET NULL")


def downgrade() -> None:
    # Backfill any null brigade to the first available one so the NOT NULL can
    # be restored; if no brigade exists the downgrade cannot proceed.
    op.execute(
        "UPDATE audit_cases SET brigade_id = (SELECT id FROM brigades ORDER BY code LIMIT 1) "
        "WHERE brigade_id IS NULL"
    )
    op.drop_constraint(_FK, "audit_cases", type_="foreignkey")
    op.create_foreign_key(_FK, "audit_cases", "brigades", ["brigade_id"], ["id"],
                          ondelete="RESTRICT")
    op.alter_column("audit_cases", "brigade_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=False)
