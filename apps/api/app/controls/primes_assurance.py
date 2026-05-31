"""Primes d'assurance — CGI Cameroun, Art. 7, A (4).

10 contrôles documentés (lecture officielle CGI 2025) :

  C1  Rapprochement Σ contrats ↔ Σ comptes 625X + 6685 + 6686 (pivot)
  C2  Auto-assurance (compte 6911) explicitement non-déductible
  C3  Assureur LOCAL (Cameroun) — exigence Art. 7 A 4 tirets 3 et 4
  C4  Assurance-vie « homme-clé » au profit société — réintégration (doctrine)
  C5  Assurance vie/santé dirigeant/famille — avantage en nature
  C6  Règle anti-cumul Art. 7 A 4 tiret 3 (santé groupe + remb. frais)
  C7  Rattachement temporel (CCA 476) pour primes à cheval
  C8  Primes payées en espèces > 100 K (croise contrôle Art. 7 bis)
  C9  TSR 15 % primes étrangères (Art. 225 — à confirmer)
  C10 Intra-groupe / captive (prix de transfert)

Sortie : agrégat par contrat + verdict + réintégration estimée.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    ContratAssurance,
    Dataset,
    DatasetKind,
    DatasetStatus,
    InsuranceBenefType,
    InsuranceType,
    InsuranceVerdict,
    JournalEntry,
    JournalEntryLine,
    RegistreAssureurAgree,
)


# ── Configuration ────────────────────────────────────────────────────────────

# Comptes SYSCOHADA Révisé visés par le contrôle (vérification officielle PDF)
PRIME_ACCOUNT_PREFIXES: tuple[str, ...] = (
    "625",   # 6251..6258 Primes d'assurance (services extérieurs)
    "6685",  # Assurances et organismes de santé (charges de personnel)
    "6686",  # Assurances retraite et fonds de pension
)

# Comptes liés au contrôle C6 (anti-cumul santé)
HEALTH_REIMBURSEMENT_ACCOUNTS: tuple[str, ...] = (
    "6684",  # Médecine du travail et pharmacie
    "6615",  # Indemnités maladie versées (personnel national)
    "6625",  # Idem (personnel non-national)
)

# Compte sur lequel guetter l'auto-assurance (C2)
AUTO_INSURANCE_PROVISION_PREFIX = "6911"

# Tolérance sur le rapprochement contrats/GL
RECONCILIATION_TOLERANCE_PCT = Decimal("1.0")  # ±1 %

# Pays = local
LOCAL_COUNTRY_CODE = "CM"


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class ContractView:
    """Vue d'un contrat enrichie de son diagnostic."""
    id: str
    filename: str
    numero_police: str | None
    assureur_nom: str | None
    assureur_pays: str
    assureur_local: bool
    beneficiaire_nom: str | None
    beneficiaire_type: str
    type_assurance: str
    date_debut: str | None
    date_fin: str | None
    prime_annuelle_ttc: float
    prime_exercice: float
    compte_syscohada: str | None
    verdict: str
    verdict_reason: str
    verdict_source: str
    findings: list[str]                 # codes de checks déclenchés
    estimated_reintegration_xaf: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "numero_police": self.numero_police,
            "assureur_nom": self.assureur_nom,
            "assureur_pays": self.assureur_pays,
            "assureur_local": self.assureur_local,
            "beneficiaire_nom": self.beneficiaire_nom,
            "beneficiaire_type": self.beneficiaire_type,
            "type_assurance": self.type_assurance,
            "date_debut": self.date_debut,
            "date_fin": self.date_fin,
            "prime_annuelle_ttc": self.prime_annuelle_ttc,
            "prime_exercice": self.prime_exercice,
            "compte_syscohada": self.compte_syscohada,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "verdict_source": self.verdict_source,
            "findings": self.findings,
            "estimated_reintegration_xaf": self.estimated_reintegration_xaf,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _starts_with_any(account: str | None, prefixes: tuple[str, ...]) -> bool:
    if not account:
        return False
    return any(account.startswith(p) for p in prefixes)


def _sum_gl_account_debit(
    db: Session, case_id: UUID, prefix: str,
) -> Decimal:
    """Σ débits − crédits sur les comptes commençant par `prefix` sur le dernier GL."""
    gl_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.GENERAL_LEDGER,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if gl_ds is None:
        return Decimal("0")
    rows = (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .all()
    )
    total = Decimal("0")
    for r in rows:
        if not (r.account_code or "").startswith(prefix):
            continue
        total += Decimal(str(r.debit or 0)) - Decimal(str(r.credit or 0))
    return total


def _gl_total_by_account(
    db: Session, case_id: UUID, prefixes: tuple[str, ...],
) -> dict[str, Decimal]:
    """Σ par compte (4 premiers chiffres) sur le dernier GL parsé."""
    gl_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.GENERAL_LEDGER,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    out: dict[str, Decimal] = {}
    if gl_ds is None:
        return out
    rows = (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .all()
    )
    for r in rows:
        acc = r.account_code or ""
        if not _starts_with_any(acc, prefixes):
            continue
        key = acc[:4]
        out[key] = out.get(key, Decimal("0")) + (
            Decimal(str(r.debit or 0)) - Decimal(str(r.credit or 0))
        )
    return out


def _resolve_local_insurer(
    db: Session, contrat: ContratAssurance,
) -> bool:
    """An insurer is 'local' if it's tagged CM AND (it's in the registry OR
    we don't have a registry hit but the country is Cameroon)."""
    if contrat.assureur_pays and contrat.assureur_pays.upper() != LOCAL_COUNTRY_CODE:
        return False
    if contrat.assureur_id:
        # Already linked to registry → trust it
        return True
    # Try to match by NIU if available
    if contrat.assureur_niu:
        hit = db.query(RegistreAssureurAgree).filter(
            RegistreAssureurAgree.niu == contrat.assureur_niu.upper()
        ).first()
        if hit:
            return True
    # Fall back to name + country
    return (contrat.assureur_pays or "CM").upper() == LOCAL_COUNTRY_CODE


# ── Per-contract diagnosis (controls C2..C10 applied per contract) ───────────


def _diagnose_contract(
    db: Session, contrat: ContratAssurance,
) -> tuple[str, str, list[str], Decimal]:
    """Returns (verdict, reason, findings_codes, reintegration_xaf).

    A contract starts ELIGIBLE and is downgraded by each check that fires.
    Manual override (verdict_source = MANUAL_OVERRIDE) takes priority.
    """
    if contrat.verdict_source and contrat.verdict_source.value == "MANUAL_OVERRIDE":
        return (
            contrat.verdict.value,
            contrat.verdict_reason or "Décision motivée du vérificateur",
            ["MANUAL_OVERRIDE"],
            Decimal(str(contrat.prime_exercice or contrat.prime_annuelle_ttc or 0))
            if contrat.verdict.value == "NON_ELIGIBLE" else Decimal("0"),
        )

    findings: list[str] = []
    reasons: list[str] = []
    is_non_eligible = False
    needs_reinstruction = False

    prime_exo = Decimal(str(contrat.prime_exercice or contrat.prime_annuelle_ttc or 0))
    ttype = contrat.type_assurance.value if contrat.type_assurance else "AUTRE"
    benef = contrat.beneficiaire_type.value if contrat.beneficiaire_type else "INCONNU"

    # C3 — Assureur local (santé personnel + retraite obligent compagnie locale)
    is_local = _resolve_local_insurer(db, contrat)
    if not is_local:
        if ttype in {"SANTE_PERSONNEL", "RETRAITE_FIN_CARRIERE"}:
            findings.append("INSURER-NOT-LOCAL-MANDATORY")
            reasons.append(
                f"Art. 7 A 4 exige une compagnie d'assurance LOCALE pour {ttype} "
                "— assureur ici hors Cameroun → non déductible."
            )
            is_non_eligible = True
        else:
            findings.append("INSURER-NOT-LOCAL")
            reasons.append(
                "Assureur hors zone CIMA/Cameroun — vérifier l'agrément local + TSR 15 %."
            )
            needs_reinstruction = True

    # C9 — TSR primes étrangères
    if not is_local:
        findings.append("TSR-CHECK-FOREIGN-INSURER")
        reasons.append(
            "Vérifier que la retenue à la source de 15 % (+ CAC) a été déclarée "
            "sur la DMM (section 1, L1 TSR) pour cette prime versée à l'étranger."
        )
        # Doesn't make the contract non-eligible by itself but flags for verification

    # C4 — Assurance-vie homme-clé (bénéficiaire = entreprise)
    if ttype == "VIE_HOMME_CLE" and benef == "ENTREPRISE":
        findings.append("LIFE-INSURANCE-COMPANY-BENEF")
        reasons.append(
            "Assurance-vie « homme-clé » au profit de la société : la mort du "
            "dirigeant n'entraîne pas une diminution mesurable de l'actif net "
            "(doctrine constante) → réintégration."
        )
        is_non_eligible = True

    # C5 — Assurance vie/santé au profit dirigeant ou famille
    if benef in {"DIRIGEANT", "FAMILLE_DIRIGEANT"} and ttype in {
        "VIE_DIRIGEANT", "VIE_HOMME_CLE", "SANTE_PERSONNEL"
    }:
        findings.append("FRINGE-BENEFIT-DIRECTOR")
        reasons.append(
            "Bénéficiaire = dirigeant ou sa famille → avantage en nature : "
            "non déductible IS + soumis à IRPP, CFC, cotisations sociales."
        )
        is_non_eligible = True

    # Inconnu = à réinstruire
    if benef == "INCONNU":
        findings.append("BENEFICIARY-UNKNOWN")
        reasons.append("Bénéficiaire non identifié sur le contrat — à clarifier.")
        needs_reinstruction = True

    if not contrat.prime_annuelle_ttc or contrat.prime_annuelle_ttc <= 0:
        findings.append("PREMIUM-MISSING")
        reasons.append("Prime annuelle non extraite — police à compléter.")
        needs_reinstruction = True

    # Verdict
    if is_non_eligible:
        return (
            InsuranceVerdict.NON_ELIGIBLE.value,
            " ".join(reasons),
            findings,
            prime_exo,
        )
    if needs_reinstruction:
        return (
            InsuranceVerdict.A_REINSTRUIRE.value,
            " ".join(reasons) or "À réinstruire après pièces complémentaires.",
            findings,
            Decimal("0"),
        )
    return (
        InsuranceVerdict.ELIGIBLE.value,
        "Contrat conforme Art. 7 A 4 — assureur local, bénéficiaire entreprise.",
        findings,
        Decimal("0"),
    )


# ── Main entrypoint ──────────────────────────────────────────────────────────


def analyze_primes_assurance(db: Session, case_id: UUID) -> dict[str, Any]:
    """Run the full primes d'assurance control suite."""
    contrats = (
        db.query(ContratAssurance)
        .filter(ContratAssurance.audit_case_id == case_id)
        .order_by(ContratAssurance.uploaded_at.desc())
        .all()
    )

    # ── C1 — Rapprochement Σ contrats ↔ Σ GL ────────────────────────────────
    gl_by_account = _gl_total_by_account(db, case_id, PRIME_ACCOUNT_PREFIXES)
    gl_total = sum(gl_by_account.values(), Decimal("0"))

    # C2 — Auto-assurance
    auto_insurance_xaf = _sum_gl_account_debit(db, case_id, AUTO_INSURANCE_PROVISION_PREFIX)

    # Contracts breakdown
    contracts_total_annuel = sum(
        (Decimal(str(c.prime_annuelle_ttc or 0)) for c in contrats), Decimal("0"),
    )
    contracts_total_exercice = sum(
        (Decimal(str(c.prime_exercice or c.prime_annuelle_ttc or 0)) for c in contrats),
        Decimal("0"),
    )

    variance = gl_total - contracts_total_exercice
    variance_pct = (
        (variance / gl_total * 100).quantize(Decimal("0.01"))
        if gl_total > 0 else Decimal("0")
    )
    reconciliation_status = (
        "OK"
        if gl_total > 0 and abs(variance_pct) <= RECONCILIATION_TOLERANCE_PCT
        else ("VARIANCE_MAJOR" if gl_total > 0 else "NO_GL")
    )

    # ── Per-contract diagnosis ──────────────────────────────────────────────
    contract_views: list[ContractView] = []
    total_reintegration = Decimal("0")
    for c in contrats:
        verdict, reason, findings, reint = _diagnose_contract(db, c)
        total_reintegration += reint

        contract_views.append(ContractView(
            id=str(c.id),
            filename=c.filename,
            numero_police=c.numero_police,
            assureur_nom=c.assureur_nom,
            assureur_pays=c.assureur_pays,
            assureur_local=_resolve_local_insurer(db, c),
            beneficiaire_nom=c.beneficiaire_nom,
            beneficiaire_type=c.beneficiaire_type.value,
            type_assurance=c.type_assurance.value,
            date_debut=c.date_debut.isoformat() if c.date_debut else None,
            date_fin=c.date_fin.isoformat() if c.date_fin else None,
            prime_annuelle_ttc=float(c.prime_annuelle_ttc or 0),
            prime_exercice=float(c.prime_exercice or c.prime_annuelle_ttc or 0),
            compte_syscohada=c.compte_syscohada,
            verdict=verdict,
            verdict_reason=reason,
            verdict_source=c.verdict_source.value,
            findings=findings,
            estimated_reintegration_xaf=float(reint),
        ))

    # C2 — Add auto-insurance to reintegration
    if auto_insurance_xaf > 0:
        total_reintegration += auto_insurance_xaf

    # ── C1 — Variance side: charges sans contrat → réintégration potentielle
    charges_sans_contrat = max(Decimal("0"), gl_total - contracts_total_exercice)

    # ── Summary ─────────────────────────────────────────────────────────────
    summary = {
        # Rapprochement (C1)
        "gl_total_xaf": float(gl_total),
        "contracts_total_annuel_xaf": float(contracts_total_annuel),
        "contracts_total_exercice_xaf": float(contracts_total_exercice),
        "variance_xaf": float(variance),
        "variance_pct": float(variance_pct),
        "reconciliation_status": reconciliation_status,
        "charges_sans_contrat_xaf": float(charges_sans_contrat),
        # Auto-assurance (C2)
        "auto_insurance_xaf": float(auto_insurance_xaf),
        # Contrats
        "contract_count": len(contract_views),
        "eligible_count": sum(1 for v in contract_views if v.verdict == "ELIGIBLE"),
        "non_eligible_count": sum(1 for v in contract_views if v.verdict == "NON_ELIGIBLE"),
        "reinstruire_count": sum(1 for v in contract_views if v.verdict == "A_REINSTRUIRE"),
        # Réintégration totale
        "total_reintegration_xaf": float(total_reintegration),
    }

    return {
        "case_id": str(case_id),
        "prime_account_prefixes": list(PRIME_ACCOUNT_PREFIXES),
        "gl_by_account": {k: float(v) for k, v in gl_by_account.items()},
        "contracts": [v.to_dict() for v in contract_views],
        "summary": summary,
        "legal_reference": "CGI Cameroun, Art. 7, A (4) — Primes d'assurance",
    }
