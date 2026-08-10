"""AI-powered Fixed Asset Register parser.

Real-world fixed-asset registers use wildly varying column names:
  - Reference: "Code", "N°", "Réf", "Asset tag", "Immobilisation"…
  - Gross value: "Valeur brute", "Valeur d'origine", "Cost", "Prix HT",
                 "Valeur d'acquisition", "VAB", "VB"…
  - Accumulated depreciation: "Amort. cumulés", "Cumul amort.",
                              "Accumulated dep.", "VNC depuis origine"…
  - Year depreciation: "Dotation exercice", "Dotation N", "Year dep.",
                       "Amortissement de l'exercice"…
  - Rate: "Taux", "Rate", "Durée (ans)", "Useful life"…

Strategy:
  1. Read the file with pandas (raw, no header inference).
  2. Send the first ~30 rows verbatim to Claude with a strict JSON schema asking
     it to identify (a) the header row index and (b) which column index maps to
     each canonical field.
  3. Walk the entire DataFrame using that mapping to produce typed records via
     the existing to_decimal / to_date helpers.

Falls back to the keyword-based parser when no API key or when Claude returns
a bad mapping.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from app.config import get_settings
from app.parsers.common import _normalize, to_date, to_decimal
from app.parsers.fixed_assets import parse_fixed_assets as parse_fixed_assets_keyword


log = logging.getLogger("fiscaudit.parser.far_ai")


# Canonical field set Claude must map to.
_FIELDS = (
    "account_number",
    "reference",
    "name",
    "acquisition_date",
    "disposal_date",
    "gross_value_xaf",
    "accumulated_depreciation_xaf",
    "register_year_depreciation_xaf",
    "rate_pct",
    "useful_life_years",
    "useful_life_months",
)

# How many rows to send to Claude as a preview. Enough to disambiguate.
_PREVIEW_ROWS = 30


_TOTAL_TOKENS = {
    "total", "totaux", "totalgeneral", "totalgénéral", "totalgral",
    "grandtotal", "subtotal", "soustotal", "ssTotal",
    "sumtotal", "sommetotal", "recap", "récap", "recapitulatif",
    "cumul", "totauxsousgroupe", "totalgroupe", "totalcategorie",
    "endingbalance", "closingbalance", "balancefinal",
}


def _is_total_row(row: pd.Series, name_idx: int | None = None) -> bool:
    """Detect any row that's a sub-total / grand-total / récap line.

    Scans the first 6 cells (broader than the name column) because totals can
    sit in a 'Description' or 'Catégorie' cell when the asset-name cell is
    blank. Also catches rows where the asset-name cell is empty but a label
    sits in an adjacent column.
    """
    cells_to_check = []
    # Always include the name column if given
    if name_idx is not None and name_idx < len(row):
        cells_to_check.append(row.iloc[name_idx])
    # Plus the first 6 cells regardless
    for k in range(min(6, len(row))):
        cells_to_check.append(row.iloc[k])

    for v in cells_to_check:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        n = _normalize(v)
        if not n:
            continue
        if n in _TOTAL_TOKENS:
            return True
        # Catch "TOTAL IMMOBILISATIONS", "Total brut 2024", etc.
        if n.startswith("total") or n.startswith("subtotal") or n.startswith("soustotal") \
           or n.startswith("grandtotal") or n.startswith("recap"):
            return True
    return False


SYSTEM_PROMPT = """You are an expert auditor of fixed asset registers
(« registre des immobilisations ») produced by Cameroonian taxpayers under
SYSCOHADA Révisé. Registers come from many ERPs (Sage, Odoo, SAP, Excel) and
have wildly varying column names in French, English, or a mix.

You will receive the first rows of an asset register as a 2-D table. Identify:

  1. `header_row_index` — the 0-based row index where the column headers sit
     (often row 0, sometimes row 1-4 if there are title rows above).
  2. `columns` — a JSON object whose keys are the canonical field names below
     and whose values are the 0-based COLUMN INDEX in that header row, or null
     if absent.

Canonical fields:
  - account_number                  — GL account number of the asset
                                      (« N° de compte », « Compte », « Compte
                                      général », « Account », « GL account »,
                                      « Code compte »). SYSCOHADA class-2
                                      accounts: 21xx-24xx (e.g. 2441, 2451).
                                      NOT the asset tag/reference — a register
                                      may have BOTH; map each to its own field.
  - reference                       — Unique asset code / tag / N° / Réf
  - name                            — Description, libellé, désignation, nature
  - acquisition_date                — Date d'acquisition / mise en service /
                                      purchase date / date d'entrée
  - disposal_date                   — Date de cession / sortie / mise au rebut
                                      (often empty)
  - gross_value_xaf                 — Valeur brute / valeur d'origine / VAB / VB
                                      / cost / prix d'acquisition (NOT including
                                      VAT in most Cameroonian registers)
  - accumulated_depreciation_xaf    — Amortissements cumulés (depuis l'origine
                                      jusqu'à la fin de l'exercice) — sometimes
                                      labelled « Cumul amort. » or
                                      « Accumulated dep. »
  - register_year_depreciation_xaf  — Dotation de l'exercice — depreciation
                                      expense JUST for the current fiscal year
                                      (do NOT confuse with accumulated)
  - rate_pct                        — Taux d'amortissement explicit column
                                      (« Taux », « Taux amort. », « Rate »,
                                      « Depreciation rate », « % amort. »).
                                      Values may be 0-100 (already a %) OR
                                      0-1 (decimal fraction, e.g. 0.20).
  - useful_life_years               — Durée d'utilité EN ANNÉES (« Durée »,
                                      « Vie utile », « Useful life », « Durée
                                      amort. ») — values like 5, 10, 20.
  - useful_life_months              — Durée d'utilité EN MOIS or PÉRIODES
                                      (« Durée en mois », « Périodes »,
                                      « Months », « Periods », « Nb mois »)
                                      — values like 60, 120, 240. NEVER
                                      confuse this with a rate column.
  - useful_life_unit                — One of "YEARS" | "MONTHS" | "PERCENT"
                                      | null. When the register has a single
                                      « Durée » column whose unit is ambiguous,
                                      tell us the unit you inferred from the
                                      magnitude of typical values:
                                        - values 1-50    → YEARS
                                        - values 12-600  → MONTHS
                                        - values 0-100   → PERCENT
                                      If unclear leave null.

RATE/LIFE COLUMN HUNTING — be thorough. Many registers have NO column literally
called « Taux » but DO have a duration column. Look for:
  - Headers containing: « durée », « duree », « vie », « life », « period »,
    « mois », « ans », « years », « taux », « rate », « % »
  - Numeric columns where typical values fall in the ranges above
  - Single-digit columns (3, 5, 10, 20) likely YEARS
  - Two-three digit columns (12, 36, 60, 120, 240) likely MONTHS
  - Decimal columns (0.05, 0.10, 0.20, 0.25) likely a rate fraction
  - Integer 5-50 columns also possibly PERCENT (5, 10, 20, 25 are common)

When BOTH a rate column and a duration column exist, prefer the rate column
(it's the auditee's declared rate). When only the duration exists, populate
useful_life_years or useful_life_months and set useful_life_unit accordingly.

Critical distinctions:
  - GROSS VALUE is the original acquisition cost — never the net book value
    (VNC) or remaining value. If a column is « Valeur nette comptable » or
    « VNC », that is NOT gross value.
  - YEAR DEPRECIATION is only this year's expense; ACCUMULATED is life-to-date.
  - If two columns could match, prefer the most specific one.
  - If the register doesn't separate disposal_date, leave it null.

CRITICAL — TOTAL ROWS:
The register almost always contains one or more sub-total / grand-total
rows (« TOTAL », « Total Immobilisations », « Sous-total », « Récap »,
« Grand Total »). These MUST NOT be counted in any subsequent sum, or the
auditee's gross value will be DOUBLE-counted. You must return the row
indices of every such total row in `total_row_indices`. Be aggressive —
when in doubt, include the row index. False positives are far less harmful
than false negatives. Examples to ALWAYS flag:
  - Row whose label is exactly « TOTAL », « Totaux », « Total général »
  - Row labelled « Sous-total catégorie » / « Récap »
  - Row at the bottom whose amounts equal the sum of the rows above
  - Row with a blank asset-name cell but a populated amount cell

Return STRICT JSON with this exact shape:
{
  "header_row_index": 0,
  "columns": {
    "account_number": null,
    "reference": 0,
    "name": 1,
    "acquisition_date": 2,
    "disposal_date": null,
    "gross_value_xaf": 3,
    "accumulated_depreciation_xaf": 4,
    "register_year_depreciation_xaf": 5,
    "rate_pct": 6,
    "useful_life_years": null,
    "useful_life_months": null
  },
  "useful_life_unit": "YEARS",
  "total_row_indices": [42, 67],
  "rationale": "Explain how you chose each column (esp. the rate/duration column) and identified the totals."
}

No markdown, no extra prose, only the JSON object."""


def _read_raw(data: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), dtype=object, header=None)
    text = data.decode("utf-8-sig", errors="replace")
    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=object, header=None, keep_default_na=False)


def _df_to_preview(df: pd.DataFrame, rows: int) -> str:
    """Serialize the first `rows` rows as a TSV-style table for Claude."""
    sub = df.head(rows)
    lines = []
    # Add column-index header so Claude can refer to columns by number.
    lines.append("COL:\t" + "\t".join(str(i) for i in range(sub.shape[1])))
    for i, row in sub.iterrows():
        cells = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            else:
                cells.append(str(v).replace("\t", " ").replace("\n", " ")[:80])
        lines.append(f"R{i}:\t" + "\t".join(cells))
    return "\n".join(lines)


def _ask_claude(preview: str) -> dict | None:
    settings = get_settings()
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=settings.anthropic_model or "claude-opus-4-7",
            max_tokens=600,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    "Here is the first slice of the fixed-asset register. "
                    "Return the JSON mapping per the schema in the system prompt.\n\n"
                    + preview
                ),
            }],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        # Pull out the first JSON object
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            log.warning("Claude returned no JSON for FAR mapping: %s", text[:200])
            return None
        return json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        log.warning("FAR AI parse failed: %s", e)
        return None


def _rate_to_pct(
    raw_rate: Any = None,
    raw_years: Any = None,
    raw_months: Any = None,
    unit_hint: str | None = None,
) -> Decimal | None:
    """Normalize a depreciation rate to percentage points.

    Priority:
      1. Explicit rate column — 0.20 → 20, 20 → 20, 25 → 25
      2. Useful life in months column — 60 → 5 years → 20 %
      3. Useful life in years column — 5 → 20 %
      4. Single ambiguous column + unit_hint — 'MONTHS' / 'YEARS' / 'PERCENT'

    Values are clamped to (0, 100].
    """
    def _clean_decimal(v: Any) -> Decimal | None:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        d = to_decimal(v)
        return d if d > 0 else None

    # 1) Explicit rate
    r = _clean_decimal(raw_rate)
    if r is not None:
        if r < 1:
            r = r * 100  # 0.20 → 20
        if 0 < r <= 100:
            return r.quantize(Decimal("0.01"))

    # 2) Months → years → %
    m = _clean_decimal(raw_months)
    if m is not None and m >= 1:
        years = m / Decimal("12")
        if years > 0:
            return (Decimal("100") / years).quantize(Decimal("0.01"))

    # 3) Years → %
    y = _clean_decimal(raw_years)
    if y is not None and y > 0:
        # If "years" is actually a month value (e.g. 120), reinterpret.
        if y > 50:
            return (Decimal("100") / (y / Decimal("12"))).quantize(Decimal("0.01"))
        return (Decimal("100") / y).quantize(Decimal("0.01"))

    # 4) Unit hint fallback when only raw_rate slot held a duration-style value
    if unit_hint == "MONTHS" and m is None and r is not None:
        years = r / Decimal("12")
        if years > 0:
            return (Decimal("100") / years).quantize(Decimal("0.01"))
    return None


def _imply_rate_from_dep(
    year_dep: Decimal | None,
    gross: Decimal | None,
    acquisition_date: date | None,
    fiscal_year_end: date,
) -> Decimal | None:
    """Compute implied rate = year_dep / gross × 100, only for assets that have
    been held a FULL fiscal year (so the rate isn't pro-rated and misleading)."""
    if year_dep is None or gross is None or gross <= 0 or year_dep <= 0:
        return None
    if acquisition_date is None:
        return None
    # Must be ≥ 12 months old at fiscal-year end
    months_held = (fiscal_year_end.year - acquisition_date.year) * 12 + \
                  (fiscal_year_end.month - acquisition_date.month)
    if months_held < 12:
        return None
    rate = (year_dep / gross) * Decimal("100")
    # Sanity: ignore weird values
    if rate <= 0 or rate > 100:
        return None
    return rate.quantize(Decimal("0.01"))


def _apply_mapping(
    df: pd.DataFrame,
    header_idx: int,
    cols: dict[str, int | None],
    total_row_indices: set[int] | None = None,
    useful_life_unit: str | None = None,
) -> list[dict[str, Any]]:
    """Walk every data row, skipping total/sub-total rows from BOTH Claude's
    `total_row_indices` list AND our defensive keyword scan."""
    total_set = total_row_indices or set()
    name_idx = cols.get("name")

    def get(row, key):
        idx = cols.get(key)
        if idx is None:
            return None
        try:
            v = row.iloc[idx]
        except (IndexError, KeyError):
            return None
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return v

    out: list[dict[str, Any]] = []
    for i in range(header_idx + 1, len(df)):
        if i in total_set:
            log.debug("Skipping row %d — flagged as total by Claude", i)
            continue
        row = df.iloc[i]
        # Defensive: catch totals Claude missed.
        if _is_total_row(row, name_idx=name_idx):
            log.debug("Skipping row %d — keyword-detected total", i)
            continue

        name = get(row, "name")
        if name is None:
            continue
        n = _normalize(name)
        if not n:
            continue

        ref = get(row, "reference")
        acq = get(row, "acquisition_date")
        disp = get(row, "disposal_date")

        acct = get(row, "account_number")
        out.append({
            "account_number":          str(acct).strip() if acct is not None else "",
            "reference":               str(ref).strip() if ref is not None else "",
            "name":                    str(name).strip(),
            "acquisition_date":        to_date(acq) if acq is not None else None,
            "disposal_date":           to_date(disp) if disp is not None else None,
            "gross_value_xaf":         to_decimal(get(row, "gross_value_xaf")),
            "accumulated_depreciation_xaf": to_decimal(get(row, "accumulated_depreciation_xaf")),
            "register_year_depreciation_xaf": to_decimal(get(row, "register_year_depreciation_xaf")),
            "rate_pct": _rate_to_pct(
                raw_rate=get(row, "rate_pct"),
                raw_years=get(row, "useful_life_years"),
                raw_months=get(row, "useful_life_months"),
                unit_hint=useful_life_unit,
            ),
        })

    # ── Implied-rate fallback for rows where rate is missing ─────────────
    # When Claude couldn't pin down a rate column, but we have year_dep +
    # gross_value + acquisition_date and the asset has been held a full year,
    # compute implied rate = year_dep / gross × 100. This is the auditee's
    # ACTUAL applied rate and is exactly what we need for the « Taux registre »
    # column.
    import datetime as _dt
    fy_end = _dt.date(_dt.date.today().year, 12, 31)
    for r in out:
        if r["rate_pct"] is not None:
            continue
        implied = _imply_rate_from_dep(
            year_dep=r.get("register_year_depreciation_xaf"),
            gross=r.get("gross_value_xaf"),
            acquisition_date=r.get("acquisition_date"),
            fiscal_year_end=fy_end,
        )
        if implied is not None:
            r["rate_pct"] = implied

    # ── Math sanity check ─────────────────────────────────────────────────
    # Even with both keyword + Claude detection, a hidden total row can slip
    # in (e.g. blank label, or label in a column we didn't scan). If the
    # SINGLE largest gross_value is suspiciously close to the sum of the rest,
    # we're likely double-counting. Drop the biggest row in that case.
    if len(out) >= 3:
        sorted_by_gross = sorted(out, key=lambda r: -(r["gross_value_xaf"] or Decimal("0")))
        biggest = sorted_by_gross[0]["gross_value_xaf"] or Decimal("0")
        rest_sum = sum((r["gross_value_xaf"] or Decimal("0")) for r in sorted_by_gross[1:])
        # If biggest >= 90 % of rest_sum AND there are ≥3 rows total, drop it.
        if biggest > 0 and rest_sum > 0 and biggest >= rest_sum * Decimal("0.9") \
                and biggest <= rest_sum * Decimal("1.1"):
            log.warning(
                "Dropping suspected hidden total row '%s' (gross=%s ≈ sum-of-rest=%s)",
                sorted_by_gross[0]["name"], biggest, rest_sum,
            )
            out = [r for r in out if r is not sorted_by_gross[0]]

    return out


def _validate_mapping(mapping: dict, n_cols: int) -> bool:
    """Sanity-check the JSON Claude returned."""
    if not isinstance(mapping, dict):
        return False
    if "header_row_index" not in mapping or "columns" not in mapping:
        return False
    cols = mapping["columns"]
    if not isinstance(cols, dict):
        return False
    # Must at least identify name + gross_value_xaf
    if cols.get("name") is None or cols.get("gross_value_xaf") is None:
        return False
    # All non-null indices must be in range
    for k, v in cols.items():
        if v is None:
            continue
        if not isinstance(v, int) or v < 0 or v >= n_cols:
            return False
    return True


def parse_fixed_assets_ai(data: bytes, filename: str) -> list[dict[str, Any]]:
    """Top-level: try Claude first, fall back to keyword parser."""
    try:
        df = _read_raw(data, filename)
    except Exception as e:
        log.warning("FAR raw read failed: %s — falling back to keyword parser", e)
        return parse_fixed_assets_keyword(data, filename)

    if df.empty:
        return []

    preview = _df_to_preview(df, _PREVIEW_ROWS)
    mapping = _ask_claude(preview)

    if mapping is None or not _validate_mapping(mapping, df.shape[1]):
        log.info("FAR AI mapping unavailable/invalid — using keyword fallback")
        return parse_fixed_assets_keyword(data, filename)

    log.info("FAR AI mapping used: %s", mapping.get("rationale", "(no rationale)"))
    total_indices = set()
    raw_totals = mapping.get("total_row_indices") or []
    if isinstance(raw_totals, list):
        for v in raw_totals:
            if isinstance(v, int) and v >= 0:
                total_indices.add(v)
    return _apply_mapping(
        df,
        int(mapping["header_row_index"]),
        mapping["columns"],
        total_row_indices=total_indices,
        useful_life_unit=mapping.get("useful_life_unit"),
    )
