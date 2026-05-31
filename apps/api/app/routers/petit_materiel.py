"""Petit matériel et outillage — CGI seuil 500 000 FCFA.

  GET   /audit-cases/{id}/petit-materiel              → analysis
  PATCH /audit-cases/{id}/petit-materiel/line         → override (qualif, rate, basis, exclude)
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.controls.petit_materiel import analyze_petit_materiel
from app.database import get_db
from app.models import (
    AuditCase, ControlFinding, ControlRun, ControlSeverity, ControlStatus,
    PetitMaterielLine, PetitMatBasis, PetitMatQualif, User,
)
from app.security import get_current_user


router = APIRouter(prefix="/audit-cases", tags=["petit_materiel"])


def _upsert_finding(db: Session, case_id: UUID, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    reint = Decimal(str(summary.get("total_reintegration_selected_xaf") or 0))
    if reint <= 0:
        return
    run = (
        db.query(ControlRun)
        .filter(ControlRun.audit_case_id == case_id, ControlRun.category == "FISCAL_C")
        .order_by(ControlRun.started_at.desc())
        .first()
    )
    if run is None:
        run = ControlRun(
            audit_case_id=case_id, category="FISCAL_C", status=ControlStatus.SUCCESS,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            summary={"findings_count": 1, "blocking": 1, "high": 0, "medium": 0,
                     "estimated_total_impact_xaf": float(reint)},
        )
        db.add(run)
        db.flush()
    db.query(ControlFinding).filter(
        ControlFinding.control_run_id == run.id,
        ControlFinding.control_code == "C-PETITMAT-500K",
    ).delete()
    description = (
        f"Petit matériel/outillage > 500 000 FCFA passé en charge : "
        f"{summary.get('line_count', 0)} ligne(s), dont {summary.get('other_count', 0)} "
        f"hors outillage à main. Réintégration retenue : {float(reint):,.0f} FCFA "
        f"(différentiel {float(summary.get('total_reint_differential_xaf', 0)):,.0f} / "
        f"total {float(summary.get('total_reint_total_xaf', 0)):,.0f})."
    ).replace(",", " ")
    db.add(ControlFinding(
        control_run_id=run.id, control_code="C-PETITMAT-500K",
        title="Petit matériel et outillage > 500 000 FCFA (seuil d'immobilisation)",
        description=description, severity=ControlSeverity.HIGH,
        legal_reference="CGI Cameroun — seuil d'immobilisation 500 000 FCFA",
        evidence=summary, estimated_impact_xaf=reint,
    ))
    db.commit()


@router.get("/{case_id}/petit-materiel")
def get_petit_materiel(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    payload = analyze_petit_materiel(db, case_id)
    try:
        _upsert_finding(db, case_id, payload)
    except Exception:
        db.rollback()
    return payload


@router.patch("/{case_id}/petit-materiel/line")
def override_line(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    piece = str(payload.get("piece_number") or "").strip()
    try:
        line_no = int(payload.get("line_number"))
    except (TypeError, ValueError):
        line_no = None
    if not piece or line_no is None:
        raise HTTPException(400, "piece_number et line_number requis.")

    row = (
        db.query(PetitMaterielLine)
        .filter(PetitMaterielLine.audit_case_id == case_id,
                PetitMaterielLine.piece_number == piece,
                PetitMaterielLine.line_number == line_no)
        .first()
    )
    if row is None:
        row = PetitMaterielLine(audit_case_id=case_id, piece_number=piece, line_number=line_no)
        db.add(row)

    if "qualification" in payload and payload["qualification"]:
        try:
            row.qualification = PetitMatQualif(str(payload["qualification"]).upper())
        except ValueError:
            raise HTTPException(400, "qualification invalide")
    if "depreciation_rate_pct" in payload:
        v = payload["depreciation_rate_pct"]
        row.depreciation_rate_pct = Decimal(str(v)) if v not in (None, "") else None
    if "reintegration_basis" in payload and payload["reintegration_basis"]:
        try:
            row.reintegration_basis = PetitMatBasis(str(payload["reintegration_basis"]).upper())
        except ValueError:
            raise HTTPException(400, "basis invalide")
    if "excluded" in payload:
        row.excluded = bool(payload["excluded"])
    if "verdict_reason" in payload:
        row.verdict_reason = payload["verdict_reason"] or None
    row.updated_by = user.id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
