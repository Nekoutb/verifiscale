"""Sub-ledger / aging total extractor.

Used by the reconciliations endpoint to auto-total a supplier (AP), customer (AR),
or inventory listing file — no manual entry by the auditor.

We don't model the file row-by-row; we just need ONE number: the sum of the
counterparty balances.

Strategy:
1. Read the file raw (no header inference).
2. Scan the first 15 rows for the header row — the one that contains "Total"
   (or "Solde" / "Balance" / "Montant" / "Encours") in its cells.
3. The "Total" column is the rightmost monetary column.
4. Sum that column for every data row, dropping any row whose first cell
   contains "Total" / "Aged Payable" / "Aged Receivable" / etc. (those are
   subtotals or grand totals the file already provides).
"""
from __future__ import annotations

import io
from decimal import Decimal

import pandas as pd

from app.parsers.common import to_decimal, _normalize


# Column-header tokens that identify the rightmost "balance" column.
_TOTAL_TOKENS = (
    "total", "totalgeneral", "totalgénéral",
    "solde", "soldenet", "soldeclient", "soldefournisseur",
    "balance", "netbalance",
    "encours", "outstanding",
    "montant", "amount", "value",
    "endingbalance", "closingbalance",
    "stockvalue", "valeurstock",
)

# Tokens that mark a row as a subtotal / aggregate that we MUST skip to avoid
# double counting. Matched against the first few cells, normalized.
_SUBTOTAL_TOKENS = (
    "total", "totalgeneral", "totalgénéral", "grandtotal",
    "agedpayable", "agedreceivable", "balanceage", "balanceagee",
    "subtotal", "soustotal", "summary",
)


def _read_raw(data: bytes, filename: str) -> pd.DataFrame:
    """Read the file without inferring headers."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), dtype=object, header=None)
    text = data.decode("utf-8-sig", errors="replace")
    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=object, header=None, keep_default_na=False)


def _find_header_row_and_total_col(df: pd.DataFrame) -> tuple[int, int] | None:
    """Locate (header_row_idx, total_col_idx) by scanning the top of the sheet."""
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        # Find any cell in this row that normalizes to one of the total tokens.
        for j, val in enumerate(row):
            if pd.isna(val):
                continue
            n = _normalize(val)
            if n in _TOTAL_TOKENS:
                # Be greedy — prefer the rightmost match in the same row in
                # case the file has both an "Amount" and a "Total" column.
                best_j = j
                for k in range(j + 1, len(row)):
                    v2 = row.iloc[k]
                    if pd.isna(v2):
                        continue
                    if _normalize(v2) in _TOTAL_TOKENS:
                        best_j = k
                return i, best_j
    return None


def _is_subtotal_cell(val) -> bool:
    if pd.isna(val):
        return False
    n = _normalize(val)
    if not n:
        return False
    # Match exact subtotal tokens OR cells that start with "total"
    if n in _SUBTOTAL_TOKENS:
        return True
    if n.startswith("total") or n.startswith("subtotal") or n.startswith("soustotal"):
        return True
    return False


def sum_aging_total(data: bytes, filename: str) -> Decimal | None:
    """Return Σ of the balance column, or None if no usable column found."""
    try:
        df = _read_raw(data, filename)
    except Exception:
        return None
    if df.empty:
        return None

    located = _find_header_row_and_total_col(df)
    if located is None:
        return None
    header_idx, total_col = located

    total = Decimal("0")
    for i in range(header_idx + 1, len(df)):
        row = df.iloc[i]
        # Skip subtotal / grand-total rows (first 2 cells worth of label).
        if any(_is_subtotal_cell(row.iloc[k]) for k in range(min(2, len(row)))):
            continue
        val = row.iloc[total_col]
        total += to_decimal(val)
    return total


# ── Inventory total ──────────────────────────────────────────────────────────
# An inventory listing usually doesn't ship with a "Total value" column —
# the auditor gets a flat product list with unit cost and quantity-on-hand.
# We compute Σ(unit_cost × quantity) to derive the stock value.

_COST_CANDIDATES = (
    "cost", "unitcost", "coutunitaire", "prixachat", "prixderevient",
    "prixunitaire", "puhd", "pumht", "valeurunitaire", "unitvalue",
)
_QTY_CANDIDATES = (
    "quantityonhand", "qtyonhand", "qty", "quantite", "quantité",
    "stockonhand", "qteenstock", "quantitestock", "qteinventaire",
    "qte", "qteactuelle",
)
_VALUE_CANDIDATES = (
    "stockvalue", "inventoryvalue", "valeurstock", "valeurinventaire",
    "totalvalue", "valeurtotal", "montantstock", "stockamount",
)


def _col_idx_by_keywords(df: pd.DataFrame, header_idx: int, keywords: tuple[str, ...]) -> int | None:
    """Find a column whose header (row `header_idx`) normalizes to any keyword."""
    row = df.iloc[header_idx]
    for j, val in enumerate(row):
        if pd.isna(val):
            continue
        n = _normalize(val)
        if n in keywords:
            return j
    # Fallback: substring match
    for j, val in enumerate(row):
        if pd.isna(val):
            continue
        n = _normalize(val)
        for kw in keywords:
            if kw in n:
                return j
    return None


def _detect_header_idx(df: pd.DataFrame) -> int | None:
    """Find any plausible header row by scanning for known column-name keywords."""
    all_keys = _COST_CANDIDATES + _QTY_CANDIDATES + _VALUE_CANDIDATES + _TOTAL_TOKENS + (
        "name", "designation", "désignation", "produit", "article", "reference",
    )
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        score = 0
        for val in row:
            if pd.isna(val):
                continue
            n = _normalize(val)
            for kw in all_keys:
                if n == kw or kw in n:
                    score += 1
                    break
        if score >= 3:
            return i
    return None


def sum_inventory_value(data: bytes, filename: str) -> Decimal | None:
    """Total stock value: prefer an explicit Value column, otherwise Σ(cost × qty)."""
    # First try the generic balance-column path — handles files that already
    # have a "Total" / "Stock Value" column.
    direct = sum_aging_total(data, filename)
    if direct is not None and direct != 0:
        return direct

    try:
        df = _read_raw(data, filename)
    except Exception:
        return None
    if df.empty:
        return None

    header_idx = _detect_header_idx(df)
    if header_idx is None:
        return None

    value_col = _col_idx_by_keywords(df, header_idx, _VALUE_CANDIDATES)
    cost_col = _col_idx_by_keywords(df, header_idx, _COST_CANDIDATES)
    qty_col = _col_idx_by_keywords(df, header_idx, _QTY_CANDIDATES)

    total = Decimal("0")
    for i in range(header_idx + 1, len(df)):
        row = df.iloc[i]
        if any(_is_subtotal_cell(row.iloc[k]) for k in range(min(2, len(row)))):
            continue
        if value_col is not None:
            v = to_decimal(row.iloc[value_col])
            if v:
                total += v
                continue
        if cost_col is not None and qty_col is not None:
            cost = to_decimal(row.iloc[cost_col])
            qty = to_decimal(row.iloc[qty_col])
            total += cost * qty
    return total if total != 0 else None
