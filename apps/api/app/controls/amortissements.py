"""Amortissements (depreciation) control — CGI Cameroun, Section D, Article 7.

Maps each line of the auditee's fixed-asset register to the appropriate
fiscal category, recomputes the straight-line depreciation expense for the
fiscal year, and compares to what's booked in the register.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.parsers.common import _normalize


# ─────────────────────────────────────────────────────────────────────────────
# CGI Cameroun — Section D, Article 7  prescribed straight-line rates.
# Order is significant: more specific keywords are evaluated first.
# Each rule has: code, label_fr, label_en, rate_pct (linear), keywords (any
# normalized substring match counts).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FiscalCategory:
    code: str
    label_fr: str
    label_en: str
    rate_pct: Decimal
    keywords: tuple[str, ...]


# Keywords normalized (lowercase, no accents, no separators) before matching.
CATEGORIES: list[FiscalCategory] = [
    FiscalCategory(
        code="A7.LAND",
        label_fr="Terrains (non amortissables)",
        label_en="Land (non-depreciable)",
        rate_pct=Decimal("0"),
        keywords=("terrain", "terrains", "land", "parcelle"),
    ),
    FiscalCategory(
        code="A7.IT.SOFT",
        label_fr="Logiciels et applications",
        label_en="Software and applications",
        rate_pct=Decimal("33.33"),
        keywords=("logiciel", "software", "saas", "licence", "license",
                  "erp", "application", "progiciel"),
    ),
    FiscalCategory(
        code="A7.IT.HW",
        label_fr="Matériel informatique (ordinateurs, serveurs, périphériques)",
        label_en="IT equipment (computers, servers, peripherals)",
        rate_pct=Decimal("25"),
        keywords=("ordinateur", "ordi", "laptop", "computer", "pc",
                  "serveur", "server", "informatique", "imprimante",
                  "printer", "scanner", "switch", "router", "routeur",
                  "ecran", "écran", "monitor", "clavier", "souris",
                  "onduleur", "ups", "nas"),
    ),
    FiscalCategory(
        code="A7.VEH.LIGHT",
        label_fr="Véhicules de tourisme et utilitaires légers",
        label_en="Passenger and light commercial vehicles",
        rate_pct=Decimal("25"),
        keywords=("vehicule", "véhicule", "voiture", "car", "auto",
                  "automobile", "berline", "suv", "pickup", "pick-up",
                  "tourisme", "utilitaire", "fourgon"),
    ),
    FiscalCategory(
        code="A7.VEH.HEAVY",
        label_fr="Véhicules industriels et poids lourds",
        label_en="Industrial vehicles and trucks",
        rate_pct=Decimal("20"),
        keywords=("camion", "truck", "poidslourd", "remorque", "trailer",
                  "tracteur", "tractor", "benne", "semiremorque"),
    ),
    FiscalCategory(
        code="A7.MACH",
        label_fr="Matériel et outillage industriel",
        label_en="Industrial machinery and tooling",
        rate_pct=Decimal("20"),
        keywords=("machine", "outillage", "outil", "machinery", "compresseur",
                  "groupeelectrogene", "generator", "pompe", "pump",
                  "moteur", "motor", "presse", "press", "moule", "mould"),
    ),
    FiscalCategory(
        code="A7.OFFICE",
        label_fr="Matériel de bureau",
        label_en="Office equipment",
        rate_pct=Decimal("20"),
        keywords=("photocopieur", "copieur", "telephone", "téléphone",
                  "fax", "telephoneip", "phone", "calculatrice",
                  "destructeur", "shredder"),
    ),
    FiscalCategory(
        code="A7.FURN",
        label_fr="Mobilier de bureau",
        label_en="Office furniture",
        rate_pct=Decimal("10"),
        keywords=("mobilier", "furniture", "bureau", "chaise", "chair",
                  "fauteuil", "armoire", "etagere", "étagère", "table",
                  "desk", "rayonnage", "shelf", "shelves"),
    ),
    FiscalCategory(
        code="A7.AC",
        label_fr="Climatisation et électroménager professionnel",
        label_en="Air conditioning & professional appliances",
        rate_pct=Decimal("20"),
        keywords=("climatiseur", "clim", "airconditioning", "ac",
                  "refrigerateur", "réfrigérateur", "fridge",
                  "congelateur", "congélateur", "freezer", "ventilateur",
                  "ventilator"),
    ),
    FiscalCategory(
        code="A7.LIGHT_CONST",
        label_fr="Constructions légères et démontables",
        label_en="Light & dismountable constructions",
        rate_pct=Decimal("20"),
        keywords=("constructionlegere", "demontable", "préfabriqué",
                  "prefab", "abri", "shed", "hangar"),
    ),
    FiscalCategory(
        code="A7.BUILD.INDUS",
        label_fr="Bâtiments industriels",
        label_en="Industrial buildings",
        rate_pct=Decimal("5"),
        keywords=("batimentindustriel", "usine", "atelier", "entrepot",
                  "warehouse", "factory"),
    ),
    FiscalCategory(
        code="A7.BUILD.COMM",
        label_fr="Bâtiments commerciaux ou administratifs",
        label_en="Commercial / administrative buildings",
        rate_pct=Decimal("5"),
        keywords=("batiment", "building", "immeuble", "construction",
                  "siege", "siège", "showroom", "boutique", "magasin",
                  "store", "shop", "office"),
    ),
    FiscalCategory(
        code="A7.FITOUT",
        label_fr="Agencements, aménagements et installations",
        label_en="Fittings, fit-outs and installations",
        rate_pct=Decimal("10"),
        keywords=("agencement", "amenagement", "aménagement", "installation",
                  "fitout", "fit-out", "cloison", "partition", "menuiserie",
                  "carrelage", "tiling", "peinture", "painting"),
    ),
    FiscalCategory(
        code="A7.SMALL_TOOLS",
        label_fr="Petit matériel et outillage (< 500 000 FCFA)",
        label_en="Small tools and equipment (< 500,000 FCFA)",
        rate_pct=Decimal("100"),  # full expensing if under threshold (see CGI art. 7)
        keywords=("petitoutillage", "petitmateriel", "smalltool",
                  "consumable", "consommable"),
    ),
]


# Fallback when nothing matches.
DEFAULT_CATEGORY = FiscalCategory(
    code="A7.OTHER",
    label_fr="Autres immobilisations (à classer manuellement)",
    label_en="Other fixed assets (to classify manually)",
    rate_pct=Decimal("20"),  # generic linear rate; auditor should review
    keywords=(),
)


def classify(asset_name: str) -> FiscalCategory:
    """Return the most specific FiscalCategory matching the asset description."""
    n = _normalize(asset_name)
    if not n:
        return DEFAULT_CATEGORY
    for cat in CATEGORIES:
        for kw in cat.keywords:
            if kw in n:
                return cat
    return DEFAULT_CATEGORY


# ─────────────────────────────────────────────────────────────────────────────
# Recomputation — straight line, prorated on days held during the fiscal year
# ─────────────────────────────────────────────────────────────────────────────


def _days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def recompute_year_depreciation(
    gross_value_xaf: Decimal,
    rate_pct: Decimal,
    acquisition_date: date | None,
    disposal_date: date | None,
    fiscal_year: int,
) -> Decimal:
    """Straight-line depreciation for the given fiscal year, prorated on days.

    - First year prorated from acquisition_date to year-end.
    - Disposal year prorated from year-start to disposal_date.
    - Land / 0 % → 0.
    """
    if rate_pct == 0 or gross_value_xaf == 0:
        return Decimal("0")

    fy_start = date(fiscal_year, 1, 1)
    fy_end = date(fiscal_year, 12, 31)

    # If the asset wasn't yet acquired or already disposed before this FY,
    # zero contribution.
    if acquisition_date and acquisition_date > fy_end:
        return Decimal("0")
    if disposal_date and disposal_date < fy_start:
        return Decimal("0")

    period_start = max(acquisition_date, fy_start) if acquisition_date else fy_start
    period_end = min(disposal_date, fy_end) if disposal_date else fy_end
    if period_end < period_start:
        return Decimal("0")

    days_in_period = Decimal((period_end - period_start).days + 1)
    days_in_yr = Decimal(_days_in_year(fiscal_year))

    annual = (gross_value_xaf * rate_pct / Decimal("100"))
    return (annual * days_in_period / days_in_yr).quantize(Decimal("0.01"))


# ─────────────────────────────────────────────────────────────────────────────
# Per-row analysis
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AmortissementRow:
    reference: str
    account_number: str
    name: str
    acquisition_date: date | None
    disposal_date: date | None
    gross_value_xaf: Decimal
    accumulated_depreciation_xaf: Decimal | None
    register_rate_pct: Decimal | None
    register_year_depreciation_xaf: Decimal | None
    # Mapped fiscal category
    fiscal_category_code: str
    fiscal_category_label_fr: str
    fiscal_category_label_en: str
    prescribed_rate_pct: Decimal
    # Match flag
    rate_match: bool
    rate_match_delta_pp: Decimal  # percentage-point delta (register − prescribed)
    # Recomputed expense
    recomputed_year_depreciation_xaf: Decimal
    variance_xaf: Decimal  # register − recomputed (positive = over-depreciated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "account_number": self.account_number,
            "name": self.name,
            "acquisition_date": self.acquisition_date.isoformat() if self.acquisition_date else None,
            "disposal_date": self.disposal_date.isoformat() if self.disposal_date else None,
            "gross_value_xaf": float(self.gross_value_xaf),
            "accumulated_depreciation_xaf": (
                float(self.accumulated_depreciation_xaf)
                if self.accumulated_depreciation_xaf is not None else None
            ),
            "register_rate_pct": float(self.register_rate_pct) if self.register_rate_pct is not None else None,
            "register_year_depreciation_xaf": (
                float(self.register_year_depreciation_xaf)
                if self.register_year_depreciation_xaf is not None else None
            ),
            "fiscal_category_code": self.fiscal_category_code,
            "fiscal_category_label_fr": self.fiscal_category_label_fr,
            "fiscal_category_label_en": self.fiscal_category_label_en,
            "prescribed_rate_pct": float(self.prescribed_rate_pct),
            "rate_match": self.rate_match,
            "rate_match_delta_pp": float(self.rate_match_delta_pp),
            "recomputed_year_depreciation_xaf": float(self.recomputed_year_depreciation_xaf),
            "variance_xaf": float(self.variance_xaf),
        }


# Tolerance: a rate is considered "matched" if it's within ±0.5 pp.
RATE_TOLERANCE_PP = Decimal("0.5")


def analyze_assets(
    assets: list[dict[str, Any]],
    fiscal_year: int,
) -> tuple[list[AmortissementRow], dict[str, Any]]:
    """Run the per-asset analysis. Returns (rows, summary)."""
    rows: list[AmortissementRow] = []
    total_register = Decimal("0")
    total_recomputed = Decimal("0")
    total_variance_abs = Decimal("0")
    rate_mismatches = 0

    for a in assets:
        cat = classify(a["name"])
        reg_rate = a.get("rate_pct")
        delta = (reg_rate - cat.rate_pct) if reg_rate is not None else Decimal("0")
        rate_match = (
            reg_rate is not None and abs(delta) <= RATE_TOLERANCE_PP
        )
        if not rate_match:
            rate_mismatches += 1

        recomputed = recompute_year_depreciation(
            gross_value_xaf=a.get("gross_value_xaf") or Decimal("0"),
            rate_pct=cat.rate_pct,
            acquisition_date=a.get("acquisition_date"),
            disposal_date=a.get("disposal_date"),
            fiscal_year=fiscal_year,
        )
        reg_dep = a.get("register_year_depreciation_xaf") or Decimal("0")
        variance = reg_dep - recomputed

        total_register += reg_dep
        total_recomputed += recomputed
        total_variance_abs += abs(variance)

        rows.append(AmortissementRow(
            reference=a.get("reference", "") or "",
            account_number=a.get("account_number", "") or "",
            name=a.get("name", "") or "",
            acquisition_date=a.get("acquisition_date"),
            disposal_date=a.get("disposal_date"),
            gross_value_xaf=a.get("gross_value_xaf") or Decimal("0"),
            accumulated_depreciation_xaf=a.get("accumulated_depreciation_xaf"),
            register_rate_pct=reg_rate,
            register_year_depreciation_xaf=a.get("register_year_depreciation_xaf"),
            fiscal_category_code=cat.code,
            fiscal_category_label_fr=cat.label_fr,
            fiscal_category_label_en=cat.label_en,
            prescribed_rate_pct=cat.rate_pct,
            rate_match=rate_match,
            rate_match_delta_pp=delta,
            recomputed_year_depreciation_xaf=recomputed,
            variance_xaf=variance,
        ))

    summary = {
        "asset_count": len(rows),
        "rate_mismatch_count": rate_mismatches,
        "total_register_year_depreciation_xaf": float(total_register),
        "total_recomputed_year_depreciation_xaf": float(total_recomputed),
        "total_variance_xaf": float(total_register - total_recomputed),
        "total_variance_abs_xaf": float(total_variance_abs),
        "fiscal_year": fiscal_year,
    }
    return rows, summary
