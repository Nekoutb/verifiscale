"""Shared parsing utilities: column matching, type coercion, header detection."""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

import pandas as pd


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _normalize(s: str) -> str:
    """Lowercase, strip accents and non-alphanumeric chars — for fuzzy column matching."""
    s = _strip_accents(str(s)).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    """Return the first column in `df` matching any of the normalized candidates.

    Strategy: exact match takes priority over substring match for ALL candidates.
    This prevents a generic candidate like "account" from substring-matching
    "Account Name" when a more specific candidate like "code" would exact-match "Code".
    """
    cands = list(candidates)
    norm_map = {_normalize(c): c for c in df.columns}

    # Pass 1: exact matches in candidate order
    for cand in cands:
        n = _normalize(cand)
        if n in norm_map:
            return norm_map[n]

    # Pass 2: substring matches in candidate order
    for cand in cands:
        n = _normalize(cand)
        for k, v in norm_map.items():
            if n in k:
                return v
    return None


def find_all_columns(df: pd.DataFrame, candidates: Iterable[str]) -> list[str]:
    """Return ALL columns matching any candidate (in df order, no duplicates)."""
    norm_targets = [_normalize(c) for c in candidates]
    out: list[str] = []
    seen: set[str] = set()
    for col in df.columns:
        n = _normalize(col)
        for t in norm_targets:
            if n == t or t in n:
                if col not in seen:
                    out.append(col)
                    seen.add(col)
                break
    return out


def to_decimal(value) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        # Remove French thousand separators and currency symbols
        s = str(value).strip().replace(" ", "").replace(" ", "")
        s = s.replace("FCFA", "").replace("XAF", "").strip()
        # Parentheses = negative (accounting notation)
        is_neg = False
        if s.startswith("(") and s.endswith(")"):
            is_neg = True
            s = s[1:-1]
        # If a comma is present and no dot, treat comma as decimal separator
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
        if s in ("", "-", "."):
            return Decimal("0")
        result = Decimal(s)
        return -result if is_neg else result
    except (InvalidOperation, ValueError):
        return Decimal("0")


def to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in ("nan", "nat"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


# Header keywords we look for when auto-detecting the header row
_HEADER_KEYWORDS = {
    "code", "compte", "account", "libelle", "libellé", "name",
    "balance", "solde", "debit", "débit", "credit", "crédit",
    "ouverture", "opening", "cloture", "clôture", "closing",
    "date", "piece", "pièce", "journal",
}


def _row_header_score(row: pd.Series) -> int:
    """Count how many cells in this row look like header keywords."""
    score = 0
    for val in row:
        if pd.isna(val):
            continue
        s = _normalize(val)
        for kw in _HEADER_KEYWORDS:
            if _normalize(kw) in s:
                score += 1
                break
    return score


def _detect_header_row(df: pd.DataFrame, max_scan: int = 10) -> int | None:
    """Look at the first `max_scan` rows; return the index of the best header row, or None."""
    best_idx, best_score = None, 0
    for i in range(min(max_scan, len(df))):
        score = _row_header_score(df.iloc[i])
        if score >= 3 and score > best_score:
            best_idx, best_score = i, score
    return best_idx


def read_tabular(data: bytes, filename: str) -> pd.DataFrame:
    """Parse Excel/CSV bytes into a DataFrame, with smart header detection.

    Handles common real-world quirks:
    - Multi-row headers (e.g. merged title row above the actual column names)
    - Excessive Unnamed: N columns (means we picked the wrong header row)
    - FR/EN CSV delimiters (`;` vs `,`)
    """
    name = filename.lower()

    if name.endswith((".xlsx", ".xls", ".xlsm")):
        # First read: default (header=0). If most columns are Unnamed, the real
        # headers are deeper in the file — find the right row and re-read.
        df = pd.read_excel(io.BytesIO(data), dtype=object)
        unnamed_ratio = sum(1 for c in df.columns if str(c).startswith("Unnamed")) / max(1, len(df.columns))

        if unnamed_ratio > 0.4:
            # Re-read with no header, scan rows to find the real one
            raw = pd.read_excel(io.BytesIO(data), dtype=object, header=None)
            hdr_idx = _detect_header_row(raw)
            if hdr_idx is not None:
                df = pd.read_excel(io.BytesIO(data), dtype=object, header=hdr_idx)

        # De-duplicate column names (Excel often has multiple "Balance" columns)
        df.columns = _dedupe_columns(list(df.columns))
        return df.dropna(how="all")

    # --- CSV ---
    text = data.decode("utf-8-sig", errors="replace")
    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=object, keep_default_na=False)
    df.columns = _dedupe_columns(list(df.columns))
    return df.dropna(how="all")


def _dedupe_columns(cols: list) -> list[str]:
    """Make duplicate column names unique by suffixing _2, _3, etc.

    Also strips leading/trailing whitespace.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in cols:
        s = str(c).strip() if c is not None else ""
        if s in seen:
            seen[s] += 1
            out.append(f"{s}_{seen[s]}")
        else:
            seen[s] = 1
            out.append(s)
    return out
