"""Fixed-asset-register reader — ingest-v2 mapping-gate flavour.

Same philosophy as ledger_reader (GL/TB): the auditor CONFIRMS a column
mapping first, then this deterministic reader applies it. No AI at read time —
the AI (fixed_assets_ai) only powers the mapping *proposal* when header hints
fail.

Row rules:
  * blank rows are structure;
  * total / sub-total / récap rows are EXCLUDED with a reason (their stated
    amounts are captured for the modal's « stated totals » card);
  * a row with no description but amounts is EXCLUDED (surfaced, not dropped);
  * everything else is an asset row.

Emitted dicts use the SAME keys controls/amortissements.py already consumes
(reference, account_number, name, dates, gross_value_xaf,
accumulated_depreciation_xaf, register_year_depreciation_xaf, rate_pct), so a
confirmed mapping feeds the existing analysis unchanged.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.parsers.canonical_fields import is_non_data_label, normalize
from app.parsers.fixed_assets_ai import _rate_to_pct
from app.parsers.ledger_reader import (
    ExcludedRow, HeaderInfo, ReadResult, to_date, to_decimal,
)

#: PAIR-style FAR members: pick the closing value first (état « à ce jour »
#: per the auditor), else the plain column, else opening.
_GROSS_PRIORITY = ("closing_gross_value", "gross_value", "opening_gross_value")
_ACCUM_PRIORITY = ("closing_accumulated_depreciation", "accumulated_depreciation",
                   "opening_accumulated_depreciation")
_NBV_PRIORITY = ("closing_nbv", "nbv", "opening_nbv")


def _get(row: list[Any], mapping: dict[str, int], key: str) -> Any:
    i = mapping.get(key)
    if i is None or i >= len(row):
        return None
    v = row[i]
    return None if v in (None, "") else v


def _first(row: list[Any], mapping: dict[str, int], keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = _get(row, mapping, k)
        if v is not None:
            return v
    return None


def read_far(rows: list[list[Any]], mapping: dict[str, int],
             hdr: HeaderInfo) -> ReadResult:
    out: list[dict[str, Any]] = []
    excluded: list[ExcludedRow] = []
    warnings: list[str] = []
    stated: dict[str, Decimal] | None = None

    totals = {
        "gross_value": Decimal("0"),
        "accumulated_depreciation": Decimal("0"),
        "year_depreciation": Decimal("0"),
    }

    data = rows[hdr.header_row + 1:]
    for n, row in enumerate(data, start=hdr.header_row + 2):  # 1-based, humans
        if not any(c not in (None, "") for c in row):
            continue

        name = _get(row, mapping, "name")
        label = str(name or "").strip()

        # Any cell of the row shouting "TOTAL …" makes it a total row.
        row_is_total = is_non_data_label(label) or any(
            normalize(c).startswith(("total", "soustotal", "grandtotal", "recap", "cumulgeneral"))
            for c in row[:6] if c not in (None, "")
        )
        if row_is_total:
            g = to_decimal(_first(row, mapping, _GROSS_PRIORITY))
            a = to_decimal(_first(row, mapping, _ACCUM_PRIORITY))
            d = to_decimal(_get(row, mapping, "year_depreciation"))
            if stated is None and (g or a or d):
                stated = {"gross_value": g, "accumulated_depreciation": a,
                          "year_depreciation": d}
            excluded.append(ExcludedRow(
                n, "Ligne de total / sous-total — jamais comptée comme immobilisation",
                label or "(total)",
                impact={"gross_value": str(g)} if g else {},
            ))
            continue

        if not label:
            g = to_decimal(_first(row, mapping, _GROSS_PRIORITY))
            excluded.append(ExcludedRow(
                n, "Ligne sans désignation — vérifiez si c'est une immobilisation",
                "(sans désignation)",
                impact={"gross_value": str(g)} if g else {},
            ))
            continue

        gross = to_decimal(_first(row, mapping, _GROSS_PRIORITY))
        accum_raw = _first(row, mapping, _ACCUM_PRIORITY)
        accum = to_decimal(accum_raw) if accum_raw is not None else None
        year_dep_raw = _get(row, mapping, "year_depreciation")
        year_dep = to_decimal(year_dep_raw) if year_dep_raw is not None else None
        rate = _rate_to_pct(raw_rate=_get(row, mapping, "rate"))

        acct = _get(row, mapping, "account_number")
        ref = _get(row, mapping, "reference")
        dod = _get(row, mapping, "depreciation_on_disposals")
        nbv_raw = _first(row, mapping, _NBV_PRIORITY)

        out.append({
            "account_number": str(acct).strip() if acct is not None else "",
            "reference": str(ref).strip() if ref is not None else "",
            "name": label,
            "acquisition_date": to_date(_get(row, mapping, "acquisition_date")),
            "disposal_date": to_date(_get(row, mapping, "disposal_date")),
            "gross_value_xaf": gross,
            "accumulated_depreciation_xaf": accum,
            "register_year_depreciation_xaf": year_dep,
            "rate_pct": rate,
            "depreciation_on_disposals_xaf": (
                to_decimal(dod) if dod is not None else None
            ),
            "nbv_xaf": to_decimal(nbv_raw) if nbv_raw is not None else None,
        })
        totals["gross_value"] += gross
        if accum is not None:
            totals["accumulated_depreciation"] += accum
        if year_dep is not None:
            totals["year_depreciation"] += year_dep

    if not out:
        warnings.append("Aucune immobilisation exploitable — vérifiez le mappage des colonnes.")

    return ReadResult("FAR", hdr, mapping, out, excluded, totals, stated, warnings)
