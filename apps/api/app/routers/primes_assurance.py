"""Primes d'assurance — CGI Cameroun, Art. 7, A (4).

Endpoints:
  GET    /audit-cases/{id}/primes-assurance       → aggregate + per-contract view
  POST   /audit-cases/{id}/primes-assurance/contracts (multipart, files=[])
                                                  → bulk upload + Claude Vision extraction
  PATCH  /audit-cases/{id}/primes-assurance/contracts/{contract_id}/verdict
                                                  → manual override (motivated)
  DELETE /audit-cases/{id}/primes-assurance/contracts/{contract_id}
                                                  → remove a contract
  GET    /audit-cases/{id}/primes-assurance/contracts/{contract_id}/file
                                                  → stream original PDF
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.controls.primes_assurance import analyze_primes_assurance
from app.database import get_db
from app.models import (
    AuditCase,
    ContratAssurance,
    ControlFinding,
    ControlRun,
    ControlSeverity,
    ControlStatus,
    Dataset,
    DatasetKind,
    DatasetStatus,
    InsuranceBenefType,
    InsuranceType,
    InsuranceVerdict,
    InsuranceVerdictSource,
    RegistreAssureurAgree,
    User,
)
from app.parsers.insurance_contract_pdf import extract_insurance_contract
from app.security import get_current_user
from app.storage import get_object, put_object


router = APIRouter(prefix="/audit-cases", tags=["primes_assurance"])

_BULK_LIMIT = 30
_MAX_BYTES = 15 * 1024 * 1024


def _serialize_contract(c: ContratAssurance) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "audit_case_id": str(c.audit_case_id),
        "filename": c.filename,
        "numero_police": c.numero_police,
        "assureur_nom": c.assureur_nom,
        "assureur_niu": c.assureur_niu,
        "assureur_pays": c.assureur_pays,
        "assureur_local": c.assureur_local,
        "souscripteur": c.souscripteur,
        "beneficiaire_nom": c.beneficiaire_nom,
        "beneficiaire_type": c.beneficiaire_type.value,
        "type_assurance": c.type_assurance.value,
        "date_debut": c.date_debut.isoformat() if c.date_debut else None,
        "date_fin": c.date_fin.isoformat() if c.date_fin else None,
        "prime_annuelle_ttc": float(c.prime_annuelle_ttc) if c.prime_annuelle_ttc else None,
        "prime_exercice": float(c.prime_exercice) if c.prime_exercice else None,
        "compte_syscohada": c.compte_syscohada,
        "verdict": c.verdict.value,
        "verdict_reason": c.verdict_reason,
        "verdict_source": c.verdict_source.value,
        "verdict_at": c.verdict_at.isoformat() if c.verdict_at else None,
        "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
        "source_extraction": (c.extracted or {}).get("source"),
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _prorata_temporis(
    prime_annuelle: Decimal, debut: date | None, fin: date | None, exercise_year: int,
) -> Decimal:
    """Prorata of the annual premium falling on the exercise year."""
    if not debut or not fin:
        return prime_annuelle
    period_start = max(debut, date(exercise_year, 1, 1))
    period_end   = min(fin, date(exercise_year, 12, 31))
    if period_end < period_start:
        return Decimal("0")
    total_days   = max(1, (fin - debut).days + 1)
    in_year_days = (period_end - period_start).days + 1
    return (prime_annuelle * Decimal(in_year_days) / Decimal(total_days)).quantize(Decimal("0.01"))


def _match_registry_insurer(db: Session, assureur_nom: str | None, niu: str | None) -> RegistreAssureurAgree | None:
    if niu:
        hit = db.query(RegistreAssureurAgree).filter(
            RegistreAssureurAgree.niu == niu.upper()
        ).first()
        if hit:
            return hit
    if assureur_nom:
        return db.query(RegistreAssureurAgree).filter(
            RegistreAssureurAgree.nom.ilike(f"%{assureur_nom.strip()[:80]}%")
        ).first()
    return None


def _process_one_contract(
    db: Session, audit_case_id: UUID, exercise_year: int,
    pdf_bytes: bytes, filename: str, mime: str | None, user_id: UUID,
) -> dict[str, Any]:
    storage_key = f"audits/{audit_case_id}/primes/{uuid_lib.uuid4()}/{filename}"
    put_object(storage_key, pdf_bytes, content_type=mime or "application/pdf")

    ds = Dataset(
        audit_case_id=audit_case_id,
        kind=DatasetKind.CONTRACT,
        original_filename=filename,
        storage_key=storage_key,
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        size_bytes=len(pdf_bytes),
        mime_type=mime or "application/pdf",
        status=DatasetStatus.PARSED,
        uploaded_by_id=user_id,
    )
    db.add(ds)
    db.flush()

    try:
        parsed = extract_insurance_contract(pdf_bytes)
    except Exception as e:  # noqa: BLE001
        ds.status = DatasetStatus.PARSE_ERROR
        ds.parse_error = f"Insurance contract extraction failed: {e}"[:2048]
        return {"filename": filename, "status": "EXTRACTION_FAILED",
                "error": str(e)[:500]}

    # Registry match
    assureur_local = (parsed.assureur_pays or "CM").upper() == "CM"
    reg = _match_registry_insurer(db, parsed.assureur_nom, parsed.assureur_niu)
    assureur_id = reg.id if reg else None
    if reg:
        assureur_local = True

    # Prorata for the audit exercise
    prime_exo = _prorata_temporis(
        parsed.prime_annuelle_ttc or Decimal("0"),
        parsed.date_debut, parsed.date_fin, exercise_year,
    )

    contrat = ContratAssurance(
        audit_case_id=audit_case_id,
        dataset_id=ds.id,
        filename=filename,
        storage_path=storage_key,
        mime_type=mime,
        size_bytes=len(pdf_bytes),
        numero_police=parsed.numero_police,
        assureur_nom=parsed.assureur_nom,
        assureur_niu=parsed.assureur_niu.upper() if parsed.assureur_niu else None,
        assureur_pays=parsed.assureur_pays or "CM",
        assureur_local=assureur_local,
        assureur_id=assureur_id,
        souscripteur=parsed.souscripteur,
        beneficiaire_nom=parsed.beneficiaire_nom,
        beneficiaire_type=InsuranceBenefType(parsed.beneficiaire_type),
        type_assurance=InsuranceType(parsed.type_assurance),
        date_debut=parsed.date_debut,
        date_fin=parsed.date_fin,
        prime_annuelle_ttc=parsed.prime_annuelle_ttc,
        prime_exercice=prime_exo,
        compte_syscohada=parsed.compte_syscohada,
        verdict=InsuranceVerdict.A_REINSTRUIRE,
        verdict_source=InsuranceVerdictSource.AUTO_CONTRACT,
        extracted={**parsed.raw, "source": parsed.source},
        uploaded_by=user_id,
    )
    db.add(contrat)
    db.flush()
    return {
        "filename": filename,
        "status": "OK",
        "contract_id": str(contrat.id),
        "assureur": parsed.assureur_nom,
        "numero_police": parsed.numero_police,
        "type_assurance": parsed.type_assurance,
        "prime_annuelle": float(parsed.prime_annuelle_ttc) if parsed.prime_annuelle_ttc else None,
        "source": parsed.source,
    }


def _upsert_finding(db: Session, case_id: UUID, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    reint = Decimal(str(summary.get("total_reintegration_xaf") or 0))
    non_elig = int(summary.get("non_eligible_count") or 0)
    if reint <= 0 and non_elig == 0:
        return

    run = (
        db.query(ControlRun)
        .filter(ControlRun.audit_case_id == case_id, ControlRun.category == "FISCAL_C")
        .order_by(ControlRun.started_at.desc())
        .first()
    )
    if run is None:
        run = ControlRun(
            audit_case_id=case_id, category="FISCAL_C",
            status=ControlStatus.SUCCESS,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            summary={"findings_count": 1, "blocking": 1, "high": 0, "medium": 0,
                     "estimated_total_impact_xaf": float(reint)},
        )
        db.add(run)
        db.flush()

    db.query(ControlFinding).filter(
        ControlFinding.control_run_id == run.id,
        ControlFinding.control_code == "C-PRIMES-ART7",
    ).delete()

    severity = ControlSeverity.BLOCKING if reint > 0 else ControlSeverity.HIGH
    description = (
        f"Primes d'assurance (CGI Art. 7 A 4) : "
        f"{summary.get('contract_count', 0)} contrat(s), "
        f"{non_elig} non éligible(s). "
        f"Σ GL 625+6685+6686 = {float(summary.get('gl_total_xaf', 0)):,.0f} FCFA, "
        f"Σ contrats (exercice) = {float(summary.get('contracts_total_exercice_xaf', 0)):,.0f} FCFA, "
        f"écart = {float(summary.get('variance_xaf', 0)):,.0f} FCFA "
        f"({float(summary.get('variance_pct', 0))} %). "
        f"Réintégration estimée : {float(reint):,.0f} FCFA."
    ).replace(",", " ")

    finding = ControlFinding(
        control_run_id=run.id,
        control_code="C-PRIMES-ART7",
        title="Primes d'assurance — Art. 7 A 4 CGI Cameroun",
        description=description,
        severity=severity,
        legal_reference="CGI Cameroun, Art. 7, A (4)",
        evidence=summary,
        estimated_impact_xaf=reint,
    )
    db.add(finding)
    db.commit()


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/{case_id}/primes-assurance")
def get_primes_assurance(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    payload = analyze_primes_assurance(db, case_id)
    try:
        _upsert_finding(db, case_id, payload)
    except Exception:
        db.rollback()
    return payload


@router.post("/{case_id}/primes-assurance/contracts", status_code=201)
async def bulk_upload_contracts(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    files: Annotated[list[UploadFile], File()],
    exercise_year: Annotated[int | None, Form()] = None,
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    if not files:
        raise HTTPException(400, "Aucun fichier reçu")
    if len(files) > _BULK_LIMIT:
        raise HTTPException(413, f"Maximum {_BULK_LIMIT} contrats par requête")
    year = exercise_year or getattr(case, "fiscal_year", None) or datetime.now().year

    results: list[dict[str, Any]] = []
    for f in files:
        data = await f.read()
        if not data:
            results.append({"filename": f.filename, "status": "EMPTY"})
            continue
        if len(data) > _MAX_BYTES:
            results.append({"filename": f.filename, "status": "TOO_LARGE"})
            continue
        try:
            results.append(_process_one_contract(
                db, case_id, year, data,
                f.filename or "contract.pdf", f.content_type, user.id,
            ))
        except Exception as e:  # noqa: BLE001
            results.append({"filename": f.filename, "status": "ERROR",
                            "error": str(e)[:500]})
    db.commit()
    return {"processed": len(results), "items": results}


@router.patch("/{case_id}/primes-assurance/contracts/{contract_id}/verdict")
def override_verdict(
    case_id: UUID,
    contract_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    c = db.get(ContratAssurance, contract_id)
    if not c or c.audit_case_id != case_id:
        raise HTTPException(404, "Contrat introuvable")
    try:
        verdict = InsuranceVerdict(str(payload.get("verdict", "")).upper())
    except ValueError:
        raise HTTPException(400, "verdict invalide (ELIGIBLE / NON_ELIGIBLE / A_REINSTRUIRE)")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Une motivation écrite est requise pour tout override.")

    c.verdict = verdict
    c.verdict_reason = reason
    c.verdict_source = InsuranceVerdictSource.MANUAL_OVERRIDE
    c.verdict_by = user.id
    c.verdict_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return _serialize_contract(c)


@router.delete("/{case_id}/primes-assurance/contracts/{contract_id}", status_code=204)
def delete_contract(
    case_id: UUID,
    contract_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    c = db.get(ContratAssurance, contract_id)
    if not c or c.audit_case_id != case_id:
        raise HTTPException(404, "Contrat introuvable")
    # Also remove the underlying Dataset (file)
    if c.dataset_id:
        ds = db.get(Dataset, c.dataset_id)
        if ds:
            db.delete(ds)
    db.delete(c)
    db.commit()
    return Response(status_code=204)


@router.get("/{case_id}/primes-assurance/contracts/{contract_id}/file")
def get_contract_file(
    case_id: UUID,
    contract_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    c = db.get(ContratAssurance, contract_id)
    if not c or c.audit_case_id != case_id:
        raise HTTPException(404, "Contrat introuvable")
    try:
        data = get_object(c.storage_path)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier manquant sur le stockage")
    return Response(
        content=data,
        media_type=c.mime_type or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{c.filename}"'},
    )
