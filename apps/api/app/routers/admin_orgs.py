"""Plateforme (superadmin) : gestion des clients + invitations d'équipe.

  GET  /admin/organizations            clients + activité (users, dossiers, données)
  POST /admin/organizations            nouveau client + son administrateur
  GET  /admin/organizations/{id}       détail d'un client (dossiers, membres)
  POST /orgs/invitations               (admin d'org) inviter un membre → lien
  GET  /orgs/invitations               invitations en attente de mon org
  GET  /auth/invitations/{token}       (public) infos d'une invitation
  POST /auth/accept-invitation         (public) créer son compte via le lien
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AuditCase, Dataset, Organization, OrgInvitation, User, UserRole,
)
from app.security import get_current_user, hash_password

router = APIRouter(tags=["admin-organizations"])


def require_superadmin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not getattr(user, "is_superadmin", False):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur plateforme.")
    return user


def _org_activity(db: Session, org: Organization) -> dict:
    users = db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar() or 0
    cases = db.query(func.count(AuditCase.id)).filter(AuditCase.organization_id == org.id).scalar() or 0
    case_ids = [r[0] for r in db.query(AuditCase.id).filter(AuditCase.organization_id == org.id).all()]
    datasets = (db.query(func.count(Dataset.id)).filter(Dataset.audit_case_id.in_(case_ids)).scalar() or 0) if case_ids else 0
    last_upload = (db.query(func.max(Dataset.uploaded_at)).filter(Dataset.audit_case_id.in_(case_ids)).scalar()) if case_ids else None
    last_login = db.query(func.max(User.last_login_at)).filter(User.organization_id == org.id).scalar()
    return {
        "id": str(org.id), "name": org.name, "contact_email": org.contact_email,
        "is_platform": org.is_platform, "is_active": org.is_active,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "user_count": users, "case_count": cases, "dataset_count": datasets,
        "last_upload_at": last_upload.isoformat() if last_upload else None,
        "last_login_at": last_login.isoformat() if last_login else None,
    }


@router.get("/admin/organizations")
def list_organizations(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_superadmin)],
):
    orgs = db.query(Organization).order_by(Organization.created_at).all()
    return [_org_activity(db, o) for o in orgs]


@router.post("/admin/organizations")
def create_organization(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_superadmin)],
    payload: dict,
):
    """Body: {name, contact_email, admin_full_name, admin_email, admin_password}"""
    name = str(payload.get("name") or "").strip()
    admin_email = str(payload.get("admin_email") or "").strip().lower()
    admin_password = str(payload.get("admin_password") or "")
    if not name or not admin_email or len(admin_password) < 6:
        raise HTTPException(status_code=400, detail="Nom, email admin et mot de passe (≥6) requis.")
    if db.query(User).filter(User.email == admin_email).first():
        raise HTTPException(status_code=400, detail="Un utilisateur avec cet email existe déjà.")
    org = Organization(name=name, contact_email=str(payload.get("contact_email") or admin_email))
    db.add(org); db.flush()
    admin = User(
        email=admin_email,
        full_name=str(payload.get("admin_full_name") or name),
        password_hash=hash_password(admin_password),
        role=UserRole.ADMIN, is_active=True, organization_id=org.id,
    )
    db.add(admin); db.commit()
    return {"ok": True, "organization_id": str(org.id), "admin_email": admin_email}


@router.get("/admin/organizations/{org_id}")
def organization_detail(
    org_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_superadmin)],
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Client introuvable")
    cases = (
        db.query(AuditCase).filter(AuditCase.organization_id == org.id)
        .order_by(AuditCase.created_at.desc()).all()
    )
    members = db.query(User).filter(User.organization_id == org.id).all()
    return {
        **_org_activity(db, org),
        "members": [{"email": u.email, "full_name": u.full_name, "role": u.role.value,
                     "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
                    for u in members],
        "cases": [{"id": str(c.id), "reference": c.reference,
                   "taxpayer": c.taxpayer.raison_sociale if c.taxpayer else None,
                   "fiscal_year": c.fiscal_year, "status": c.status,
                   "created_at": c.created_at.isoformat() if c.created_at else None}
                  for c in cases],
    }


# ── Invitations d'équipe (admin de l'organisation) ──────────────────────────

@router.post("/orgs/invitations")
def create_invitation(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: dict,
):
    if user.role != UserRole.ADMIN and not getattr(user, "is_superadmin", False):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur de l'organisation.")
    if not user.organization_id:
        raise HTTPException(status_code=400, detail="Aucune organisation rattachée.")
    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Cet email a déjà un compte.")
    inv = OrgInvitation(organization_id=user.organization_id, email=email,
                        role=str(payload.get("role") or "AUDITEUR"), invited_by=user.id)
    db.add(inv); db.commit()
    return {"ok": True, "email": email, "token": inv.token,
            "invite_path": f"/invitation/{inv.token}",
            "expires_at": inv.expires_at.isoformat()}


@router.get("/orgs/invitations")
def list_invitations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if not user.organization_id:
        return []
    invs = (db.query(OrgInvitation)
            .filter(OrgInvitation.organization_id == user.organization_id,
                    OrgInvitation.accepted_at.is_(None))
            .order_by(OrgInvitation.created_at.desc()).all())
    return [{"email": i.email, "role": i.role, "invite_path": f"/invitation/{i.token}",
             "expires_at": i.expires_at.isoformat()} for i in invs]


# ── Acceptation (public) ────────────────────────────────────────────────────

@router.get("/auth/invitations/{token}")
def invitation_info(token: str, db: Annotated[Session, Depends(get_db)]):
    inv = db.query(OrgInvitation).filter(OrgInvitation.token == token).first()
    if not inv or inv.accepted_at is not None:
        raise HTTPException(status_code=404, detail="Invitation introuvable ou déjà utilisée.")
    if inv.expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Invitation expirée.")
    org = db.get(Organization, inv.organization_id)
    return {"email": inv.email, "organization": org.name if org else "", "role": inv.role}


@router.post("/auth/accept-invitation")
def accept_invitation(db: Annotated[Session, Depends(get_db)], payload: dict):
    token = str(payload.get("token") or "")
    full_name = str(payload.get("full_name") or "").strip()
    password = str(payload.get("password") or "")
    inv = db.query(OrgInvitation).filter(OrgInvitation.token == token).first()
    if not inv or inv.accepted_at is not None:
        raise HTTPException(status_code=404, detail="Invitation introuvable ou déjà utilisée.")
    if inv.expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Invitation expirée.")
    if not full_name or len(password) < 6:
        raise HTTPException(status_code=400, detail="Nom complet et mot de passe (≥6) requis.")
    if db.query(User).filter(User.email == inv.email).first():
        raise HTTPException(status_code=400, detail="Cet email a déjà un compte.")
    try:
        role = UserRole(inv.role)
    except ValueError:
        role = UserRole.AUDITEUR
    user = User(email=inv.email, full_name=full_name,
                password_hash=hash_password(password), role=role,
                is_active=True, organization_id=inv.organization_id)
    inv.accepted_at = datetime.utcnow()
    db.add(user); db.commit()
    return {"ok": True, "email": inv.email}
