"""AI-powered General Ledger parser.

The keyword-based parser in ``general_ledger.py`` falls back to synthetic
per-line piece numbers when the JE identifier column isn't recognised — which
silently broke pièce grouping for Odoo / Sage / SAP exports with non-standard
column names.

This module uses Claude to identify the column layout of any GL — FEC, Odoo
Journal Items, Sage 100/X3, SAP, Excel templates — and refuses to fall back
on synthetic IDs. If no JE reference can be found we raise a clear error and
let the UI surface it to the auditor.

Returns the same ``ParsedGLLine`` shape as the keyword parser so the rest of
the pipeline (datasets router, controls, reconciliations) is unaffected.
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
from app.parsers.general_ledger import (
    ParsedGLLine, _split_code_and_name, parse as parse_keyword,
)


log = logging.getLogger("fiscaudit.parser.gl_ai")

_PREVIEW_ROWS = 25


SYSTEM_PROMPT = """You are an expert auditor at the Cameroon DGI ingesting a
GENERAL LEDGER produced by ANY accounting system — SYSCOHADA FEC, Odoo
(account.move.line), Sage 100, Sage X3, SAP, Microsoft Dynamics, Cegid,
QuickBooks, Excel templates. Column headers vary widely in French / English /
a mix.

You will receive the first rows of the ledger as a 2-D table. Identify the
0-based COLUMN INDEX for each canonical field below.

Canonical fields (all required unless marked optional):

  - piece_number     The UNIQUE journal-entry reference. EVERY line of the same
                     accounting entry must share the SAME value here. Common
                     headers:
                       Odoo:      "Number", "Move Name", "Move Number"
                       Sage FEC:  "EcritureNum", "PieceRef"
                       Sage 100:  "N° Pièce", "Piece"
                       SAP:       "Document Number", "Belegnummer"
                       SYSCOHADA: "Pièce", "N° Pièce", "Référence"
                       Generic:   "Voucher", "Entry No", "Reference", "Doc"
                     NEVER pick the per-line "Id" column.
                     NEVER pick a column whose values are unique on every row
                     (that would be the line id, not the entry id).

  - entry_date       The accounting / posting date of the entry. Common:
                       Odoo "Date", Sage "EcritureDate", SAP "Posting Date",
                       SYSCOHADA "Date pièce".

  - journal_code     The journal/book code (CSH4, BNK, OD, VE, AC…). Common:
                       Odoo "Journal", Sage FEC "JournalCode".

  - account_code     Account number. Sometimes packed with the name in one
                     cell ("411100 Customers") — you still return the column
                     index, our code splits the cell. Common headers:
                       Odoo "Account", Sage FEC "CompteNum",
                       SAP "G/L Account", SYSCOHADA "Compte".

  - account_name     Account libellé / description. Often in a separate column
                     ("CompteLib", "Account Name") but may be absent if the
                     account_code cell already contains it.

  - libelle          Per-line description / memo / narration. Common:
                       Odoo "Label", Sage FEC "EcritureLib",
                       SAP "Text", SYSCOHADA "Libellé".

  - debit            Debit amount column.
  - credit           Credit amount column.

  - lettrage         (optional) Reconciliation / matching code. Common:
                       Odoo "Matching Number", Sage FEC "EcritureLet".

  - header_row_index The 0-based row index where these headers sit (often 0,
                     sometimes 1-5 if a title / company block is above).

CRITICAL — JE identifier:
  - The control logic of this product groups lines by `piece_number`. If you
    return a column that is unique per row (i.e. the line id) the entire
    control is broken silently. Look at the SAMPLE rows you're given and
    verify the candidate `piece_number` has REPEATED values across consecutive
    lines (each accounting entry has 2+ lines that balance to zero).
  - If you genuinely cannot find a JE identifier column, set
    `piece_number` to null in the JSON — the system will refuse the parse
    and prompt the auditor to clarify.

Return STRICT JSON with this exact shape (no markdown, no prose):

{
  "header_row_index": 0,
  "columns": {
    "piece_number": 1,
    "entry_date": 2,
    "journal_code": 3,
    "account_code": 4,
    "account_name": null,
    "libelle": 6,
    "debit": 7,
    "credit": 8,
    "lettrage": null
  },
  "rationale": "Short reason — esp. how you confirmed piece_number repeats across lines of the same entry."
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
                "content": "Here is the first slice of the general ledger. Return the JSON mapping per the schema.\n\n" + preview,
            }],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            log.warning("GL AI: no JSON in Claude response: %s", text[:200])
            return None
        return json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        log.warning("GL AI parse failed: %s", e)
        return None


def _validate_mapping(mapping: dict, n_cols: int) -> tuple[bool, str | None]:
    """Validate the JSON Claude returned. Returns (ok, error_msg)."""
    if not isinstance(mapping, dict):
        return False, "Mapping is not an object"
    cols = mapping.get("columns")
    if not isinstance(cols, dict):
        return False, "Missing 'columns'"
    if cols.get("piece_number") is None:
        return False, "AUCUNE colonne 'Pièce / N° écriture' identifiable — le contrôle est suspendu."
    required = ("piece_number", "entry_date", "account_code", "debit", "credit")
    for k in required:
        v = cols.get(k)
        if v is None:
            return False, f"Colonne manquante : '{k}'"
        if not isinstance(v, int) or v < 0 or v >= n_cols:
            return False, f"Colonne '{k}' hors plage (index {v})"
    return True, None


def _walk(
    df: pd.DataFrame,
    header_idx: int,
    cols: dict[str, int | None],
) -> list[ParsedGLLine]:
    """Walk every data row, applying Claude's column mapping. Forward-fills
    account_code when the file is grouped (account header row followed by
    blank-code data rows)."""
    out: list[ParsedGLLine] = []
    current_acc_code: str | None = None
    current_acc_name: str | None = None

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

    for i in range(header_idx + 1, len(df)):
        row = df.iloc[i]

        # Account: split "411100 Customers" → ("411100", "Customers")
        raw_acc = get(row, "account_code")
        if raw_acc is not None:
            code_only, name_in_code = _split_code_and_name(str(raw_acc))
            if code_only and code_only[0].isdigit():
                current_acc_code = code_only
                explicit_name = get(row, "account_name")
                if explicit_name is not None:
                    current_acc_name = str(explicit_name).strip()
                elif name_in_code:
                    current_acc_name = name_in_code

        if not current_acc_code:
            continue

        debit = to_decimal(get(row, "debit"))
        credit = to_decimal(get(row, "credit"))
        edate = to_date(get(row, "entry_date"))
        raw_piece = get(row, "piece_number")
        piece = str(raw_piece).strip() if raw_piece is not None else ""

        # Skip account-header rows (no piece + no date + no amounts)
        if debit == 0 and credit == 0 and not edate and not piece:
            continue

        # The whole point: we never invent a piece_number. If a row has amounts
        # but no piece, drop it loudly (logged) rather than fabricating one.
        if not piece:
            log.warning("GL AI: dropping row %d — no piece_number in source", i)
            continue

        # Skip total / opening / closing summary rows
        libelle_raw = str(get(row, "libelle") or "").strip()
        norm_lib = _normalize(libelle_raw)
        if any(norm_lib.startswith(p) for p in ("total", "soustotal", "soldeouv",
                                                  "soldefinal", "openingbalance",
                                                  "endingbalance", "soldeinit")):
            continue

        journal = str(get(row, "journal_code") or "").strip()[:64]
        lettrage_raw = get(row, "lettrage")
        lettrage = str(lettrage_raw).strip()[:64] if lettrage_raw else None

        out.append(ParsedGLLine(
            entry_date=edate,
            piece_number=piece[:128],
            journal_code=journal or "OD",
            account_code=current_acc_code[:64],
            account_name=(current_acc_name or "")[:512],
            libelle=libelle_raw[:2048],
            debit=debit,
            credit=credit,
            lettrage=lettrage,
        ))

    return out


def parse(data: bytes, filename: str) -> tuple[list[ParsedGLLine], dict]:
    """AI-first GL parsing. Falls back to the keyword parser ONLY when Claude
    is unavailable (no API key). When Claude is available but can't identify a
    piece_number column, raises a clear error — we never invent IDs."""
    df = _read_raw(data, filename)
    if df.empty:
        return [], {}

    mapping = _ask_claude(_preview(df, _PREVIEW_ROWS))
    if mapping is None:
        log.info("GL AI: no API key / Claude unavailable — falling back to keyword parser")
        return parse_keyword(data, filename)

    ok, err = _validate_mapping(mapping, df.shape[1])
    if not ok:
        raise ValueError(
            f"L'IA n'a pas pu cartographier votre grand-livre : {err} "
            f"Vérifiez que le fichier contient bien une colonne d'identifiant "
            f"de pièce / écriture (ex : 'Number', 'Move Name', 'EcritureNum')."
        )

    rows = _walk(df, int(mapping["header_row_index"]), mapping["columns"])
    log.info("GL AI mapping used: %s", mapping.get("rationale", ""))

    # Build a human-readable detection report for the UI
    cols_used = mapping["columns"]
    report = {
        "source": "ai",
        "rationale": mapping.get("rationale", ""),
        "detected": {
            "piece_number":  cols_used.get("piece_number") is not None,
            "entry_date":    cols_used.get("entry_date") is not None,
            "journal_code":  cols_used.get("journal_code") is not None,
            "account_code":  cols_used.get("account_code") is not None,
            "account_name":  cols_used.get("account_name") is not None,
            "libelle":       cols_used.get("libelle") is not None,
            "debit":         cols_used.get("debit") is not None,
            "credit":        cols_used.get("credit") is not None,
            "lettrage":      cols_used.get("lettrage") is not None,
        },
        "column_indices": cols_used,
        "header_row_index": mapping["header_row_index"],
    }
    return rows, report
