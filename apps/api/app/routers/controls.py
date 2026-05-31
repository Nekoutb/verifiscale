"""Control runs endpoint.

POST /control-runs              — trigger a control run on an audit case for a given category
POST /control-runs/all          — run every available category in one call
GET  /control-runs/{id}         — fetch run + its findings
GET  /control-runs/audit-case/{id} — list all runs for a case
GET  /control-runs/catalog      — return the static catalog of categories + control codes
"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.controls.base import ControlContext
from app.controls.registry import CATEGORY_METADATA, run_category
from app.database import get_db
from app.models import (
    AuditCase, ControlFinding, ControlRun, ControlStatus,
    Dataset, DatasetKind, JournalEntry, MonthlyReturn, TrialBalanceLine, User,
)
from app.schemas import ControlRunOut
from app.security import get_current_user


router = APIRouter(prefix="/control-runs", tags=["controls"])


class RunRequest(BaseModel):
    audit_case_id: UUID
    category: str = "SYSCOHADA_A"


@router.get("/catalog")
def get_catalog():
    """Static catalog of every category and its controls (for the UI sidebar)."""
    return {
        cat: {
            "name": meta["name"],
            "controls": [
                {"code": code, "title": title} for code, title, _ in meta["controls"]
            ],
        }
        for cat, meta in CATEGORY_METADATA.items()
    }


@router.post("", response_model=ControlRunOut, status_code=201)
def trigger_run(
    payload: RunRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    case = db.get(AuditCase, payload.audit_case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    if payload.category not in CATEGORY_METADATA:
        raise HTTPException(status_code=400, detail=f"Catégorie inconnue : {payload.category}")

    run = ControlRun(
        audit_case_id=case.id, category=payload.category,
        triggered_by_id=user.id, status=ControlStatus.RUNNING,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        ctx = _build_context(db, case.id)
        findings = run_category(payload.category, ctx)

        for f in findings:
            db.add(ControlFinding(
                control_run_id=run.id,
                control_code=f.control_code,
                title=f.title,
                description=f.description,
                severity=f.severity,
                legal_reference=f.legal_reference,
                evidence=f.evidence,
                estimated_impact_xaf=f.estimated_impact_xaf,
            ))

        run.status = ControlStatus.SUCCESS
        run.finished_at = datetime.now(timezone.utc)
        run.summary = _summarize(findings)
        db.commit()
    except Exception as e:  # noqa: BLE001
        run.status = ControlStatus.FAILED
        run.error = str(e)[:2000]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

    return (
        db.query(ControlRun)
        .options(joinedload(ControlRun.findings))
        .filter(ControlRun.id == run.id)
        .first()
    )


def _summarize(findings) -> dict:
    return {
        "findings_count": len(findings),
        "blocking": sum(1 for f in findings if f.severity.value == "BLOCKING"),
        "high": sum(1 for f in findings if f.severity.value == "HIGH"),
        "medium": sum(1 for f in findings if f.severity.value == "MEDIUM"),
        "low": sum(1 for f in findings if f.severity.value == "LOW"),
        "info": sum(1 for f in findings if f.severity.value == "INFO"),
        "estimated_total_impact_xaf": sum(f.estimated_impact_xaf or 0 for f in findings),
    }


def _build_context(db: Session, audit_case_id: UUID) -> ControlContext:
    case = db.get(AuditCase, audit_case_id)

    # Pick the LATEST PARSED dataset of each kind. A later PARSE_ERROR upload
    # must NOT shadow an earlier successful one.
    from app.models import DatasetStatus
    tb_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == audit_case_id,
            Dataset.kind == DatasetKind.TRIAL_BALANCE,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    gl_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == audit_case_id,
            Dataset.kind == DatasetKind.GENERAL_LEDGER,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )

    tb_lines = []
    if tb_ds:
        tb_lines = [
            {
                "account_code": l.account_code, "account_name": l.account_name,
                "opening_debit": l.opening_debit, "opening_credit": l.opening_credit,
                "period_debit": l.period_debit, "period_credit": l.period_credit,
                "closing_debit": l.closing_debit, "closing_credit": l.closing_credit,
            }
            for l in db.query(TrialBalanceLine).filter(TrialBalanceLine.dataset_id == tb_ds.id).all()
        ]

    je_list, gl_lines = [], []
    if gl_ds:
        entries = (
            db.query(JournalEntry)
            .options(joinedload(JournalEntry.lines))
            .filter(JournalEntry.dataset_id == gl_ds.id)
            .all()
        )
        for je in entries:
            lines = [
                {"account_code": l.account_code, "account_name": l.account_name,
                 "libelle": l.libelle, "debit": l.debit, "credit": l.credit}
                for l in je.lines
            ]
            je_list.append({
                "piece": je.piece_number, "date": je.entry_date,
                "journal": je.journal_code, "lines": lines,
            })
            for l in lines:
                gl_lines.append({"piece": je.piece_number, "date": je.entry_date,
                                 "journal": je.journal_code, **l})

    extra: dict = {}
    if case:
        extra["lpf_dates"] = {
            "fiscal_year": case.fiscal_year,
            "period_start": case.period_start,
            "period_end": case.period_end,
            "avis_verification_date": case.avis_verification_date,
            "debut_intervention_date": case.debut_intervention_date,
            "fin_intervention_date": case.fin_intervention_date,
            "notification_date": case.notification_date,
            "reponse_contribuable_date": case.reponse_contribuable_date,
        }

    # Monthly returns — used by Categories D, E, I and the cross-controls
    mr_rows = (
        db.query(MonthlyReturn)
        .filter(MonthlyReturn.audit_case_id == audit_case_id)
        .all()
    )
    extra["monthly_returns"] = [
        {
            "id": str(r.id),
            "tax_type": r.tax_type.value,
            "period_year": r.period_year,
            "period_month": r.period_month,
            "period_quarter": r.period_quarter,
            "filing_date": r.filing_date.isoformat() if r.filing_date else None,
            "filing_deadline": r.filing_deadline.isoformat() if r.filing_deadline else None,
            "declared_amount": float(r.declared_amount) if r.declared_amount is not None else 0.0,
            "base_amount": float(r.base_amount) if r.base_amount is not None else None,
            "credit_reporte": float(r.credit_reporte) if r.credit_reporte is not None else None,
            "status": r.status.value,
        }
        for r in mr_rows
    ]

    return ControlContext(
        audit_case_id=str(audit_case_id),
        trial_balance=tb_lines,
        general_ledger=gl_lines,
        journal_entries=je_list,
        extra=extra,
    )


@router.get("/audit-case/{audit_case_id}", response_model=list[ControlRunOut])
def list_runs(
    audit_case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    return (
        db.query(ControlRun)
        .options(joinedload(ControlRun.findings))
        .filter(ControlRun.audit_case_id == audit_case_id)
        .order_by(ControlRun.started_at.desc())
        .all()
    )


@router.get("/{run_id}", response_model=ControlRunOut)
def get_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    run = (
        db.query(ControlRun)
        .options(joinedload(ControlRun.findings))
        .filter(ControlRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run introuvable")
    return run
