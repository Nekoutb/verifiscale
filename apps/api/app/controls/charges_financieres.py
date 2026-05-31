"""Charges financières — CGI Cameroun, Art. 7 B.

Intérêts servis aux associés — 4 tests cumulatifs (le plus restrictif s'applique) :

  T1  Taux ≤ taux des avances BEAC + 2 points (tous associés)
  T2  Convention de prêt écrite + enregistrée ET capital entièrement libéré
      (tous associés) — sinon 100 % des intérêts réintégrés
  T3  Sous-capitalisation : avances ≤ 1,5 × capitaux propres
      (associés détenant ≥ 25 %)
  T4  Earnings-stripping : intérêts ≤ 25 % de l'EBITDA fiscal
      (résultat avant IS + intérêts associés + amortissements) (associés ≥ 25 %)

Contrôles complémentaires :
  - IRCM 16,5 % sur intérêts servis aux associés (croisé DMM L62)
  - TSR 15 % si prêteur non-résident (croisé DMM L1)
  - Comptes courants d'associés DÉBITEURS (acte anormal de gestion)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    ChargesFinAssocie,
    ChargesFinCaseParams,
    ChgFinVerdict,
    Dataset,
    DatasetKind,
    DatasetStatus,
    JournalEntry,
    JournalEntryLine,
    TrialBalanceLine,
)


# Seuils Art. 7 B
THIN_CAP_MULTIPLE = Decimal("1.5")        # avances ≤ 1,5 × capitaux propres
EARNINGS_STRIP_PCT = Decimal("25")        # intérêts ≤ 25 % EBITDA fiscal
SIGNIFICANT_HOLDING_PCT = Decimal("25")   # seuil associé "significatif"
ART7B_UPLIFT = Decimal("2.0")             # + 2 points sur le taux BEAC
IRCM_RATE = Decimal("16.5")               # retenue IRCM sur intérêts associés

# Comptes SYSCOHADA Révisé — intérêts (classe 67) et comptes courants associés
INTEREST_ACCOUNTS = ("6713", "6741", "6742")   # dettes liées participations + avances/CC bloqués
ALL_INTEREST_PREFIX = "67"
SHAREHOLDER_CURRENT_ACCOUNT = "462"            # Associés, comptes courants
# Capitaux propres SYSCOHADA = comptes 10 à 15 (capital, primes, écarts, réserves,
# report à nouveau, résultat, subventions d'investissement, provisions réglementées)
EQUITY_PREFIXES = ("10", "11", "12", "13", "14", "15")


@dataclass
class AssocieView:
    id: str
    nom: str
    niu: str | None
    pct_detention: float | None
    is_resident: bool
    is_significant: bool
    avance_moyenne_xaf: float
    interet_servi_xaf: float
    compte_gl: str | None
    convention_enregistree: bool
    has_convention_file: bool
    # Tests
    taux_implicite_pct: float | None
    t1_excess_xaf: float
    t2_failed: bool
    t3_excess_xaf: float
    t4_excess_xaf: float
    reintegration_xaf: float
    verdict: str
    verdict_reason: str
    verdict_source: str
    findings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _gl_dataset(db: Session, case_id: UUID) -> Dataset | None:
    return (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id,
                Dataset.kind == DatasetKind.GENERAL_LEDGER,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )


def _gl_lines(db: Session, gl_ds: Dataset):
    return (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .all()
    )


_MONTH_LABELS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                 "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]


def _latest_tb(db: Session, case_id: UUID) -> Dataset | None:
    return (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id,
                Dataset.kind == DatasetKind.TRIAL_BALANCE,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )


def _derive_equity_and_ebitda(db: Session, case_id: UUID) -> dict[str, Any]:
    """Auto-compute, from the latest parsed trial balance:

      - capitaux_propres = Σ soldes de clôture des comptes 10–15 (créditeur +)
      - résultat_avant_IS = Σ (crédit − débit) des classes 6, 7 et 8 (sauf 89)
      - intérêts = solde des comptes 67X (charge, débiteur +)
      - amortissements = solde des comptes 68X (charge, débiteur +)
      - EBITDA fiscal = résultat_avant_IS + intérêts + amortissements
    """
    tb = _latest_tb(db, case_id)
    if tb is None:
        return {"available": False}

    rows = db.query(TrialBalanceLine).filter(TrialBalanceLine.dataset_id == tb.id).all()
    equity = Decimal("0")
    resultat = Decimal("0")
    interets = Decimal("0")
    amort = Decimal("0")
    for r in rows:
        acc = (r.account_code or "").strip()
        if not acc:
            continue
        close_credit = Decimal(str(r.closing_credit or 0))
        close_debit = Decimal(str(r.closing_debit or 0))
        net_cr = close_credit - close_debit       # créditeur positif
        net_db = close_debit - close_credit        # débiteur positif (charges)

        # Capitaux propres (classes 10–15)
        if acc[:2] in EQUITY_PREFIXES:
            equity += net_cr

        # Résultat avant IS : classes 6, 7 et 8 sauf 89
        if acc.startswith(("6", "7")) or (acc.startswith("8") and not acc.startswith("89")):
            resultat += net_cr   # produits (crédit) − charges (débit) = résultat

        # Intérêts (67X) et amortissements (68X) — charges, débiteur positif
        if acc.startswith("67"):
            interets += net_db
        if acc.startswith("68"):
            amort += net_db

    ebitda = resultat + interets + amort
    return {
        "available": True,
        "source_filename": tb.original_filename,
        "capitaux_propres_xaf": float(equity),
        "resultat_avant_is_xaf": float(resultat),
        "interets_67_xaf": float(interets),
        "amortissements_68_xaf": float(amort),
        "ebitda_fiscal_xaf": float(ebitda),
    }


def _cc_monthly_rollforward(
    db: Session, case_id: UUID, gl_ds: Dataset | None, cap_pct: Decimal,
) -> dict[str, Any]:
    """Month-by-month rollforward of associate current accounts (462X).

    For each 462 sub-account (one associate), reconstruct:
        closing[m] = closing[m-1] + (Σ credits_m − Σ debits_m)
    in a creditor-positive convention. A month is DEBTOR when closing < 0,
    i.e. the company has advanced funds to the associate (acte anormal de
    gestion). Imputed interest income = Σ over debtor months of
    |closing| × (BEAC+2)% / 12.

    Never nets across different associate sub-accounts.
    """
    empty = {"accounts": [], "total_imputed_interest_xaf": 0.0,
             "any_debtor": False, "opening_source": "none"}
    if gl_ds is None:
        return empty

    # Opening balances from the latest PARSED trial balance
    tb_ds = (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id,
                Dataset.kind == DatasetKind.TRIAL_BALANCE,
                Dataset.status == DatasetStatus.PARSED)
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    opening: dict[str, Decimal] = {}
    if tb_ds is not None:
        for r in db.query(TrialBalanceLine).filter(TrialBalanceLine.dataset_id == tb_ds.id).all():
            acc = r.account_code or ""
            if acc.startswith(SHAREHOLDER_CURRENT_ACCOUNT):
                opening[acc] = opening.get(acc, Decimal("0")) + (
                    Decimal(str(r.opening_credit or 0)) - Decimal(str(r.opening_debit or 0))
                )

    # Monthly movements from the GL (creditor-positive = credit − debit)
    rows = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .all()
    )
    accounts: dict[str, dict[str, Any]] = {}
    for line, entry in rows:
        acc = line.account_code or ""
        if not acc.startswith(SHAREHOLDER_CURRENT_ACCOUNT):
            continue
        m = entry.entry_date.month if entry.entry_date else None
        if not m or m < 1 or m > 12:
            continue
        d = accounts.setdefault(acc, {"name": line.account_name, "mov": [Decimal("0")] * 12})
        d["mov"][m - 1] += Decimal(str(line.credit or 0)) - Decimal(str(line.debit or 0))

    monthly_rate = cap_pct / Decimal("100") / Decimal("12")
    out_accounts: list[dict[str, Any]] = []
    total_imputed = Decimal("0")

    for acc in sorted(accounts.keys()):
        d = accounts[acc]
        bal = opening.get(acc, Decimal("0"))
        months = []
        debtor_months = 0
        max_debtor = Decimal("0")
        acc_imputed = Decimal("0")
        for i in range(12):
            bal = bal + d["mov"][i]
            is_debtor = bal < 0
            if is_debtor:
                debtor_months += 1
                debit_amt = -bal
                if debit_amt > max_debtor:
                    max_debtor = debit_amt
                acc_imputed += debit_amt * monthly_rate
            months.append({
                "month": i + 1,
                "label": _MONTH_LABELS[i],
                "closing_xaf": float(bal),
                "debtor": is_debtor,
            })
        total_imputed += acc_imputed
        out_accounts.append({
            "account_code": acc,
            "account_name": d["name"],
            "opening_xaf": float(opening.get(acc, Decimal("0"))),
            "months": months,
            "debtor_months": debtor_months,
            "max_debtor_xaf": float(max_debtor),
            "imputed_interest_xaf": float(acc_imputed),
        })

    return {
        "accounts": out_accounts,
        "total_imputed_interest_xaf": float(total_imputed),
        "any_debtor": any(a["debtor_months"] > 0 for a in out_accounts),
        "opening_source": "trial_balance" if tb_ds is not None else "none",
    }


def analyze_charges_financieres(
    db: Session, case_id: UUID, beac_cap_pct: Decimal,
) -> dict[str, Any]:
    """Run the full Art. 7 B analysis.

    `beac_cap_pct` = taux des avances BEAC + 2 points (déjà calculé par l'appelant
    depuis le service BEAC ou le paramètre du dossier).
    """
    params = db.get(ChargesFinCaseParams, case_id)
    # Auto-derive from the trial balance; a manual param value (if set) overrides.
    derivation = _derive_equity_and_ebitda(db, case_id)
    auto_equity = Decimal(str(derivation["capitaux_propres_xaf"])) if derivation.get("available") else None
    auto_ebitda = Decimal(str(derivation["ebitda_fiscal_xaf"])) if derivation.get("available") else None

    manual_equity = Decimal(str(params.capitaux_propres_xaf)) if params and params.capitaux_propres_xaf else None
    manual_ebitda = Decimal(str(params.ebitda_fiscal_xaf)) if params and params.ebitda_fiscal_xaf else None

    capitaux_propres = manual_equity if manual_equity is not None else auto_equity
    ebitda = manual_ebitda if manual_ebitda is not None else auto_ebitda

    # ── GL roll-up of class 67 + shareholder current accounts ──────────────
    gl_ds = _gl_dataset(db, case_id)
    gl_interest_67 = Decimal("0")
    gl_interest_assoc = Decimal("0")           # 6713/6741/6742
    cc_associe_balance = Decimal("0")          # net of 462 (>0 = créditeur = société doit; <0 = débiteur)
    by_account: dict[str, Decimal] = {}
    if gl_ds is not None:
        for l in _gl_lines(db, gl_ds):
            acc = l.account_code or ""
            debit = Decimal(str(l.debit or 0))
            credit = Decimal(str(l.credit or 0))
            if acc.startswith(ALL_INTEREST_PREFIX):
                net = debit - credit
                gl_interest_67 += net
                by_account[acc[:4]] = by_account.get(acc[:4], Decimal("0")) + net
                if any(acc.startswith(p) for p in INTEREST_ACCOUNTS):
                    gl_interest_assoc += net
            if acc.startswith(SHAREHOLDER_CURRENT_ACCOUNT):
                # crédit = la société doit à l'associé ; débit = l'associé doit à la société
                cc_associe_balance += credit - debit

    # Compte courant DÉBITEUR — rollforward MENSUEL par sous-compte 462X
    # (remplace le net annuel, qui masquait les positions débitrices intra-année)
    cc_rollforward = _cc_monthly_rollforward(db, case_id, gl_ds, beac_cap_pct)
    cc_imputed_interest = Decimal(str(cc_rollforward["total_imputed_interest_xaf"]))
    # Exposition débitrice maximale tous comptes confondus (info)
    cc_debiteur_xaf = max(
        (Decimal(str(a["max_debtor_xaf"])) for a in cc_rollforward["accounts"]),
        default=Decimal("0"),
    )

    # ── Per-associé tests ──────────────────────────────────────────────────
    associes = (
        db.query(ChargesFinAssocie)
        .filter(ChargesFinAssocie.audit_case_id == case_id)
        .order_by(ChargesFinAssocie.created_at.asc())
        .all()
    )

    # Total advances by significant (>=25%) shareholders — for T3 ratio (collective)
    avances_sig_total = sum(
        (Decimal(str(a.avance_moyenne_xaf or 0)) for a in associes
         if a.pct_detention is not None and Decimal(str(a.pct_detention)) >= SIGNIFICANT_HOLDING_PCT),
        Decimal("0"),
    )
    interets_sig_total = sum(
        (Decimal(str(a.interet_servi_xaf or 0)) for a in associes
         if a.pct_detention is not None and Decimal(str(a.pct_detention)) >= SIGNIFICANT_HOLDING_PCT),
        Decimal("0"),
    )

    avance_max_t3 = (THIN_CAP_MULTIPLE * capitaux_propres) if capitaux_propres else None
    interet_max_t4 = (EARNINGS_STRIP_PCT / 100 * ebitda) if ebitda else None
    # T4 collective excess, prorated per associé below
    t4_collective_excess = (
        max(Decimal("0"), interets_sig_total - interet_max_t4) if interet_max_t4 is not None else Decimal("0")
    )
    # T3 collective excess fraction (share of advances above the ceiling)
    t3_collective_ratio = (
        max(Decimal("0"), Decimal("1") - (avance_max_t3 / avances_sig_total))
        if (avance_max_t3 is not None and avances_sig_total > 0) else Decimal("0")
    )

    views: list[AssocieView] = []
    total_reintegration = Decimal("0")

    for a in associes:
        avance = Decimal(str(a.avance_moyenne_xaf or 0))
        interet = Decimal(str(a.interet_servi_xaf or 0))
        pct = Decimal(str(a.pct_detention)) if a.pct_detention is not None else None
        significant = pct is not None and pct >= SIGNIFICANT_HOLDING_PCT

        findings: list[str] = []
        reasons: list[str] = []

        # Manual override?
        if a.verdict_source and a.verdict_source.value == "MANUAL_OVERRIDE":
            reint = interet if a.verdict.value == "NON_ELIGIBLE" else Decimal("0")
            total_reintegration += reint
            views.append(AssocieView(
                id=str(a.id), nom=a.nom, niu=a.niu,
                pct_detention=float(pct) if pct is not None else None,
                is_resident=a.is_resident, is_significant=significant,
                avance_moyenne_xaf=float(avance), interet_servi_xaf=float(interet),
                compte_gl=a.compte_gl, convention_enregistree=a.convention_enregistree,
                has_convention_file=bool(a.convention_storage_path),
                taux_implicite_pct=float((interet / avance * 100)) if avance > 0 else None,
                t1_excess_xaf=0, t2_failed=False, t3_excess_xaf=0, t4_excess_xaf=0,
                reintegration_xaf=float(reint),
                verdict=a.verdict.value,
                verdict_reason=a.verdict_reason or "Décision motivée du vérificateur",
                verdict_source="MANUAL_OVERRIDE", findings=["MANUAL_OVERRIDE"],
            ))
            continue

        # T1 — taux plafond
        taux_implicite = (interet / avance * 100) if avance > 0 else None
        interet_max_t1 = (avance * beac_cap_pct / 100)
        t1_excess = max(Decimal("0"), interet - interet_max_t1) if avance > 0 else Decimal("0")
        if t1_excess > 0:
            findings.append("T1-RATE-CAP")
            reasons.append(
                f"Taux implicite {float(taux_implicite):.2f}% > plafond {float(beac_cap_pct):.2f}% "
                f"(BEAC+2) → excédent {float(t1_excess):,.0f} FCFA.".replace(",", " ")
            )

        # T2 — forme
        t2_failed = not a.convention_enregistree
        if t2_failed:
            findings.append("T2-NO-REGISTERED-AGREEMENT")
            reasons.append(
                "Absence de convention de prêt enregistrée → 100 % des intérêts non déductibles."
            )

        # T3 — sous-capitalisation (collectif, prorata)
        t3_excess = Decimal("0")
        if significant and t3_collective_ratio > 0:
            t3_excess = (interet * t3_collective_ratio)
            findings.append("T3-THIN-CAP")
            reasons.append(
                f"Sous-capitalisation : avances associés ≥25% > 1,5× capitaux propres "
                f"→ {float(t3_collective_ratio*100):.1f}% des intérêts réintégrés."
            )

        # T4 — earnings-stripping (collectif, prorata par part d'intérêt)
        t4_excess = Decimal("0")
        if significant and t4_collective_excess > 0 and interets_sig_total > 0:
            share = interet / interets_sig_total
            t4_excess = (t4_collective_excess * share)
            findings.append("T4-EARNINGS-STRIP")
            reasons.append(
                f"Intérêts associés ≥25% > 25% EBITDA fiscal → quote-part réintégrée "
                f"{float(t4_excess):,.0f} FCFA.".replace(",", " ")
            )

        # IRCM / TSR signals
        if interet > 0:
            findings.append("IRCM-CHECK")
            if not a.is_resident:
                findings.append("TSR-CHECK-FOREIGN")

        # Réintégration pour cet associé = max des plafonds T1/T3/T4, OU 100% si T2 échoue
        if t2_failed:
            reint = interet
        else:
            reint = max(t1_excess, t3_excess, t4_excess)
        total_reintegration += reint

        if reint <= 0 and not findings:
            verdict = ChgFinVerdict.ELIGIBLE.value
            reason = "Intérêts conformes Art. 7 B (taux, forme, ratios respectés)."
        elif reint > 0:
            verdict = ChgFinVerdict.NON_ELIGIBLE.value
            reason = " ".join(reasons) or "Excédent réintégré."
        else:
            verdict = ChgFinVerdict.A_REINSTRUIRE.value
            reason = " ".join(reasons) or "À réinstruire."

        views.append(AssocieView(
            id=str(a.id), nom=a.nom, niu=a.niu,
            pct_detention=float(pct) if pct is not None else None,
            is_resident=a.is_resident, is_significant=significant,
            avance_moyenne_xaf=float(avance), interet_servi_xaf=float(interet),
            compte_gl=a.compte_gl, convention_enregistree=a.convention_enregistree,
            has_convention_file=bool(a.convention_storage_path),
            taux_implicite_pct=float(taux_implicite) if taux_implicite is not None else None,
            t1_excess_xaf=float(t1_excess), t2_failed=t2_failed,
            t3_excess_xaf=float(t3_excess), t4_excess_xaf=float(t4_excess),
            reintegration_xaf=float(reint),
            verdict=verdict, verdict_reason=reason,
            verdict_source="AUTO", findings=findings,
        ))

    # Intérêt théorique sur comptes courants débiteurs = réintégration additionnelle
    total_reintegration += cc_imputed_interest

    summary = {
        "beac_cap_pct": float(beac_cap_pct),
        "capitaux_propres_xaf": float(capitaux_propres) if capitaux_propres else None,
        "ebitda_fiscal_xaf": float(ebitda) if ebitda else None,
        "avance_max_t3_xaf": float(avance_max_t3) if avance_max_t3 else None,
        "interet_max_t4_xaf": float(interet_max_t4) if interet_max_t4 else None,
        "gl_interest_67_xaf": float(gl_interest_67),
        "gl_interest_assoc_xaf": float(gl_interest_assoc),
        "avances_sig_total_xaf": float(avances_sig_total),
        "interets_sig_total_xaf": float(interets_sig_total),
        "cc_associe_debiteur_xaf": float(cc_debiteur_xaf),
        "cc_imputed_interest_xaf": float(cc_imputed_interest),
        "cc_any_debtor": cc_rollforward["any_debtor"],
        "associe_count": len(views),
        "non_eligible_count": sum(1 for v in views if v.verdict == "NON_ELIGIBLE"),
        "total_reintegration_xaf": float(total_reintegration),
        "ircm_base_xaf": float(interets_sig_total + sum(
            (Decimal(str(a.interet_servi_xaf or 0)) for a in associes
             if a.pct_detention is None or Decimal(str(a.pct_detention)) < SIGNIFICANT_HOLDING_PCT),
            Decimal("0"),
        )),
        "ircm_rate_pct": float(IRCM_RATE),
    }

    return {
        "case_id": str(case_id),
        "interest_accounts": list(INTEREST_ACCOUNTS),
        "gl_by_account": {k: float(v) for k, v in by_account.items()},
        "associes": [v.to_dict() for v in views],
        "cc_rollforward": cc_rollforward,
        "derivation": derivation,
        "equity_source": "manual" if manual_equity is not None else ("trial_balance" if auto_equity is not None else "none"),
        "ebitda_source": "manual" if manual_ebitda is not None else ("trial_balance" if auto_ebitda is not None else "none"),
        "summary": summary,
        "legal_reference": "CGI Cameroun, Art. 7 B — charges financières",
    }
