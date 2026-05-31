"""Tax parameters extracted from CGI 2025.

Centralised so a single source of truth governs the controls engine.
When the Loi de Finances modifies a rate, update here and re-run.
All amounts in FCFA.
"""
from decimal import Decimal


# ---- IS — Impôt sur les Sociétés ----
IS_RATE_STANDARD = Decimal("0.30")           # CGI art. 17 (1)
IS_RATE_REDUCED = Decimal("0.25")            # CGI art. 17 bis — CA HT ≤ 3 Mrd
IS_REDUCED_CA_THRESHOLD = Decimal("3000000000")  # 3 Mrd FCFA
IS_NEGLIGIBLE_FRACTION = Decimal("1000")     # CGI art. 17 (3) — fraction <1000 FCFA négligée
CAC_RATE = Decimal("0.10")                   # +10 % CAC sur IS, TVA, IRPP

# Acomptes provisionnels IS — CGI art. 21
IS_ACOMPTE_RATE_REEL = Decimal("0.02")       # 2 % CA mensuel
IS_ACOMPTE_RATE_REEL_CAC = Decimal("0.022")  # 2,2 % CA mensuel — IS + CAC 10 %
IS_ACOMPTE_RATE_SIMPLIFIE = Decimal("0.05")  # 5 % CA mensuel
IS_ACOMPTE_RATE_HORS_FICHIER = Decimal("0.10")
IS_ACOMPTE_RATE_MARGES_ADM = Decimal("0.14") # 14 % marge brute

# Minimum de perception — CGI art. 22-23
IS_MIN_PERCEPTION_RATE_REEL = Decimal("0.02")
IS_MIN_PERCEPTION_RATE_SIMPLIFIE = Decimal("0.05")

# Reports déficitaires — CGI art. 12
DEFICIT_CARRYFORWARD_YEARS = 4
DEFICIT_CARRYFORWARD_YEARS_BANKS = 6

# Plafonds de charges déductibles — CGI art. 7
PLAFOND_DONS_INTERET_GENERAL = Decimal("0.005")    # 0,5 % CA
PLAFOND_DONS_CLUBS_SPORTIFS = Decimal("0.05")      # 5 % CA
PLAFOND_FRAIS_SIEGE_ASSIST_TECH = Decimal("0.025") # 2,5 % BI
PLAFOND_BREVETS_MARQUES = Decimal("0.025")         # 2,5 % BI
PLAFOND_COMMISSIONS_ETRANGERES = Decimal("0.01")   # 1 % achats
PLAFOND_COTISATIONS_RETRAITE_EXPAT = Decimal("0.15")  # 15 % salaire base
SEUIL_IMMOBILISATION_PETIT_MATERIEL = Decimal("500000")
SEUIL_PAIEMENT_ESPECES_NON_DEDUCTIBLE = Decimal("100000")
SEUIL_PAIEMENT_BANCAIRE_OBLIGATOIRE = Decimal("100000")
PLAFOND_INTERETS_CC_RATIO_CAPITAUX_PROPRES = Decimal("1.5")
PLAFOND_INTERETS_CC_RATIO_RESULTAT = Decimal("0.25")
ASSOCIE_DETENTION_SEUIL = Decimal("0.10")    # CGI art. 7-A-2

# ---- TVA — CGI Titre II ----
TVA_RATE_STANDARD = Decimal("0.175")          # CGI art. 142 (CAC inclus)
TVA_RATE_ZERO = Decimal("0.00")
TVA_REGIME_REEL_CA_SEUIL = Decimal("50000000") # CGI art. 132
TVA_DEDUCTIBILITE_DELAI_EXERCICES = 2          # CGI art. 143 (2)
TVA_PRORATA_SEUIL_MIN = Decimal("0.10")        # CGI art. 147

# ---- IRPP — CGI art. 69 ----
IRPP_BAREMME = [
    (Decimal("0"),         Decimal("2000000"),  Decimal("0.10")),
    (Decimal("2000000"),   Decimal("3000000"),  Decimal("0.15")),
    (Decimal("3000000"),   Decimal("5000000"),  Decimal("0.25")),
    (Decimal("5000000"),   None,                Decimal("0.35")),
]
IRPP_ABATTEMENT_BASE = Decimal("500000")       # CGI art. 29
IRPP_FRAIS_PRO_RATE = Decimal("0.30")          # CGI art. 34
IRPP_FRAIS_PRO_PLAFOND = Decimal("4800000")
IRPP_DISPENSE_SALAIRE_MENSUEL = Decimal("62000")

# Retenues à la source
RETENUE_PRESTATAIRES_PUBLICS = Decimal("0.055")  # 5,5 % avec CAC, CGI art. 92
RETENUE_HONORAIRES_LIBERAUX = Decimal("0.05")    # CGI art. 92 bis
RETENUE_MANDATAIRES = Decimal("0.10")            # CGI art. 93 bis

# TSR — Taxe Spéciale sur les Revenus, CGI art. 225-228
TSR_RATE_GENERAL = Decimal("0.15")
TSR_RATE_MOYEN = Decimal("0.10")
TSR_RATE_REDUIT = Decimal("0.03")
TSR_BIEN_PRESTATION_RATIO = Decimal("0.25")

# ---- LPF ----
INTERET_RETARD_MENSUEL = Decimal("0.015")      # 1,5 % / mois — LPF art. L 95
INTERET_RETARD_PLAFOND = Decimal("0.50")       # plafonné 50 %
MAJORATION_BONNE_FOI = Decimal("0.30")          # LPF art. L 96
MAJORATION_MAUVAISE_FOI = Decimal("1.00")
MAJORATION_MANOEUVRES_FRAUDULEUSES = Decimal("1.50")
CONSERVATION_DOCUMENTS_ANS = 10                # LPF art. L 4
PRESCRIPTION_DROIT_REPRISE_ANS = 4
DELAI_AVIS_VERIFICATION_JOURS = 15             # LPF art. L 13
DELAI_VERIFICATION_SUR_PLACE_MOIS = 3          # LPF art. L 40
DELAI_REPONSE_CONTRIBUABLE_JOURS = 30          # LPF art. L 24
DELAI_REPONSE_ADMINISTRATION_JOURS = 60        # LPF art. L 26

# Amendes spécifiques DSF — LPF art. L 99
AMENDE_NON_DEPOT_DSF_DGE = Decimal("5000000")
AMENDE_NON_DEPOT_DSF_CIME = Decimal("1000000")
AMENDE_NON_DEPOT_DSF_CDI = Decimal("250000")
AMENDE_FACTURE_OU_NIU_MIN = Decimal("100000")  # LPF art. L 102
AMENDE_FAUSSE_FACTURE_RATE = Decimal("1.00")   # 100 % valeur transaction


# ---- SYSCOHADA classes & sub-classes used by the controls engine ----
# Class 7 = produits (CA = sous-classe 70)
ACCOUNTS_CA = ["70"]
ACCOUNTS_VENTES_MARCHANDISES = ["701"]
ACCOUNTS_VENTES_PRODUITS = ["702", "703", "704"]
ACCOUNTS_PRESTATIONS = ["705", "706"]
ACCOUNTS_PRODUITS_ACCESSOIRES = ["707"]
ACCOUNTS_PRODUITS_HAO = ["82", "84", "86", "88"]

# Class 6 = charges
ACCOUNTS_ACHATS_MARCHANDISES = ["601"]
ACCOUNTS_ACHATS_MP = ["602"]
ACCOUNTS_VARIATIONS_STOCKS = ["603"]
ACCOUNTS_AUTRES_ACHATS = ["604", "605", "608"]
ACCOUNTS_TRANSPORTS = ["61"]
ACCOUNTS_SERVICES_EXTERIEURS = ["62"]
ACCOUNTS_AUTRES_SERVICES = ["63"]
ACCOUNTS_IMPOTS_TAXES = ["64"]
ACCOUNTS_AUTRES_CHARGES = ["65"]
ACCOUNTS_DONS_SUBVENTIONS = ["658"]      # Subventions accordées (incl. dons)
ACCOUNTS_CHARGES_PERSONNEL = ["66"]
ACCOUNTS_FRAIS_FINANCIERS = ["67"]
ACCOUNTS_INTERETS_EMPRUNTS = ["671", "672"]
ACCOUNTS_AMORTISSEMENTS = ["68"]

# Charges fiscalement non-déductibles connues
ACCOUNTS_NON_DEDUCTIBLES_IS = ["641"]    # selon classification sous-comptes
# Note: les amendes/pénalités sont typiquement comptabilisées en 6478 ou 678

# Class 4 = tiers — comptes fiscaux
ACCT_TVA_COLLECTEE = "4431"     # TVA facturée
ACCT_TVA_DEDUCTIBLE_IMMO = "4451"
ACCT_TVA_DEDUCTIBLE_BS = "4452"
ACCT_IS_A_PAYER = "4441"
ACCT_IRPP_RETENU = "4471"
ACCT_CNPS = "4311"

# Class 1 = ressources durables
ACCT_CAPITAL = "101"
ACCT_RESERVES = "11"
ACCT_REPORT_A_NOUVEAU = "12"     # 121 bénéfice / 129 perte
ACCT_RESULTAT_NET = "13"
