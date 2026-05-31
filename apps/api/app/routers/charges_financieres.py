"""Charges financières — CGI Cameroun, Art. 7 B.

Endpoints:
  GET    /reference/beac-rates                       → live BEAC rates (cached)
  GET    /audit-cases/{id}/charges-financieres       → full Art. 7 B analysis
  PATCH  /audit-cases/{id}/charges-financieres/params → set capitaux propres, EBITDA, rate basis
  POST   /audit-cases/{id}/charges-financieres/associes        → add a lender line
  PATCH  /audit-cases/{id}/charges-financieres/associes/{aid}  → edit a lender line
  DELETE /audit-cases/{id}/charges-financieres/associes/{aid}  → remove a lender line
  POST   /audit-cases/{id}/charges-financieres/associes/{aid}/convention  → upload PDF
  PATCH  /audit-cases/{id}/charges-financieres/associes/{aid}/verdict     → manual override
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.controls.charges_financieres import analyze_charges_financieres
from app.database import get_db
from app.models import (
    AuditCase, ChargesFinAssocie, ChargesFinCaseParams, ChgFinVerdict,
    ChgFinVerdictSource, ControlFinding, ControlRun, ControlSeverity,
    ControlStatus, User,
)
from app.security import get_current_user
from app.services.beac_rates import get_beac_rates, ART7B_UPLIFT_POINTS
from app.storage import get_object, put_object


router = APIRouter(tags=["charges_financieres"])


# ── BEAC reference rates ─────────────────────────────────────────────────────


@router.get("/reference/beac-rates")
def beac_rates(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    refresh: bool = False,
):
    return get_beac_rates(db, force_refresh=refresh).to_dict()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_cap_pct(db: Session, case_id: UUID) -> Decimal:
    """Resolve the Art. 7 B cap = TIAO BEAC + 2 points.

    Per the standard reading of "taux des avances de la Banque Centrale",
    the reference rate is the TIAO. (Only basis used.)
    """
    rates = get_beac_rates(db)
    return Decimal(str(rates.tiao_pct)) + ART7B_UPLIFT_POINTS


def _serialize_associe(a: ChargesFinAssocie) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "nom": a.nom,
        "niu": a.niu,
        "pct_detention": float(a.pct_detention) if a.pct_detention is not None else None,
        "is_resident": a.is_resident,
        "avance_moyenne_xaf": float(a.avance_moyenne_xaf) if a.avance_moyenne_xaf is not None else None,
        "interet_servi_xaf": float(a.interet_servi_xaf) if a.interet_servi_xaf is not None else None,
        "compte_gl": a.compte_gl,
        "convention_enregistree": a.convention_enregistree,
        "has_convention_file": bool(a.convention_storage_path),
        "verdict": a.verdict.value,
        "verdict_reason": a.verdict_reason,
        "verdict_source": a.verdict_source.value,
    }


def _upsert_finding(db: Session, case_id: UUID, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    reint = Decimal(str(summary.get("total_reintegration_xaf") or 0))
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
        ControlFinding.control_code == "C-CHGFIN-ART7B",
    ).delete()
    description = (
        f"Charges financières (CGI Art. 7 B) : {summary.get('associe_count', 0)} associé(s) prêteur(s), "
        f"{summary.get('non_eligible_count', 0)} non conforme(s). "
        f"Plafond taux {summary.get('beac_cap_pct')}% (BEAC+2). "
        f"Réintégration estimée : {float(reint):,.0f} FCFA."
    ).replace(",", " ")
    db.add(ControlFinding(
        control_run_id=run.id, control_code="C-CHGFIN-ART7B",
        title="Charges financières — intérêts aux associés (CGI Art. 7 B)",
        description=description, severity=ControlSeverity.BLOCKING,
        legal_reference="CGI Cameroun, Art. 7 B",
        evidence=summary, estimated_impact_xaf=reint,
    ))
    db.commit()


# ── Analysis ─────────────────────────────────────────────────────────────────


@router.get("/audit-cases/{case_id}/charges-financieres")
def get_charges_financieres(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    cap = _resolve_cap_pct(db, case_id)
    payload = analyze_charges_financieres(db, case_id, cap)
    # Attach the live BEAC context
    payload["beac"] = get_beac_rates(db).to_dict()
    params = db.get(ChargesFinCaseParams, case_id)
    payload["params"] = {
        "capitaux_propres_xaf": float(params.capitaux_propres_xaf) if params and params.capitaux_propres_xaf else None,
        "ebitda_fiscal_xaf": float(params.ebitda_fiscal_xaf) if params and params.ebitda_fiscal_xaf else None,
        "rate_basis": params.rate_basis if params else "TIAO",
    }
    try:
        _upsert_finding(db, case_id, payload)
    except Exception:
        db.rollback()
    return payload


@router.patch("/audit-cases/{case_id}/charges-financieres/params")
def set_params(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    params = db.get(ChargesFinCaseParams, case_id)
    if params is None:
        params = ChargesFinCaseParams(audit_case_id=case_id)
        db.add(params)
    if "capitaux_propres_xaf" in payload:
        v = payload["capitaux_propres_xaf"]
        params.capitaux_propres_xaf = Decimal(str(v)) if v is not None else None
    if "ebitda_fiscal_xaf" in payload:
        v = payload["ebitda_fiscal_xaf"]
        params.ebitda_fiscal_xaf = Decimal(str(v)) if v is not None else None
    if "rate_basis" in payload:
        rb = str(payload["rate_basis"]).upper()
        params.rate_basis = "MARGINAL" if rb == "MARGINAL" else "TIAO"
    params.updated_by = user.id
    params.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "rate_basis": params.rate_basis,
            "capitaux_propres_xaf": float(params.capitaux_propres_xaf) if params.capitaux_propres_xaf else None,
            "ebitda_fiscal_xaf": float(params.ebitda_fiscal_xaf) if params.ebitda_fiscal_xaf else None}


@router.post("/audit-cases/{case_id}/charges-financieres/associes", status_code=201)
def add_associe(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    nom = (payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(400, "Le nom de l'associé est requis.")

    def _dec(key):
        v = payload.get(key)
        try:
            return Decimal(str(v)) if v is not None and v != "" else None
        except Exception:  # noqa: BLE001
            return None

    a = ChargesFinAssocie(
        audit_case_id=case_id,
        nom=nom,
        niu=(payload.get("niu") or None),
        pct_detention=_dec("pct_detention"),
        is_resident=bool(payload.get("is_resident", True)),
        avance_moyenne_xaf=_dec("avance_moyenne_xaf"),
        interet_servi_xaf=_dec("interet_servi_xaf"),
        compte_gl=(payload.get("compte_gl") or None),
        convention_enregistree=bool(payload.get("convention_enregistree", False)),
        verdict=ChgFinVerdict.A_REINSTRUIRE,
        verdict_source=ChgFinVerdictSource.AUTO,
        created_by=user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize_associe(a)


@router.patch("/audit-cases/{case_id}/charges-financieres/associes/{aid}")
def edit_associe(
    case_id: UUID, aid: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    a = db.get(ChargesFinAssocie, aid)
    if not a or a.audit_case_id != case_id:
        raise HTTPException(404, "Associé introuvable")

    def _dec(key):
        v = payload.get(key)
        try:
            return Decimal(str(v)) if v is not None and v != "" else None
        except Exception:  # noqa: BLE001
            return None

    if "nom" in payload: a.nom = (payload["nom"] or a.nom).strip()
    if "niu" in payload: a.niu = payload["niu"] or None
    if "pct_detention" in payload: a.pct_detention = _dec("pct_detention")
    if "is_resident" in payload: a.is_resident = bool(payload["is_resident"])
    if "avance_moyenne_xaf" in payload: a.avance_moyenne_xaf = _dec("avance_moyenne_xaf")
    if "interet_servi_xaf" in payload: a.interet_servi_xaf = _dec("interet_servi_xaf")
    if "compte_gl" in payload: a.compte_gl = payload["compte_gl"] or None
    if "convention_enregistree" in payload: a.convention_enregistree = bool(payload["convention_enregistree"])
    db.commit()
    db.refresh(a)
    return _serialize_associe(a)


@router.delete("/audit-cases/{case_id}/charges-financieres/associes/{aid}", status_code=204)
def delete_associe(
    case_id: UUID, aid: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    a = db.get(ChargesFinAssocie, aid)
    if not a or a.audit_case_id != case_id:
        raise HTTPException(404, "Associé introuvable")
    db.delete(a)
    db.commit()
    return Response(status_code=204)


@router.post("/audit-cases/{case_id}/charges-financieres/associes/{aid}/convention", status_code=201)
async def upload_convention(
    case_id: UUID, aid: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
):
    a = db.get(ChargesFinAssocie, aid)
    if not a or a.audit_case_id != case_id:
        raise HTTPException(404, "Associé introuvable")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Fichier vide")
    key = f"audits/{case_id}/chgfin/{aid}/{uuid_lib.uuid4()}_{file.filename or 'convention.pdf'}"
    put_object(key, data, content_type=file.content_type)
    a.convention_filename = file.filename
    a.convention_storage_path = key
    a.convention_enregistree = True  # presence of registered agreement assumed; auditor can toggle
    db.commit()
    return _serialize_associe(a)


@router.get("/audit-cases/{case_id}/charges-financieres/associes/{aid}/convention")
def get_convention(
    case_id: UUID, aid: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    a = db.get(ChargesFinAssocie, aid)
    if not a or a.audit_case_id != case_id or not a.convention_storage_path:
        raise HTTPException(404, "Convention introuvable")
    try:
        data = get_object(a.convention_storage_path)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier manquant")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{a.convention_filename}"'})


@router.patch("/audit-cases/{case_id}/charges-financieres/associes/{aid}/verdict")
def override_verdict(
    case_id: UUID, aid: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    a = db.get(ChargesFinAssocie, aid)
    if not a or a.audit_case_id != case_id:
        raise HTTPException(404, "Associé introuvable")
    try:
        verdict = ChgFinVerdict(str(payload.get("verdict", "")).upper())
    except ValueError:
        raise HTTPException(400, "verdict invalide")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Motivation écrite obligatoire.")
    a.verdict = verdict
    a.verdict_reason = reason
    a.verdict_source = ChgFinVerdictSource.MANUAL_OVERRIDE
    a.verdict_by = user.id
    a.verdict_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return _serialize_associe(a)
