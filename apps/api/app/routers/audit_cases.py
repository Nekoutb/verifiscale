"""Audit cases (dossiers d'audit)."""
import hashlib
import uuid as uuid_lib
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import AuditCase, AuditType, Brigade, Dataset, DatasetKind, DatasetStatus, TaxRegime, Taxpayer, TrialBalanceLine, User, AuditStatus, RiskLevel
from app.routers.taxpayers import _validate_niu
from app.schemas import AuditCaseCreate, AuditCaseOut, AuditCaseQuickCreate
from app.security import get_current_user
from app.storage import put_object


# Which LPF DatasetKind maps to which date field on AuditCase
_LPF_DATE_FIELD: dict[str, str] = {
    "AVIS_VERIFICATION":         "avis_verification_date",
    "DEBUT_INTERVENTION_PV":     "debut_intervention_date",
    "FIN_INTERVENTION_PV":       "fin_intervention_date",
    "NOTIFICATION_REDRESSEMENT": "notification_date",
    "REPONSE_CONTRIBUABLE":      "reponse_contribuable_date",
}


class AuditCasePatch(BaseModel):
    """Partial update — all fields optional."""
    fiscal_year: int | None = None
    period_start: date | None = None
    period_end: date | None = None
    audit_type: str | None = None
    starting_year: int | None = None
    number_of_years: int | None = None
    status: str | None = None
    risk_level: str | None = None
    avis_verification_date: date | None = None
    debut_intervention_date: date | None = None
    fin_intervention_date: date | None = None
    notification_date: date | None = None
    reponse_contribuable_date: date | None = None


router = APIRouter(prefix="/audit-cases", tags=["audit_cases"])


@router.get("", response_model=list[AuditCaseOut])
def list_audit_cases(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    q = db.query(AuditCase).options(joinedload(AuditCase.taxpayer))
    # Brigade-scoped for non-admin
    if user.role.value != "ADMIN" and user.brigade_id:
        q = q.filter(AuditCase.brigade_id == user.brigade_id)
    return q.order_by(AuditCase.created_at.desc()).all()


@router.post("", response_model=AuditCaseOut, status_code=201)
def create_audit_case(
    payload: AuditCaseCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if not db.get(Taxpayer, payload.taxpayer_id):
        raise HTTPException(status_code=404, detail="Contribuable introuvable")
    if not db.get(Brigade, payload.brigade_id):
        raise HTTPException(status_code=404, detail="Brigade introuvable")
    if payload.assignee_id and not db.get(User, payload.assignee_id):
        raise HTTPException(status_code=404, detail="Auditeur introuvable")
    try:
        risk = RiskLevel(payload.risk_level)
    except ValueError:
        raise HTTPException(status_code=400, detail="Niveau de risque invalide")

    case = AuditCase(
        reference=payload.reference,
        taxpayer_id=payload.taxpayer_id,
        brigade_id=payload.brigade_id,
        assignee_id=payload.assignee_id or user.id,
        fiscal_year=payload.fiscal_year,
        period_start=payload.period_start,
        period_end=payload.period_end,
        risk_level=risk,
        status=AuditStatus.PLANIFICATION,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.post("/quick", response_model=AuditCaseOut, status_code=201)
def quick_create_audit_case(
    payload: AuditCaseQuickCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """One-shot dossier creation: upserts the taxpayer by NIU, picks the user's
    brigade (or the first brigade for an admin without one), and auto-generates
    a reference of the form 'CAS-{YEAR}-{NNNN}'.
    """
    niu = _validate_niu(payload.niu)
    try:
        regime = TaxRegime(payload.regime)
    except ValueError:
        raise HTTPException(status_code=400, detail="Régime fiscal invalide")
    try:
        risk = RiskLevel(payload.risk_level)
    except ValueError:
        raise HTTPException(status_code=400, detail="Niveau de risque invalide")
    try:
        atype = AuditType(payload.audit_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Type d'audit invalide")
    if payload.number_of_years < 1 or payload.number_of_years > 10:
        raise HTTPException(status_code=400, detail="Nombre d'années doit être entre 1 et 10")

    # Upsert taxpayer
    tp = db.query(Taxpayer).filter(Taxpayer.niu == niu).first()
    if tp is None:
        tp = Taxpayer(
            niu=niu, raison_sociale=payload.raison_sociale,
            address=payload.address, sector=payload.sector,
            sector_code=payload.sector_code or "DROIT_COMMUN", regime=regime,
            tax_center=payload.tax_center,
            legal_form=payload.legal_form,
            capital_social=payload.capital_social,
            activity_start_date=payload.activity_start_date,
            rccm=payload.rccm,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            contact_email=payload.contact_email,
        )
        db.add(tp)
        db.flush()
    else:
        # Refresh fields if the caller provided richer info
        if payload.raison_sociale and tp.raison_sociale != payload.raison_sociale:
            tp.raison_sociale = payload.raison_sociale
        for attr in (
            "address", "sector", "sector_code", "tax_center", "legal_form", "capital_social",
            "activity_start_date", "rccm", "contact_name", "contact_phone", "contact_email",
        ):
            val = getattr(payload, attr)
            if val and not getattr(tp, attr):
                setattr(tp, attr, val)

    # Pick brigade: user's own, else the first brigade in the system (admin path)
    brigade_id = user.brigade_id
    if brigade_id is None:
        first = db.query(Brigade).order_by(Brigade.code).first()
        if first is None:
            raise HTTPException(400, "Aucune brigade configurée — créer une brigade d'abord")
        brigade_id = first.id

    # Auto-reference: CAS-{year}-{NNNN}
    ref = payload.reference
    if not ref:
        year = payload.starting_year
        count = db.query(AuditCase).filter(AuditCase.fiscal_year == year).count()
        ref = f"CAS-{year}-{count + 1:04d}"

    case = AuditCase(
        reference=ref,
        taxpayer_id=tp.id,
        brigade_id=brigade_id,
        assignee_id=user.id,
        fiscal_year=payload.starting_year,
        period_start=date(payload.starting_year, 1, 1),
        period_end=date(payload.starting_year + payload.number_of_years - 1, 12, 31),
        audit_type=atype,
        starting_year=payload.starting_year,
        number_of_years=payload.number_of_years,
        risk_level=risk,
        status=AuditStatus.PLANIFICATION,
        avis_verification_date=payload.avis_verification_date,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.post("/{case_id}/lpf-documents", status_code=201)
async def upload_lpf_document(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    document_date: Annotated[date | None, Form()] = None,
):
    """Attach an LPF milestone PDF (avis, notification, etc.) and auto-fill
    the corresponding date on the AuditCase. The PDF is stored as a Dataset
    so it's downloadable and audit-trailed alongside everything else.
    """
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    if kind not in _LPF_DATE_FIELD:
        raise HTTPException(400, f"Type de document LPF inconnu : {kind}")
    try:
        kind_enum = DatasetKind(kind)
    except ValueError:
        raise HTTPException(400, "Type LPF invalide pour Dataset")

    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "PDF trop volumineux (>50 Mo)")
    storage_key = f"audits/{case_id}/lpf/{uuid_lib.uuid4()}/{file.filename}"
    put_object(storage_key, data, content_type=file.content_type)

    ds = Dataset(
        audit_case_id=case_id, kind=kind_enum,
        original_filename=file.filename or "lpf.pdf",
        storage_key=storage_key,
        content_hash=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data), mime_type=file.content_type or "application/pdf",
        status=DatasetStatus.PARSED, uploaded_by_id=user.id,
    )
    db.add(ds)

    # Auto-fill the case date: prefer the explicit document_date, else today
    target_field = _LPF_DATE_FIELD[kind]
    setattr(case, target_field, document_date or date.today())

    db.commit()
    db.refresh(case)
    return {
        "dataset_id": str(ds.id),
        "kind": kind,
        "document_date": getattr(case, target_field).isoformat(),
        "case": {
            "avis_verification_date":     case.avis_verification_date.isoformat() if case.avis_verification_date else None,
            "debut_intervention_date":    case.debut_intervention_date.isoformat() if case.debut_intervention_date else None,
            "fin_intervention_date":      case.fin_intervention_date.isoformat() if case.fin_intervention_date else None,
            "notification_date":          case.notification_date.isoformat() if case.notification_date else None,
            "reponse_contribuable_date":  case.reponse_contribuable_date.isoformat() if case.reponse_contribuable_date else None,
        },
    }


@router.get("/{case_id}/lpf-documents")
def list_lpf_documents(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    kinds = [DatasetKind(k) for k in _LPF_DATE_FIELD.keys()]
    rows = (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id, Dataset.kind.in_(kinds))
        .order_by(Dataset.uploaded_at.desc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "kind": r.kind.value,
            "original_filename": r.original_filename,
            "uploaded_at": r.uploaded_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{case_id}", response_model=AuditCaseOut)
def get_audit_case(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    case = db.query(AuditCase).options(joinedload(AuditCase.taxpayer)).get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return case


@router.get("/{case_id}/bank-accounts")
def list_bank_accounts(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Detect bank accounts from the latest PARSED trial balance.

    Returns SYSCOHADA class 52 (Banques) accounts the auditee uses — one per
    distinct account_code with movement or closing balance. The Audit Data UI
    uses this to render upload slots for bank statements: one per bank × per year.
    """
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    tb_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.TRIAL_BALANCE,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if not tb_ds:
        return {"bank_accounts": [], "source_dataset_id": None, "note": "Aucune balance générale chargée — importer une balance pour détecter les comptes 52X."}

    # SYSCOHADA Révisé: class 52 = Banques. In practice some bookkeepers also use
    # 51X labelled "Banque…". We catch both — and also any class 5 account whose
    # libellé contains "banq" (case-insensitive) for edge cases.
    from sqlalchemy import or_, func
    bank_rows = (
        db.query(TrialBalanceLine)
        .filter(
            TrialBalanceLine.dataset_id == tb_ds.id,
            or_(
                TrialBalanceLine.account_code.startswith("52"),
                # class 51 with "banque" in name (legacy/non-strict accounting)
                # also matches "BICEC", "SGC", etc. accounts kept under 51 historically
                TrialBalanceLine.account_code.startswith("51"),
                func.lower(TrialBalanceLine.account_name).contains("banq"),
            ),
        )
        .order_by(TrialBalanceLine.account_code)
        .all()
    )

    accounts = [
        {
            "account_code": r.account_code,
            "account_name": r.account_name,
            "closing_debit": float(r.closing_debit),
            "closing_credit": float(r.closing_credit),
        }
        for r in bank_rows
    ]
    return {
        "bank_accounts": accounts,
        "source_dataset_id": str(tb_ds.id),
        "source_filename": tb_ds.original_filename,
    }


@router.patch("/{case_id}", response_model=AuditCaseOut)
def update_audit_case(
    case_id: UUID,
    payload: AuditCasePatch,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Update editable fields on a dossier — fiscal_year, dates, status, risk."""
    case = db.query(AuditCase).options(joinedload(AuditCase.taxpayer)).get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Dossier introuvable")

    # Apply fields if provided
    if payload.fiscal_year is not None:
        case.fiscal_year = payload.fiscal_year
        # Auto-realign period dates if not explicitly set in the same payload
        if payload.period_start is None:
            case.period_start = date(payload.fiscal_year, 1, 1)
        if payload.period_end is None:
            case.period_end = date(payload.fiscal_year, 12, 31)

    if payload.period_start is not None:
        case.period_start = payload.period_start
    if payload.period_end is not None:
        case.period_end = payload.period_end

    if payload.status is not None:
        try:
            case.status = AuditStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Statut invalide : {payload.status}")
    if payload.risk_level is not None:
        try:
            case.risk_level = RiskLevel(payload.risk_level)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Niveau de risque invalide : {payload.risk_level}")

    if payload.audit_type is not None:
        try:
            case.audit_type = AuditType(payload.audit_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Type d'audit invalide : {payload.audit_type}")
    if payload.starting_year is not None:
        case.starting_year = payload.starting_year
    if payload.number_of_years is not None:
        if payload.number_of_years < 1 or payload.number_of_years > 10:
            raise HTTPException(status_code=400, detail="Nombre d'années doit être entre 1 et 10")
        case.number_of_years = payload.number_of_years

    for f in (
        "avis_verification_date", "debut_intervention_date",
        "fin_intervention_date", "notification_date", "reponse_contribuable_date",
    ):
        val = getattr(payload, f)
        if val is not None:
            setattr(case, f, val)

    db.commit()
    db.refresh(case)
    return case
