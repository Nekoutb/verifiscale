"""Bank statement closing-balance extractor.

Tries hard to find the final balance:
  - For Excel/CSV: scans the entire sheet for any "solde" / "balance" /
    "closing" keyword and returns the rightmost monetary value on that row.
    Falls back to the last numeric value in the rightmost amount column.
  - For PDF: uses Claude Vision when ANTHROPIC_API_KEY is set, otherwise
    returns None and lets the UI surface "à renseigner".
"""
from __future__ import annotations

import io
import logging
import os
import re
from decimal import Decimal
from typing import Any

import pandas as pd

from app.parsers.common import _normalize, to_decimal


log = logging.getLogger("fiscaudit.parser.bank")


# Keywords that mark a row as the closing-balance row
_CLOSING_KEYWORDS = (
    "soldecloture", "soldefinal", "soldenouveau", "soldefin",
    "soldeau", "newbalance", "closingbalance", "endingbalance",
    "soldecrediteur", "soldedebiteur",
    "solde",  # last-resort generic — only the *latest* match is kept
)


def _read_excel_or_csv(data: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), dtype=object, header=None)
    text = data.decode("utf-8-sig", errors="replace")
    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=object, header=None, keep_default_na=False)


def _largest_amount_in_row(row: pd.Series) -> Decimal | None:
    """Return the largest |value| in the row that looks like an amount."""
    best: Decimal | None = None
    for v in row:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        d = to_decimal(v)
        if d == 0:
            continue
        if best is None or abs(d) > abs(best):
            best = d
    return best


def _rightmost_amount_in_row(row: pd.Series) -> Decimal | None:
    """Last non-zero parseable monetary cell in the row (left→right)."""
    last: Decimal | None = None
    for v in row:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        # Skip dates and obviously non-monetary tokens
        if re.search(r"[A-Za-zÀ-ÿ]", s) and not re.search(r"\d", s):
            continue
        d = to_decimal(v)
        if d != 0:
            last = d
    return last


def parse_bank_statement_closing(data: bytes, filename: str) -> Decimal | None:
    """Return the statement's closing balance as Decimal, or None if unreadable."""
    name = filename.lower()

    # PDF — try Claude Vision when available
    if name.endswith(".pdf"):
        return _parse_pdf_closing(data)

    try:
        df = _read_excel_or_csv(data, filename)
    except Exception as e:
        log.warning("Bank statement read failed: %s", e)
        return None
    if df.empty:
        return None

    # 1) Scan for a row with a "solde de clôture" keyword
    last_closing: Decimal | None = None
    for i in range(len(df)):
        row = df.iloc[i]
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            n = _normalize(v)
            if not n:
                continue
            if any(kw in n for kw in _CLOSING_KEYWORDS):
                amt = _rightmost_amount_in_row(row) or _largest_amount_in_row(row)
                if amt is not None and amt != 0:
                    last_closing = amt
                break  # don't re-scan same row

    if last_closing is not None:
        return last_closing

    # 2) Fallback: last non-zero value in the rightmost numeric column.
    # Find the column with the most parseable numbers.
    col_scores: dict[int, int] = {}
    for ci in range(df.shape[1]):
        cnt = 0
        for v in df.iloc[:, ci]:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            d = to_decimal(v)
            if d != 0:
                cnt += 1
        col_scores[ci] = cnt
    if not col_scores:
        return None
    best_col = max(col_scores, key=col_scores.get)
    if col_scores[best_col] < 3:
        return None
    # Walk bottom-up for the last non-zero value
    for i in range(len(df) - 1, -1, -1):
        v = df.iat[i, best_col]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        d = to_decimal(v)
        if d != 0:
            return d
    return None


def _parse_pdf_closing(pdf_bytes: bytes) -> Decimal | None:
    """Claude Vision path — returns None if no API key configured."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import base64, json
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7"),
            max_tokens=200,
            system=(
                "Extract the CLOSING balance from this bank statement. "
                "Return strict JSON: {\"closing_balance_xaf\": <number>} "
                "or {\"closing_balance_xaf\": null} if not found. "
                "Use the final balance, not the previous-period balance. "
                "Negative = debit/overdraft."
            ),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": "Extract the closing balance."},
                ],
            }],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        # Find the first JSON object in the response
        match = re.search(r"\{[^{}]*closing_balance_xaf[^{}]*\}", text)
        if not match:
            return None
        obj = json.loads(match.group(0))
        v = obj.get("closing_balance_xaf")
        return Decimal(str(v)) if v is not None else None
    except Exception as e:  # noqa: BLE001
        log.warning("Bank PDF Vision parse failed: %s", e)
        return None
