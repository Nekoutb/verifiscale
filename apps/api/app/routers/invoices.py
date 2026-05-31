"""Supplier invoices — bulk ingest + per-vendor compliance reports.

Endpoints:
  POST /invoices/bulk          (multipart, files=[]) → ingest N PDFs
  GET  /invoices/audit-case/{id}                     → list invoices for a case
  GET  /invoices/audit-case/{id}/by-vendor            → vendor-grouped summary
  GET  /invoices/{id}/pdf                            → stream the original PDF
  GET  /invoices/{id}                                → single invoice detail
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AuditCase, Dataset, DatasetKind, DatasetStatus, Invoice, InvoiceStatus, User,
)
from app.parsers.invoices import extract_invoice, score_invoice
from app.security import get_current_user
from app.storage import get_object, put_object


router = APIRouter(prefix="/invoices", tags=["invoices"])

# Hard cap on the bulk upload to keep one HTTP request reasonable.
# Larger batches should be paginated client-side.
_BULK_LIMIT = 50
_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MiB each


def _to_iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _to_iso_date(d) -> str | None:
    return d.isoformat() if d else None


def _serialize(inv: Invoice) -> dict[str, Any]:
    return {
        "id": str(inv.id),
        "audit_case_id": str(inv.audit_case_id),
        "dataset_id": str(inv.dataset_id),
        "status": inv.status.value,
        "ocr_error": inv.ocr_error,
        "supplier_niu": inv.supplier_niu,
        "supplier_name": inv.supplier_name,
        "supplier_rccm": inv.supplier_rccm,
        "supplier_address": inv.supplier_address,
        "supplier_tax_center": inv.supplier_tax_center,
        "customer_niu": inv.customer_niu,
        "customer_name": inv.customer_name,
        "invoice_number": inv.invoice_number,
        "invoice_date": _to_iso_date(inv.invoice_date),
        "base_ht_xaf": float(inv.base_ht_xaf) if inv.base_ht_xaf is not None else None,
        "tva_xaf": float(inv.tva_xaf) if inv.tva_xaf is not None else None,
        "ttc_xaf": float(inv.ttc_xaf) if inv.ttc_xaf is not None else None,
        "tva_rate_pct": float(inv.tva_rate_pct) if inv.tva_rate_pct is not None else None,
        "currency": inv.currency,
        "description": inv.description,
        "control_results": inv.control_results,
        "failed_fond_count": inv.failed_fond_count,
        "failed_forme_count": inv.failed_forme_count,
        "is_compliant": inv.is_compliant,
        "created_at": _to_iso(inv.created_at),
        "processed_at": _to_iso(inv.processed_at),
        "original_filename": inv.dataset.original_filename if inv.dataset else None,
    }


def _process_pdf(db: Session, audit_case_id: UUID, file_data: bytes, filename: str, user_id: UUID, mime: str | None) -> Invoice:
    """Store the PDF, OCR it, score it, persist the Invoice row."""
    storage_key = f"audits/{audit_case_id}/invoices/{uuid_lib.uuid4()}/{filename}"
    put_object(storage_key, file_data, content_type=mime or "application/pdf")

    ds = Dataset(
        audit_case_id=audit_case_id, kind=DatasetKind.INVOICE,
        original_filename=filename, storage_key=storage_key,
        content_hash=hashlib.sha256(file_data).hexdigest(),
        size_bytes=len(file_data), mime_type=mime or "application/pdf",
        status=DatasetStatus.PARSED, uploaded_by_id=user_id,
    )
    db.add(ds)
    db.flush()

    inv = Invoice(
        audit_case_id=audit_case_id, dataset_id=ds.id,
        status=InvoiceStatus.PROCESSING,
    )
    db.add(inv)
    db.flush()

    try:
        parsed = extract_invoice(file_data, filename)
        d = parsed.data
        inv.supplier_name = d.supplier_name
        inv.supplier_niu = (d.supplier_niu or None) and d.supplier_niu.upper()
        inv.supplier_rccm = d.supplier_rccm
        inv.supplier_address = d.supplier_address
        inv.supplier_tax_center = d.supplier_tax_center
        inv.customer_name = d.customer_name
        inv.customer_niu = (d.customer_niu or None) and d.customer_niu.upper()
        inv.invoice_number = d.invoice_number
        if d.invoice_date:
            try:
                inv.invoice_date = datetime.strptime(d.invoice_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        inv.base_ht_xaf = Decimal(str(d.base_ht_xaf)) if d.base_ht_xaf is not None else None
        inv.tva_xaf = Decimal(str(d.tva_xaf)) if d.tva_xaf is not None else None
        inv.ttc_xaf = Decimal(str(d.ttc_xaf)) if d.ttc_xaf is not None else None
        inv.tva_rate_pct = Decimal(str(d.tva_rate_pct)) if d.tva_rate_pct is not None else None
        inv.currency = d.currency or "XAF"
        inv.description = d.description
        inv.raw_ocr = parsed.raw

        scored = score_invoice(d)
        inv.control_results = {"fond": scored["fond"], "forme": scored["forme"]}
        inv.failed_fond_count = scored["failed_fond_count"]
        inv.failed_forme_count = scored["failed_forme_count"]
        inv.is_compliant = scored["is_compliant"]
        inv.status = InvoiceStatus.PARSED
        inv.processed_at = datetime.utcnow()
    except Exception as e:  # noqa: BLE001
        inv.status = InvoiceStatus.OCR_ERROR
        inv.ocr_error = str(e)[:2048]

    return inv


@router.post("/bulk", status_code=201)
async def bulk_upload_invoices(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    audit_case_id: Annotated[UUID, Form()],
    files: Annotated[list[UploadFile], File()],
):
    """Upload up to 50 PDFs in one request. Each PDF is OCR'd + scored
    against CGI art. 150 / LPF L 8 bis controls immediately.

    For 10 000+ invoices, call this endpoint in batches of 50 from the client.
    """
    case = db.get(AuditCase, audit_case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    if not files:
        raise HTTPException(400, "Aucun fichier reçu")
    if len(files) > _BULK_LIMIT:
        raise HTTPException(413, f"Lot trop volumineux : maximum {_BULK_LIMIT} fichiers par requête")

    created: list[dict[str, Any]] = []
    for f in files:
        data = await f.read()
        if not data:
            continue
        if len(data) > _MAX_PDF_BYTES:
            created.append({"filename": f.filename, "status": "REJECTED", "reason": "PDF > 20 Mo"})
            continue
        inv = _process_pdf(db, audit_case_id, data, f.filename or "invoice.pdf", user.id, f.content_type)
        created.append({
            "filename": f.filename, "status": inv.status.value,
            "invoice_id": str(inv.id),
            "supplier_name": inv.supplier_name,
            "is_compliant": inv.is_compliant,
        })

    db.commit()
    return {"processed": len(created), "items": created}


@router.get("/audit-case/{audit_case_id}")
def list_invoices(
    audit_case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    only_failed: bool = False,
    vendor_niu: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    q = db.query(Invoice).filter(Invoice.audit_case_id == audit_case_id)
    if only_failed:
        q = q.filter(Invoice.is_compliant.is_(False))
    if vendor_niu:
        q = q.filter(Invoice.supplier_niu == vendor_niu.upper())
    total = q.count()
    rows = q.order_by(Invoice.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_serialize(r) for r in rows]}


@router.get("/audit-case/{audit_case_id}/by-vendor")
def vendor_summary(
    audit_case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Vendor-level rollup: total invoices, compliant vs failed counts, total TTC."""
    compliant_int = case((Invoice.is_compliant.is_(True), 1), else_=0)
    rows = (
        db.query(
            Invoice.supplier_niu,
            Invoice.supplier_name,
            func.count(Invoice.id).label("total"),
            func.sum(compliant_int).label("compliant_sum"),
            func.sum(Invoice.ttc_xaf).label("total_ttc"),
            func.sum(Invoice.failed_fond_count).label("sum_failed_fond"),
            func.sum(Invoice.failed_forme_count).label("sum_failed_forme"),
        )
        .filter(Invoice.audit_case_id == audit_case_id)
        .group_by(Invoice.supplier_niu, Invoice.supplier_name)
        .order_by(func.count(Invoice.id).desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        compliant_n = int(r.compliant_sum or 0)
        total = int(r.total or 0)
        out.append({
            "supplier_niu": r.supplier_niu,
            "supplier_name": r.supplier_name or "(inconnu)",
            "total_invoices": total,
            "compliant_invoices": compliant_n,
            "failed_invoices": total - compliant_n,
            "total_ttc_xaf": float(r.total_ttc or 0),
            "sum_failed_fond": int(r.sum_failed_fond or 0),
            "sum_failed_forme": int(r.sum_failed_forme or 0),
        })
    return {"vendors": out}


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Facture introuvable")
    return _serialize(inv)


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Stream the original PDF back to the client for review."""
    inv = db.get(Invoice, invoice_id)
    if not inv or not inv.dataset:
        raise HTTPException(404, "Facture introuvable")
    try:
        data = get_object(inv.dataset.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier PDF manquant")
    return Response(
        content=data,
        media_type=inv.dataset.mime_type or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{inv.dataset.original_filename}"'},
    )
