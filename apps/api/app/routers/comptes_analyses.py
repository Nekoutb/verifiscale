"""Comptes d'associés (46XX), comptes divers (4711/4712) et provisions.

  GET  /audit-cases/{id}/comptes-associes   position mensuelle 46XX + transactions
  GET  /audit-cases/{id}/comptes-divers     4711 débiteurs / 4712 créditeurs
  POST /audit-cases/{id}/ledger-review      coche « justification reçue » /
                                            « masquer (contrepassée) »
  GET  /audit-cases/{id}/provisions         rollforward des provisions
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.controls import provisions as prov_ctl
from app.controls.running_balance import run_analysis, serialize as rb_serialize
from app.database import get_db
from app.models import (
    AuditCase, Dataset, DatasetKind, DatasetStatus, JournalEntry, JournalEntryLine,
    LedgerLineReview, ReviewModule, TrialBalanceLine, User,
)
from app.security import get_current_user

router = APIRouter(prefix="/audit-cases", tags=["comptes-analyses"])

SHAREHOLDER_PREFIXES = ("46",)
SUNDRY_DEBTOR_PREFIXES = ("4711",)
SUNDRY_CREDITOR_PREFIXES = ("4712",)


def _latest(db: Session, case_id: UUID, kind: DatasetKind) -> Dataset | None:
    return (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id, Dataset.kind == kind,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )


def _sources(db: Session, case_id: UUID):
    """(tb_lines, gl_lines_with_piece, tb_ds, gl_ds) — GL lines carry
    piece_number / entry_date lifted from their parent entry."""
    tb_ds = _latest(db, case_id, DatasetKind.TRIAL_BALANCE)
    gl_ds = _latest(db, case_id, DatasetKind.GENERAL_LEDGER)
    tb_lines = (
        db.query(TrialBalanceLine).filter(TrialBalanceLine.dataset_id == tb_ds.id).all()
        if tb_ds else []
    )
    gl_lines = []
    if gl_ds:
        rows = (
            db.query(JournalEntryLine, JournalEntry.piece_number, JournalEntry.entry_date)
            .join(JournalEntry, JournalEntryLine.entry_id == JournalEntry.id)
            .filter(JournalEntry.dataset_id == gl_ds.id)
            .all()
        )
        for line, piece, dt in rows:
            line.piece_number = piece      # transient attributes for the engines
            line.entry_date = dt
            gl_lines.append(line)
    return tb_lines, gl_lines, tb_ds, gl_ds


def _reviews(db: Session, case_id: UUID, module: ReviewModule):
    return {
        (r.piece_number, r.line_number): r
        for r in db.query(LedgerLineReview).filter(
            LedgerLineReview.audit_case_id == case_id,
            LedgerLineReview.module == module,
        ).all()
    }


def _case_or_404(db: Session, case_id: UUID) -> AuditCase:
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return case


# ── Comptes d'associés 46XX ─────────────────────────────────────────────────

@router.get("/{case_id}/comptes-associes")
def comptes_associes(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    _case_or_404(db, case_id)
    tb_lines, gl_lines, tb_ds, gl_ds = _sources(db, case_id)
    if not tb_ds and not gl_ds:
        return {"data_loaded": False, "accounts": [], "summary": None}

    analyses = run_analysis(tb_lines, gl_lines, SHAREHOLDER_PREFIXES, flag_side="DEBIT")
    reviews = _reviews(db, case_id, ReviewModule.SHAREHOLDER)
    accounts = rb_serialize(analyses, reviews)

    unjustified = 0
    unjustified_xaf = 0.0
    for acc in accounts:
        if acc["flagged_months"] == 0:
            continue
        for t in acc["transactions"]:
            if t["debit_xaf"] > 0 and not t["justified"] and not t["hidden_offset"]:
                unjustified += 1
                unjustified_xaf += t["debit_xaf"]

    summary = {
        "account_count": len(accounts),
        "accounts_in_debit": sum(1 for a in accounts if a["flagged_months"] > 0),
        "flagged_months_total": sum(a["flagged_months"] for a in accounts),
        "max_debit_xaf": max((a["max_wrong_side_xaf"] for a in accounts), default=0.0),
        "unjustified_count": unjustified,
        "unjustified_xaf": unjustified_xaf,
        "tb_filename": tb_ds.original_filename if tb_ds else None,
        "gl_filename": gl_ds.original_filename if gl_ds else None,
    }
    return {"data_loaded": True, "summary": summary, "accounts": accounts}


# ── Comptes divers 4711 / 4712 ──────────────────────────────────────────────

@router.get("/{case_id}/comptes-divers")
def comptes_divers(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    _case_or_404(db, case_id)
    tb_lines, gl_lines, tb_ds, gl_ds = _sources(db, case_id)
    if not tb_ds and not gl_ds:
        return {"data_loaded": False, "debtors": [], "creditors": [], "summary": None}

    reviews = _reviews(db, case_id, ReviewModule.SUNDRY)
    debtors = rb_serialize(
        run_analysis(tb_lines, gl_lines, SUNDRY_DEBTOR_PREFIXES, flag_side="BOTH"), reviews)
    creditors = rb_serialize(
        run_analysis(tb_lines, gl_lines, SUNDRY_CREDITOR_PREFIXES, flag_side="BOTH"), reviews)

    def worst(accs, nature):
        return max((abs(m["balance_xaf"]) for a in accs for m in a["months"]
                    if m["flagged"] and m["nature"] == nature), default=0.0)

    summary = {
        "debtor_account_count": len(debtors),
        "creditor_account_count": len(creditors),
        "debtor_flagged_months": sum(a["flagged_months"] for a in debtors),
        "creditor_flagged_months": sum(a["flagged_months"] for a in creditors),
        "max_debit_xaf": max(worst(debtors, "DEBIT"), worst(creditors, "DEBIT")),
        "max_credit_xaf": max(worst(debtors, "CREDIT"), worst(creditors, "CREDIT")),
        "tb_filename": tb_ds.original_filename if tb_ds else None,
        "gl_filename": gl_ds.original_filename if gl_ds else None,
    }
    return {"data_loaded": True, "summary": summary, "debtors": debtors, "creditors": creditors}


# ── Review flags ────────────────────────────────────────────────────────────

@router.post("/{case_id}/ledger-review")
def set_ledger_review(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: dict,
):
    """Body: {module, piece_number, line_number, account_code,
              justified?: bool, hidden_offset?: bool, note?: str}"""
    _case_or_404(db, case_id)
    try:
        module = ReviewModule(str(payload.get("module", "")).upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="Module inconnu (SHAREHOLDER | SUNDRY).")
    piece = str(payload.get("piece_number") or "")
    line_no = payload.get("line_number")
    if not piece or line_no is None:
        raise HTTPException(status_code=400, detail="piece_number et line_number sont requis.")

    row = (
        db.query(LedgerLineReview)
        .filter(LedgerLineReview.audit_case_id == case_id,
                LedgerLineReview.module == module,
                LedgerLineReview.piece_number == piece,
                LedgerLineReview.line_number == int(line_no))
        .first()
    )
    if row is None:
        row = LedgerLineReview(
            audit_case_id=case_id, module=module, piece_number=piece,
            line_number=int(line_no), account_code=str(payload.get("account_code") or "")[:64],
        )
        db.add(row)
    if "justified" in payload:
        row.justified = bool(payload["justified"])
    if "hidden_offset" in payload:
        row.hidden_offset = bool(payload["hidden_offset"])
    if "note" in payload:
        row.note = (str(payload["note"]) or None) and str(payload["note"])[:1024]
    row.updated_by = user.id
    db.commit()
    return {"ok": True, "justified": row.justified, "hidden_offset": row.hidden_offset}


# ── Provisions ──────────────────────────────────────────────────────────────

@router.get("/{case_id}/provisions")
def provisions(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    _case_or_404(db, case_id)
    tb_lines, gl_lines, tb_ds, gl_ds = _sources(db, case_id)
    if not tb_ds:
        return {"data_loaded": False, "rows": [], "summary": None,
                "note": "Balance générale absente — le rollforward part des soldes d'ouverture."}

    rows, summary = prov_ctl.analyze_provisions(tb_lines, gl_lines)
    summary["tb_filename"] = tb_ds.original_filename if tb_ds else None
    summary["gl_filename"] = gl_ds.original_filename if gl_ds else None
    summary["gl_loaded"] = gl_ds is not None
    return {
        "data_loaded": True,
        "summary": summary,
        "groups": [{"key": k, "label": lbl} for k, _p, lbl in prov_ctl.PROVISION_GROUPS],
        "rows": prov_ctl.serialize(rows),
    }
