"""Cash-payments control endpoint — CGI Cameroun Art. 7 bis (100 000 FCFA HT)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.controls.cash_payments import analyze_cash_payments
from app.database import get_db
from app.models import (
    AuditCase, CashCurrentYear, CashDecisionSrc, CashExclusionKind,
    CashPaymentAssessment, ControlFinding, ControlRun, ControlSeverity,
    ControlStatus, User,
)
from app.security import get_current_user


router = APIRouter(prefix="/audit-cases", tags=["cash_payments"])


@router.get("/{case_id}/cash-payments")
def get_cash_payments(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Run the cash-payments control on the latest GL.

    Side-effect: when there is at least one CONFIRMED line, write/refresh a
    ControlFinding in the FISCAL_C category so the consolidated findings page
    in Rapports & Notifications picks it up.
    """
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    result = analyze_cash_payments(db, case_id)

    summary = result.get("summary") or {}
    confirmed = int(summary.get("confirmed_count") or 0)
    likely = int(summary.get("likely_count") or 0)
    total_amount = Decimal(str(summary.get("total_amount_xaf") or 0))

    # Upsert a ControlRun + ControlFinding for category FISCAL_C / code C-CASH
    if confirmed > 0 or likely > 0:
        # Find or create the most recent run for this case + category
        run = (
            db.query(ControlRun)
            .filter(ControlRun.audit_case_id == case_id, ControlRun.category == "FISCAL_C")
            .order_by(ControlRun.started_at.desc())
            .first()
        )
        if run is None:
            run = ControlRun(
                audit_case_id=case_id,
                category="FISCAL_C",
                status=ControlStatus.SUCCESS,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                summary={
                    "findings_count": 1,
                    "blocking": 1 if confirmed else 0,
                    "high": 0 if confirmed else 1,
                    "medium": 0,
                    "estimated_total_impact_xaf": float(total_amount),
                },
            )
            db.add(run)
            db.flush()

        # Drop any previous cash-payments finding so we don't duplicate
        db.query(ControlFinding).filter(
            ControlFinding.control_run_id == run.id,
            ControlFinding.control_code == "C-CASH-100K",
        ).delete()

        severity = ControlSeverity.BLOCKING if confirmed else ControlSeverity.HIGH
        description = (
            f"Le grand-livre comporte {confirmed} ligne(s) confirmée(s) et "
            f"{likely} ligne(s) probable(s) de débits financés par caisse "
            f"(classes {'/'.join(result.get('debit_classes_tested', []))} : "
            f"charges, immobilisations, stocks, tiers, capitaux) au-delà du "
            f"seuil de {result['threshold_xaf']:.0f} FCFA "
            f"(CGI art. 7 bis). Montant cumulé : {float(total_amount):,.0f} FCFA — "
            f"intégralement non déductible et à réintégrer."
        ).replace(",", " ")

        finding = ControlFinding(
            control_run_id=run.id,
            control_code="C-CASH-100K",
            title="Règlements en espèces > 100 000 FCFA (CGI art. 7 bis)",
            description=description,
            severity=severity,
            legal_reference="CGI Cameroun, Art. 7 bis",
            evidence={
                "threshold_xaf": result["threshold_xaf"],
                "confirmed_count": confirmed,
                "likely_count": likely,
                "supplier_count": summary.get("supplier_count"),
                "source_dataset_id": result.get("source_dataset_id"),
                "source_filename": result.get("source_filename"),
            },
            estimated_impact_xaf=total_amount,
        )
        db.add(finding)
        db.commit()

    return result


@router.patch("/{case_id}/cash-payments/line")
def override_cash_line(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    """Override the auto-suggestion on a cash-payment line:
      - current_year_decision (YES | NO | UNKNOWN)
      - excluded (bool) + exclusion_kind (SALARY/MISSION/ADMIN_FEE/OTHER)
      - decision_reason (motivation)
    """
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
        db.query(CashPaymentAssessment)
        .filter(CashPaymentAssessment.audit_case_id == case_id,
                CashPaymentAssessment.piece_number == piece,
                CashPaymentAssessment.line_number == line_no)
        .first()
    )
    if row is None:
        row = CashPaymentAssessment(
            audit_case_id=case_id, piece_number=piece, line_number=line_no,
        )
        db.add(row)

    if "current_year_decision" in payload and payload["current_year_decision"]:
        try:
            row.current_year_decision = CashCurrentYear(str(payload["current_year_decision"]).upper())
        except ValueError:
            raise HTTPException(400, "current_year_decision invalide (YES/NO/UNKNOWN)")
        row.decision_source = CashDecisionSrc.MANUAL
    if "excluded" in payload:
        row.excluded = bool(payload["excluded"])
    if "exclusion_kind" in payload and payload["exclusion_kind"]:
        try:
            row.exclusion_kind = CashExclusionKind(str(payload["exclusion_kind"]).upper())
        except ValueError:
            raise HTTPException(400, "exclusion_kind invalide")
    if "decision_reason" in payload:
        row.decision_reason = payload["decision_reason"] or None
    row.updated_by = user.id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
