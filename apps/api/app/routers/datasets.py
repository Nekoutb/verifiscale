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
from app.parsers.file_dims import file_dims
from app.parsers.fixed_assets_ai import parse_fixed_assets_ai as parse_fixed_assets
from app.schemas import DatasetOut, DatasetPatch, TrialBalanceLineOut
from app.security import get_current_user
from app.storage import put_object, get_object
from app.services import ingest_preview


router = APIRouter(prefix="/datasets", tags=["datasets"])

# Ingest-v2: these kinds are NEVER auto-ingested. The auditor must confirm the
# column mapping first (mandatory-field checklist + totals + balance verdict).
_MAPPING_GATED_KINDS = {
    DatasetKind.TRIAL_BALANCE,
    DatasetKind.GENERAL_LEDGER,
    DatasetKind.FIXED_ASSETS_REGISTER,
}


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

    # Ingest-v2 — GL/TB stop here: stored, not ingested. The auditor confirms the
    # column mapping via /mapping-preview -> /confirm-mapping before any line
    # reaches the ledger tables.
    if kind_enum in _MAPPING_GATED_KINDS:
        ds.status = DatasetStatus.PENDING_MAPPING
        # Control totals part 1: what the FILE contains. read_* stays null
        # until the auditor confirms the mapping and ingestion runs.
        dims = file_dims(data, ds.original_filename)
        if dims:
            ds.control_totals = {
                "file_rows": dims["rows"], "file_cols": dims["cols"],
                "sheets": dims["sheets"],
                "read_rows": None, "read_cols": None,
                "excluded_rows": None, "structural_rows": None,
                "complete": None,
            }
        db.commit()
        db.refresh(ds)
        return ds

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

        # Control totals: file dims vs what the parser actually read. For
        # AI-extracted kinds (aging/inventory totals, bank closing) `rows` is a
        # placeholder, so only claim read counts where they are meaningful.
        dims = file_dims(data, ds.original_filename)
        if dims:
            read_rows = len(rows)
            meaningful = ds.kind == DatasetKind.FIXED_ASSETS_REGISTER
            ds.control_totals = {
                "file_rows": dims["rows"], "file_cols": dims["cols"],
                "sheets": dims["sheets"],
                "read_rows": read_rows if meaningful else None,
                "read_cols": None,
                "excluded_rows": None, "structural_rows": None,
                # FAR: every file row is either a parsed asset or a
                # header/total/blank line — flag incomplete only when the
                # parser returned nothing from a non-empty file.
                "complete": (read_rows > 0 or dims["rows"] == 0) if meaningful else None,
            }

        ds.status = DatasetStatus.PARSED
        from sqlalchemy.sql import func
        ds.parsed_at = func.now()
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        ds.status = DatasetStatus.PARSE_ERROR
        ds.parse_error = str(e)[:2048]
        db.commit()


@router.post("/{dataset_id}/mapping-preview")
def mapping_preview(
    dataset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    payload: dict | None = None,
) -> dict:
    """Propose (or re-evaluate) the column mapping for a GL/TB — WITHOUT ingesting.

    Body is optional: `{"mapping": {...}}` re-previews live while the auditor
    remaps a column in the UI. Returns the mandatory-field checklist, per-column
    samples, column totals, the balance verdict, the rows that would be excluded
    (with their balance impact) and a handful of rows rendered exactly as they
    would be ingested.
    """
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Jeu de données introuvable")
    if ds.kind not in _MAPPING_GATED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=("Le mapping guidé ne s'applique qu'au grand livre, à la "
                    "balance et au registre des immobilisations."),
        )
    try:
        data = get_object(ds.storage_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Fichier illisible : {e}")

    override = (payload or {}).get("mapping") or None
    try:
        return ingest_preview.build_preview(
            data, ds.original_filename, ds.kind.value, override_mapping=override,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{dataset_id}/confirm-mapping", response_model=DatasetOut)
def confirm_mapping(
    dataset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    payload: dict = None,  # type: ignore[assignment]
):
    """Ingest a GL/TB using the auditor-approved mapping.

    Body: `{"mapping": {...}, "acknowledge_unbalanced": bool}`.
    An unbalanced import is permitted but only with an explicit acknowledgement.
    Re-confirming replaces any previously ingested lines for this dataset.
    """
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Jeu de données introuvable")
    if ds.kind not in _MAPPING_GATED_KINDS:
        raise HTTPException(status_code=400, detail="Type non concerné par le mapping guidé.")

    body = payload or {}
    mapping = body.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise HTTPException(status_code=400, detail="Mapping manquant.")

    try:
        data = get_object(ds.storage_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Fichier illisible : {e}")

    # Idempotent: re-confirming wipes what a previous confirmation ingested.
    if ds.kind == DatasetKind.FIXED_ASSETS_REGISTER:
        pass  # no ledger table — the confirmed mapping itself is the ingestion
    elif ds.kind == DatasetKind.TRIAL_BALANCE:
        db.query(TrialBalanceLine).filter(TrialBalanceLine.dataset_id == ds.id).delete()
    else:
        old = db.query(JournalEntry).filter(JournalEntry.dataset_id == ds.id).all()
        for e in old:
            db.query(JournalEntryLine).filter(JournalEntryLine.entry_id == e.id).delete()
        db.query(JournalEntry).filter(JournalEntry.dataset_id == ds.id).delete()
    db.flush()

    try:
        ingest_preview.ingest_confirmed(
            db, ds, data, mapping,
            acknowledge_unbalanced=bool(body.get("acknowledge_unbalanced")),
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        db.rollback()
        ds.status = DatasetStatus.PARSE_ERROR
        ds.parse_error = str(e)[:2048]
        db.commit()
        raise HTTPException(status_code=500, detail=f"Échec de l'ingestion : {e}")

    db.refresh(ds)
    return ds


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
