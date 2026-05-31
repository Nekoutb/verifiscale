"""General ledger / FEC parser.

Supports several common shapes:
1. **Flat FEC** (canonical): every row has its own date/piece/journal/account/amounts.
2. **Account-grouped GL** (Odoo / Sage exports): account code appears once on a
   header row, followed by N data rows where the code column is blank; final
   row per account is a "Total".
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TypedDict

from app.parsers.common import find_column, read_tabular, to_date, to_decimal


class ParsedGLLine(TypedDict):
    entry_date: date | None
    piece_number: str
    journal_code: str
    account_code: str
    account_name: str
    libelle: str
    debit: Decimal
    credit: Decimal
    lettrage: str | None


_COLS = {
    "entry_date":   ["date", "date piece", "date valeur", "ecriturejour", "entry date",
                     "date comptable", "accounting date"],
    # Odoo Journal Items export uses "Number" or "Move Name" — add those plus
    # other common ERP labels.
    "piece_number": ["number", "movename", "move name", "move", "move number",
                     "no", "n", "name", "entry number", "entry no",
                     "piece", "n piece", "numero piece", "document",
                     "ecriturenum", "piecenum", "reference", "ref", "voucher"],
    "journal_code": ["journal", "code journal", "journalcode", "journal book"],
    "account_code": ["compte", "n compte", "compte general", "comptenum",
                     "account", "code", "account code"],
    "account_name": ["intitule compte", "libelle compte", "comptelib",
                     "account name", "nom compte"],
    # Odoo: "Label". Sage: "Libellé écriture". Add "memo", "narration", "partner".
    "libelle":      ["label", "libelle", "libelle ecriture", "description",
                     "ecriturelib", "memo", "communication", "narration", "partner"],
    "debit":        ["debit", "montant debit", "debiteur"],
    "credit":       ["credit", "montant credit", "crediteur"],
    # Odoo: "Matching Number". Sage FEC: "EcritureLet".
    "lettrage":     ["matching number", "matching", "lettrage", "ecriturelet",
                     "let", "reconcile", "reconciliation"],
}


# When a single cell contains "<code> <name>" (e.g. "411100 Customers"), split.
import re as _re
_CODE_NAME_RE = _re.compile(r"^\s*(\d[\d\-/.]*?)\s+(.+)$")


def _split_code_and_name(raw: str) -> tuple[str, str | None]:
    """Return (code, name) — splits Odoo-style 'code description' cells.

    Examples:
      '411100 Customers'                            -> ('411100', 'Customers')
      '571141 Cash in national currency MOMO'       -> ('571141', 'Cash in national currency MOMO')
      '411100'                                      -> ('411100', None)
      ''                                            -> ('', None)
    """
    if not raw:
        return "", None
    s = str(raw).strip()
    m = _CODE_NAME_RE.match(s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, None

# Libellés that indicate sub-total / opening lines we should skip
_SKIP_LIBELLE_PREFIXES = (
    "initial balance", "solde initial", "solde ouverture", "opening balance",
    "total ", "totaux ", "ending balance", "solde final",
)


def parse(data: bytes, filename: str) -> tuple[list[ParsedGLLine], dict]:
    df = read_tabular(data, filename)
    if df.empty:
        return [], {}

    mapping: dict[str, str | None] = {}
    for canonical, candidates in _COLS.items():
        mapping[canonical] = find_column(df, candidates)

    # account_code is the only strictly required column
    if not mapping["account_code"]:
        raise ValueError(
            "Colonne 'Compte' (ou 'Code') introuvable. "
            f"Colonnes détectées : {', '.join(str(c) for c in df.columns)}"
        )

    # piece_number is now optional — we'll synthesize one if missing
    has_piece = bool(mapping["piece_number"])

    rows: list[ParsedGLLine] = []
    current_account_code: str | None = None
    current_account_name: str | None = None
    synthetic_piece_seq = 0

    for idx, r in df.iterrows():
        # ── Resolve account code (forward-fill for grouped GLs) ────────────
        raw_code = r[mapping["account_code"]]
        code_str = str(raw_code).strip() if raw_code is not None else ""
        if code_str and code_str.lower() not in ("nan", "none", "", "code"):
            # Looks like an account code? (starts with a digit)
            if code_str[0].isdigit():
                # Odoo packs "411100 Customers" in a single cell — split it.
                code_only, name_in_code = _split_code_and_name(code_str)
                current_account_code = code_only
                # Prefer an explicit account_name column; otherwise use the
                # name we extracted from the combined cell.
                if mapping["account_name"]:
                    nm = r[mapping["account_name"]]
                    if nm is not None and str(nm).strip().lower() not in ("nan", "none", ""):
                        current_account_name = str(nm).strip()
                    elif name_in_code:
                        current_account_name = name_in_code
                elif name_in_code:
                    current_account_name = name_in_code
            else:
                # Header text in the code column — skip
                continue

        if not current_account_code:
            continue  # No account established yet (junk header rows)

        # ── Skip total / opening summary rows ───────────────────────────────
        libelle_raw = str(r[mapping["libelle"]]).strip() if mapping["libelle"] and r[mapping["libelle"]] is not None else ""
        if any(libelle_raw.lower().startswith(p) for p in _SKIP_LIBELLE_PREFIXES):
            continue

        # ── Pull amounts — skip the row if both are zero AND no date/piece ─
        debit  = to_decimal(r[mapping["debit"]])  if mapping["debit"]  else Decimal("0")
        credit = to_decimal(r[mapping["credit"]]) if mapping["credit"] else Decimal("0")
        entry_date = to_date(r[mapping["entry_date"]]) if mapping["entry_date"] else None
        piece = str(r[mapping["piece_number"]]).strip() if has_piece and r[mapping["piece_number"]] is not None else ""

        if debit == 0 and credit == 0 and not entry_date and not piece:
            # Likely the account header row itself — already captured the code, skip
            continue

        # Synthesize a piece number if file doesn't provide one
        if not piece or piece.lower() in ("nan", "none"):
            synthetic_piece_seq += 1
            piece = f"AUTO-{synthetic_piece_seq:06d}"

        # Defensive truncation — protect against ERPs that ship absurdly long
        # codes / journals / lettrage strings (Odoo, in particular, can put
        # 'Misc Operations 2026/05' style compound codes here).
        journal_str = str(r[mapping["journal_code"]]).strip() if mapping["journal_code"] else ""
        lettrage_str = str(r[mapping["lettrage"]]).strip() if mapping["lettrage"] and r[mapping["lettrage"]] else None

        rows.append(
            ParsedGLLine(
                entry_date=entry_date,
                piece_number=piece[:128],
                journal_code=journal_str[:64],
                account_code=current_account_code[:64],
                account_name=(current_account_name or "")[:512],
                libelle=libelle_raw[:2048],
                debit=debit,
                credit=credit,
                lettrage=lettrage_str[:64] if lettrage_str else None,
            )
        )

    return rows, {k: v for k, v in mapping.items() if v}
