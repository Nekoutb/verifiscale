"""Acompte mensuel IS — CGI Cameroun, Art. 21 — endpoint."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.controls.acompte_is import analyze_acompte_is
from app.database import get_db
from app.models import AuditCase, User
from app.security import get_current_user


router = APIRouter(prefix="/audit-cases", tags=["acompte_is"])


@router.get("/{case_id}/acompte-is")
def get_acompte_is(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    year: Annotated[int | None, Query(description="Exercice fiscal — défaut : fiscal_year du dossier")] = None,
) -> dict:
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    fiscal_year = year or getattr(case, "fiscal_year", None) or getattr(case, "starting_year", None)
    if fiscal_year is None:
        raise HTTPException(400, "Exercice fiscal non défini sur ce dossier")

    return analyze_acompte_is(db, case_id, int(fiscal_year))
