"""Seed the database with sample brigades, users, taxpayers, an audit case, and
a realistic trial balance so the demo is immediately runnable.

Run inside the API container:
    docker compose exec api python -m scripts.seed
"""
import hashlib
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

# Allow `import app.*` when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AuditCase, AuditStatus, Brigade, Dataset, DatasetKind, DatasetStatus,
    RiskLevel, Taxpayer, TaxRegime, TrialBalanceLine, User, UserRole,
)
from app.security import hash_password

from scripts.sample_data import SAMPLE_TB


def seed(db: Session) -> None:
    if db.query(Brigade).count() > 0:
        print("Already seeded — skipping.")
        return

    print("Seeding brigades…")
    brigades = [
        Brigade(code="DGE",      name="Direction des Grandes Entreprises", region="Centre"),
        Brigade(code="CIME-YDE", name="CIME Yaoundé",                       region="Centre"),
        Brigade(code="CDI-DLA",  name="CDI Douala-Akwa",                    region="Littoral"),
    ]
    db.add_all(brigades)
    db.flush()

    print("Seeding users (mot de passe : Password123!)…")
    pwd = hash_password("Password123!")
    users = [
        User(email="admin@dgi.cm",      full_name="Admin DGI",            role=UserRole.ADMIN,        password_hash=pwd,
             phone_number="+237 6 99 00 11 22", organization="DGI Cameroun — Direction Générale"),
        User(email="b.etoundi@dgi.cm",  full_name="Etoundi Bertrand",     role=UserRole.AUDITEUR,     password_hash=pwd, brigade_id=brigades[0].id,
             phone_number="+237 6 77 12 34 56", organization="DGI Cameroun — DGE"),
        User(email="s.ngono@dgi.cm",    full_name="Ngono Sylvie",         role=UserRole.SUPERVISEUR,  password_hash=pwd, brigade_id=brigades[0].id,
             phone_number="+237 6 99 88 77 66", organization="DGI Cameroun — DGE"),
        User(email="j.mbarga@dgi.cm",   full_name="Mbarga Joseph",        role=UserRole.AUDITEUR,     password_hash=pwd, brigade_id=brigades[1].id,
             phone_number="+237 6 55 44 33 22", organization="DGI Cameroun — CIME Yaoundé"),
        User(email="chef.cdi@dgi.cm",   full_name="Chef de Brigade CDI",  role=UserRole.CHEF_BRIGADE, password_hash=pwd, brigade_id=brigades[2].id,
             phone_number="+237 6 91 23 45 67", organization="DGI Cameroun — CDI Douala-Akwa"),
    ]
    db.add_all(users)
    db.flush()

    print("Seeding taxpayers…")
    taxpayers = [
        Taxpayer(niu="M021712345678P", raison_sociale="SOCIÉTÉ CAMEROUNAISE DE NÉGOCE SA",
                 address="Akwa, Douala", sector="Commerce de gros", regime=TaxRegime.REEL),
        Taxpayer(niu="P081498765432K", raison_sociale="CIMENTERIES DU LITTORAL SARL",
                 address="Bonabéri, Douala", sector="Industrie - BTP", regime=TaxRegime.REEL),
        Taxpayer(niu="M021598732145D", raison_sociale="AGRO SERVICES CAMEROUN SA",
                 address="Bafoussam", sector="Agro-industrie", regime=TaxRegime.REEL),
    ]
    db.add_all(taxpayers)
    db.flush()

    print("Seeding audit cases…")
    cases = [
        AuditCase(
            reference="2026-DGE-001", taxpayer_id=taxpayers[0].id, brigade_id=brigades[0].id,
            assignee_id=users[1].id, fiscal_year=2024,
            period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
            status=AuditStatus.EN_COURS, risk_level=RiskLevel.ELEVE,
            avis_verification_date=date(2026, 2, 1),
        ),
        AuditCase(
            reference="2026-DGE-002", taxpayer_id=taxpayers[1].id, brigade_id=brigades[0].id,
            assignee_id=users[3].id, fiscal_year=2024,
            period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
            status=AuditStatus.PLANIFICATION, risk_level=RiskLevel.MOYEN,
        ),
        AuditCase(
            reference="2025-CIME-014", taxpayer_id=taxpayers[2].id, brigade_id=brigades[1].id,
            assignee_id=users[1].id, fiscal_year=2023,
            period_start=date(2023, 1, 1), period_end=date(2023, 12, 31),
            status=AuditStatus.RAPPORT, risk_level=RiskLevel.FAIBLE,
        ),
    ]
    db.add_all(cases)
    db.flush()

    print("Seeding sample trial balance on first case…")
    sample_bytes = b"seeded-sample-tb"
    sample_hash = hashlib.sha256(sample_bytes).hexdigest()
    ds = Dataset(
        audit_case_id=cases[0].id,
        kind=DatasetKind.TRIAL_BALANCE,
        original_filename="balance_2024_SCNS_SA.xlsx",
        storage_key=f"audits/{cases[0].id}/datasets/seed-{uuid.uuid4()}/sample.xlsx",
        content_hash=sample_hash,
        size_bytes=len(sample_bytes),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        status=DatasetStatus.PARSED,
        rows_count=len(SAMPLE_TB),
        uploaded_by_id=users[1].id,
    )
    db.add(ds)
    db.flush()

    for row in SAMPLE_TB:
        code, name, od, oc, pd_, pc, cd, cc = row
        db.add(TrialBalanceLine(
            dataset_id=ds.id, account_code=code, account_name=name,
            opening_debit=Decimal(od), opening_credit=Decimal(oc),
            period_debit=Decimal(pd_), period_credit=Decimal(pc),
            closing_debit=Decimal(cd), closing_credit=Decimal(cc),
        ))

    db.commit()
    print(f"Done — created {len(brigades)} brigades, {len(users)} users, "
          f"{len(taxpayers)} taxpayers, {len(cases)} audit cases, "
          f"1 trial balance ({len(SAMPLE_TB)} lines) on case {cases[0].reference}.")
    print("\nLogin :  any seeded email  /  password = Password123!")
    print("Try :     /dossiers → 2026-DGE-001 → Données & contrôles → Lancer un contrôle\n")


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
