"""Petit matériel et outillage — CGI Cameroun (seuil 500 000 FCFA).

Règle : une acquisition ≥ 500 000 FCFA doit être IMMOBILISÉE (classe 2) puis
amortie, et non passée directement en charge. L'outillage à main dit petit
outillage s'amortit toutefois à 100 % (donc aucun impact si correctement
qualifié).

Approche (validée) :
  - Test par LIGNE ≥ 500 000 FCFA sur les comptes de charges porteurs.
  - Qualification auto par mots-clés (override auditeur) → taux d'amort. 1ère année.
  - DEUX montants de réintégration affichés (choix du vérificateur) :
      • DIFFERENTIAL = coût − (coût × taux_1ère_année)   ← recommandé
      • TOTAL        = coût                                ← strict

Note : la détection du FRACTIONNEMENT (plusieurs factures < 500K d'un même
fournisseur destinées à contourner le seuil) relève du contrôle des FACTURES
— elle est traitée dans le module dédié aux factures, pas ici.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    Dataset, DatasetKind, DatasetStatus, JournalEntry, JournalEntryLine,
    PetitMaterielLine, PetitMatBasis, PetitMatQualif,
)


THRESHOLD_XAF = Decimal("500000")   # seuil d'immobilisation obligatoire

# Comptes de charges porteurs de petit matériel / équipement
TARGET_ACCOUNTS = ("6056",)                       # Achats de petit matériel et outillage
GREY_ZONE_ACCOUNTS = ("6044", "6047", "6055", "624")  # fournitures atelier/bureau, entretien

# Taux d'amortissement de 1ère année par qualification (barème CGI Art. 7 D)
QUALIF_RATE: dict[str, Decimal] = {
    "HAND_TOOL": Decimal("100"),
    "IT": Decimal("25"),
    "REPRO": Decimal("33.33"),
    "FURNITURE": Decimal("10"),
    "EQUIPMENT": Decimal("20"),
    "OTHER": Decimal("20"),
    "EXCLUDED": Decimal("100"),
}

# Mots-clés → qualification (auto, override possible)
_KEYWORDS: list[tuple[str, list[str]]] = [
    ("HAND_TOOL", ["outillage", "clé", "cle ", "marteau", "perceuse", "pince", "tournevis",
                    "scie", "perforateur", "foreuse", "meuleuse", "burin", "lime", "tenaille",
                    "boulonneuse", "visseuse", "agrafeuse"]),
    ("IT", ["ordinateur", "laptop", "pc ", "portable", "imprimante", "scanner", "serveur",
             "onduleur", "switch", "routeur", "disque", "ecran", "écran", "clavier", "souris",
             "tablette", "telephone", "téléphone", "smartphone"]),
    ("REPRO", ["photocopieur", "copieur", "reprographie", "duplicateur"]),
    ("FURNITURE", ["bureau", "chaise", "fauteuil", "armoire", "table", "mobilier", "étagère",
                    "etagere", "rayonnage", "meuble", "comptoir"]),
    ("EQUIPMENT", ["machine", "groupe électrogène", "groupe electrogene", "climatiseur",
                    "climatisation", "compresseur", "pompe", "moteur", "équipement", "equipement",
                    "vitrine", "frigo", "congélateur", "congelateur", "four"]),
]


@dataclass
class PMLine:
    piece_number: str
    entry_date: str | None
    line_number: int
    account_code: str
    account_name: str | None
    libelle: str | None
    amount_xaf: Decimal
    supplier_guess: str | None
    qualification: str
    qualification_source: str       # AUTO | MANUAL
    depreciation_rate_pct: Decimal
    reint_differential_xaf: Decimal
    reint_total_xaf: Decimal
    reint_third_xaf: Decimal
    basis: str                      # DIFFERENTIAL | TOTAL | THIRD
    reintegration_xaf: Decimal      # selon basis
    excluded: bool
    verdict_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "piece_number": self.piece_number,
            "entry_date": self.entry_date,
            "line_number": self.line_number,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "libelle": self.libelle,
            "amount_xaf": float(self.amount_xaf),
            "supplier_guess": self.supplier_guess,
            "qualification": self.qualification,
            "qualification_source": self.qualification_source,
            "depreciation_rate_pct": float(self.depreciation_rate_pct),
            "reint_differential_xaf": float(self.reint_differential_xaf),
            "reint_total_xaf": float(self.reint_total_xaf),
            "reint_third_xaf": float(self.reint_third_xaf),
            "basis": self.basis,
            "reintegration_xaf": float(self.reintegration_xaf),
            "excluded": self.excluded,
            "verdict_reason": self.verdict_reason,
        }


def _auto_qualify(libelle: str | None, account_name: str | None) -> str:
    text = f"{libelle or ''} {account_name or ''}".lower()
    for qualif, kws in _KEYWORDS:
        if any(kw in text for kw in kws):
            return qualif
    return "OTHER"


def _supplier_guess(libelle: str | None) -> str | None:
    if not libelle:
        return None
    s = re.sub(r"\b(F|FA|FAC|FACT|FACTURE|BON|BC)\s*[°N]?\.?\s*\d+\b", "", libelle, flags=re.I)
    s = re.sub(r"\b\d{2,4}[/.-]\d{1,2}[/.-]\d{1,4}\b", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -:,;")
    return s[:50] or None


def _latest_dataset(db: Session, case_id: UUID, kind: DatasetKind) -> Dataset | None:
    return (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id, Dataset.kind == kind,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )


def analyze_petit_materiel(db: Session, case_id: UUID) -> dict[str, Any]:
    gl_ds = _latest_dataset(db, case_id, DatasetKind.GENERAL_LEDGER)
    if gl_ds is None:
        return {
            "threshold_xaf": float(THRESHOLD_XAF),
            "target_accounts": list(TARGET_ACCOUNTS),
            "lines": [], "summary": None,
            "note": "Aucun grand-livre chargé. Importez-le pour activer ce contrôle.",
            "legal_reference": "CGI Cameroun — seuil d'immobilisation 500 000 FCFA",
        }

    # Overrides indexed by (piece, line)
    overrides = {
        (o.piece_number, o.line_number): o
        for o in db.query(PetitMaterielLine).filter(
            PetitMaterielLine.audit_case_id == case_id).all()
    }

    all_prefixes = TARGET_ACCOUNTS + GREY_ZONE_ACCOUNTS
    rows = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .order_by(JournalEntry.entry_date, JournalEntry.piece_number, JournalEntryLine.line_number)
        .all()
    )

    out: list[PMLine] = []
    candidates: list[tuple[JournalEntryLine, JournalEntry]] = []
    for line, entry in rows:
        acc = line.account_code or ""
        if not any(acc.startswith(p) for p in all_prefixes):
            continue
        amount = Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        if amount <= 0:
            continue
        candidates.append((line, entry))

    for line, entry in candidates:
        amount = Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        # Only lines >= threshold are findings; below are not tested (legitimately expensable)
        if amount < THRESHOLD_XAF:
            continue

        key = (entry.piece_number, line.line_number)
        ov = overrides.get(key)

        if ov and ov.qualification is not None:
            qualif = ov.qualification.value
            qualif_source = "MANUAL"
        else:
            qualif = _auto_qualify(line.libelle, line.account_name)
            qualif_source = "AUTO"

        excluded = bool(ov and ov.excluded)

        rate = (Decimal(str(ov.depreciation_rate_pct)) if ov and ov.depreciation_rate_pct is not None
                else QUALIF_RATE.get(qualif, Decimal("20")))

        amort_1 = (amount * rate / 100)
        reint_diff = max(Decimal("0"), amount - amort_1)
        reint_total = amount
        # 3e option : 1/3 déductible, 2/3 réintégré
        reint_third = (amount * Decimal("2") / Decimal("3")).quantize(Decimal("1"))

        basis = (ov.reintegration_basis.value if ov and ov.reintegration_basis else "DIFFERENTIAL")
        if excluded:
            reintegration = Decimal("0")
        elif basis == "TOTAL":
            reintegration = reint_total
        elif basis == "THIRD":
            reintegration = reint_third
        else:
            reintegration = reint_diff

        out.append(PMLine(
            piece_number=entry.piece_number,
            entry_date=entry.entry_date.isoformat() if entry.entry_date else None,
            line_number=line.line_number,
            account_code=line.account_code,
            account_name=line.account_name,
            libelle=line.libelle,
            amount_xaf=amount,
            supplier_guess=_supplier_guess(line.libelle),
            qualification=qualif,
            qualification_source=qualif_source,
            depreciation_rate_pct=rate,
            reint_differential_xaf=reint_diff,
            reint_total_xaf=reint_total,
            reint_third_xaf=reint_third,
            basis=basis,
            reintegration_xaf=reintegration,
            excluded=excluded,
            in_far=False,
            split_flag=False,
            verdict_reason=(ov.verdict_reason if ov else None),
        ))

    out.sort(key=lambda l: -float(l.amount_xaf))

    total_diff = sum((l.reint_differential_xaf for l in out if not l.excluded), Decimal("0"))
    total_full = sum((l.reint_total_xaf for l in out if not l.excluded), Decimal("0"))
    total_third = sum((l.reint_third_xaf for l in out if not l.excluded), Decimal("0"))
    total_selected = sum((l.reintegration_xaf for l in out), Decimal("0"))

    summary = {
        "threshold_xaf": float(THRESHOLD_XAF),
        "line_count": len(out),
        "hand_tool_count": sum(1 for l in out if l.qualification == "HAND_TOOL"),
        "other_count": sum(1 for l in out if l.qualification not in ("HAND_TOOL", "EXCLUDED")),
        "excluded_count": sum(1 for l in out if l.excluded),
        "total_amount_xaf": float(sum((l.amount_xaf for l in out), Decimal("0"))),
        "total_reint_differential_xaf": float(total_diff),
        "total_reint_total_xaf": float(total_full),
        "total_reint_third_xaf": float(total_third),
        "total_reintegration_selected_xaf": float(total_selected),
    }

    return {
        "threshold_xaf": float(THRESHOLD_XAF),
        "target_accounts": list(TARGET_ACCOUNTS),
        "grey_zone_accounts": list(GREY_ZONE_ACCOUNTS),
        "source_filename": gl_ds.original_filename,
        "lines": [l.to_dict() for l in out],
        "summary": summary,
        "legal_reference": "CGI Cameroun — seuil d'immobilisation 500 000 FCFA ; outillage à main amorti 100 %",
    }
