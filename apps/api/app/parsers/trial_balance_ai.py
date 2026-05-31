"""AI-powered Trial Balance parser.

The trial balance comes in many layouts: 6 columns (opening D/C, period D/C,
closing D/C), 8 columns (with previous-year totals), Odoo aggregated views,
custom Excel templates. This module uses Claude to identify the 7 canonical
fields and walks the file row by row to produce the same shape as the keyword
parser in ``trial_balance.py``.

Falls back to the keyword parser when no API key is set.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from decimal import Decimal
from typing import Any

import pandas as pd

from app.config import get_settings
from app.parsers.common import _normalize, to_decimal
from app.parsers.general_ledger import _split_code_and_name
from app.parsers.trial_balance import parse as parse_keyword


log = logging.getLogger("fiscaudit.parser.tb_ai")

_PREVIEW_ROWS = 30


SYSTEM_PROMPT = """You are an expert auditor at the Cameroon DGI ingesting a
TRIAL BALANCE («Balance générale» 6 colonnes) from ANY accounting system. The
canonical SYSCOHADA layout has 7 fields per row:

  - account_code         Account number (e.g. 411100, 571141)
  - account_name         Account description / libellé
  - opening_debit        Opening balance — debit side
  - opening_credit       Opening balance — credit side
  - period_debit         Period movements — debit side
  - period_credit        Period movements — credit side
  - closing_debit        Closing balance — debit side
  - closing_credit       Closing balance — credit side

Column header names vary widely. Examples per ERP / language:
  - "Compte" / "Account" / "Code Compte" / "CompteNum"          → account_code
  - "Libellé" / "Designation" / "Intitulé" / "Name"             → account_name
  - "Solde Ouverture Débit" / "Opening D" / "SD Init" / "Initial Debit"
                                                                → opening_debit
  - "Solde Ouverture Crédit" / "Opening C" / "SC Init"          → opening_credit
  - "Débit période" / "Mvt D" / "Period D" / "Total Débits"     → period_debit
  - "Crédit période" / "Mvt C" / "Period C" / "Total Crédits"   → period_credit
  - "Solde Clôture D" / "Closing D" / "SD Final" / "Solde D"    → closing_debit
  - "Solde Clôture C" / "Closing C" / "SC Final" / "Solde C"    → closing_credit

Identify the 0-based COLUMN INDEX for each field. The account_code and
account_name fields are MANDATORY. The opening/period/closing D-C pairs are
each mandatory as a PAIR — if you can find the closing pair but not the
opening pair, that's still acceptable (some ERPs export only closing
balances; the system handles that gracefully).

CRITICAL — TOTAL ROWS:
The TB almost always has TOTAL / SOUS-TOTAL rows at the bottom (and sometimes
mid-file per class). Return their row indices in `total_row_indices` so we
skip them when summing.

Return STRICT JSON with this shape (no markdown, no prose):

{
  "header_row_index": 0,
  "columns": {
    "account_code":    0,
    "account_name":    1,
    "opening_debit":   2,
    "opening_credit":  3,
    "period_debit":    4,
    "period_credit":   5,
    "closing_debit":   6,
    "closing_credit":  7
  },
  "total_row_indices": [123, 124],
  "rationale": "Short reason — esp. how you distinguished opening / movement / closing pairs."
}"""


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
                cells.append(str(v).replace("\t", " ").replace("\n", " ")[:70])
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
            model=settings.anthropic_model or "claude-sonnet-4-5",
            max_tokens=700,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": "Here is the trial balance preview. Return the JSON mapping per the schema.\n\n" + preview,
            }],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            log.warning("TB AI: no JSON in Claude response: %s", text[:200])
            return None
        return json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        log.warning("TB AI parse failed: %s", e)
        return None


def _validate_mapping(mapping: dict, n_cols: int) -> bool:
    if not isinstance(mapping, dict) or not isinstance(mapping.get("columns"), dict):
        return False
    cols = mapping["columns"]
    if cols.get("account_code") is None or cols.get("account_name") is None:
        return False
    if cols.get("closing_debit") is None or cols.get("closing_credit") is None:
        return False
    for k, v in cols.items():
        if v is None:
            continue
        if not isinstance(v, int) or v < 0 or v >= n_cols:
            return False
    return True


def _is_total_row(row: pd.Series) -> bool:
    for k in range(min(4, len(row))):
        v = row.iloc[k]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        n = _normalize(v)
        if not n:
            continue
        if n.startswith(("total", "sousstotal", "grandtotal", "soustotal", "recap")):
            return True
    return False


def parse(data: bytes, filename: str) -> tuple[list[dict[str, Any]], dict]:
    df = _read_raw(data, filename)
    if df.empty:
        return [], {}

    mapping = _ask_claude(_preview(df, _PREVIEW_ROWS))
    if mapping is None:
        log.info("TB AI: no API key — falling back to keyword parser")
        return parse_keyword(data, filename)

    if not _validate_mapping(mapping, df.shape[1]):
        log.info("TB AI: mapping invalid — falling back to keyword parser")
        return parse_keyword(data, filename)

    cols = mapping["columns"]
    header_idx = int(mapping["header_row_index"])
    total_set = set(mapping.get("total_row_indices") or [])

    rows: list[dict[str, Any]] = []
    for i in range(header_idx + 1, len(df)):
        if i in total_set:
            continue
        row = df.iloc[i]
        if _is_total_row(row):
            continue

        raw_code = row.iloc[cols["account_code"]] if cols.get("account_code") is not None else None
        if raw_code is None or (isinstance(raw_code, float) and pd.isna(raw_code)):
            continue
        code_only, name_in_code = _split_code_and_name(str(raw_code))
        if not code_only or not code_only[0].isdigit():
            continue

        name_raw = row.iloc[cols["account_name"]] if cols.get("account_name") is not None else None
        name = str(name_raw).strip() if name_raw is not None and not (isinstance(name_raw, float) and pd.isna(name_raw)) else (name_in_code or "")

        def dec(key: str) -> Decimal:
            idx = cols.get(key)
            if idx is None:
                return Decimal("0")
            try:
                return to_decimal(row.iloc[idx])
            except (IndexError, KeyError):
                return Decimal("0")

        rows.append({
            "account_code":   code_only[:64],
            "account_name":   name[:512],
            "opening_debit":  dec("opening_debit"),
            "opening_credit": dec("opening_credit"),
            "period_debit":   dec("period_debit"),
            "period_credit":  dec("period_credit"),
            "closing_debit":  dec("closing_debit"),
            "closing_credit": dec("closing_credit"),
        })

    log.info("TB AI mapping used: %s", mapping.get("rationale", ""))

    report = {
        "source": "ai",
        "rationale": mapping.get("rationale", ""),
        "detected": {
            "account_code":   cols.get("account_code")   is not None,
            "account_name":   cols.get("account_name")   is not None,
            "opening_debit":  cols.get("opening_debit")  is not None,
            "opening_credit": cols.get("opening_credit") is not None,
            "period_debit":   cols.get("period_debit")   is not None,
            "period_credit":  cols.get("period_credit")  is not None,
            "closing_debit":  cols.get("closing_debit")  is not None,
            "closing_credit": cols.get("closing_credit") is not None,
        },
        "column_indices": cols,
        "header_row_index": header_idx,
    }
    return rows, report
