"""Taxpayers."""
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Taxpayer, TaxRegime, User
from app.schemas import TaxpayerCreate, TaxpayerOut
from app.security import get_current_user


router = APIRouter(prefix="/taxpayers", tags=["taxpayers"])

# Cameroon NIU format: prefix M (moral) or P (physical) + 9 digits + uppercase suffix
NIU_PATTERN = re.compile(r"^[MPmp]\d{9,12}[A-Z]$")


def _validate_niu(niu: str) -> str:
    niu = niu.strip().upper()
    if not NIU_PATTERN.match(niu):
        raise HTTPException(status_code=400, detail="Format NIU invalide (attendu : M021xxxxxxxxxX)")
    return niu


@router.get("", response_model=list[TaxpayerOut])
def list_taxpayers(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    q: str | None = Query(default=None, description="Filter on NIU or raison_sociale"),
):
    query = db.query(Taxpayer)
    if not getattr(user, "is_superadmin", False) and user.organization_id is not None:
        query = query.filter(Taxpayer.organization_id == user.organization_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Taxpayer.niu.ilike(like)) | (Taxpayer.raison_sociale.ilike(like)))
    return query.order_by(Taxpayer.raison_sociale).limit(200).all()


@router.post("", response_model=TaxpayerOut, status_code=201)
def create_taxpayer(
    payload: TaxpayerCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    niu = _validate_niu(payload.niu)
    # Unicité du NIU PAR ORGANISATION — un autre cabinet peut auditer le même
    # contribuable sans que cela bloque (ni ne révèle) quoi que ce soit ici.
    org_id = getattr(user, "organization_id", None)
    dup_q = db.query(Taxpayer).filter(Taxpayer.niu == niu)
    dup_q = (dup_q.filter(Taxpayer.organization_id == org_id) if org_id is not None
             else dup_q.filter(Taxpayer.organization_id.is_(None)))
    if dup_q.first():
        raise HTTPException(status_code=409, detail="NIU déjà enregistré")
    try:
        regime = TaxRegime(payload.regime)
    except ValueError:
        raise HTTPException(status_code=400, detail="Régime fiscal invalide")
    tp = Taxpayer(
        niu=niu, raison_sociale=payload.raison_sociale,
        address=payload.address, sector=payload.sector,
        sector_code=payload.sector_code or "DROIT_COMMUN", regime=regime,
        organization_id=org_id,
    )
    db.add(tp)
    db.commit()
    db.refresh(tp)
    return tp
