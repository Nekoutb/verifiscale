"""Category A — Intégrité comptable SYSCOHADA.

Implements the 8 conditions of régularité (art. 17) plus key derived checks
listed in the controls catalog. Each check is a small, focused function so it
can be tested in isolation and reordered without coupling.
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from datetime import date, timedelta

from app.controls.base import Finding, ControlContext
from app.models.control_run import ControlSeverity


# SYSCOHADA chart of accounts: valid first digit (classes 1-9)
_VALID_CLASSES = set("123456789")


def a1_double_entry(ctx: ControlContext) -> list[Finding]:
    """A1 — Each journal entry must satisfy Σ debits = Σ credits (art. 17.2)."""
    out: list[Finding] = []
    for je in ctx.journal_entries:
        total_d = sum((Decimal(str(l.get("debit", 0))) for l in je["lines"]), start=Decimal("0"))
        total_c = sum((Decimal(str(l.get("credit", 0))) for l in je["lines"]), start=Decimal("0"))
        diff = total_d - total_c
        if abs(diff) >= Decimal("0.01"):
            out.append(Finding(
                control_code="A1",
                title=f"Écriture déséquilibrée — pièce {je['piece']}",
                description=(
                    f"L'écriture comptable {je['piece']} du {je.get('date', '?')} "
                    f"présente un déséquilibre de {diff:+,.0f} FCFA "
                    f"(débits {total_d:,.0f} ≠ crédits {total_c:,.0f}). "
                    f"L'article 17.2 de l'Acte Uniforme OHADA impose la partie double."
                ),
                severity=ControlSeverity.BLOCKING,
                legal_reference="SYSCOHADA art. 17.2",
                evidence={
                    "piece": je["piece"],
                    "date": str(je.get("date", "")),
                    "total_debit": float(total_d),
                    "total_credit": float(total_c),
                    "difference": float(diff),
                    "lines_count": len(je["lines"]),
                },
                estimated_impact_xaf=float(abs(diff)),
            ))
    return out


def a2_pj_present(ctx: ControlContext) -> list[Finding]:
    """A2 — Pièce justificative datée pour chaque ligne (art. 17.3)."""
    out: list[Finding] = []
    missing_pj_count = 0
    missing_date_count = 0
    for je in ctx.journal_entries:
        if not je.get("piece"):
            missing_pj_count += 1
        if not je.get("date"):
            missing_date_count += 1
    if missing_pj_count > 0:
        out.append(Finding(
            control_code="A2",
            title=f"{missing_pj_count} écriture(s) sans numéro de pièce",
            description="L'article 17.3 exige une pièce justificative datée pour chaque écriture.",
            severity=ControlSeverity.HIGH,
            legal_reference="SYSCOHADA art. 17.3",
            evidence={"count": missing_pj_count},
        ))
    if missing_date_count > 0:
        out.append(Finding(
            control_code="A2",
            title=f"{missing_date_count} écriture(s) sans date",
            description="Toute écriture doit être datée (art. 17.3).",
            severity=ControlSeverity.HIGH,
            legal_reference="SYSCOHADA art. 17.3",
            evidence={"count": missing_date_count},
        ))
    return out


def a3_chronology(ctx: ControlContext) -> list[Finding]:
    """A3 — Chronologie: no entry should be older than the previous entry of the
    same journal (art. 16 al. 3-5 + art. 22)."""
    out: list[Finding] = []
    by_journal: dict[str, list[tuple[str, date]]] = defaultdict(list)
    for je in ctx.journal_entries:
        d = je.get("date")
        j = je.get("journal", "")
        if isinstance(d, date):
            by_journal[j].append((je["piece"], d))

    for j, entries in by_journal.items():
        entries.sort(key=lambda x: x[0])  # sort by piece number
        last_date: date | None = None
        breaks: list[dict] = []
        for piece, d in entries:
            if last_date and d < last_date:
                breaks.append({"piece": piece, "date": str(d), "previous_date": str(last_date)})
            last_date = max(last_date, d) if last_date else d
        if breaks:
            out.append(Finding(
                control_code="A3",
                title=f"Ruptures de chronologie dans le journal {j} ({len(breaks)} cas)",
                description=(
                    f"Le journal {j} comporte {len(breaks)} pièce(s) dont la date est antérieure "
                    f"à la dernière pièce numérotée. Indice d'écritures antidatées (art. 16, 22)."
                ),
                severity=ControlSeverity.HIGH,
                legal_reference="SYSCOHADA art. 16 al. 3-5 + art. 22",
                evidence={"journal": j, "breaks_sample": breaks[:10], "total_breaks": len(breaks)},
            ))
    return out


def a5_plan_compte(ctx: ControlContext) -> list[Finding]:
    """A5 — Plan de comptes conforme OHADA (codification décimale, classes 1-9)."""
    out: list[Finding] = []
    invalid: set[str] = set()
    for line in ctx.trial_balance:
        code = str(line["account_code"]).strip()
        if not code or code[0] not in _VALID_CLASSES:
            invalid.add(code)
    if invalid:
        out.append(Finding(
            control_code="A5",
            title=f"{len(invalid)} compte(s) hors plan comptable SYSCOHADA",
            description=(
                "Les comptes utilisés doivent appartenir à la nomenclature normalisée "
                "(classes 1 à 9). Comptes anormaux détectés."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="SYSCOHADA art. 18 + Titre VII",
            evidence={"invalid_accounts": sorted(invalid)[:50], "count": len(invalid)},
        ))
    return out


def a8_opening_eq_prior_closing(ctx: ControlContext) -> list[Finding]:
    """A8 — Bilan ouverture N = Bilan clôture N-1 — art. 34.

    Vérification simplifiée : pour chaque compte de bilan (classes 1-5),
    l'ouverture N doit être présente. Si le contexte fournit `prior_closing`,
    on compare ligne à ligne.
    """
    out: list[Finding] = []
    prior = ctx.extra.get("prior_closing")  # dict {account_code: (debit, credit)}
    if not prior:
        return out
    deviations: list[dict] = []
    by_acct = {l["account_code"]: l for l in ctx.trial_balance}
    for acct, (pd_, pc_) in prior.items():
        line = by_acct.get(acct)
        opening_d = Decimal(str(line["opening_debit"])) if line else Decimal("0")
        opening_c = Decimal(str(line["opening_credit"])) if line else Decimal("0")
        if abs(opening_d - Decimal(str(pd_))) >= Decimal("1") or abs(opening_c - Decimal(str(pc_))) >= Decimal("1"):
            deviations.append({
                "account_code": acct,
                "prior_close_debit": float(pd_),
                "prior_close_credit": float(pc_),
                "opening_debit": float(opening_d),
                "opening_credit": float(opening_c),
            })
    if deviations:
        out.append(Finding(
            control_code="A8",
            title=f"Bilan d'ouverture ≠ clôture N-1 sur {len(deviations)} compte(s)",
            description="Le bilan d'ouverture doit reprendre exactement la clôture précédente (art. 34).",
            severity=ControlSeverity.BLOCKING,
            legal_reference="SYSCOHADA art. 34",
            evidence={"deviations_sample": deviations[:20], "count": len(deviations)},
            estimated_impact_xaf=sum(abs(d["opening_debit"] - d["prior_close_debit"]) for d in deviations),
        ))
    return out


def a13_tb_balance(ctx: ControlContext) -> list[Finding]:
    """A13 — Global TB equilibrium: Σ Débits = Σ Crédits (opening/period/closing)."""
    out: list[Finding] = []
    tb = ctx.trial_balance
    if not tb:
        return out

    sums = {
        "opening": (sum(Decimal(str(l["opening_debit"])) for l in tb),
                    sum(Decimal(str(l["opening_credit"])) for l in tb)),
        "period":  (sum(Decimal(str(l["period_debit"])) for l in tb),
                    sum(Decimal(str(l["period_credit"])) for l in tb)),
        "closing": (sum(Decimal(str(l["closing_debit"])) for l in tb),
                    sum(Decimal(str(l["closing_credit"])) for l in tb)),
    }
    labels = {"opening": "ouverture", "period": "période", "closing": "clôture"}
    for k, (d, c) in sums.items():
        diff = d - c
        if abs(diff) >= Decimal("1"):
            out.append(Finding(
                control_code="A13",
                title=f"Balance non équilibrée — soldes de {labels[k]}",
                description=(
                    f"Σ Débits = {d:,.0f} ≠ Σ Crédits = {c:,.0f} "
                    f"(écart {diff:+,.0f} FCFA)."
                ),
                severity=ControlSeverity.BLOCKING,
                legal_reference="SYSCOHADA art. 17.2 + 34",
                evidence={"phase": k, "total_debit": float(d), "total_credit": float(c), "difference": float(diff)},
                estimated_impact_xaf=float(abs(diff)),
            ))
    return out


def a13b_rollforward(ctx: ControlContext) -> list[Finding]:
    """A13bis — Rollforward: opening + period = closing on every account."""
    out: list[Finding] = []
    deviations: list[dict] = []
    for l in ctx.trial_balance:
        od = Decimal(str(l["opening_debit"])) - Decimal(str(l["opening_credit"]))
        per = Decimal(str(l["period_debit"])) - Decimal(str(l["period_credit"]))
        cd = Decimal(str(l["closing_debit"])) - Decimal(str(l["closing_credit"]))
        expected = od + per
        if abs(expected - cd) >= Decimal("1"):
            deviations.append({
                "account_code": l["account_code"],
                "account_name": l["account_name"],
                "expected_closing_net": float(expected),
                "actual_closing_net": float(cd),
                "difference": float(cd - expected),
            })
    if deviations:
        total_impact = sum(abs(d["difference"]) for d in deviations)
        out.append(Finding(
            control_code="A13b",
            title=f"Anomalie de rollforward sur {len(deviations)} compte(s)",
            description=(
                "Pour ces comptes, solde d'ouverture + mouvements ≠ solde de clôture. "
                "Indique une rupture d'intégrité dans la balance 6 colonnes."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="Bonne pratique + SYSCOHADA art. 19",
            evidence={"deviations_sample": deviations[:50], "count": len(deviations)},
            estimated_impact_xaf=float(total_impact),
        ))
    return out


def a13c_tb_vs_gl(ctx: ControlContext) -> list[Finding]:
    """A13c — Reconciliation: TB period movements ≡ GL aggregated movements per account."""
    if not ctx.general_ledger:
        return []
    out: list[Finding] = []
    # Aggregate GL by account
    gl_agg: dict[str, tuple[Decimal, Decimal]] = defaultdict(lambda: (Decimal("0"), Decimal("0")))
    for l in ctx.general_ledger:
        acct = l["account_code"]
        d, c = gl_agg[acct]
        gl_agg[acct] = (d + Decimal(str(l.get("debit", 0))), c + Decimal(str(l.get("credit", 0))))

    deviations: list[dict] = []
    for tbl in ctx.trial_balance:
        acct = tbl["account_code"]
        tb_d, tb_c = Decimal(str(tbl["period_debit"])), Decimal(str(tbl["period_credit"]))
        gl_d, gl_c = gl_agg.get(acct, (Decimal("0"), Decimal("0")))
        if abs(tb_d - gl_d) >= Decimal("1") or abs(tb_c - gl_c) >= Decimal("1"):
            deviations.append({
                "account_code": acct,
                "account_name": tbl["account_name"],
                "tb_debit": float(tb_d), "tb_credit": float(tb_c),
                "gl_debit": float(gl_d), "gl_credit": float(gl_c),
                "delta_debit": float(tb_d - gl_d), "delta_credit": float(tb_c - gl_c),
            })

    if deviations:
        out.append(Finding(
            control_code="A13c",
            title=f"Balance ≠ grand-livre sur {len(deviations)} compte(s)",
            description=(
                "Les mouvements de la balance ne correspondent pas à l'agrégation du grand-livre. "
                "Indice fort de comptabilité incomplète, écritures hors GL, ou GL non extrait intégralement."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="SYSCOHADA art. 19 + bonne pratique",
            evidence={"deviations_sample": deviations[:50], "count": len(deviations)},
            estimated_impact_xaf=float(sum(abs(d["delta_debit"]) + abs(d["delta_credit"]) for d in deviations)),
        ))
    return out


def a9_no_compensation(ctx: ControlContext) -> list[Finding]:
    """A9 — Non-compensation: aucun compte de tiers ne doit afficher D=0 ET C=0 sur
    le solde de clôture si des mouvements existent (art. 34)."""
    out: list[Finding] = []
    suspect: list[dict] = []
    for l in ctx.trial_balance:
        if not l["account_code"].startswith(("40", "41", "42", "43", "44", "46", "47")):
            continue
        period_total = (Decimal(str(l["period_debit"])) + Decimal(str(l["period_credit"])))
        closing_total = (Decimal(str(l["closing_debit"])) + Decimal(str(l["closing_credit"])))
        if period_total > 0 and closing_total == 0:
            suspect.append({"account_code": l["account_code"], "account_name": l["account_name"]})
    if suspect:
        out.append(Finding(
            control_code="A9",
            title=f"{len(suspect)} compte(s) de tiers à solde nul après mouvements significatifs",
            description=(
                "L'article 34 SYSCOHADA proscrit toute compensation actif/passif non juridiquement "
                "fondée. Comptes de tiers à solde nul après mouvements importants → vérifier l'absence "
                "de compensation cachée."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="SYSCOHADA art. 34",
            evidence={"suspect_accounts": suspect[:50], "count": len(suspect)},
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# A4 — Identification ligne par ligne (origine, imputation, contenu, PJ)
# ─────────────────────────────────────────────────────────────────────────────
def a4_line_identification(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 17.5 — chaque ligne doit comporter : origine (journal),
    imputation (compte), contenu (libellé) et référence pièce justificative."""
    if not ctx.general_ledger:
        return []

    missing_libelle = []
    missing_journal = []
    missing_account = []
    missing_piece = []
    examined = 0

    for line in ctx.general_ledger:
        examined += 1
        if not line.get("libelle") or not str(line.get("libelle", "")).strip():
            missing_libelle.append(line)
        if not line.get("journal"):
            missing_journal.append(line)
        if not line.get("account_code"):
            missing_account.append(line)
        if not line.get("piece"):
            missing_piece.append(line)

    out: list[Finding] = []
    for label, defects, severity in [
        ("libellé",                missing_libelle, ControlSeverity.MEDIUM),
        ("code journal (origine)", missing_journal, ControlSeverity.MEDIUM),
        ("compte d'imputation",    missing_account, ControlSeverity.HIGH),
        ("référence pièce",        missing_piece,   ControlSeverity.HIGH),
    ]:
        if defects:
            sample = [
                {"piece": d.get("piece"), "date": str(d.get("date", "")),
                 "account": d.get("account_code")} for d in defects[:10]
            ]
            pct = (len(defects) / examined) * 100 if examined else 0
            out.append(Finding(
                control_code="A4",
                title=f"{len(defects)} ligne(s) sans {label} ({pct:.1f}% du grand-livre)",
                description=(
                    f"L'article 17.5 SYSCOHADA exige pour chaque ligne d'écriture : "
                    f"origine (journal), imputation (compte), contenu (libellé) et référence pièce. "
                    f"{len(defects)} ligne(s) sur {examined} sont sans {label}."
                ),
                severity=severity,
                legal_reference="SYSCOHADA art. 17.5",
                evidence={"count": len(defects), "examined": examined, "sample": sample},
            ))

    if not out:
        out.append(Finding(
            control_code="A4",
            title=f"Identification des lignes conforme ({examined} lignes vérifiées)",
            description="Toutes les lignes du grand-livre comportent les 4 éléments requis (art. 17.5).",
            severity=ControlSeverity.INFO,
            legal_reference="SYSCOHADA art. 17.5",
            evidence={"examined": examined},
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# A6 — Présence des 4 livres comptables obligatoires
# ─────────────────────────────────────────────────────────────────────────────
def a6_quatre_livres(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 17.8 + 19 — les 4 livres obligatoires :
    1) Livre journal · 2) Grand livre · 3) Balance · 4) Livre d'inventaire."""
    has_journal = bool(ctx.journal_entries)
    has_gl = bool(ctx.general_ledger)
    has_tb = bool(ctx.trial_balance)

    livres = {
        "Livre journal":     has_journal,
        "Grand livre":       has_gl,
        "Balance générale":  has_tb,
        "Livre d'inventaire": None,  # not uploadable currently — manual check
    }

    missing = [name for name, present in livres.items() if present is False]
    manual = [name for name, present in livres.items() if present is None]

    if missing:
        return [Finding(
            control_code="A6",
            title=f"Livre(s) obligatoire(s) manquant(s) : {', '.join(missing)}",
            description=(
                f"L'article 17.8 SYSCOHADA impose la tenue de 4 livres obligatoires. "
                f"Manquant(s) : {', '.join(missing)}. "
                "À demander au contribuable avant de poursuivre la vérification."
            ),
            severity=ControlSeverity.BLOCKING,
            legal_reference="SYSCOHADA art. 17.8 + 19",
            evidence={"missing": missing, "to_verify_manually": manual},
        )]

    return [Finding(
        control_code="A6",
        title=f"Livre journal, grand livre et balance présents — livre d'inventaire à vérifier manuellement",
        description=(
            "Les 3 livres dématérialisables (journal, GL, balance) sont chargés dans la plateforme. "
            "Le livre d'inventaire (recensement physique annuel signé) doit être vérifié manuellement "
            "auprès du contribuable (art. 17.8 + 19)."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA art. 17.8 + 19",
        evidence={"loaded": [n for n, p in livres.items() if p], "to_verify_manually": manual},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# A7 — Livres cotés et paraphés (art. 66)
# ─────────────────────────────────────────────────────────────────────────────
def a7_cotation_paraphage(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 66 — livre journal et livre d'inventaire cotés et paraphés
    par le greffe du tribunal (ou autorité compétente). Manuel pour livres papier ;
    pour livres dématérialisés, signature électronique conforme."""
    return [Finding(
        control_code="A7",
        title="Cotation et paraphage des livres — vérification manuelle requise",
        description=(
            "L'article 66 SYSCOHADA impose que le livre journal et le livre d'inventaire soient "
            "cotés et paraphés par le greffe du tribunal de commerce (ou autorité compétente). "
            "Pour les livres dématérialisés : signature électronique conforme exigée. "
            "Vérifier physiquement les livres et joindre les certificats au dossier."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA art. 66",
    )]


# ─────────────────────────────────────────────────────────────────────────────
# A10 — Délai d'arrêté ≤ 4 mois post-clôture (art. 23)
# ─────────────────────────────────────────────────────────────────────────────
def a10_delai_arrete(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 23 — la comptabilité doit être arrêtée et les états financiers
    établis dans les 4 mois suivant la clôture."""
    d = ctx.extra.get("lpf_dates", {})
    period_end = d.get("period_end")
    today = date.today()

    if not period_end:
        return [Finding(
            control_code="A10",
            title="Date de clôture non renseignée",
            description="Renseigner period_end sur le dossier pour vérifier le délai d'arrêté.",
            severity=ControlSeverity.INFO,
            legal_reference="SYSCOHADA art. 23",
        )]

    # period_end may arrive as date or string
    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)

    # 4 months ≈ 122 days; use proper month arithmetic
    deadline = date(period_end.year + (period_end.month + 4 - 1) // 12,
                    ((period_end.month + 4 - 1) % 12) + 1,
                    min(period_end.day, 28))
    jours_depuis_cloture = (today - period_end).days
    jours_avant_deadline = (deadline - today).days

    if jours_depuis_cloture < 0:
        return [Finding(
            control_code="A10",
            title=f"Période non encore clôturée (clôture prévue le {period_end})",
            description="L'arrêté des comptes n'est pas encore dû.",
            severity=ControlSeverity.INFO,
            legal_reference="SYSCOHADA art. 23",
            evidence={"period_end": str(period_end), "deadline": str(deadline)},
        )]

    if jours_avant_deadline < 0:
        return [Finding(
            control_code="A10",
            title=f"Délai d'arrêté dépassé ({-jours_avant_deadline} jours de retard)",
            description=(
                f"La période est clôturée depuis {jours_depuis_cloture} jours (le {period_end}). "
                f"L'arrêté des comptes devait être effectué avant le {deadline} (art. 23). "
                "Vérifier que les états financiers ont été effectivement établis."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="SYSCOHADA art. 23",
            evidence={"period_end": str(period_end), "deadline": str(deadline),
                      "retard_jours": -jours_avant_deadline},
        )]

    return [Finding(
        control_code="A10",
        title=f"Délai d'arrêté en cours — échéance {deadline} ({jours_avant_deadline} j restants)",
        description=(
            f"Clôture : {period_end}. "
            f"Délai légal d'arrêté des comptes (4 mois) : {deadline}. "
            f"Il reste {jours_avant_deadline} jours."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA art. 23",
        evidence={"period_end": str(period_end), "deadline": str(deadline),
                  "jours_restants": jours_avant_deadline},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# A11 — Permanence des méthodes inter-exercices (art. 40-41)
# ─────────────────────────────────────────────────────────────────────────────
def a11_permanence_methodes(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 40-41 — méthodes d'évaluation et de présentation doivent
    être permanentes d'un exercice à l'autre. Changement = mention en annexe + retraitement."""
    return [Finding(
        control_code="A11",
        title="Permanence des méthodes — vérification manuelle inter-exercices",
        description=(
            "L'article 40-41 SYSCOHADA exige la permanence des méthodes comptables d'un exercice "
            "à l'autre. Tout changement (méthode d'amortissement, valorisation stocks PEPS/CMP, "
            "présentation des charges, etc.) doit être : "
            "(1) justifié et mentionné dans l'état annexé · "
            "(2) appliqué rétroactivement avec retraitement comparatif. "
            "À vérifier en comparant les annexes N et N-1, et en interrogeant le contribuable "
            "sur tout changement de méthode."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA art. 40-41",
    )]


# ─────────────────────────────────────────────────────────────────────────────
# A12 — Corrections d'erreurs significatives → report à nouveau (121/129)
# ─────────────────────────────────────────────────────────────────────────────
_CORRECTION_KEYWORDS = re.compile(
    r"\b(correction|régularisation|regularisation|erreur|redressement|"
    r"rectification|annulation)\b", re.IGNORECASE,
)


def a12_correction_erreurs(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 20 — les corrections d'erreurs significatives portant sur des
    exercices antérieurs doivent transiter par les comptes 121 (report à nouveau
    bénéficiaire) ou 129 (report à nouveau déficitaire), JAMAIS via le résultat N."""
    if not ctx.journal_entries:
        return []

    suspect_corrections = []
    for je in ctx.journal_entries:
        # Look at the entry libellé OR any line libellé
        match = False
        for line in je.get("lines", []):
            if _CORRECTION_KEYWORDS.search(str(line.get("libelle", ""))):
                match = True
                break
        if not match:
            continue

        # Check if this entry touches 121 or 129
        touches_report = any(
            str(l.get("account_code", "")).startswith(("121", "129"))
            for l in je.get("lines", [])
        )
        # Check if it touches a P&L account (classes 6 or 7) — flag if no 121/129 counter-entry
        touches_pl = any(
            str(l.get("account_code", "")).startswith(("6", "7"))
            for l in je.get("lines", [])
        )

        if touches_pl and not touches_report:
            total_d = sum((Decimal(str(l.get("debit", 0))) for l in je["lines"]), Decimal("0"))
            suspect_corrections.append({
                "piece": je.get("piece"),
                "date": str(je.get("date", "")),
                "journal": je.get("journal"),
                "amount": float(total_d),
                "libelle": next(
                    (l.get("libelle", "") for l in je["lines"]
                     if _CORRECTION_KEYWORDS.search(str(l.get("libelle", "")))),
                    "",
                ),
            })

    if not suspect_corrections:
        return [Finding(
            control_code="A12",
            title="Aucune correction d'erreur P&L sans contrepartie report à nouveau détectée",
            description="Les corrections d'erreurs identifiées transitent correctement par les comptes 121/129 (art. 20).",
            severity=ControlSeverity.INFO,
            legal_reference="SYSCOHADA art. 20",
        )]

    return [Finding(
        control_code="A12",
        title=f"{len(suspect_corrections)} correction(s) d'erreur passée(s) en résultat (devraient être en 121/129)",
        description=(
            f"L'article 20 SYSCOHADA impose que les corrections d'erreurs significatives "
            f"portant sur des exercices antérieurs soient enregistrées au crédit du compte 121 "
            f"(report à nouveau bénéficiaire) ou au débit du 129 (report à nouveau déficitaire), "
            f"jamais en résultat de l'exercice. "
            f"{len(suspect_corrections)} écriture(s) qualifiée(s) de correction touchent un compte "
            f"de classe 6 ou 7 sans contrepartie 121/129 — à investiguer."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="SYSCOHADA art. 20",
        evidence={"count": len(suspect_corrections), "sample": suspect_corrections[:20]},
        estimated_impact_xaf=float(sum(c["amount"] for c in suspect_corrections)),
    )]


# ─────────────────────────────────────────────────────────────────────────────
# A14 — Système comptable (Normal vs SMT) cohérent avec CA — art. 13
# ─────────────────────────────────────────────────────────────────────────────
# SYSCOHADA Révisé seuil SMT : CA ≤ 60 MFCFA (zone OHADA — secteur ressources)
SEUIL_SMT_CA = Decimal("60_000_000")


def a14_systeme_comptable(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 13 — système comptable à appliquer selon le CA :
    - Système Minimal de Trésorerie (SMT) : CA ≤ 60 MFCFA
    - Système Normal : CA > 60 MFCFA"""
    aggs = ctx.extra.get("tb_aggregates")
    if not aggs or aggs.chiffre_affaires <= 0:
        return []

    ca = aggs.chiffre_affaires
    expected = "SMT (Système Minimal de Trésorerie)" if ca <= SEUIL_SMT_CA else "Système Normal"
    severity = ControlSeverity.INFO

    return [Finding(
        control_code="A14",
        title=f"Système attendu : {expected} (CA = {ca:,.0f} FCFA)",
        description=(
            f"Chiffre d'affaires : {ca:,.0f} FCFA. "
            f"Seuil SYSCOHADA Révisé : {SEUIL_SMT_CA:,.0f} FCFA. "
            f"Système attendu : {expected}. "
            f"Vérifier que les états financiers présentés sont cohérents avec ce système "
            f"(SMT : comptabilité de trésorerie simplifiée · SN : comptabilité d'engagement complète)."
        ),
        severity=severity,
        legal_reference="SYSCOHADA art. 13",
        evidence={
            "ca": float(ca),
            "seuil_smt": float(SEUIL_SMT_CA),
            "systeme_attendu": "SMT" if ca <= SEUIL_SMT_CA else "SN",
        },
    )]


# Registry — ordered execution
CATEGORY_A_CONTROLS = [
    ("A1",   "Équilibre individuel des écritures",              a1_double_entry),
    ("A2",   "Présence pièce et date",                          a2_pj_present),
    ("A3",   "Chronologie des écritures",                       a3_chronology),
    ("A4",   "Identification ligne par ligne (art. 17.5)",      a4_line_identification),
    ("A5",   "Plan de comptes SYSCOHADA",                       a5_plan_compte),
    ("A6",   "Présence des 4 livres obligatoires",              a6_quatre_livres),
    ("A7",   "Livres cotés et paraphés",                        a7_cotation_paraphage),
    ("A8",   "Bilan ouverture = clôture N-1",                   a8_opening_eq_prior_closing),
    ("A9",   "Non-compensation comptes de tiers",               a9_no_compensation),
    ("A10",  "Délai d'arrêté ≤ 4 mois post-clôture",            a10_delai_arrete),
    ("A11",  "Permanence des méthodes (art. 40-41)",            a11_permanence_methodes),
    ("A12",  "Corrections d'erreurs via 121/129",               a12_correction_erreurs),
    ("A13",  "Équilibre global de la balance",                  a13_tb_balance),
    ("A13b", "Rollforward par compte",                          a13b_rollforward),
    ("A13c", "Balance vs grand-livre",                          a13c_tb_vs_gl),
    ("A14",  "Système comptable (Normal vs SMT)",               a14_systeme_comptable),
]


def run_category_a(ctx: ControlContext) -> list[Finding]:
    """Run every Category A control and concatenate findings."""
    all_findings: list[Finding] = []
    for _, _, fn in CATEGORY_A_CONTROLS:
        try:
            all_findings.extend(fn(ctx))
        except Exception as e:  # noqa: BLE001
            all_findings.append(Finding(
                control_code=fn.__name__.split("_")[0].upper(),
                title=f"Erreur d'exécution du contrôle {fn.__name__}",
                description=str(e),
                severity=ControlSeverity.INFO,
                legal_reference="—",
            ))
    return all_findings
