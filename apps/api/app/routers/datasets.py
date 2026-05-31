"""Datasets: upload + parse + retrieve."""
import hashlib
import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AuditCase, Dataset, DatasetKind, DatasetStatus, JournalEntry, JournalEntryLine,
    TrialBalanceLine, User,
)
from app.parsers import general_ledger_ai as gl_parser, trial_balance_ai as tb_parser
from app.parsers.aging_ai import sum_aging_total_ai, sum_inventory_value_ai
from app.parsers.bank_statement import parse_bank_statement_closing
from app.parsers.fixed_assets_ai import parse_fixed_assets_ai as parse_fixed_assets
from app.schemas import DatasetOut, DatasetPatch, TrialBalanceLineOut
from app.security import get_current_user
from app.storage import put_object


router = APIRouter(prefix="/datasets", tags=["datasets"])


_PARSEABLE_KINDS = {
    DatasetKind.TRIAL_BALANCE,
    DatasetKind.GENERAL_LEDGER,
    DatasetKind.ACCOUNTS_PAYABLE_AGING,
    DatasetKind.ACCOUNTS_RECEIVABLE_AGING,
    DatasetKind.INVENTORY_LISTING,
    DatasetKind.FIXED_ASSETS_REGISTER,
    DatasetKind.BANK_STATEMENT,
}


@router.post("", response_model=DatasetOut, status_code=201)
async def upload_dataset(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    audit_case_id: Annotated[UUID, Form()],
    kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    period_year: Annotated[int | None, Form()] = None,
    bank_account_code: Annotated[str | None, Form()] = None,
):
    case = db.get(AuditCase, audit_case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    try:
        kind_enum = DatasetKind(kind)
    except ValueError:
        raise HTTPException(status_code=400, detail="Type de jeu de données invalide")

    data = await file.read()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (>200 Mo)")

    content_hash = hashlib.sha256(data).hexdigest()
    storage_key = f"audits/{audit_case_id}/datasets/{uuid.uuid4()}/{file.filename}"
    put_object(storage_key, data, content_type=file.content_type)

    ds = Dataset(
        audit_case_id=audit_case_id, kind=kind_enum,
        original_filename=file.filename or "untitled",
        storage_key=storage_key, content_hash=content_hash,
        size_bytes=len(data), mime_type=file.content_type,
        status=DatasetStatus.UPLOADED, uploaded_by_id=user.id,
        period_year=period_year,
        bank_account_code=bank_account_code,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)

    # Inline parse for small files; in production this is dispatched to Celery
    if kind_enum in _PARSEABLE_KINDS:
        _parse_and_persist(db, ds, data)

    db.refresh(ds)
    return ds


def _parse_and_persist(db: Session, ds: Dataset, data: bytes) -> None:
    ds.status = DatasetStatus.PARSING
    db.commit()
    try:
        if ds.kind == DatasetKind.TRIAL_BALANCE:
            rows, mapping = tb_parser.parse(data, ds.original_filename)
            for r in rows:
                db.add(TrialBalanceLine(dataset_id=ds.id, **r))
        elif ds.kind == DatasetKind.GENERAL_LEDGER:
            rows, mapping = gl_parser.parse(data, ds.original_filename)
            # Group lines by piece -> JournalEntry
            entries: dict[str, JournalEntry] = {}
            line_seq: dict[str, int] = {}
            for r in rows:
                key = r["piece_number"]
                if key not in entries:
                    if not r["entry_date"]:
                        continue  # skip lines without a date
                    entries[key] = JournalEntry(
                        dataset_id=ds.id, piece_number=key,
                        journal_code=r["journal_code"] or "OD", entry_date=r["entry_date"],
                    )
                    db.add(entries[key])
                    db.flush()  # get id
                    line_seq[key] = 0
                line_seq[key] += 1
                db.add(JournalEntryLine(
                    entry_id=entries[key].id, line_number=line_seq[key],
                    account_code=r["account_code"], account_name=r["account_name"],
                    libelle=r["libelle"], debit=r["debit"], credit=r["credit"],
                    lettrage=r["lettrage"],
                ))
            mapping = mapping
        elif ds.kind in (DatasetKind.ACCOUNTS_PAYABLE_AGING,
                          DatasetKind.ACCOUNTS_RECEIVABLE_AGING):
            kind_short = "AP" if ds.kind == DatasetKind.ACCOUNTS_PAYABLE_AGING else "AR"
            total = sum_aging_total_ai(data, ds.original_filename, kind=kind_short)
            ds.summary_amount = total if total is not None else None
            try:
                import pandas as pd, io as _io
                df = pd.read_excel(_io.BytesIO(data), header=None) if ds.original_filename.lower().endswith((".xlsx", ".xls", ".xlsm")) else None
                rows = [None] * (len(df) - 1 if df is not None else 0)
            except Exception:
                rows = []
            mapping = {"auto_total_xaf": float(total) if total is not None else None, "ai": True}
        elif ds.kind == DatasetKind.INVENTORY_LISTING:
            total = sum_inventory_value_ai(data, ds.original_filename)
            ds.summary_amount = total if total is not None else None
            try:
                import pandas as pd, io as _io
                df = pd.read_excel(_io.BytesIO(data), header=None) if ds.original_filename.lower().endswith((".xlsx", ".xls", ".xlsm")) else None
                rows = [None] * (len(df) - 1 if df is not None else 0)
            except Exception:
                rows = []
            mapping = {"auto_total_xaf": float(total) if total is not None else None, "ai": True}
        elif ds.kind == DatasetKind.FIXED_ASSETS_REGISTER:
            assets = parse_fixed_assets(data, ds.original_filename)
            rows = assets
            from decimal import Decimal as _D
            total_gross = sum((a.get("gross_value_xaf") or _D("0")) for a in assets)
            ds.summary_amount = total_gross
            mapping = {"asset_count": len(assets), "total_gross_xaf": float(total_gross)}
        elif ds.kind == DatasetKind.BANK_STATEMENT:
            closing = parse_bank_statement_closing(data, ds.original_filename)
            ds.summary_amount = closing if closing is not None else None
            rows = [None] if closing is not None else []
            mapping = {"closing_balance_xaf": float(closing) if closing is not None else None}
        else:
            mapping = {}

        ds.column_mapping = mapping
        ds.rows_count = len(rows)
        ds.status = DatasetStatus.PARSED
        from sqlalchemy.sql import func
        ds.parsed_at = func.now()
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        ds.status = DatasetStatus.PARSE_ERROR
        ds.parse_error = str(e)[:2048]
        db.commit()


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    return ds


@router.patch("/{dataset_id}", response_model=DatasetOut)
def patch_dataset(
    dataset_id: UUID,
    payload: DatasetPatch,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Update auditor-entered metadata on a dataset (notably summary_amount)."""
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    if payload.summary_amount is not None:
        ds.summary_amount = payload.summary_amount
    if payload.period_year is not None:
        ds.period_year = payload.period_year
    if payload.bank_account_code is not None:
        ds.bank_account_code = payload.bank_account_code
    db.commit()
    db.refresh(ds)
    return ds


@router.get("/{dataset_id}/trial-balance", response_model=list[TrialBalanceLineOut])
def get_trial_balance_lines(
    dataset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    return (
        db.query(TrialBalanceLine)
        .filter(TrialBalanceLine.dataset_id == dataset_id)
        .order_by(TrialBalanceLine.account_code)
        .all()
    )


@router.get("/audit-case/{audit_case_id}", response_model=list[DatasetOut])
def list_datasets_for_case(
    audit_case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    return (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == audit_case_id)
        .order_by(Dataset.uploaded_at.desc())
        .all()
    )
