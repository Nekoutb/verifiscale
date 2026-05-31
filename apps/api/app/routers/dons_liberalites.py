"""Dons et libéralités — CGI Cameroun, Art. 7.

Endpoints:
  GET    /audit-cases/{id}/dons-liberalites
         → aggregate + per-line view (uses persisted evidence verdicts)

  POST   /audit-cases/{id}/dons-liberalites/lines/{piece}/{line}/evidence
         (multipart: file, doc_kind)
         → upload one justificatif, persist + run Claude extraction
           (extraction left as a follow-up — see task #60)

  PATCH  /audit-cases/{id}/dons-liberalites/lines/{piece}/{line}/verdict
         (JSON: { verdict, reason })
         → manual override by the vérificateur

  GET    /audit-cases/{id}/dons-liberalites/lines/{piece}/{line}/evidence
         → list evidence rows for a line

  GET    /audit-cases/{id}/dons-liberalites/evidence/{evidence_id}/file
         → stream the original document

  DELETE /audit-cases/{id}/dons-liberalites/evidence/{evidence_id}
         → remove a justificatif

  GET    /audit-cases/{id}/dons-liberalites/djp.csv
         → export a Demande de Justificatifs (DJP, art. L20 LPF) for all
           ORANGE/ROUGE lines without sufficient evidence

Emits a ControlFinding (category FISCAL_C, code C-DONS-5PM) on every GET so
the consolidated /reports page picks it up.
"""
from __future__ import annotations

import csv
import io
import uuid as uuid_lib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, UploadFile, Body,
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.controls.dons_liberalites import (
    analyze_dons_liberalites,
    _compute_ca_ht,
    _get_or_create_ai_analysis,
)
from app.database import get_db
from app.models import (
    AiConfidence, AuditCase, ControlFinding, ControlRun, ControlSeverity,
    ControlStatus, Dataset, DatasetKind, DatasetStatus, DonationDocKind,
    DonationEvidence, DonationGroup, DonationGroupLine,
    DonationLibelleAnalysis, DonationVerdict, DonationVerdictSource,
    JournalEntry, JournalEntryLine, User,
)
from app.security import get_current_user
from app.services.dons_ai_analyzer import analyze_group_with_docs
from app.storage import get_object, put_object


router = APIRouter(prefix="/audit-cases", tags=["dons_liberalites"])

_MAX_DOC_BYTES = 20 * 1024 * 1024  # 20 MiB per justificatif


# ── Helpers ──────────────────────────────────────────────────────────────────


def _serialize_evidence(e: DonationEvidence) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "audit_case_id": str(e.audit_case_id),
        "piece_number": e.piece_number,
        "line_number": e.line_number,
        "slip_id": e.slip_id,
        "doc_kind": e.doc_kind.value,
        "filename": e.filename,
        "mime_type": e.mime_type,
        "size_bytes": e.size_bytes,
        "extracted": e.extracted,
        "verdict": e.verdict.value,
        "verdict_reason": e.verdict_reason,
        "verdict_source": e.verdict_source.value,
        "verdict_at": e.verdict_at.isoformat() if e.verdict_at else None,
        "uploaded_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
    }


def _upsert_finding(db: Session, case_id: UUID, payload: dict[str, Any]) -> None:
    """Refresh the FISCAL_C / C-DONS-5PM ControlFinding from the latest run."""
    summary = payload.get("summary") or {}
    reintegration = Decimal(str(summary.get("reintegration_xaf") or 0))
    non_eligible = Decimal(str(summary.get("total_non_eligible_xaf") or 0))
    to_reinstruct = Decimal(str(summary.get("total_a_reinstruire_xaf") or 0))

    if reintegration <= 0 and non_eligible <= 0 and to_reinstruct <= 0:
        return

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
            summary={"findings_count": 1, "blocking": 1, "high": 0, "medium": 0,
                     "estimated_total_impact_xaf": float(reintegration)},
        )
        db.add(run)
        db.flush()

    db.query(ControlFinding).filter(
        ControlFinding.control_run_id == run.id,
        ControlFinding.control_code == "C-DONS-5PM",
    ).delete()

    severity = (
        ControlSeverity.BLOCKING if reintegration > 0
        else ControlSeverity.HIGH
    )
    plafond = float(summary.get("plafond_xaf") or 0)
    ca_ht = float(summary.get("ca_ht_xaf") or 0)
    description = (
        f"Comptes 658X / 6713 / 838X : "
        f"engagé {float(summary.get('total_engage_xaf') or 0):,.0f} FCFA, "
        f"non éligible {float(non_eligible):,.0f} FCFA, "
        f"à réinstruire {float(to_reinstruct):,.0f} FCFA. "
        f"Plafond légal 5‰ × CA HT ({ca_ht:,.0f}) = {plafond:,.0f} FCFA. "
        f"Réintégration estimée : {float(reintegration):,.0f} FCFA "
        f"(CGI art. 7 — dons et libéralités)."
    ).replace(",", " ")

    finding = ControlFinding(
        control_run_id=run.id,
        control_code="C-DONS-5PM",
        title="Dons et libéralités au-delà du plafond 5‰ CA HT (CGI art. 7)",
        description=description,
        severity=severity,
        legal_reference="CGI Cameroun, Art. 7 — dons et libéralités",
        evidence={
            "plafond_per_mille": summary.get("plafond_per_mille"),
            "plafond_xaf": summary.get("plafond_xaf"),
            "ca_ht_xaf": summary.get("ca_ht_xaf"),
            "ca_ht_source": summary.get("ca_ht_source"),
            "total_engage_xaf": summary.get("total_engage_xaf"),
            "total_eligible_avant_plafond_xaf": summary.get("total_eligible_avant_plafond_xaf"),
            "total_non_eligible_xaf": summary.get("total_non_eligible_xaf"),
            "total_a_reinstruire_xaf": summary.get("total_a_reinstruire_xaf"),
            "excedent_plafond_xaf": summary.get("excedent_plafond_xaf"),
            "source_dataset_id": payload.get("source_dataset_id"),
            "source_filename": payload.get("source_filename"),
        },
        estimated_impact_xaf=reintegration,
    )
    db.add(finding)
    db.commit()


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/{case_id}/dons-liberalites")
def get_dons_liberalites(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    payload = analyze_dons_liberalites(db, case_id)
    try:
        _upsert_finding(db, case_id, payload)
    except Exception:
        db.rollback()
    return payload


@router.post(
    "/{case_id}/dons-liberalites/evidence",
    status_code=201,
)
async def upload_evidence(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    piece: Annotated[str, Form()],
    line: Annotated[int, Form()],
    doc_kind: Annotated[str, Form()] = "AUTRE",
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Fichier vide")
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(413, "Fichier trop volumineux : maximum 20 Mo")

    try:
        kind_enum = DonationDocKind(doc_kind.upper())
    except ValueError:
        raise HTTPException(400, f"doc_kind inconnu : {doc_kind}")

    storage_key = (
        f"audits/{case_id}/dons/{piece}/L{line}/"
        f"{uuid_lib.uuid4()}_{file.filename or 'doc.bin'}"
    )
    put_object(storage_key, data, content_type=file.content_type)

    evidence = DonationEvidence(
        audit_case_id=case_id,
        piece_number=piece,
        line_number=line,
        doc_kind=kind_enum,
        filename=file.filename or "doc.bin",
        storage_path=storage_key,
        mime_type=file.content_type,
        size_bytes=len(data),
        verdict=DonationVerdict.A_REINSTRUIRE,
        verdict_reason="Document chargé — extraction en attente.",
        verdict_source=DonationVerdictSource.DOC_EXTRACTED,
        uploaded_by=user.id,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return _serialize_evidence(evidence)


@router.get("/{case_id}/dons-liberalites/line-evidence")
def list_line_evidence(
    case_id: UUID,
    piece: str,
    line: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    rows = (
        db.query(DonationEvidence)
        .filter(
            DonationEvidence.audit_case_id == case_id,
            DonationEvidence.piece_number == piece,
            DonationEvidence.line_number == line,
        )
        .order_by(DonationEvidence.uploaded_at.desc())
        .all()
    )
    return {"items": [_serialize_evidence(e) for e in rows]}


@router.patch("/{case_id}/dons-liberalites/verdict")
def override_verdict(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    piece = str(payload.get("piece", "")).strip()
    try:
        line = int(payload.get("line", 0))
    except (TypeError, ValueError):
        line = 0
    if not piece or line <= 0:
        raise HTTPException(400, "piece et line sont requis dans le corps de la requête.")
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    try:
        verdict = DonationVerdict(str(payload.get("verdict", "")).upper())
    except ValueError:
        raise HTTPException(400, "verdict invalide (ELIGIBLE / NON_ELIGIBLE / A_REINSTRUIRE)")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Une motivation écrite est requise pour tout override.")

    # Persist as a synthetic DonationEvidence row tagged MANUAL_OVERRIDE so
    # the audit trail keeps the auditor identity + timestamp.
    e = DonationEvidence(
        audit_case_id=case_id,
        piece_number=piece,
        line_number=line,
        doc_kind=DonationDocKind.AUTRE,
        filename="(override)",
        storage_path="",
        verdict=verdict,
        verdict_reason=reason,
        verdict_source=DonationVerdictSource.MANUAL_OVERRIDE,
        verdict_by=user.id,
        verdict_at=datetime.now(timezone.utc),
        uploaded_by=user.id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _serialize_evidence(e)


@router.get("/{case_id}/dons-liberalites/evidence/{evidence_id}/file")
def get_evidence_file(
    case_id: UUID,
    evidence_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    e = db.get(DonationEvidence, evidence_id)
    if not e or e.audit_case_id != case_id:
        raise HTTPException(404, "Justificatif introuvable")
    if not e.storage_path:
        raise HTTPException(404, "Aucun fichier rattaché (entrée d'override).")
    try:
        data = get_object(e.storage_path)
    except FileNotFoundError:
        raise HTTPException(404, "Fichier manquant sur le stockage")
    return Response(
        content=data,
        media_type=e.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{e.filename}"'},
    )


@router.delete("/{case_id}/dons-liberalites/evidence/{evidence_id}",
               status_code=204)
def delete_evidence(
    case_id: UUID,
    evidence_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    e = db.get(DonationEvidence, evidence_id)
    if not e or e.audit_case_id != case_id:
        raise HTTPException(404, "Justificatif introuvable")
    db.delete(e)
    db.commit()
    return Response(status_code=204)


@router.get("/{case_id}/dons-liberalites/djp.csv")
def export_djp_csv(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Export a CSV of lines needing justificatifs — to attach to a
    Demande de Justificatifs au contribuable (art. L20 LPF)."""
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    payload = analyze_dons_liberalites(db, case_id)
    rows = payload.get("lines") or []

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "Pièce", "Date", "Ligne", "Compte", "Intitulé compte",
        "Libellé GL", "Montant FCFA", "Confiance",
        "Bénéficiaire (estimation)", "NIU détecté",
        "Justificatifs attendus",
    ])
    for r in rows:
        if r.get("verdict") not in ("A_REINSTRUIRE", "NON_ELIGIBLE"):
            continue
        if r.get("has_evidence") and r.get("verdict") == "ELIGIBLE":
            continue
        w.writerow([
            r.get("piece_number"),
            r.get("entry_date") or "",
            r.get("line_number"),
            r.get("account_code"),
            r.get("account_name") or "",
            r.get("libelle") or "",
            f"{r.get('amount_xaf', 0):.0f}",
            r.get("confidence"),
            r.get("beneficiary_name_guess") or "",
            r.get("beneficiary_niu") or "",
            "Reçu de l'organisme + statuts/agrément + preuve de virement",
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="djp_dons_{case_id}.csv"'
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# AI deepening — Claude libellé analysis per line + groups
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/{case_id}/dons-liberalites/ai-analyze")
def trigger_ai_analysis(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()] = None,  # type: ignore[assignment]
):
    """Trigger Claude analysis on a subset of lines.

    payload = {
        "lines": [{"piece_number": "...", "line_number": 1}, ...],   # required
    }
    Each line is looked up in the GL, the libellé is sent to Claude, and the
    result is cached in donation_libelle_analysis.
    """
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    lines = (payload or {}).get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise HTTPException(400, "Liste de lignes requise.")
    # Resolve GL for the case
    gl_ds = (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id,
                Dataset.kind == DatasetKind.GENERAL_LEDGER,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if gl_ds is None:
        raise HTTPException(400, "Aucun grand-livre disponible.")
    # CA context
    ca_ht, _src = _compute_ca_ht(db, case_id)
    fiscal_year = getattr(case, "fiscal_year", None)

    targets: list[tuple[str, int, JournalEntryLine, JournalEntry]] = []
    # Pull each requested (piece, line) from the latest GL
    for item in lines:
        piece = str(item.get("piece_number") or "").strip()
        try:
            line_no = int(item.get("line_number"))
        except (TypeError, ValueError):
            continue
        row = (
            db.query(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .filter(JournalEntry.dataset_id == gl_ds.id,
                    JournalEntry.piece_number == piece,
                    JournalEntryLine.line_number == line_no)
            .first()
        )
        if row:
            line, entry = row
            targets.append((piece, line_no, line, entry))

    processed = 0
    for piece, line_no, line, _entry in targets:
        _get_or_create_ai_analysis(
            db, case_id, piece, line_no, line.libelle, line.account_code,
            float(ca_ht), fiscal_year, do_call=True,
        )
        processed += 1
    db.commit()
    return {"processed": processed, "requested": len(lines)}


@router.post("/{case_id}/dons-liberalites/groups", status_code=201)
def create_group(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nom du groupe requis.")
    lines = payload.get("lines") or []
    g = DonationGroup(
        audit_case_id=case_id,
        name=name[:256],
        description=(payload.get("description") or None),
        group_verdict_source="A_REINSTRUIRE",
        created_by=user.id,
    )
    db.add(g)
    db.flush()
    for item in lines:
        piece = str(item.get("piece_number") or "").strip()
        try:
            line_no = int(item.get("line_number"))
        except (TypeError, ValueError):
            continue
        if not piece:
            continue
        # Drop any existing membership on this line (one group per line)
        db.query(DonationGroupLine).filter(
            DonationGroupLine.piece_number == piece,
            DonationGroupLine.line_number == line_no,
            DonationGroupLine.group_id.in_(
                db.query(DonationGroup.id).filter(DonationGroup.audit_case_id == case_id)
            ),
        ).delete(synchronize_session=False)
        db.add(DonationGroupLine(group_id=g.id, piece_number=piece, line_number=line_no))
    db.commit()
    db.refresh(g)
    return {"id": str(g.id), "name": g.name}


@router.patch("/{case_id}/dons-liberalites/groups/{group_id}")
def update_group(
    case_id: UUID,
    group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: Annotated[dict, Body()],
):
    g = db.get(DonationGroup, group_id)
    if not g or g.audit_case_id != case_id:
        raise HTTPException(404, "Groupe introuvable")
    if "name" in payload and payload["name"]:
        g.name = str(payload["name"])[:256]
    if "description" in payload:
        g.description = payload["description"] or None
    if "group_verdict" in payload and payload["group_verdict"]:
        verdict = str(payload["group_verdict"]).upper()
        if verdict not in {"ELIGIBLE", "NON_ELIGIBLE", "A_REINSTRUIRE"}:
            raise HTTPException(400, "group_verdict invalide")
        g.group_verdict = verdict
        g.group_verdict_source = "MANUAL"
    if "group_verdict_reason" in payload:
        g.group_verdict_reason = payload["group_verdict_reason"] or None
    db.commit()
    return {"ok": True}


@router.delete("/{case_id}/dons-liberalites/groups/{group_id}", status_code=204)
def delete_group(
    case_id: UUID, group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    g = db.get(DonationGroup, group_id)
    if not g or g.audit_case_id != case_id:
        raise HTTPException(404, "Groupe introuvable")
    db.delete(g)
    db.commit()
    return Response(status_code=204)


@router.post("/{case_id}/dons-liberalites/groups/{group_id}/evidence", status_code=201)
async def upload_group_evidence(
    case_id: UUID, group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    doc_kind: Annotated[str, Form()] = "AUTRE",
):
    g = db.get(DonationGroup, group_id)
    if not g or g.audit_case_id != case_id:
        raise HTTPException(404, "Groupe introuvable")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Fichier vide")
    try:
        kind_enum = DonationDocKind(doc_kind.upper())
    except ValueError:
        raise HTTPException(400, f"doc_kind inconnu : {doc_kind}")

    import uuid as uuid_lib
    storage_key = (
        f"audits/{case_id}/dons/groups/{group_id}/"
        f"{uuid_lib.uuid4()}_{file.filename or 'doc.bin'}"
    )
    put_object(storage_key, data, content_type=file.content_type)

    evidence = DonationEvidence(
        audit_case_id=case_id,
        piece_number="",          # group-level evidence
        line_number=0,
        doc_kind=kind_enum,
        filename=file.filename or "doc.bin",
        storage_path=storage_key,
        mime_type=file.content_type,
        size_bytes=len(data),
        verdict=DonationVerdict.A_REINSTRUIRE,
        verdict_reason="Pièce du groupe — analyse Claude en attente.",
        verdict_source=DonationVerdictSource.DOC_EXTRACTED,
        uploaded_by=user.id,
        group_id=group_id,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return {"id": str(evidence.id), "filename": evidence.filename}


@router.post("/{case_id}/dons-liberalites/groups/{group_id}/ai-analyze")
def analyze_group_documents(
    case_id: UUID, group_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Run Claude on the group's uploaded docs + member-line summary.

    Result populates group_verdict / ai_confidence / group_verdict_reason and
    will propagate at the next GET (unless a line has a MANUAL_OVERRIDE).
    """
    g = db.get(DonationGroup, group_id)
    if not g or g.audit_case_id != case_id:
        raise HTTPException(404, "Groupe introuvable")

    # Member lines
    member_assocs = (
        db.query(DonationGroupLine)
        .filter(DonationGroupLine.group_id == group_id)
        .all()
    )
    # Resolve current GL libellés for these members
    gl_ds = (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id,
                Dataset.kind == DatasetKind.GENERAL_LEDGER,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    lines_payload: list[dict[str, Any]] = []
    if gl_ds is not None and member_assocs:
        for a in member_assocs:
            row = (
                db.query(JournalEntryLine, JournalEntry)
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
                .filter(JournalEntry.dataset_id == gl_ds.id,
                        JournalEntry.piece_number == a.piece_number,
                        JournalEntryLine.line_number == a.line_number)
                .first()
            )
            if row:
                line, entry = row
                amount = float(Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0)))
                lines_payload.append({
                    "piece": a.piece_number,
                    "line": a.line_number,
                    "account": line.account_code,
                    "libelle": line.libelle,
                    "amount": amount,
                    "date": entry.entry_date.isoformat() if entry.entry_date else None,
                })

    # Load group docs (RECU/CONVENTION/AGREMENT…)
    docs: list[tuple[bytes, str]] = []
    evidences = (
        db.query(DonationEvidence)
        .filter(DonationEvidence.group_id == group_id)
        .order_by(DonationEvidence.uploaded_at.asc())
        .all()
    )
    for e in evidences:
        if not e.storage_path:
            continue
        try:
            blob = get_object(e.storage_path)
            docs.append((blob, e.mime_type or "application/pdf"))
        except FileNotFoundError:
            continue

    v = analyze_group_with_docs(g.name, lines_payload, docs)
    g.group_verdict = v.verdict
    g.ai_confidence = AiConfidence(v.confidence)
    g.ai_indicators = {"items": v.indicators}
    g.group_verdict_reason = v.reason
    g.group_verdict_source = "AUTO_DOC"
    db.commit()
    return {
        "verdict": v.verdict,
        "confidence": v.confidence,
        "reason": v.reason,
        "indicators": v.indicators,
        "lines_analyzed": len(lines_payload),
        "docs_analyzed": len(docs),
    }
