"""Unicité par organisation : taxpayers.niu et audit_cases.reference.

Deux cabinets différents peuvent légitimement auditer le MÊME contribuable
(même NIU) — l'unicité globale forçait la réutilisation inter-organisations
du même enregistrement Taxpayer (fuite de données croisée). Idem pour les
références de dossier : chaque organisation a sa propre séquence CAS-….

Revision ID: 0024_multitenant_uniques
Revises: 0023_must_change_password
Create Date: 2026-08-16
"""
from alembic import op

revision = "0024_multitenant_uniques"
down_revision = "0023_must_change_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("taxpayers_niu_key", "taxpayers", type_="unique")
    op.create_unique_constraint(
        "uq_taxpayers_org_niu", "taxpayers", ["organization_id", "niu"]
    )
    op.drop_constraint("audit_cases_reference_key", "audit_cases", type_="unique")
    op.create_unique_constraint(
        "uq_audit_cases_org_reference", "audit_cases", ["organization_id", "reference"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_audit_cases_org_reference", "audit_cases", type_="unique")
    op.create_unique_constraint("audit_cases_reference_key", "audit_cases", ["reference"])
    op.drop_constraint("uq_taxpayers_org_niu", "taxpayers", type_="unique")
    op.create_unique_constraint("taxpayers_niu_key", "taxpayers", ["niu"])
