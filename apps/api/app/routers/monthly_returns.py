"""Monthly tax return endpoints.

POST /monthly-returns                      — manual entry (admin / auditor)
POST /monthly-returns/parse                — extract a return from an uploaded PDF dataset
GET  /monthly-returns/audit-case/{id}      — list all returns for an audit case
GET  /monthly-returns/{id}                 — single return + payment proofs
"""
from __future__ import annotations

import hashlib
import logging
import uuid as uuid_lib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    AuditCase, Dataset, DatasetKind, DatasetStatus, MonthlyReturn, PaymentMethod,
    PaymentProof, ReturnStatus, TaxType, User,
)
from app.parsers.dmm_pdf import extract_dmm
from app.parsers.pdf_returns import (
    extract_monthly_return, extract_payment_proof, filing_deadline_for,
)
from app.schemas import MonthlyReturnCreate, MonthlyReturnOut, ParseReturnRequest
from app.security import get_current_user
from app.storage import get_object, put_object


log = logging.getLogger("fiscaudit.routers.monthly_returns")

router = APIRouter(prefix="/monthly-returns", tags=["monthly-returns"])


# ──────────────────────────────────────────────────────────────────────────────
# Schemas (kept inline; lightweight)
# ──────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel  # noqa: E402


class ParsePaymentRequest(BaseModel):
    monthly_return_id: UUID
    dataset_id: UUID  # uploaded PDF dataset (kind=PAYMENT_PROOF)


# ──────────────────────────────────────────────────────────────────────────────
# Manual entry
# ──────────────────────────────────────────────────────────────────────────────


@router.post("", response_model=MonthlyReturnOut, status_code=201)
def create_return(
    payload: MonthlyReturnCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    case = db.get(AuditCase, payload.audit_case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    try:
        tax_type = TaxType(payload.tax_type)
    except ValueError:
        raise HTTPException(400, f"tax_type invalide : {payload.tax_type}")

    mr = MonthlyReturn(
        audit_case_id=case.id,
        tax_type=tax_type,
        period_year=payload.period_year,
        period_month=payload.period_month,
        period_quarter=payload.period_quarter,
        filing_date=payload.filing_date,
        filing_deadline=filing_deadline_for(tax_type, payload.period_year, payload.period_month),
        declared_amount=payload.declared_amount,
        base_amount=payload.base_amount,
        status=ReturnStatus.FILED if payload.filing_date else ReturnStatus.PENDING,
        notes=payload.notes,
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    return mr


# ──────────────────────────────────────────────────────────────────────────────
# PDF parse — Claude Vision (or mock)
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/parse", response_model=MonthlyReturnOut, status_code=201)
def parse_from_dataset(
    payload: ParseReturnRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Run Claude Vision (or mock) on a PDF dataset and create a MonthlyReturn row.

    The dataset must already exist (uploaded via POST /datasets) and have one of
    the MONTHLY_RETURN_* kinds.
    """
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset introuvable")

    case = db.get(AuditCase, dataset.audit_case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    # Resolve the hint, if provided
    hint: TaxType | None = None
    if payload.tax_type_hint:
        try:
            hint = TaxType(payload.tax_type_hint)
        except ValueError:
            raise HTTPException(400, f"tax_type_hint invalide : {payload.tax_type_hint}")

    # Load the PDF bytes from local storage
    try:
        pdf_bytes = get_object(dataset.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier PDF introuvable dans le stockage")

    # Run the extraction
    parsed = extract_monthly_return(
        pdf_bytes,
        hint_tax_type=hint,
        audit_case_period=(case.fiscal_year, 1),
    )

    log.info(
        "Parsed monthly return: tax=%s year=%s month=%s amount=%s source=%s",
        parsed.tax_type.value, parsed.period_year, parsed.period_month,
        parsed.declared_amount, parsed.source,
    )

    mr = MonthlyReturn(
        audit_case_id=case.id,
        tax_type=parsed.tax_type,
        period_year=parsed.period_year,
        period_month=parsed.period_month,
        period_quarter=parsed.period_quarter,
        filing_date=parsed.filing_date,
        filing_deadline=filing_deadline_for(parsed.tax_type, parsed.period_year, parsed.period_month),
        declared_amount=parsed.declared_amount,
        base_amount=parsed.base_amount,
        credit_reporte=parsed.credit_reporte,
        source_dataset_id=dataset.id,
        extracted_data=parsed.raw,
        status=ReturnStatus.FILED if parsed.filing_date else ReturnStatus.PENDING,
        notes=f"Extraction source: {parsed.source}",
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    return mr


# ──────────────────────────────────────────────────────────────────────────────
# Payment receipts (quittances)
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/payment-proofs/parse", status_code=201)
def parse_payment_proof(
    payload: ParsePaymentRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Run Vision/mock extraction on a PAYMENT_PROOF dataset and attach to the return."""
    mr = db.get(MonthlyReturn, payload.monthly_return_id)
    if not mr:
        raise HTTPException(404, "Déclaration introuvable")
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset introuvable")

    try:
        pdf_bytes = get_object(dataset.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier PDF introuvable dans le stockage")

    parsed = extract_payment_proof(pdf_bytes)

    try:
        method = PaymentMethod(parsed.method)
    except ValueError:
        method = PaymentMethod.VIREMENT

    proof = PaymentProof(
        monthly_return_id=mr.id,
        payment_date=parsed.payment_date,
        amount_paid=parsed.amount_paid,
        reference=parsed.reference,
        method=method,
        bank=parsed.bank,
        source_dataset_id=dataset.id,
        extracted_data=parsed.raw,
        notes=f"Extraction source: {parsed.source}",
    )
    db.add(proof)

    # If amount_paid covers the declared amount, mark the return as PAID
    if parsed.amount_paid >= mr.declared_amount:
        mr.status = ReturnStatus.PAID

    db.commit()
    db.refresh(mr)

    log.info(
        "Parsed payment proof for return %s: amount=%s date=%s source=%s",
        mr.id, parsed.amount_paid, parsed.payment_date, parsed.source,
    )

    return {
        "id": str(proof.id),
        "monthly_return_id": str(mr.id),
        "payment_date": str(parsed.payment_date),
        "amount_paid": float(parsed.amount_paid),
        "reference": parsed.reference,
        "method": method.value,
        "bank": parsed.bank,
        "source": parsed.source,
    }


# ──────────────────────────────────────────────────────────────────────────────
# List / fetch
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/audit-case/{audit_case_id}", response_model=list[MonthlyReturnOut])
def list_for_case(
    audit_case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    return (
        db.query(MonthlyReturn)
        .options(joinedload(MonthlyReturn.payment_proofs))
        .filter(MonthlyReturn.audit_case_id == audit_case_id)
        .order_by(
            MonthlyReturn.tax_type,
            MonthlyReturn.period_year,
            MonthlyReturn.period_month.nullslast(),
        )
        .all()
    )


@router.get("/{return_id}", response_model=MonthlyReturnOut)
def get_return(
    return_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    mr = (
        db.query(MonthlyReturn)
        .options(joinedload(MonthlyReturn.payment_proofs))
        .filter(MonthlyReturn.id == return_id)
        .first()
    )
    if not mr:
        raise HTTPException(404, "Déclaration introuvable")
    return mr


@router.delete("/dataset/{dataset_id}", status_code=204)
def delete_dmm_dataset(
    dataset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Delete a DMM PDF + all MonthlyReturn rows extracted from it.

    Removes the storage object too so the dataset is fully gone.
    """
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset introuvable")
    # Drop all MonthlyReturn rows linked to this dataset
    db.query(MonthlyReturn).filter(
        MonthlyReturn.source_dataset_id == dataset_id
    ).delete()
    db.delete(ds)
    db.commit()
    return None


@router.delete("/{return_id}", status_code=204)
def delete_one_return(
    return_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Delete a single MonthlyReturn (one tax type / month line)."""
    mr = db.get(MonthlyReturn, return_id)
    if not mr:
        raise HTTPException(404, "Déclaration introuvable")
    db.delete(mr)
    db.commit()
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Bulk DMM upload — accepts N PDFs and extracts ALL tax lines per PDF
# ──────────────────────────────────────────────────────────────────────────────

_BULK_DMM_LIMIT = 24
_MAX_DMM_BYTES = 10 * 1024 * 1024


def _process_one_dmm(
    db: Session,
    audit_case_id: UUID,
    pdf_bytes: bytes,
    filename: str,
    mime: str | None,
    user_id: UUID,
) -> dict[str, Any]:
    storage_key = f"audits/{audit_case_id}/dmm/{uuid_lib.uuid4()}/{filename}"
    put_object(storage_key, pdf_bytes, content_type=mime or "application/pdf")

    ds = Dataset(
        audit_case_id=audit_case_id,
        kind=DatasetKind.MONTHLY_RETURN,
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
        parsed = extract_dmm(pdf_bytes)
    except Exception as e:
        ds.status = DatasetStatus.PARSE_ERROR
        ds.parse_error = f"DMM extraction failed: {e}"[:2048]
        return {"filename": filename, "dataset_id": str(ds.id),
                "status": "EXTRACTION_FAILED", "error": str(e), "lines_created": 0}

    if not parsed.period_year or not parsed.period_month:
        return {"filename": filename, "dataset_id": str(ds.id),
                "status": "PERIOD_UNKNOWN", "lines_created": 0}

    created = 0
    for tl in parsed.tax_lines:
        try:
            tax_type = TaxType(tl.get("tax_type"))
        except (ValueError, KeyError, TypeError):
            continue
        declared = Decimal(str(tl.get("declared_amount") or 0))
        principal = tl.get("principal_amount") or 0
        if declared <= 0 and principal <= 0:
            continue
        base = tl.get("base_amount")
        cac = tl.get("cac_amount")
        penalty = tl.get("penalty_amount")

        db.query(MonthlyReturn).filter(
            MonthlyReturn.audit_case_id == audit_case_id,
            MonthlyReturn.tax_type == tax_type,
            MonthlyReturn.period_year == parsed.period_year,
            MonthlyReturn.period_month == parsed.period_month,
        ).delete()

        mr = MonthlyReturn(
            audit_case_id=audit_case_id,
            tax_type=tax_type,
            period_year=parsed.period_year,
            period_month=parsed.period_month,
            filing_date=parsed.filing_date,
            filing_deadline=filing_deadline_for(
                tax_type, parsed.period_year, parsed.period_month,
            ),
            declared_amount=declared,
            base_amount=Decimal(str(base)) if base is not None else None,
            source_dataset_id=ds.id,
            extracted_data={
                "dmm_source": parsed.source,
                "line_code": tl.get("line_code"),
                "principal_amount": principal,
                "cac_amount": cac,
                "penalty_amount": penalty,
                "tax_line_notes": tl.get("notes"),
                "taxpayer_niu": parsed.taxpayer_niu,
                "document_number": parsed.document_number,
                "total_to_pay_dmm": float(parsed.total_to_pay) if parsed.total_to_pay else None,
            },
            status=ReturnStatus.FILED if parsed.filing_date else ReturnStatus.PENDING,
            notes=f"DMM extraction ({parsed.source})",
        )
        db.add(mr)
        created += 1

    return {
        "filename": filename,
        "dataset_id": str(ds.id),
        "status": "OK",
        "period_year": parsed.period_year,
        "period_month": parsed.period_month,
        "filing_date": parsed.filing_date.isoformat() if parsed.filing_date else None,
        "document_number": parsed.document_number,
        "taxpayer_niu": parsed.taxpayer_niu,
        "lines_created": created,
        "source": parsed.source,
    }


@router.post("/bulk-dmm", status_code=201)
async def bulk_upload_dmm(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    audit_case_id: Annotated[UUID, Form()],
    files: Annotated[list[UploadFile], File()],
):
    case = db.get(AuditCase, audit_case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    if not files:
        raise HTTPException(400, "Aucun fichier reçu")
    if len(files) > _BULK_DMM_LIMIT:
        raise HTTPException(413, f"Maximum {_BULK_DMM_LIMIT} DMM par requête")

    results: list[dict[str, Any]] = []
    for f in files:
        data = await f.read()
        if not data:
            results.append({"filename": f.filename, "status": "EMPTY", "lines_created": 0})
            continue
        if len(data) > _MAX_DMM_BYTES:
            results.append({"filename": f.filename, "status": "TOO_LARGE", "lines_created": 0})
            continue
        try:
            results.append(_process_one_dmm(
                db, audit_case_id, data,
                f.filename or "dmm.pdf", f.content_type, user.id,
            ))
        except Exception as e:
            log.exception("DMM processing failed for %s", f.filename)
            results.append({"filename": f.filename, "status": "ERROR",
                            "error": str(e)[:500], "lines_created": 0})

    db.commit()
    return {
        "processed": len(results),
        "total_lines_created": sum(r.get("lines_created", 0) for r in results),
        "items": results,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Monthly grid view
# ──────────────────────────────────────────────────────────────────────────────

_GRID_TAX_TYPES = [
    "ACOMPTE_IS", "TVA", "IRPP_SALAIRES", "IRCM",
    "PRECOMPTE_LOYERS", "PRECOMPTE_ACHATS", "TSR", "CFC", "FNE",
]
_MONTH_LABELS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


@router.get("/audit-case/{audit_case_id}/grid")
def monthly_grid(
    audit_case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    year: int,
):
    rows = (
        db.query(MonthlyReturn)
        .filter(
            MonthlyReturn.audit_case_id == audit_case_id,
            MonthlyReturn.period_year == year,
        )
        .order_by(MonthlyReturn.period_month, MonthlyReturn.tax_type)
        .all()
    )

    by_month_tax: dict[int, dict[str, dict[str, Any]]] = {m: {} for m in range(1, 13)}
    for r in rows:
        if not r.period_month:
            continue
        ed = r.extracted_data or {}
        by_month_tax[r.period_month][r.tax_type.value] = {
            "id": str(r.id),
            "declared_amount": float(r.declared_amount or 0),
            "base_amount": float(r.base_amount) if r.base_amount is not None else None,
            "principal_amount": ed.get("principal_amount"),
            "cac_amount": ed.get("cac_amount"),
            "penalty_amount": ed.get("penalty_amount"),
            "line_code": ed.get("line_code"),
            "filing_date": r.filing_date.isoformat() if r.filing_date else None,
            "filing_deadline": r.filing_deadline.isoformat() if r.filing_deadline else None,
            "status": r.status.value if r.status else None,
            "source_dataset_id": str(r.source_dataset_id) if r.source_dataset_id else None,
        }

    months = []
    for m in range(1, 13):
        cells = by_month_tax[m]
        total = sum(c.get("declared_amount") or 0 for c in cells.values())
        any_dataset = next((c.get("source_dataset_id") for c in cells.values() if c.get("source_dataset_id")), None)
        months.append({
            "month": m,
            "month_label": _MONTH_LABELS[m - 1],
            "has_dmm": bool(cells),
            "source_dataset_id": any_dataset,
            "total_declared_xaf": total,
            "by_tax_type": cells,
        })

    totals_by_tax = {tt: 0.0 for tt in _GRID_TAX_TYPES}
    for m in months:
        for tt, cell in m["by_tax_type"].items():
            if tt in totals_by_tax:
                totals_by_tax[tt] += cell.get("declared_amount") or 0

    return {
        "year": year,
        "tax_types": _GRID_TAX_TYPES,
        "months": months,
        "annual_totals_by_tax_type": totals_by_tax,
        "annual_total": sum(totals_by_tax.values()),
        "months_with_dmm": sum(1 for m in months if m["has_dmm"]),
    }
