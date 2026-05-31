"""Amortissements analysis endpoint — CGI Cameroun Section D, Art. 7."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.controls.amortissements import analyze_assets
from app.database import get_db
from app.models import AuditCase, Dataset, DatasetKind, User
from app.parsers.fixed_assets_ai import parse_fixed_assets_ai as parse_fixed_assets
from app.security import get_current_user
from app.storage import get_object


router = APIRouter(prefix="/audit-cases", tags=["amortissements"])


@router.get("/{case_id}/amortissements")
def get_amortissements_analysis(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Parse the latest FAR for this case, map each asset to its CGI Art. 7
    category, recompute depreciation on a straight-line basis from acquisition
    date, and return per-row + summary results.
    """
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    far_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.FIXED_ASSETS_REGISTER,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if not far_ds:
        return {
            "fiscal_year": case.fiscal_year,
            "source_dataset_id": None,
            "source_filename": None,
            "rows": [],
            "summary": None,
            "note": (
                "Aucun registre d'immobilisations chargé. Importez-le dans "
                "Données › Registre des immobilisations pour activer l'analyse."
            ),
        }

    try:
        data = get_object(far_ds.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier source introuvable en stockage")

    assets = parse_fixed_assets(data, far_ds.original_filename)
    rows, summary = analyze_assets(assets, fiscal_year=case.fiscal_year)

    # Sort: variances first (largest absolute), then by reference
    rows.sort(key=lambda r: (-abs(r.variance_xaf), r.reference))

    return {
        "fiscal_year": case.fiscal_year,
        "source_dataset_id": str(far_ds.id),
        "source_filename": far_ds.original_filename,
        "rows": [r.to_dict() for r in rows],
        "summary": summary,
    }
