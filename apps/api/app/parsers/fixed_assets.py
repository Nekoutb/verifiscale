"""Fixed-asset register parser.

Extracts one row per asset from an Excel/CSV fixed-asset register. The format
varies widely across taxpayers — we sniff the header row, then map by keyword
match (FR + EN).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from app.parsers.common import (
    find_column, read_tabular, to_date, to_decimal, _normalize,
)


# Header keyword candidates, ordered most→least specific so find_column's
# exact-then-substring strategy picks the right one when a register has
# multiple monetary columns.
_REFERENCE = ("reference", "ref", "codeasset", "code", "numero", "no",
              "assetid", "assetcode", "tag", "immobilisation")
_NAME = ("designation", "désignation", "libelle", "libellé", "name",
         "description", "nature", "denomination", "intitule")
_ACQ_DATE = ("dateacquisition", "dateacq", "datemise", "datemiseenservice",
             "acquisitiondate", "purchasedate", "datemes", "dateentree",
             "dateachat", "date")
_DISP_DATE = ("datecession", "datesortie", "datemiserebut", "disposaldate",
              "datedecession", "datedisposition", "datesale")
_GROSS_VAL = ("valeurbrute", "coutacquisition", "coût", "cout", "vbrute",
              "valeurorigine", "valeurdorigine", "prixacquisition",
              "grossvalue", "originalcost", "cost", "valeur", "montant")
_RATE = ("tauxamortissement", "tauxamort", "tauxamortissmt", "taux",
         "depreciationrate", "ratepc", "rateamortissement")
_LIFE_YEARS = ("dureeutile", "dureeutilite", "duréeutile", "dureeamortissement",
               "usefullife", "lifeyears", "années", "annees", "duration")
_YEAR_DEP = ("dotationexercice", "dotationannuelle", "amortissementexercice",
             "dotationdelexercice", "depreciationyear", "yearlydepreciation",
             "amortissementdelexercice", "amortismtexercice", "dotation")
_ACCUM_DEP = ("amortissementcumule", "cumulamortissement", "amortismtcumule",
              "accumulateddepreciation", "totalamortissement")


def _to_date_safe(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return to_date(v)


def _rate_to_pct(raw_rate: Any, raw_years: Any) -> Decimal | None:
    """Return depreciation rate as a Decimal percent (e.g. 20 for 20 %).

    Strategy:
      1. If a rate column has a value: parse it. If it's < 1, treat it as a
         decimal fraction (0.20 → 20). Otherwise it's already a %.
      2. Else if years column has a value: 100 / years.
    """
    if raw_rate is not None and not (isinstance(raw_rate, float) and pd.isna(raw_rate)):
        d = to_decimal(raw_rate)
        if d > 0:
            if d < 1:
                return d * 100  # 0.20 → 20
            return d  # already a percent
    if raw_years is not None and not (isinstance(raw_years, float) and pd.isna(raw_years)):
        years = to_decimal(raw_years)
        if years > 0:
            return (Decimal("100") / years).quantize(Decimal("0.01"))
    return None


def parse_fixed_assets(data: bytes, filename: str) -> list[dict[str, Any]]:
    """Return one dict per asset row.

    Each dict carries: reference, name, acquisition_date, disposal_date,
    gross_value_xaf, rate_pct (Decimal or None), register_year_depreciation_xaf
    (Decimal or None), accumulated_depreciation_xaf, raw (the original row).
    """
    df = read_tabular(data, filename)
    if df.empty:
        return []

    cols = {
        "ref":      find_column(df, _REFERENCE),
        "name":     find_column(df, _NAME),
        "acq":      find_column(df, _ACQ_DATE),
        "disp":     find_column(df, _DISP_DATE),
        "gross":    find_column(df, _GROSS_VAL),
        "rate":     find_column(df, _RATE),
        "years":    find_column(df, _LIFE_YEARS),
        "year_dep": find_column(df, _YEAR_DEP),
        "accum":    find_column(df, _ACCUM_DEP),
    }

    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        name = row.get(cols["name"]) if cols["name"] else None
        if name is None or (isinstance(name, float) and pd.isna(name)):
            continue
        # skip pseudo-rows like 'TOTAL'
        n = _normalize(name)
        if not n or n.startswith("total") or n in ("designation", "name"):
            continue

        out.append({
            "reference":               str(row.get(cols["ref"], "")).strip() if cols["ref"] else "",
            "name":                    str(name).strip(),
            "acquisition_date":        _to_date_safe(row.get(cols["acq"])) if cols["acq"] else None,
            "disposal_date":           _to_date_safe(row.get(cols["disp"])) if cols["disp"] else None,
            "gross_value_xaf":         to_decimal(row.get(cols["gross"])) if cols["gross"] else Decimal("0"),
            "rate_pct":                _rate_to_pct(
                                          row.get(cols["rate"]) if cols["rate"] else None,
                                          row.get(cols["years"]) if cols["years"] else None,
                                       ),
            "register_year_depreciation_xaf": to_decimal(row.get(cols["year_dep"])) if cols["year_dep"] else None,
            "accumulated_depreciation_xaf":   to_decimal(row.get(cols["accum"])) if cols["accum"] else None,
        })
    return out
