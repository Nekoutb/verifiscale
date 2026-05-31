"""Brigades (DGI units)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Brigade, User
from app.schemas import BrigadeOut
from app.security import get_current_user


router = APIRouter(prefix="/brigades", tags=["brigades"])


@router.get("", response_model=list[BrigadeOut])
def list_brigades(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    return db.query(Brigade).order_by(Brigade.name).all()
