"""Pre-computed aggregates from the trial balance, reused by many controls.

Computing the chiffre d'affaires, the total achats, the résultat net etc.
once and passing it via ControlContext.extra avoids each control re-scanning
the balance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


def _sum_classes(tb: list[dict], prefixes: list[str], side: str = "net_credit") -> Decimal:
    """Sum closing balances for accounts whose code starts with any of `prefixes`.

    side:
        - "net_credit" → closing_credit - closing_debit (use for products / passif)
        - "net_debit"  → closing_debit - closing_credit (use for charges / actif)
        - "credit_only" → closing_credit
        - "debit_only" → closing_debit
    """
    total = Decimal("0")
    for line in tb:
        code = line["account_code"]
        if not any(code.startswith(p) for p in prefixes):
            continue
        cd = Decimal(str(line["closing_debit"]))
        cc = Decimal(str(line["closing_credit"]))
        if side == "net_credit":   total += cc - cd
        elif side == "net_debit":  total += cd - cc
        elif side == "credit_only":total += cc
        elif side == "debit_only": total += cd
    return total


@dataclass
class TBAggregates:
    """Aggregates computed once from the trial balance."""
    chiffre_affaires: Decimal = Decimal("0")          # ventes (Σ class 70 credit net)
    ventes_marchandises: Decimal = Decimal("0")
    ventes_produits: Decimal = Decimal("0")
    prestations: Decimal = Decimal("0")
    produits_accessoires: Decimal = Decimal("0")

    achats_marchandises: Decimal = Decimal("0")
    achats_mp: Decimal = Decimal("0")
    autres_achats: Decimal = Decimal("0")
    transports: Decimal = Decimal("0")
    services_exterieurs: Decimal = Decimal("0")
    autres_services: Decimal = Decimal("0")
    impots_taxes: Decimal = Decimal("0")
    autres_charges: Decimal = Decimal("0")
    dons_subventions: Decimal = Decimal("0")
    charges_personnel: Decimal = Decimal("0")
    frais_financiers: Decimal = Decimal("0")
    interets_emprunts: Decimal = Decimal("0")
    amortissements: Decimal = Decimal("0")

    capital_souscrit: Decimal = Decimal("0")
    reserves: Decimal = Decimal("0")
    report_a_nouveau: Decimal = Decimal("0")
    resultat_net: Decimal = Decimal("0")

    tva_collectee: Decimal = Decimal("0")
    tva_deductible_bs: Decimal = Decimal("0")
    tva_deductible_immo: Decimal = Decimal("0")

    # Derived
    capitaux_propres: Decimal = Decimal("0")
    resultat_exploitation: Decimal = Decimal("0")
    benefice_imposable_approx: Decimal = Decimal("0")


def compute_tb_aggregates(tb: list[dict]) -> TBAggregates:
    from app.controls import tax_params as T
    a = TBAggregates()
    a.chiffre_affaires    = _sum_classes(tb, T.ACCOUNTS_CA, "net_credit")
    a.ventes_marchandises = _sum_classes(tb, T.ACCOUNTS_VENTES_MARCHANDISES, "net_credit")
    a.ventes_produits     = _sum_classes(tb, T.ACCOUNTS_VENTES_PRODUITS, "net_credit")
    a.prestations         = _sum_classes(tb, T.ACCOUNTS_PRESTATIONS, "net_credit")
    a.produits_accessoires= _sum_classes(tb, T.ACCOUNTS_PRODUITS_ACCESSOIRES, "net_credit")

    a.achats_marchandises = _sum_classes(tb, T.ACCOUNTS_ACHATS_MARCHANDISES, "net_debit")
    a.achats_mp           = _sum_classes(tb, T.ACCOUNTS_ACHATS_MP, "net_debit")
    a.autres_achats       = _sum_classes(tb, T.ACCOUNTS_AUTRES_ACHATS, "net_debit")
    a.transports          = _sum_classes(tb, T.ACCOUNTS_TRANSPORTS, "net_debit")
    a.services_exterieurs = _sum_classes(tb, T.ACCOUNTS_SERVICES_EXTERIEURS, "net_debit")
    a.autres_services     = _sum_classes(tb, T.ACCOUNTS_AUTRES_SERVICES, "net_debit")
    a.impots_taxes        = _sum_classes(tb, T.ACCOUNTS_IMPOTS_TAXES, "net_debit")
    a.autres_charges      = _sum_classes(tb, T.ACCOUNTS_AUTRES_CHARGES, "net_debit")
    a.dons_subventions    = _sum_classes(tb, T.ACCOUNTS_DONS_SUBVENTIONS, "net_debit")
    a.charges_personnel   = _sum_classes(tb, T.ACCOUNTS_CHARGES_PERSONNEL, "net_debit")
    a.frais_financiers    = _sum_classes(tb, T.ACCOUNTS_FRAIS_FINANCIERS, "net_debit")
    a.interets_emprunts   = _sum_classes(tb, T.ACCOUNTS_INTERETS_EMPRUNTS, "net_debit")
    a.amortissements      = _sum_classes(tb, T.ACCOUNTS_AMORTISSEMENTS, "net_debit")

    a.capital_souscrit    = _sum_classes(tb, [T.ACCT_CAPITAL], "net_credit")
    a.reserves            = _sum_classes(tb, [T.ACCT_RESERVES], "net_credit")
    a.report_a_nouveau    = _sum_classes(tb, [T.ACCT_REPORT_A_NOUVEAU], "net_credit")
    a.resultat_net        = _sum_classes(tb, [T.ACCT_RESULTAT_NET], "net_credit")

    a.tva_collectee       = _sum_classes(tb, [T.ACCT_TVA_COLLECTEE], "net_credit")
    a.tva_deductible_bs   = _sum_classes(tb, [T.ACCT_TVA_DEDUCTIBLE_BS], "net_debit")
    a.tva_deductible_immo = _sum_classes(tb, [T.ACCT_TVA_DEDUCTIBLE_IMMO], "net_debit")

    a.capitaux_propres = a.capital_souscrit + a.reserves + a.report_a_nouveau + a.resultat_net

    total_charges_expl = (
        a.achats_marchandises + a.achats_mp + a.autres_achats +
        a.transports + a.services_exterieurs + a.autres_services +
        a.impots_taxes + a.autres_charges + a.charges_personnel + a.amortissements
    )
    total_produits_expl = (
        a.ventes_marchandises + a.ventes_produits + a.prestations + a.produits_accessoires
    )
    a.resultat_exploitation = total_produits_expl - total_charges_expl

    # Approximation : résultat fiscal ≈ résultat net comptable (sans réintégrations)
    a.benefice_imposable_approx = a.resultat_net if a.resultat_net != 0 else a.resultat_exploitation

    return a
