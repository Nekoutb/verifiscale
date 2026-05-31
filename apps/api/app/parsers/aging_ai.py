"""AI-powered total extractor for AP / AR aging and Inventory listings.

The same Claude column-inference pattern as `fixed_assets_ai.py`, but tuned to
return ONE number: the total of the balance column (for AP/AR) or the total
stock value (for Inventory, either a Value column or Cost × Qty).

For Excel/CSV with strange column names — "Outstanding", "Encours net",
"Solde fournisseur", "Net Amount", "Stock Value", "Valeur totale", etc. —
Claude identifies the right column, the system sums it, skipping subtotal /
grand-total footer rows.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from decimal import Decimal
from typing import Literal

import pandas as pd

from app.config import get_settings
from app.parsers.aging import sum_aging_total, sum_inventory_value
from app.parsers.common import _normalize, to_decimal


log = logging.getLogger("fiscaudit.parser.aging_ai")

_PREVIEW_ROWS = 25


SYSTEM_PROMPT_AP_AR = """You are an expert auditor at the Cameroon DGI.
You are given the first rows of a {kind} sub-ledger / aging file produced by
ANY accounting system (Sage, Odoo, SAP, Excel template). Column names vary
widely in French and English.

Identify the column that holds the COUNTERPARTY OUTSTANDING BALANCE — the
total amount owed by the customer (AR) or to the supplier (AP) at the
reporting date. Examples of valid balance columns:
  - Solde, Encours, Outstanding, Net amount, Net balance, Solde net,
    Solde fournisseur, Solde client, Balance, Montant restant dû, Total dû,
    Total general (when it sums the aging buckets)

REJECT aging-bucket columns (0-30j, 31-60j, 61-90j, > 90j, current, past due)
unless the file ONLY has buckets and no consolidated total — in that case
pick the rightmost numeric bucket column called "Total" or last aging bucket.

CRITICAL — TOTAL ROWS:
Aging files almost always contain « TOTAL » / « Sous-total » / « Total
général » rows that would DOUBLE-COUNT the balances if summed. You MUST
return the row indices of every such row in `total_row_indices`. Be
aggressive — false positives are far better than false negatives. Examples
to flag: row with first cell « TOTAL », « Totaux », « Total fournisseurs »,
« Sous-total », « Grand total », « Aged Payable », « Aged Receivable », any
bottom row whose balance equals the sum of the rows above, or any row with
a blank counterparty-name cell but a populated balance cell.

Return STRICT JSON:
{{
  "header_row_index": <int>,
  "balance_column_index": <int>,
  "total_row_indices": [<int>, ...],
  "rationale": "Short reason"
}}

No markdown, no extra prose."""


SYSTEM_PROMPT_INVENTORY = """You are an expert auditor of inventory listings.
You receive the first rows of a stock register from ANY ERP. Column names vary.

Identify either:
  A. A direct "stock value" column — Valeur stock, Stock value, Inventory
     value, Valeur totale, Total HT, Montant — that already holds the
     value per SKU; or
  B. A pair of cost-and-quantity columns — Cost / Coût / Prix unitaire / Unit
     cost + Quantity / Qte / Quantite / Quantity on hand — that must be
     multiplied per row to derive the value.

CRITICAL — TOTAL ROWS: same as for AP/AR. Identify every total / sub-total
/ grand-total row in `total_row_indices` so they're excluded from the sum.

Return STRICT JSON with EXACTLY one of these shapes:
{
  "header_row_index": <int>,
  "value_column_index": <int>,
  "total_row_indices": [<int>, ...],
  "rationale": "..."
}
OR
{
  "header_row_index": <int>,
  "cost_column_index": <int>,
  "qty_column_index": <int>,
  "total_row_indices": [<int>, ...],
  "rationale": "..."
}

No markdown, no extra prose."""


_SUBTOTAL_TOKENS = (
    "total", "totalgeneral", "totalgénéral", "totaux", "totalgral",
    "grandtotal", "subtotal", "soustotal", "summary", "recap", "récap",
    "agedpayable", "agedreceivable", "balanceage", "balanceagee",
    "cumul", "totauxsousgroupe", "totalgroupe",
)


def _read_raw(data: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), dtype=object, header=None)
    text = data.decode("utf-8-sig", errors="replace")
    sep = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=object, header=None, keep_default_na=False)


def _preview(df: pd.DataFrame, rows: int) -> str:
    sub = df.head(rows)
    lines = ["COL:\t" + "\t".join(str(i) for i in range(sub.shape[1]))]
    for i, row in sub.iterrows():
        cells = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            else:
                cells.append(str(v).replace("\t", " ").replace("\n", " ")[:60])
        lines.append(f"R{i}:\t" + "\t".join(cells))
    return "\n".join(lines)


def _ask_claude(system: str, preview: str) -> dict | None:
    settings = get_settings()
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=settings.anthropic_model or "claude-opus-4-7",
            max_tokens=400,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": "Here is the preview. Return the JSON per the schema.\n\n" + preview,
            }],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            log.warning("Claude returned no JSON for aging: %s", text[:200])
            return None
        return json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        log.warning("Aging AI parse failed: %s", e)
        return None


def _is_subtotal_row(row: pd.Series) -> bool:
    """Scan the first 6 cells (not just 3) so labels like 'Total fournisseurs'
    in column 2 are caught even when the counterparty-name column is blank."""
    for k in range(min(6, len(row))):
        v = row.iloc[k]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        n = _normalize(v)
        if not n:
            continue
        if n in _SUBTOTAL_TOKENS:
            return True
        if n.startswith(("total", "subtotal", "soustotal", "grandtotal", "recap")):
            return True
    return False


def _post_sum_sanity(values: list[Decimal]) -> Decimal:
    """If the single largest value ≈ sum of the rest, drop it (likely a
    hidden total row our other checks missed)."""
    if len(values) < 3:
        return sum(values, Decimal("0"))
    values_sorted = sorted(values, key=lambda v: -v)
    biggest = values_sorted[0]
    rest = sum(values_sorted[1:], Decimal("0"))
    if biggest > 0 and rest > 0 and biggest >= rest * Decimal("0.9") \
            and biggest <= rest * Decimal("1.1"):
        log.warning("Aging — dropping suspected hidden total row (%s ≈ rest %s)", biggest, rest)
        return rest
    return biggest + rest


def _sum_column(df: pd.DataFrame, header_idx: int, col_idx: int, total_set: set[int] | None = None) -> Decimal:
    total_set = total_set or set()
    vals: list[Decimal] = []
    for i in range(header_idx + 1, len(df)):
        if i in total_set:
            continue
        row = df.iloc[i]
        if _is_subtotal_row(row):
            continue
        try:
            v = row.iloc[col_idx]
        except (IndexError, KeyError):
            continue
        d = to_decimal(v)
        if d != 0:
            vals.append(d)
    return _post_sum_sanity(vals)


def _sum_cost_x_qty(df: pd.DataFrame, header_idx: int, cost_idx: int, qty_idx: int, total_set: set[int] | None = None) -> Decimal:
    total_set = total_set or set()
    vals: list[Decimal] = []
    for i in range(header_idx + 1, len(df)):
        if i in total_set:
            continue
        row = df.iloc[i]
        if _is_subtotal_row(row):
            continue
        try:
            c = to_decimal(row.iloc[cost_idx])
            q = to_decimal(row.iloc[qty_idx])
        except (IndexError, KeyError):
            continue
        v = c * q
        if v != 0:
            vals.append(v)
    return _post_sum_sanity(vals)


def _parse_total_indices(mapping: dict) -> set[int]:
    raw = mapping.get("total_row_indices") or []
    out: set[int] = set()
    if isinstance(raw, list):
        for v in raw:
            if isinstance(v, int) and v >= 0:
                out.add(v)
    return out


def sum_aging_total_ai(
    data: bytes,
    filename: str,
    kind: Literal["AP", "AR"] = "AP",
) -> Decimal | None:
    """AI-first AP/AR total. Falls back to the keyword parser on any miss."""
    try:
        df = _read_raw(data, filename)
    except Exception as e:
        log.warning("Aging read failed: %s — falling back", e)
        return sum_aging_total(data, filename)
    if df.empty:
        return None

    mapping = _ask_claude(
        SYSTEM_PROMPT_AP_AR.format(kind="supplier (AP)" if kind == "AP" else "customer (AR)"),
        _preview(df, _PREVIEW_ROWS),
    )
    if (mapping
        and isinstance(mapping.get("header_row_index"), int)
        and isinstance(mapping.get("balance_column_index"), int)
        and 0 <= mapping["balance_column_index"] < df.shape[1]):
        log.info("Aging %s AI mapping: %s", kind, mapping.get("rationale", ""))
        return _sum_column(
            df,
            mapping["header_row_index"],
            mapping["balance_column_index"],
            total_set=_parse_total_indices(mapping),
        )

    log.info("Aging %s — AI unavailable, using keyword parser", kind)
    return sum_aging_total(data, filename)


def sum_inventory_value_ai(data: bytes, filename: str) -> Decimal | None:
    """AI-first inventory total. Falls back to keyword/cost×qty parser."""
    try:
        df = _read_raw(data, filename)
    except Exception as e:
        log.warning("Inventory read failed: %s — falling back", e)
        return sum_inventory_value(data, filename)
    if df.empty:
        return None

    mapping = _ask_claude(SYSTEM_PROMPT_INVENTORY, _preview(df, _PREVIEW_ROWS))
    if mapping and isinstance(mapping.get("header_row_index"), int):
        hdr = mapping["header_row_index"]
        total_set = _parse_total_indices(mapping)
        if isinstance(mapping.get("value_column_index"), int):
            log.info("Inventory AI mapping (value col): %s", mapping.get("rationale", ""))
            return _sum_column(df, hdr, mapping["value_column_index"], total_set=total_set)
        if (isinstance(mapping.get("cost_column_index"), int)
            and isinstance(mapping.get("qty_column_index"), int)):
            log.info("Inventory AI mapping (cost×qty): %s", mapping.get("rationale", ""))
            return _sum_cost_x_qty(df, hdr, mapping["cost_column_index"], mapping["qty_column_index"], total_set=total_set)

    log.info("Inventory — AI unavailable, using keyword parser")
    return sum_inventory_value(data, filename)
