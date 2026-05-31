"""Category C — Impôt sur les Sociétés (CGI Titre I, Chapitre I).

Each control derives its findings from the trial balance aggregates produced
by `aggregates.compute_tb_aggregates`. Controls that need external data
(monthly returns, prior-year DSF, FCA status) are stubbed until those sources
are wired in subsequent sprints.
"""
from __future__ import annotations

from decimal import Decimal

from app.controls import tax_params as T
from app.controls.aggregates import TBAggregates
from app.controls.base import ControlContext, Finding
from app.models.control_run import ControlSeverity


def _aggs(ctx: ControlContext) -> TBAggregates:
    """Reuse aggregates pre-computed and stashed in ctx.extra by the orchestrator."""
    return ctx.extra["tb_aggregates"]


# ----------------------------------------------------------------------------
# C1 — Taux IS
# ----------------------------------------------------------------------------
def c1_taux_is(ctx: ControlContext) -> list[Finding]:
    """Vérifie que le taux IS appliqué correspond au CA (CGI art. 17 + 17 bis)."""
    a = _aggs(ctx)
    if a.chiffre_affaires <= 0 or a.benefice_imposable_approx <= 0:
        return []

    expected_rate = T.IS_RATE_REDUCED if a.chiffre_affaires <= T.IS_REDUCED_CA_THRESHOLD else T.IS_RATE_STANDARD
    is_expected = (a.benefice_imposable_approx * expected_rate).quantize(Decimal("1"))

    # Crude detection: closing balance of 4441 (IS à payer) should be in the ballpark
    is_declared = ctx.extra.get("is_declared")  # optional, from DSF if available

    findings = [Finding(
        control_code="C1",
        title=f"Recalcul IS : {is_expected:,.0f} FCFA "
              f"({'25 %' if expected_rate == T.IS_RATE_REDUCED else '30 %'} appliqué)",
        description=(
            f"Chiffre d'affaires : {a.chiffre_affaires:,.0f} FCFA "
            f"→ taux IS applicable {'25 %' if expected_rate == T.IS_RATE_REDUCED else '30 %'}. "
            f"Bénéfice imposable approché : {a.benefice_imposable_approx:,.0f} FCFA. "
            f"IS recalculé : {is_expected:,.0f} FCFA "
            f"(hors CAC additionnels 10 %)."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="CGI art. 17 + 17 bis",
        evidence={
            "ca": float(a.chiffre_affaires),
            "rate_applied": float(expected_rate),
            "is_recalculated": float(is_expected),
            "benefice_imposable_approx": float(a.benefice_imposable_approx),
        },
    )]

    if is_declared is not None:
        is_declared = Decimal(str(is_declared))
        diff = is_expected - is_declared
        if abs(diff) >= Decimal("10000"):
            findings.append(Finding(
                control_code="C1b",
                title=f"Écart IS calculé vs déclaré : {diff:+,.0f} FCFA",
                description="L'IS recalculé sur la base de l'agrégation comptable diverge significativement de l'IS déclaré.",
                severity=ControlSeverity.HIGH,
                legal_reference="CGI art. 17",
                evidence={"is_declared": float(is_declared), "is_recalculated": float(is_expected), "diff": float(diff)},
                estimated_impact_xaf=float(abs(diff)),
            ))
    return findings


# ----------------------------------------------------------------------------
# C3 — Minimum de perception
# ----------------------------------------------------------------------------
def c3_minimum_perception(ctx: ControlContext) -> list[Finding]:
    """IS doit être au moins 2 % du CA (5 % simplifié) — CGI art. 22-23."""
    a = _aggs(ctx)
    if a.chiffre_affaires <= 0:
        return []

    # Default to régime réel for the prototype
    min_rate = T.IS_MIN_PERCEPTION_RATE_REEL
    min_is = (a.chiffre_affaires * min_rate).quantize(Decimal("1"))

    expected_rate = T.IS_RATE_REDUCED if a.chiffre_affaires <= T.IS_REDUCED_CA_THRESHOLD else T.IS_RATE_STANDARD
    is_calc = (a.benefice_imposable_approx * expected_rate).quantize(Decimal("1")) if a.benefice_imposable_approx > 0 else Decimal("0")

    if is_calc >= min_is:
        return []

    shortfall = min_is - is_calc
    return [Finding(
        control_code="C3",
        title=f"Minimum de perception applicable : {min_is:,.0f} FCFA",
        description=(
            f"IS calculé sur le bénéfice : {is_calc:,.0f} FCFA. "
            f"Minimum de perception (2 % CA) : {min_is:,.0f} FCFA. "
            f"Le contribuable doit s'acquitter du minimum, soit un complément de {shortfall:,.0f} FCFA."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="CGI art. 22-23",
        evidence={
            "ca": float(a.chiffre_affaires),
            "min_perception_rate": float(min_rate),
            "min_perception_due": float(min_is),
            "is_calcule_sur_benefice": float(is_calc),
            "shortfall": float(shortfall),
        },
        estimated_impact_xaf=float(shortfall),
    )]


# ----------------------------------------------------------------------------
# C9 — Plafond dons et subventions
# ----------------------------------------------------------------------------
def c9_plafond_dons(ctx: ControlContext) -> list[Finding]:
    """Dons d'intérêt général ≤ 0,5 % CA (5 % clubs sportifs) — CGI art. 7-A-5."""
    a = _aggs(ctx)
    if a.chiffre_affaires <= 0 or a.dons_subventions <= 0:
        return []

    plafond = (a.chiffre_affaires * T.PLAFOND_DONS_INTERET_GENERAL).quantize(Decimal("1"))
    if a.dons_subventions <= plafond:
        return []

    depassement = a.dons_subventions - plafond
    return [Finding(
        control_code="C9",
        title=f"Dépassement plafond dons : +{depassement:,.0f} FCFA à réintégrer",
        description=(
            f"Dons comptabilisés (cl. 658) : {a.dons_subventions:,.0f} FCFA. "
            f"Plafond légal (0,5 % CA) : {plafond:,.0f} FCFA. "
            f"L'excédent de {depassement:,.0f} FCFA est non déductible et doit être réintégré au résultat fiscal."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="CGI art. 7-A-5",
        evidence={
            "dons_comptabilises": float(a.dons_subventions),
            "plafond": float(plafond),
            "depassement": float(depassement),
            "ca": float(a.chiffre_affaires),
        },
        estimated_impact_xaf=float(depassement),
    )]


# ----------------------------------------------------------------------------
# C11 — Frais de siège & assistance technique étrangers
# ----------------------------------------------------------------------------
def c11_assistance_technique(ctx: ControlContext) -> list[Finding]:
    """≤ 2,5 % du bénéfice imposable — CGI art. 7-A-1-d."""
    a = _aggs(ctx)
    # Approximation : on regarde la classe 622 (locations + services extérieurs)
    # En production, il faudrait identifier explicitement les sous-comptes 6228
    # (assistance technique) et 6231 (redevances brevets).
    services_ext = a.services_exterieurs
    if a.benefice_imposable_approx <= 0 or services_ext <= 0:
        return []

    plafond = (a.benefice_imposable_approx * T.PLAFOND_FRAIS_SIEGE_ASSIST_TECH).quantize(Decimal("1"))

    # Seuil de tolérance : flag uniquement si services > 20 % du BI
    if services_ext < a.benefice_imposable_approx * Decimal("0.20"):
        return []

    if services_ext <= plafond:
        return []

    return [Finding(
        control_code="C11",
        title="Services extérieurs (cl. 62) à vérifier vs plafond assistance technique",
        description=(
            f"Charges de services extérieurs : {services_ext:,.0f} FCFA. "
            f"Plafond indicatif (2,5 % du BI) : {plafond:,.0f} FCFA. "
            "Si une partie correspond à de l'assistance technique étrangère, le dépassement doit être réintégré (art. 7-A-1-d)."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="CGI art. 7-A-1-d",
        evidence={
            "services_exterieurs": float(services_ext),
            "plafond_indicatif": float(plafond),
            "benefice_imposable_approx": float(a.benefice_imposable_approx),
        },
    )]


# ----------------------------------------------------------------------------
# C14 — Intérêts comptes courants associés
# ----------------------------------------------------------------------------
def c14_interets_cc_associes(ctx: ControlContext) -> list[Finding]:
    """Plafonds : sommes ≤ 1,5 × capitaux propres ET intérêts ≤ 25 % résultat avant IS/amort. — CGI art. 7-B."""
    a = _aggs(ctx)
    interets = a.interets_emprunts
    if interets <= 0 or a.capitaux_propres <= 0:
        return []

    resultat_avant = a.resultat_exploitation + a.amortissements + a.frais_financiers
    plafond_interets = (resultat_avant * T.PLAFOND_INTERETS_CC_RATIO_RESULTAT).quantize(Decimal("1"))

    if interets <= plafond_interets:
        return []

    depassement = interets - plafond_interets
    return [Finding(
        control_code="C14",
        title=f"Intérêts d'emprunts à vérifier vs plafond CC associés",
        description=(
            f"Intérêts comptabilisés (cl. 671/672) : {interets:,.0f} FCFA. "
            f"Plafond légal (25 % du résultat avant IS/amort./intérêts) : {plafond_interets:,.0f} FCFA. "
            f"Si tout ou partie correspond à des intérêts de comptes courants d'associés détenant ≥ 25 % du capital, "
            f"l'excédent de {depassement:,.0f} FCFA est non déductible."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="CGI art. 7-B",
        evidence={
            "interets_emprunts": float(interets),
            "plafond_interets": float(plafond_interets),
            "depassement_potentiel": float(depassement),
            "capitaux_propres": float(a.capitaux_propres),
        },
    )]


# ----------------------------------------------------------------------------
# C17 — Report déficitaire
# ----------------------------------------------------------------------------
def c17_report_deficitaire(ctx: ControlContext) -> list[Finding]:
    """Report ≤ 4 ans (6 ans banques) — CGI art. 12."""
    a = _aggs(ctx)
    # Negative report à nouveau = déficit reporté
    if a.report_a_nouveau >= 0:
        return []
    deficit_reporte = -a.report_a_nouveau

    return [Finding(
        control_code="C17",
        title=f"Déficit reporté : {deficit_reporte:,.0f} FCFA — vérifier ancienneté",
        description=(
            f"Le compte 12 (Report à nouveau) présente un solde débiteur net de {deficit_reporte:,.0f} FCFA. "
            f"Conformément à l'art. 12 du CGI, le report déficitaire est limité à 4 exercices "
            f"(6 pour les établissements de crédit). "
            "Vérifier le détail des exercices d'origine et écarter les déficits > N-4."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="CGI art. 12",
        evidence={"deficit_reporte": float(deficit_reporte)},
    )]


# ----------------------------------------------------------------------------
# C19 — Charges fiscalement non déductibles
# ----------------------------------------------------------------------------
def c19_charges_non_deductibles(ctx: ControlContext) -> list[Finding]:
    """IS / IRPP / amendes / pénalités ≠ déductibles — CGI art. 7-A-3."""
    # Identify sous-comptes non-déductibles dans les charges
    NON_DED_PATTERNS = {
        "6471": "Impôts directs et taxes assimilées (IS, IRPP)",
        "6478": "Pénalités et amendes fiscales",
        "651":  "Pertes sur créances irrécouvrables (à vérifier)",
        "658":  "Subventions accordées (cf. plafond C9)",
        "678":  "Pertes et charges exceptionnelles HAO",
    }
    findings = []
    for line in ctx.trial_balance:
        for pattern, label in NON_DED_PATTERNS.items():
            if not line["account_code"].startswith(pattern):
                continue
            charge = Decimal(str(line["closing_debit"])) - Decimal(str(line["closing_credit"]))
            if charge <= 0:
                continue
            findings.append(Finding(
                control_code="C19",
                title=f"Charge à réintégrer : {line['account_code']} — {line['account_name']}",
                description=(
                    f"Compte {line['account_code']} ({label}) — solde débiteur {charge:,.0f} FCFA. "
                    f"Cette catégorie de charge est non déductible fiscalement et doit être réintégrée."
                ),
                severity=ControlSeverity.HIGH,
                legal_reference="CGI art. 7-A-3",
                evidence={
                    "account_code": line["account_code"],
                    "account_name": line["account_name"],
                    "category": label,
                    "amount": float(charge),
                },
                estimated_impact_xaf=float(charge),
            ))
    return findings


# ----------------------------------------------------------------------------
# C-summary — résumé du bénéfice fiscal reconstitué
# ----------------------------------------------------------------------------
def c_summary(ctx: ControlContext) -> list[Finding]:
    """Donne une vue d'ensemble du résultat fiscal reconstitué."""
    a = _aggs(ctx)
    if a.chiffre_affaires == 0:
        return []
    return [Finding(
        control_code="C0",
        title="Synthèse — Résultat & IS reconstitués",
        description=(
            f"CA : {a.chiffre_affaires:,.0f} FCFA · "
            f"Charges expl. : {(a.achats_marchandises + a.achats_mp + a.autres_achats + a.transports + a.services_exterieurs + a.autres_services + a.impots_taxes + a.charges_personnel + a.amortissements):,.0f} FCFA · "
            f"Résultat expl. : {a.resultat_exploitation:,.0f} FCFA · "
            f"Résultat net comptable : {a.resultat_net:,.0f} FCFA."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA Titre IX",
        evidence={
            "ca": float(a.chiffre_affaires),
            "resultat_exploitation": float(a.resultat_exploitation),
            "resultat_net": float(a.resultat_net),
            "capitaux_propres": float(a.capitaux_propres),
            "amortissements": float(a.amortissements),
        },
    )]


# ----------------------------------------------------------------------------
# C20 — Acomptes IS mensuels = 2,2 % du CA mensuel — recoupement annuel
# ----------------------------------------------------------------------------
def c20_acompte_is_mensuel(ctx: ControlContext) -> list[Finding]:
    """CGI art. 21 — chaque mois le contribuable verse un acompte IS de 2,2 %
    (2 % IS + 10 % CAC) du CA mensuel. Σ acomptes annuels = 2,2 % × CA annuel.

    Recoupe Σ(declared_amount des DSF-M ACOMPTE_IS) vs 2,2 % × CA total (cl. 70).
    """
    a = _aggs(ctx)
    if a.chiffre_affaires <= 0:
        return []

    expected_total = (a.chiffre_affaires * T.IS_ACOMPTE_RATE_REEL_CAC).quantize(Decimal("1"))

    # Σ of all ACOMPTE_IS monthly returns for this case
    returns = ctx.extra.get("monthly_returns", []) or []
    acomptes = [r for r in returns if r.get("tax_type") == "ACOMPTE_IS"]
    declared_total = sum(
        (Decimal(str(r.get("declared_amount") or 0)) for r in acomptes),
        Decimal("0"),
    )

    if not acomptes:
        return [Finding(
            control_code="C20",
            title=f"Aucune déclaration d'acompte IS chargée — attendu : {expected_total:,.0f} FCFA (2,2 % du CA)",
            description=(
                f"Aucun acompte IS mensuel chargé pour ce dossier. "
                f"Sur la base du CA déclaré ({a.chiffre_affaires:,.0f} FCFA), "
                f"le total attendu des acomptes IS mensuels est {expected_total:,.0f} FCFA "
                f"(2,2 % × CA, soit 2 % IS + 10 % CAC). "
                "Importer les 12 DSF-M d'acompte IS pour effectuer le recoupement."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 21",
            evidence={
                "ca_annuel": float(a.chiffre_affaires),
                "rate_with_cac": float(T.IS_ACOMPTE_RATE_REEL_CAC),
                "expected_total": float(expected_total),
                "returns_loaded": 0,
            },
        )]

    diff = declared_total - expected_total
    tolerance = expected_total * Decimal("0.01")  # 1 % tolerance for rounding

    if abs(diff) <= tolerance:
        return [Finding(
            control_code="C20",
            title=f"Acomptes IS recoupés : Σ déclarés ≈ 2,2 % × CA ({declared_total:,.0f} FCFA)",
            description=(
                f"Σ acomptes IS déclarés sur {len(acomptes)} mois : {declared_total:,.0f} FCFA. "
                f"Attendu (2,2 % × CA de {a.chiffre_affaires:,.0f} FCFA) : {expected_total:,.0f} FCFA. "
                f"Écart : {diff:+,.0f} FCFA — dans la tolérance."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 21",
            evidence={
                "ca_annuel": float(a.chiffre_affaires),
                "declared_total": float(declared_total),
                "expected_total": float(expected_total),
                "diff": float(diff),
                "returns_count": len(acomptes),
            },
        )]

    severity = ControlSeverity.HIGH if abs(diff) > expected_total * Decimal("0.05") else ControlSeverity.MEDIUM
    return [Finding(
        control_code="C20",
        title=f"Écart acomptes IS déclarés vs 2,2 % CA : {diff:+,.0f} FCFA",
        description=(
            f"Σ acomptes IS déclarés sur {len(acomptes)} mois : {declared_total:,.0f} FCFA. "
            f"Attendu sur la base du CA annuel ({a.chiffre_affaires:,.0f} FCFA × 2,2 %) : "
            f"{expected_total:,.0f} FCFA. "
            f"Écart de {diff:+,.0f} FCFA → "
            f"{'sous-déclaration' if diff < 0 else 'sur-déclaration ou irrégularité'} à investiguer "
            "(omissions d'acomptes, base assise CA incorrecte, ou erreur de taux)."
        ),
        severity=severity,
        legal_reference="CGI art. 21",
        evidence={
            "ca_annuel": float(a.chiffre_affaires),
            "rate_with_cac": float(T.IS_ACOMPTE_RATE_REEL_CAC),
            "declared_total": float(declared_total),
            "expected_total": float(expected_total),
            "diff": float(diff),
            "returns_count": len(acomptes),
        },
        estimated_impact_xaf=float(abs(diff)),
    )]


CATEGORY_C_CONTROLS = [
    ("C0",  "Synthèse résultat & IS reconstitués",      c_summary),
    ("C1",  "Recalcul IS et taux applicable",           c1_taux_is),
    ("C3",  "Minimum de perception (2 % CA)",           c3_minimum_perception),
    ("C9",  "Plafond dons (0,5 % CA)",                  c9_plafond_dons),
    ("C11", "Frais siège / assistance technique",        c11_assistance_technique),
    ("C14", "Plafond intérêts CC associés",             c14_interets_cc_associes),
    ("C17", "Report déficitaire (≤ 4 ans)",             c17_report_deficitaire),
    ("C19", "Charges non déductibles à réintégrer",     c19_charges_non_deductibles),
    ("C20", "Acomptes IS mensuels = 2,2 % CA — recoupement annuel", c20_acompte_is_mensuel),
]


def run_category_c(ctx: ControlContext) -> list[Finding]:
    all_findings: list[Finding] = []
    for _, _, fn in CATEGORY_C_CONTROLS:
        try:
            all_findings.extend(fn(ctx))
        except Exception as e:  # noqa: BLE001
            all_findings.append(Finding(
                control_code="C-ERR",
                title=f"Erreur dans {fn.__name__}",
                description=str(e),
                severity=ControlSeverity.INFO,
                legal_reference="—",
            ))
    return all_findings
