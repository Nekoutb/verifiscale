"""Category B — SYSCOHADA Évaluation, règles comptables, SIG & TFT.

Implements the 14 controls in the catalog covering valuation rules
(stocks, amortissements, provisions, réévaluation, escompte, devises),
the SIG (Soldes Intermédiaires de Gestion) cascade and the TFT.

Many B controls require qualitative judgment (PEPS vs CMP method,
componentization, provisions criteria) — these emit MEDIUM/INFO reminders
with an explicit checklist for the auditor rather than a hard fail.
"""
from __future__ import annotations

from decimal import Decimal

from app.controls import tax_params as T
from app.controls.aggregates import TBAggregates
from app.controls.base import ControlContext, Finding
from app.models.control_run import ControlSeverity


def _aggs(ctx: ControlContext) -> TBAggregates:
    return ctx.extra["tb_aggregates"]


def _sum_class(ctx: ControlContext, prefixes: tuple[str, ...], side: str) -> Decimal:
    """Sum a movement column (period_debit, period_credit, closing_debit, closing_credit)
    across all TB lines whose account code starts with any of `prefixes`."""
    total = Decimal("0")
    for line in ctx.trial_balance:
        if any(line["account_code"].startswith(p) for p in prefixes):
            total += Decimal(str(line.get(side, 0) or 0))
    return total


# ─────────────────────────────────────────────────────────────────────────────
# B1 — Stocks valorisés en PEPS ou CMP uniquement (LIFO interdit)
# ─────────────────────────────────────────────────────────────────────────────
def b1_stocks_methode(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 44 + Chap. 14 — PEPS (FIFO) ou CMP uniquement. LIFO interdit."""
    stocks_class_3 = _sum_class(ctx, ("3",), "closing_debit")
    if stocks_class_3 == 0:
        return []  # No stocks — control N/A
    return [Finding(
        control_code="B1",
        title="Vérifier la méthode de valorisation des stocks (PEPS ou CMP uniquement)",
        description=(
            f"Stocks à la clôture (classe 3) : {stocks_class_3:,.0f} FCFA. "
            "L'article 44 SYSCOHADA n'autorise QUE les méthodes Premier Entré Premier Sorti (PEPS / FIFO) "
            "ou Coût Moyen Pondéré (CMP). La méthode Dernier Entré Premier Sorti (LIFO) est INTERDITE. "
            "Vérifier dans les notes annexes la méthode appliquée et sa permanence (cf. B11)."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA art. 44 + Chap. 14",
        evidence={"stocks_cloture_class3": float(stocks_class_3)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B2 — Inventaire clôture = min(coût, VNR)
# ─────────────────────────────────────────────────────────────────────────────
def b2_inventaire_vnr(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 44 — stocks valorisés au plus bas du coût et de la VNR."""
    stocks = _sum_class(ctx, ("3",), "closing_debit")
    if stocks == 0:
        return []
    return [Finding(
        control_code="B2",
        title="Vérifier la dépréciation des stocks au plus bas du coût et de la VNR",
        description=(
            f"Stocks de clôture : {stocks:,.0f} FCFA. "
            "L'article 44 SYSCOHADA impose la valorisation au plus bas du coût d'entrée ET de la "
            "Valeur Nette de Réalisation (VNR = prix de vente − coûts d'achèvement et de commercialisation). "
            "Si VNR < coût → dépréciation obligatoire via compte 39 (dépréciation des stocks). "
            "Vérifier la cohérence avec les comptes 39 et la note annexe."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA art. 44",
        evidence={"stocks_brut_cloture": float(stocks)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B3 — Cohérence variation des stocks : SI + Achats − SF = Coût des ventes
# ─────────────────────────────────────────────────────────────────────────────
def b3_variation_stocks(ctx: ControlContext) -> list[Finding]:
    """Vérifier l'équation comptable de base sur les stocks marchandises."""
    si = _sum_class(ctx, ("31",), "opening_debit")    # stocks marchandises ouverture
    sf = _sum_class(ctx, ("31",), "closing_debit")    # stocks marchandises clôture
    achats = _sum_class(ctx, ("601",), "period_debit") # achats marchandises
    variation = _sum_class(ctx, ("6031",), "period_debit") - _sum_class(ctx, ("6031",), "period_credit")
    cout_des_ventes_theorique = si + achats - sf

    if achats == 0 and si == 0 and sf == 0:
        return []

    # Cost of sales = achats + variation (where variation = SI - SF, debit if stock decreased)
    # Variation comptable should equal SI - SF
    variation_theorique = si - sf
    diff = variation - variation_theorique

    if abs(diff) <= Decimal("1000"):
        return [Finding(
            control_code="B3",
            title=f"Variation des stocks cohérente : {variation:,.0f} FCFA",
            description=(
                f"Stocks marchandises : ouverture {si:,.0f} − clôture {sf:,.0f} = {variation_theorique:,.0f} FCFA. "
                f"Variation comptabilisée au 6031 : {variation:,.0f} FCFA. Écart : {diff:+,.0f} FCFA (cohérent)."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="SYSCOHADA Cohérence",
            evidence={
                "stock_ouverture": float(si), "stock_cloture": float(sf),
                "achats": float(achats), "variation_comptabilisee": float(variation),
                "variation_theorique": float(variation_theorique),
                "cout_des_ventes_theorique": float(cout_des_ventes_theorique),
            },
        )]

    return [Finding(
        control_code="B3",
        title=f"Incohérence variation stocks : écart {diff:+,.0f} FCFA",
        description=(
            f"Stocks marchandises : ouverture {si:,.0f} FCFA, clôture {sf:,.0f} FCFA. "
            f"Variation théorique (SI − SF) = {variation_theorique:,.0f} FCFA. "
            f"Variation comptabilisée au 6031 : {variation:,.0f} FCFA. "
            f"Écart de {diff:+,.0f} FCFA → vérifier les écritures d'inventaire de clôture."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA — équation des stocks",
        evidence={
            "stock_ouverture": float(si), "stock_cloture": float(sf),
            "achats": float(achats), "variation_comptabilisee": float(variation),
            "variation_theorique": float(variation_theorique), "ecart": float(diff),
        },
        estimated_impact_xaf=float(abs(diff)),
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B4 — Dotations amortissements obligatoires même sans bénéfice
# ─────────────────────────────────────────────────────────────────────────────
def b4_dotations_amortissements(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 45 + 49 — les dotations aux amortissements sont obligatoires
    même en l'absence de bénéfice. Vérifier que les immobilisations amortissables
    génèrent une dotation."""
    # Immobilisations amortissables : classes 21 (terrains : non), 22 (terrains : non),
    # 23 (bâtiments : oui), 24 (matériel : oui)
    immo_amortissables = _sum_class(ctx, ("23", "24"), "closing_debit")
    amort_cumules = _sum_class(ctx, ("28",), "closing_credit")
    dotations_periode = _sum_class(ctx, ("681",), "period_debit")
    cumul_dotations_periode = _sum_class(ctx, ("28",), "period_credit")

    if immo_amortissables == 0:
        return []

    # Bénéfice de l'exercice (peut être négatif)
    a = _aggs(ctx)

    if dotations_periode == 0 and immo_amortissables > 0:
        return [Finding(
            control_code="B4",
            title=f"Aucune dotation aux amortissements malgré {immo_amortissables:,.0f} FCFA d'immobilisations amortissables",
            description=(
                f"Immobilisations amortissables (classes 23 + 24) : {immo_amortissables:,.0f} FCFA. "
                f"Aucun mouvement détecté au compte 681 (dotations) pour l'exercice. "
                "L'article 45 SYSCOHADA impose la comptabilisation des amortissements MÊME EN L'ABSENCE "
                f"DE BÉNÉFICE (résultat exercice : {a.resultat_net:,.0f} FCFA). "
                "Risque de redressement fiscal et de présentation infidèle des comptes."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="SYSCOHADA art. 45 + 49",
            evidence={
                "immo_amortissables_cloture": float(immo_amortissables),
                "amort_cumules_cloture": float(amort_cumules),
                "dotations_periode_681": float(dotations_periode),
                "resultat_net": float(a.resultat_net),
            },
            estimated_impact_xaf=float(immo_amortissables * Decimal("0.10")),  # estim 10%/an
        )]

    # Cohérence dotations vs cumul mouvements 28
    diff = dotations_periode - cumul_dotations_periode
    if abs(diff) > Decimal("1000"):
        return [Finding(
            control_code="B4",
            title=f"Incohérence dotations vs cumul d'amortissements : écart {diff:+,.0f} FCFA",
            description=(
                f"Dotations exercice (681) : {dotations_periode:,.0f} FCFA. "
                f"Augmentation des amortissements cumulés (28) : {cumul_dotations_periode:,.0f} FCFA. "
                f"Écart : {diff:+,.0f} FCFA → vérifier les cessions, mises au rebut ou réajustements."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="SYSCOHADA art. 45 + 49",
            evidence={"dotations_periode": float(dotations_periode), "cumul_periode": float(cumul_dotations_periode), "ecart": float(diff)},
        )]

    return [Finding(
        control_code="B4",
        title=f"Dotations amortissements OK : {dotations_periode:,.0f} FCFA",
        description=f"Dotations enregistrées au 681 cohérentes avec l'augmentation des amortissements cumulés au 28.",
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA art. 45 + 49",
        evidence={"dotations": float(dotations_periode), "cumul": float(cumul_dotations_periode)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B5 — Modes d'amortissement interdits (revenus, financier)
# ─────────────────────────────────────────────────────────────────────────────
def b5_modes_amortissement(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 45 — modes interdits : amortissement par les revenus,
    amortissement financier."""
    immo = _sum_class(ctx, ("21", "22", "23", "24"), "closing_debit")
    if immo == 0:
        return []
    return [Finding(
        control_code="B5",
        title="Vérifier les modes d'amortissement appliqués (linéaire, dégressif uniquement)",
        description=(
            "L'article 45 SYSCOHADA limite les modes d'amortissement autorisés à : "
            "linéaire (norme), dégressif (sur autorisation), et exceptionnel (justifié). "
            "Les modes 'amortissement par les revenus' et 'amortissement financier' "
            "sont EXPRESSÉMENT INTERDITS. "
            "Vérifier la note annexe et le tableau des immobilisations."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="SYSCOHADA art. 45",
        evidence={"immo_brutes_cloture": float(immo)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B6 — Approche par composants : catégories autorisées uniquement
# ─────────────────────────────────────────────────────────────────────────────
def b6_approche_composants(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 38 + Chap. 4 — décomposition par composants autorisée
    uniquement pour catégories définies (immo techniques importantes)."""
    immo_techniques = _sum_class(ctx, ("23", "24"), "closing_debit")
    if immo_techniques < Decimal("50_000_000"):
        return []  # Pas significatif
    return [Finding(
        control_code="B6",
        title="Approche par composants — vérifier les catégories d'immobilisations concernées",
        description=(
            f"Immobilisations techniques (classes 23 + 24) : {immo_techniques:,.0f} FCFA. "
            "L'article 38 SYSCOHADA autorise la décomposition par composants pour les immobilisations "
            "dont une partie significative a une durée d'utilité différente. "
            "Catégories typiquement éligibles : aéronefs, navires, immeubles complexes, gros équipements industriels. "
            "Vérifier que la décomposition est documentée et limitée aux catégories autorisées."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA art. 38 + Chap. 4",
        evidence={"immo_techniques": float(immo_techniques)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B7 — Provisions : 3 conditions cumulatives
# ─────────────────────────────────────────────────────────────────────────────
def b7_provisions_conditions(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 48 + Chap. 18 — une provision doit satisfaire les 3 conditions
    cumulatives : (1) obligation actuelle, (2) sortie de ressources probable,
    (3) estimation fiable."""
    provisions = _sum_class(ctx, ("19",), "closing_credit") + _sum_class(ctx, ("49",), "closing_credit") \
        + _sum_class(ctx, ("59",), "closing_credit")
    if provisions == 0:
        return []
    return [Finding(
        control_code="B7",
        title=f"Provisions à la clôture : {provisions:,.0f} FCFA — vérifier les 3 conditions cumulatives",
        description=(
            f"Soldes créditeurs provisions (cl. 19 + 49 + 59) : {provisions:,.0f} FCFA. "
            "L'article 48 SYSCOHADA exige que chaque provision satisfasse les 3 conditions cumulatives : "
            "(1) obligation actuelle (légale, réglementaire ou implicite) résultant d'un événement passé · "
            "(2) sortie de ressources probable pour éteindre cette obligation · "
            "(3) montant pouvant être estimé de manière fiable. "
            "Vérifier le dossier de provisions et écarter toute provision pour risques non documentés."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="SYSCOHADA art. 48 + Chap. 18",
        evidence={"total_provisions_cloture": float(provisions)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B8 — Subvention investissement (14x) → reprise au 799 prorata amortissement
# ─────────────────────────────────────────────────────────────────────────────
def b8_subvention_investissement(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA Chap. 17 — subventions d'investissement (cl. 14) doivent être
    reprises au compte 799 (reprises de subventions d'investissement) au prorata
    des amortissements des immobilisations subventionnées."""
    subv = _sum_class(ctx, ("14",), "closing_credit")
    if subv == 0:
        return []

    reprise_periode = _sum_class(ctx, ("799",), "period_credit")
    dotations = _sum_class(ctx, ("681",), "period_debit")

    if reprise_periode == 0:
        return [Finding(
            control_code="B8",
            title=f"Subvention investissement {subv:,.0f} FCFA — aucune reprise au 799 enregistrée",
            description=(
                f"Le compte 14x (subventions d'investissement) présente un solde créditeur de {subv:,.0f} FCFA. "
                "Le Chap. 17 SYSCOHADA impose la reprise au compte 799 (produits) au prorata des "
                "amortissements des immobilisations subventionnées. "
                f"Aucun mouvement au crédit du 799 sur l'exercice (dotations 681 : {dotations:,.0f} FCFA). "
                "Risque de sous-évaluation du résultat."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="SYSCOHADA Chap. 17",
            evidence={"subvention_solde": float(subv), "reprise_periode": float(reprise_periode)},
            estimated_impact_xaf=float(subv * Decimal("0.10")),  # estim ~10% reprise annuelle
        )]

    return [Finding(
        control_code="B8",
        title=f"Subvention investissement — reprise enregistrée : {reprise_periode:,.0f} FCFA",
        description=(
            f"Solde subvention : {subv:,.0f} FCFA. Reprise exercice (799) : {reprise_periode:,.0f} FCFA. "
            "Vérifier que le prorata correspond au taux d'amortissement des immobilisations subventionnées."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA Chap. 17",
        evidence={"subvention_solde": float(subv), "reprise_periode": float(reprise_periode), "dotations": float(dotations)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B9 — Devises 478 → provision pertes de change (déjà implémenté)
# ─────────────────────────────────────────────────────────────────────────────
def b9_devises(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 54-58 — écart de conversion actif (478) → provision obligatoire."""
    findings = []
    for line in ctx.trial_balance:
        if line["account_code"].startswith("478"):
            cd = Decimal(str(line["closing_debit"]))
            if cd > Decimal("1"):
                findings.append(Finding(
                    control_code="B9",
                    title=f"Écart de conversion actif {line['account_code']} → provision obligatoire",
                    description=(
                        f"Le compte {line['account_code']} ({line['account_name']}) présente un solde "
                        f"débiteur de {cd:,.0f} FCFA. Conformément aux articles 54-58 SYSCOHADA, cette "
                        f"perte latente de change doit faire l'objet d'une provision pour pertes de "
                        f"change (compte 6972) à la clôture."
                    ),
                    severity=ControlSeverity.HIGH,
                    legal_reference="SYSCOHADA art. 54-58",
                    evidence={"account_code": line["account_code"], "ecart_conversion_actif": float(cd)},
                    estimated_impact_xaf=float(cd),
                ))
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# B10 — Réévaluation : 100% immo corporelles + financières, jamais partielle
# ─────────────────────────────────────────────────────────────────────────────
def b10_reevaluation(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 62-65 — réévaluation libre obligatoirement intégrale
    (100% des immo corporelles ET financières), jamais partielle."""
    # Indicateurs de réévaluation : compte 1052 (écart de réévaluation libre)
    ecart_reev = _sum_class(ctx, ("1052",), "closing_credit")
    if ecart_reev == 0:
        return []
    return [Finding(
        control_code="B10",
        title=f"Réévaluation libre — écart {ecart_reev:,.0f} FCFA au 1052 — vérifier l'intégralité",
        description=(
            f"Un écart de réévaluation libre est enregistré (compte 1052 : {ecart_reev:,.0f} FCFA). "
            "Les articles 62-65 SYSCOHADA imposent que la réévaluation libre porte sur "
            "100 % des immobilisations corporelles ET financières de l'entité — JAMAIS partielle. "
            "Vérifier l'exhaustivité du périmètre de réévaluation et la cohérence avec la note annexe."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="SYSCOHADA art. 62-65",
        evidence={"ecart_reevaluation_libre": float(ecart_reev)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B11 — Escompte de règlement = produit financier (765/77), jamais déduit prix d'achat
# ─────────────────────────────────────────────────────────────────────────────
def b11_escompte_reglement(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA art. 35-38 — l'escompte de règlement obtenu est un produit financier
    (765 ou 77) ; l'escompte accordé est une charge financière (665). Jamais en
    diminution du prix d'achat ou de vente."""
    escomptes_obtenus = _sum_class(ctx, ("765",), "period_credit")
    escomptes_accordes = _sum_class(ctx, ("665",), "period_debit")
    achats = _sum_class(ctx, ("601", "602"), "period_debit")

    if escomptes_obtenus == 0 and escomptes_accordes == 0 and achats == 0:
        return []

    # Heuristique : si les achats nets affichés sont anormalement bas, possible déduction d'escompte
    return [Finding(
        control_code="B11",
        title=(
            f"Escomptes : obtenus {escomptes_obtenus:,.0f} FCFA · accordés {escomptes_accordes:,.0f} FCFA"
        ),
        description=(
            "L'article 35-38 SYSCOHADA impose : "
            "(1) escompte de règlement obtenu → produit financier (compte 765) · "
            "(2) escompte de règlement accordé → charge financière (compte 665). "
            "Ils ne peuvent JAMAIS être déduits du prix d'achat (601) ni du prix de vente (701). "
            "Vérifier les conditions générales de vente/achat et l'imputation correcte."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="SYSCOHADA art. 35-38",
        evidence={
            "escomptes_obtenus_765": float(escomptes_obtenus),
            "escomptes_accordes_665": float(escomptes_accordes),
            "achats_brut": float(achats),
        },
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B12 — Cohérence SIG (XA→XI) selon formules normalisées
# ─────────────────────────────────────────────────────────────────────────────
def b12_coherence_sig(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA Titre IX Chap. 4 — vérifier les formules SIG :
    Marge brute → Valeur ajoutée → EBE → Résultat exploitation → Résultat net."""
    a = _aggs(ctx)
    if a.chiffre_affaires == 0:
        return []

    # Reconstitution formelle
    marge_commerciale = a.ventes_marchandises - a.achats_marchandises
    consommations_intermediaires = (
        a.achats_marchandises + a.achats_mp + a.autres_achats
        + a.transports + a.services_exterieurs + a.autres_services + a.impots_taxes + a.autres_charges
    )
    valeur_ajoutee = a.chiffre_affaires - consommations_intermediaires
    ebe = valeur_ajoutee - a.charges_personnel
    resultat_exploitation = ebe - a.amortissements
    resultat_financier = -a.frais_financiers  # produits financiers non agrégés
    resultat_avant_impot = resultat_exploitation + resultat_financier
    # Bénéfice imposable approximatif déjà calculé par les agrégats
    resultat_net_reconstitue = a.benefice_imposable_approx

    # Vérification cohérence avec le compte 13 effectif
    diff = a.resultat_net - resultat_net_reconstitue
    relative_diff = abs(diff) / abs(a.resultat_net) if a.resultat_net != 0 else Decimal("0")

    # Si écart > 5% du résultat net → flag
    if relative_diff > Decimal("0.05") and abs(diff) > Decimal("100_000"):
        return [Finding(
            control_code="B12",
            title=f"Incohérence SIG : résultat reconstitué ≠ résultat comptabilisé (écart {diff:+,.0f} FCFA)",
            description=(
                f"Reconstitution SIG : "
                f"VA {valeur_ajoutee:,.0f} · EBE {ebe:,.0f} · "
                f"RE {resultat_exploitation:,.0f} · Résultat avant impôt {resultat_avant_impot:,.0f} FCFA. "
                f"Résultat net comptabilisé (compte 13) : {a.resultat_net:,.0f} FCFA. "
                f"Écart : {diff:+,.0f} FCFA ({float(relative_diff)*100:.1f} %). "
                "Vérifier les écritures de détermination du résultat et les éléments HAO."
            ),
            severity=ControlSeverity.MEDIUM,
            legal_reference="SYSCOHADA Titre IX Chap. 4",
            evidence={
                "marge_commerciale": float(marge_commerciale),
                "valeur_ajoutee": float(valeur_ajoutee),
                "ebe": float(ebe),
                "resultat_exploitation": float(resultat_exploitation),
                "resultat_reconstitue": float(resultat_net_reconstitue),
                "resultat_comptabilise": float(a.resultat_net),
                "ecart": float(diff),
            },
            estimated_impact_xaf=float(abs(diff)),
        )]

    return [Finding(
        control_code="B12",
        title=f"SIG cohérents — résultat reconstitué ≈ résultat comptabilisé",
        description=(
            f"Cascade SIG : VA {valeur_ajoutee:,.0f} → EBE {ebe:,.0f} → "
            f"RE {resultat_exploitation:,.0f} FCFA. "
            f"Résultat net (compte 13) : {a.resultat_net:,.0f} FCFA — cohérent avec la reconstitution."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA Titre IX Chap. 4",
        evidence={
            "valeur_ajoutee": float(valeur_ajoutee),
            "ebe": float(ebe),
            "resultat_exploitation": float(resultat_exploitation),
            "resultat_net": float(a.resultat_net),
        },
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B-SIG — Affichage des SIG (existant, légèrement enrichi)
# ─────────────────────────────────────────────────────────────────────────────
def b_sig(ctx: ControlContext) -> list[Finding]:
    """SIG normalisés du Système Normal SYSCOHADA (vue d'ensemble auditeur)."""
    a = _aggs(ctx)
    if a.chiffre_affaires == 0:
        return []
    marge_commerciale = a.ventes_marchandises - a.achats_marchandises
    valeur_ajoutee = (
        a.chiffre_affaires - a.achats_marchandises - a.achats_mp - a.autres_achats
        - a.transports - a.services_exterieurs - a.autres_services - a.impots_taxes - a.autres_charges
    )
    ebe = valeur_ajoutee - a.charges_personnel
    resultat_exploitation = ebe - a.amortissements

    return [Finding(
        control_code="B-SIG",
        title="Soldes Intermédiaires de Gestion (SIG) reconstitués",
        description=(
            f"XA Marge commerciale : {marge_commerciale:,.0f} FCFA · "
            f"XB CA : {a.chiffre_affaires:,.0f} FCFA · "
            f"XC Valeur ajoutée : {valeur_ajoutee:,.0f} FCFA · "
            f"XD EBE : {ebe:,.0f} FCFA · "
            f"XE Résultat d'exploitation : {resultat_exploitation:,.0f} FCFA."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA Titre IX Chap. 4",
        evidence={
            "marge_commerciale": float(marge_commerciale),
            "chiffre_affaires": float(a.chiffre_affaires),
            "valeur_ajoutee": float(valeur_ajoutee),
            "ebe": float(ebe),
            "resultat_exploitation": float(resultat_exploitation),
            "resultat_net": float(a.resultat_net),
        },
    )]


# ─────────────────────────────────────────────────────────────────────────────
# B13 — Résultat net = solde compte 13
# ─────────────────────────────────────────────────────────────────────────────
def b13_resultat_eq_compte_13(ctx: ControlContext) -> list[Finding]:
    """Le résultat net doit apparaître au compte 13 (131 bénéfice / 139 perte)."""
    a = _aggs(ctx)
    derived_resultat = a.resultat_exploitation
    if a.resultat_net == 0:
        return [Finding(
            control_code="B13",
            title="Aucun résultat comptabilisé au compte 13",
            description=(
                "Le solde net du compte 13 (résultat) est nul. "
                "Si l'exercice présente une activité, l'écriture de détermination du résultat est manquante."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="SYSCOHADA Titre IX",
            evidence={"resultat_net_cl_13": 0.0, "derived_from_classes_6_7": float(derived_resultat)},
        )]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# B14 — TFT : Trésorerie clôture = BT − DT du bilan
# ─────────────────────────────────────────────────────────────────────────────
def b14_tft(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA Titre IX Chap. 5 — Tableau des Flux de Trésorerie :
    Trésorerie nette de clôture = Banques + Caisse − Découverts."""
    # Trésorerie active : classes 51 (banques), 52 (instruments paiement), 53 (caisse), 57 (caisse opérations)
    banques = _sum_class(ctx, ("51", "52", "53"), "closing_debit") - _sum_class(ctx, ("51", "52", "53"), "closing_credit")
    caisse = _sum_class(ctx, ("57",), "closing_debit") - _sum_class(ctx, ("57",), "closing_credit")
    # Concours bancaires courants — découverts (cl. 561) → dettes de trésorerie
    concours = _sum_class(ctx, ("561",), "closing_credit")

    tresorerie_nette = banques + caisse - concours

    if banques == 0 and caisse == 0 and concours == 0:
        return []

    return [Finding(
        control_code="B14",
        title=f"Trésorerie nette de clôture : {tresorerie_nette:,.0f} FCFA",
        description=(
            f"Banques et instruments paiement (cl. 51-52-53) : {banques:,.0f} FCFA · "
            f"Caisse (cl. 57) : {caisse:,.0f} FCFA · "
            f"Concours bancaires (cl. 561) : −{concours:,.0f} FCFA. "
            f"Trésorerie nette = {tresorerie_nette:,.0f} FCFA. "
            "Vérifier la cohérence avec la dernière ligne du Tableau des Flux de Trésorerie (TFT)."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="SYSCOHADA Titre IX Chap. 5",
        evidence={
            "banques": float(banques),
            "caisse": float(caisse),
            "concours_bancaires": float(concours),
            "tresorerie_nette_cloture": float(tresorerie_nette),
        },
    )]


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_B_CONTROLS = [
    ("B1",    "Stocks valorisés en PEPS ou CMP uniquement",            b1_stocks_methode),
    ("B2",    "Inventaire clôture = min(coût, VNR)",                   b2_inventaire_vnr),
    ("B3",    "Cohérence variation stocks SI + Achats − SF",           b3_variation_stocks),
    ("B4",    "Dotations amortissements obligatoires",                 b4_dotations_amortissements),
    ("B5",    "Modes d'amortissement interdits",                       b5_modes_amortissement),
    ("B6",    "Approche par composants — catégories autorisées",       b6_approche_composants),
    ("B7",    "Provisions — 3 conditions cumulatives",                 b7_provisions_conditions),
    ("B8",    "Subvention investissement (14) reprise au 799",         b8_subvention_investissement),
    ("B9",    "Provision pertes de change (478)",                      b9_devises),
    ("B10",   "Réévaluation libre intégrale 100%",                     b10_reevaluation),
    ("B11",   "Escompte de règlement = produit/charge financier",      b11_escompte_reglement),
    ("B12",   "Cohérence SIG (XA→XI) formules normalisées",            b12_coherence_sig),
    ("B-SIG", "SIG reconstitués (vue d'ensemble)",                     b_sig),
    ("B13",   "Résultat net = solde compte 13",                        b13_resultat_eq_compte_13),
    ("B14",   "TFT — Trésorerie nette de clôture",                     b14_tft),
]


def run_category_b(ctx: ControlContext) -> list[Finding]:
    all_findings: list[Finding] = []
    for _, _, fn in CATEGORY_B_CONTROLS:
        try:
            all_findings.extend(fn(ctx))
        except Exception as e:  # noqa: BLE001
            all_findings.append(Finding(
                control_code="B-ERR", title=f"Erreur {fn.__name__}",
                description=str(e), severity=ControlSeverity.INFO, legal_reference="—",
            ))
    return all_findings
