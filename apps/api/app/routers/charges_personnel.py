"""Charges de personnel — Art. 7 A 1 a/b/c. GL classe 66 (+ jetons 65x)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.controls.charges_personnel import ARTICLE_7A1, analyze_personnel
from app.database import get_db
from app.models import (
    AuditCase, Dataset, DatasetKind, DatasetStatus, JournalEntry, JournalEntryLine, User,
)
from app.security import get_current_user

router = APIRouter(prefix="/audit-cases", tags=["charges-personnel"])


@router.get("/{case_id}/charges-personnel")
def get_charges_personnel(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Dossier introuvable")

    gl = (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id,
                Dataset.kind == DatasetKind.GENERAL_LEDGER,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if gl is None:
        return {"gl_loaded": False, "article": ARTICLE_7A1, "rows": [], "summary": None}

    lines = (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntryLine.entry_id == JournalEntry.id)
        .filter(JournalEntry.dataset_id == gl.id)
        .filter((JournalEntryLine.account_code.like("66%"))
                | (JournalEntryLine.account_code.like("65%")))
        .all()
    )
    rows, summary = analyze_personnel(lines)
    return {
        "gl_loaded": True,
        "gl_filename": gl.original_filename,
        "article": ARTICLE_7A1,
        "summary": summary,
        "rows": [
            {
                "account_code": r.account_code,
                "account_name": r.account_name,
                "libelle": r.libelle,
                "montant_xaf": float(r.montant_xaf),
                "entry_count": r.entry_count,
                "verdict": r.verdict,
                "motif": r.motif,
                "article": r.article,
                "source": r.source,
            }
            for r in rows
        ],
    }
