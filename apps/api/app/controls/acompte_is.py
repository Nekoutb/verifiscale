"""Acompte mensuel IS — CGI Cameroun, Art. 21.

Base légale (DGI, fiche technique IS) :
  « Les acomptes mensuels d'IS sont calculés par application des taux de 2 %,
    et de 5 % respectivement pour les entreprises du régime du réel et les
    entreprises du simplifié sur le chiffre d'affaires mensuel majoré des
    CAC (article 21 du CGI). »
  « Le paiement des acomptes est attendu au plus tard le 15 du mois suivant
    celui de la réalisation des opérations (article 21 du CGI). »

Première itération — contrôles (a) (b) (c) :
  (a) Présence des 12 DMM ACOMPTE_IS de l'exercice
  (b) Pour chaque mois : acompte_DMM ≈ taux × Σ crédits 70XX du mois (±1 %)
  (c) Annuel : Σ crédits 70XX (GL) ≈ Σ CA déclaré (12 DMM)

À venir en partie 2 :
  (d) Pénalités / intérêts de retard (Art. L106 LPF)
  (e) Imputation DAR-IS : Σ acomptes versés = ligne « acomptes versés »
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    Dataset,
    DatasetKind,
    DatasetStatus,
    JournalEntry,
    JournalEntryLine,
    MonthlyReturn,
    TaxType,
)


# ── Paramètres légaux (CGI Cameroun, Art. 21) ────────────────────────────────

#: Taux IS + CAC 10 % par régime fiscal — appliqués au CA HT mensuel
ACOMPTE_RATES_PCT: dict[str, Decimal] = {
    "REEL":      Decimal("2.2"),   # 2 % IS + 10 % CAC
    "SIMPLIFIE": Decimal("5.5"),   # 5 % IS + 10 % CAC
}

#: Préfixe SYSCOHADA des comptes de produits (CA HT)
REVENUE_ACCOUNT_PREFIX = "70"

#: Tolérance d'écart sur le contrôle (b) avant flag
MONTHLY_TOLERANCE_PCT = Decimal("1.0")     # ±1 %
ANNUAL_TOLERANCE_PCT  = Decimal("1.0")     # ±1 %

#: Seuil au-delà duquel l'écart bascule en sévérité majeure
MAJOR_VARIANCE_PCT = Decimal("5.0")

#: Mois (FR) pour étiquetage
_MONTH_LABELS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class MonthLine:
    month: int
    period_label: str
    # Source GL
    ca_gl_xaf: Decimal
    expected_acompte_xaf: Decimal
    # Source DMM
    dmm_present: bool
    dmm_filing_date: date | None
    filing_deadline: date
    declared_acompte_xaf: Decimal
    ca_dmm_xaf: Decimal | None
    # Computed
    variance_xaf: Decimal             # declared - expected
    variance_pct: Decimal | None
    deadline_status: str              # ON_TIME | LATE | MISSING | NO_FILING_DATE
    status: str                       # OK | VARIANCE_MINOR | VARIANCE_MAJOR | MISSING_DMM | NO_CA

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "period_label": self.period_label,
            "ca_gl_xaf": float(self.ca_gl_xaf),
            "expected_acompte_xaf": float(self.expected_acompte_xaf),
            "dmm_present": self.dmm_present,
            "dmm_filing_date": self.dmm_filing_date.isoformat() if self.dmm_filing_date else None,
            "filing_deadline": self.filing_deadline.isoformat(),
            "declared_acompte_xaf": float(self.declared_acompte_xaf),
            "ca_dmm_xaf": float(self.ca_dmm_xaf) if self.ca_dmm_xaf is not None else None,
            "variance_xaf": float(self.variance_xaf),
            "variance_pct": float(self.variance_pct) if self.variance_pct is not None else None,
            "deadline_status": self.deadline_status,
            "status": self.status,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_rate(regime: str | None) -> tuple[str, Decimal]:
    """Returns (normalized regime, rate %). Defaults to REEL."""
    r = (regime or "REEL").upper()
    if r not in ACOMPTE_RATES_PCT:
        r = "REEL"
    return (r, ACOMPTE_RATES_PCT[r])


def _next_month_15(year: int, month: int) -> date:
    """Filing deadline = 15 du mois suivant (CGI Art. 21)."""
    if month == 12:
        return date(year + 1, 1, 15)
    return date(year, month + 1, 15)


def _classify_status(
    dmm_present: bool,
    expected: Decimal,
    variance_abs_pct: Decimal,
) -> str:
    if expected <= 0:
        return "NO_CA"
    if not dmm_present:
        return "MISSING_DMM"
    if variance_abs_pct <= MONTHLY_TOLERANCE_PCT:
        return "OK"
    if variance_abs_pct <= MAJOR_VARIANCE_PCT:
        return "VARIANCE_MINOR"
    return "VARIANCE_MAJOR"


# ── Main entrypoint ──────────────────────────────────────────────────────────


def analyze_acompte_is(db: Session, case_id: UUID, fiscal_year: int) -> dict[str, Any]:
    """Run the acompte-IS analysis for a given fiscal year.

    Returns a dict suitable for direct JSON serialization to the UI.
    """
    # 1) Pull the latest PARSED GL for this case
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

    # 2) Determine regime — fallback to REEL until taxpayer.fiscal_regime is wired
    regime_norm, rate_pct = _resolve_rate("REEL")
    rate = rate_pct / Decimal("100")

    # 3) Compute monthly CA from GL (Σ crédits − débits comptes 70XX, par mois)
    ca_by_month: dict[int, Decimal] = {m: Decimal("0") for m in range(1, 13)}
    if gl_ds is not None:
        rows = (
            db.query(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .filter(JournalEntry.dataset_id == gl_ds.id)
            .all()
        )
        for line, entry in rows:
            if not line.account_code or not line.account_code.startswith(REVENUE_ACCOUNT_PREFIX):
                continue
            if entry.entry_date is None or entry.entry_date.year != fiscal_year:
                continue
            credit = Decimal(str(line.credit or 0))
            debit = Decimal(str(line.debit or 0))
            ca_by_month[entry.entry_date.month] += (credit - debit)

    # 4) Pull DMM ACOMPTE_IS rows for this case + year
    returns = (
        db.query(MonthlyReturn)
        .filter(
            MonthlyReturn.audit_case_id == case_id,
            MonthlyReturn.tax_type == TaxType.ACOMPTE_IS,
            MonthlyReturn.period_year == fiscal_year,
        )
        .all()
    )
    by_month_dmm: dict[int, MonthlyReturn] = {
        r.period_month: r for r in returns if r.period_month is not None
    }

    # 5) Build per-month rows
    months: list[MonthLine] = []
    for m in range(1, 13):
        ca_gl = ca_by_month[m]
        if ca_gl < 0:
            ca_gl = Decimal("0")  # crédits négatifs nets — pas d'acompte attendu
        expected = (ca_gl * rate).quantize(Decimal("1"))
        deadline = _next_month_15(fiscal_year, m)

        r = by_month_dmm.get(m)
        if r is not None:
            declared = Decimal(str(r.declared_amount or 0))
            ca_dmm = Decimal(str(r.base_amount)) if r.base_amount is not None else None
            filing_date = r.filing_date
            dmm_present = True
        else:
            declared = Decimal("0")
            ca_dmm = None
            filing_date = None
            dmm_present = False

        variance = declared - expected
        variance_pct = None
        if expected > 0:
            variance_pct = (variance / expected * Decimal("100")).quantize(Decimal("0.01"))

        if not dmm_present:
            deadline_status = "MISSING"
        elif filing_date is None:
            deadline_status = "NO_FILING_DATE"
        elif filing_date <= deadline:
            deadline_status = "ON_TIME"
        else:
            deadline_status = "LATE"

        variance_abs_pct = abs(variance_pct) if variance_pct is not None else Decimal("0")
        status = _classify_status(dmm_present, expected, variance_abs_pct)

        months.append(MonthLine(
            month=m,
            period_label=f"{_MONTH_LABELS_FR[m - 1]} {fiscal_year}",
            ca_gl_xaf=ca_gl,
            expected_acompte_xaf=expected,
            dmm_present=dmm_present,
            dmm_filing_date=filing_date,
            filing_deadline=deadline,
            declared_acompte_xaf=declared,
            ca_dmm_xaf=ca_dmm,
            variance_xaf=variance,
            variance_pct=variance_pct,
            deadline_status=deadline_status,
            status=status,
        ))

    # 6) Annual aggregates (controls (a) and (c))
    ca_gl_annual = sum((m.ca_gl_xaf for m in months), Decimal("0"))
    ca_dmm_annual = sum(
        (m.ca_dmm_xaf for m in months if m.ca_dmm_xaf is not None),
        Decimal("0"),
    )
    expected_total = (ca_gl_annual * rate).quantize(Decimal("1"))
    declared_total = sum((m.declared_acompte_xaf for m in months), Decimal("0"))

    ca_variance = ca_gl_annual - ca_dmm_annual
    ca_variance_pct = None
    if ca_gl_annual > 0:
        ca_variance_pct = (ca_variance / ca_gl_annual * Decimal("100")).quantize(Decimal("0.01"))

    acompte_variance = declared_total - expected_total
    acompte_variance_pct = None
    if expected_total > 0:
        acompte_variance_pct = (acompte_variance / expected_total * Decimal("100")).quantize(Decimal("0.01"))

    dmm_present_months = [m.month for m in months if m.dmm_present]
    dmm_missing_months = [m.month for m in months if not m.dmm_present]

    # Overall traffic-light status
    if not dmm_present_months and ca_gl_annual == 0:
        summary_status = "GREY"      # rien à analyser
    elif dmm_missing_months or any(m.status == "VARIANCE_MAJOR" for m in months):
        summary_status = "RED"
    elif any(m.status == "VARIANCE_MINOR" for m in months) or (
        ca_variance_pct is not None and abs(ca_variance_pct) > ANNUAL_TOLERANCE_PCT
    ):
        summary_status = "AMBER"
    else:
        summary_status = "GREEN"

    note: str | None = None
    if gl_ds is None:
        note = (
            "Aucun grand-livre chargé pour ce dossier. Importez-le dans "
            "Données › Grand-livre pour activer le contrôle des acomptes IS."
        )

    return {
        "fiscal_year": fiscal_year,
        "regime": regime_norm,
        "rate_pct": float(rate_pct),
        "revenue_account_prefix": REVENUE_ACCOUNT_PREFIX,
        "source_dataset_id": str(gl_ds.id) if gl_ds else None,
        "source_filename": gl_ds.original_filename if gl_ds else None,
        "months": [m.to_dict() for m in months],
        "annual": {
            "ca_gl_xaf": float(ca_gl_annual),
            "ca_dmm_xaf": float(ca_dmm_annual),
            "ca_variance_xaf": float(ca_variance),
            "ca_variance_pct": float(ca_variance_pct) if ca_variance_pct is not None else None,
            "expected_total_acompte_xaf": float(expected_total),
            "declared_total_acompte_xaf": float(declared_total),
            "acompte_variance_xaf": float(acompte_variance),
            "acompte_variance_pct": float(acompte_variance_pct) if acompte_variance_pct is not None else None,
            "dmm_present_months": dmm_present_months,
            "dmm_missing_months": dmm_missing_months,
            "dmm_count": len(dmm_present_months),
            "tolerance_pct": float(ANNUAL_TOLERANCE_PCT),
        },
        "summary_status": summary_status,
        "note": note,
        "legal_reference": "CGI Cameroun, Art. 21 — acomptes mensuels IS",
    }
