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
    _: Annotated[User, Depends(get_current_user)],
    q: str | None = Query(default=None, description="Filter on NIU or raison_sociale"),
):
    query = db.query(Taxpayer)
    if q:
        like = f"%{q}%"
        query = query.filter((Taxpayer.niu.ilike(like)) | (Taxpayer.raison_sociale.ilike(like)))
    return query.order_by(Taxpayer.raison_sociale).limit(200).all()


@router.post("", response_model=TaxpayerOut, status_code=201)
def create_taxpayer(
    payload: TaxpayerCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    niu = _validate_niu(payload.niu)
    if db.query(Taxpayer).filter(Taxpayer.niu == niu).first():
        raise HTTPException(status_code=409, detail="NIU déjà enregistré")
    try:
        regime = TaxRegime(payload.regime)
    except ValueError:
        raise HTTPException(status_code=400, detail="Régime fiscal invalide")
    tp = Taxpayer(
        niu=niu, raison_sociale=payload.raison_sociale,
        address=payload.address, sector=payload.sector,
        sector_code=payload.sector_code or "DROIT_COMMUN", regime=regime,
    )
    db.add(tp)
    db.commit()
    db.refresh(tp)
    return tp
