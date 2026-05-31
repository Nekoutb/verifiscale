"""Trial balance parser (SYSCOHADA balance 6 colonnes, art. 19).

Supports two common file shapes:
1. **6-column format** (SYSCOHADA canonical): separate Debit/Credit columns
   for Opening, Period (movements), Closing.
2. **Net-balance format** (Odoo / Wave / many small-business tools):
   single `Balance` column where positive = debit balance, negative = credit.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from app.parsers.common import find_all_columns, find_column, read_tabular, to_decimal


class ParsedTBLine(TypedDict):
    account_code: str
    account_name: str
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_debit: Decimal
    closing_credit: Decimal


# Column synonyms in FR (canonical) and EN — be generous
_COLS = {
    "account_code":   ["compte", "n compte", "numero compte", "code compte", "code",
                       "account", "account code", "acct", "no compte"],
    "account_name":   ["libelle", "libelle compte", "intitule", "name", "description",
                       "account name", "nom compte", "denomination"],
    "opening_debit":  ["ouverture debit", "ouv debit", "ouv d", "solde initial debit",
                       "opening debit", "sodebit", "debit ouverture"],
    "opening_credit": ["ouverture credit", "ouv credit", "ouv c", "solde initial credit",
                       "opening credit", "socredit", "credit ouverture"],
    "period_debit":   ["mouvement debit", "mvt debit", "mvt d", "movement debit", "movd",
                       "debit periode", "debit"],
    "period_credit":  ["mouvement credit", "mvt credit", "mvt c", "movement credit", "movc",
                       "credit periode", "credit"],
    "closing_debit":  ["cloture debit", "clo debit", "clo d", "solde final debit",
                       "closing debit", "sf debit", "debit cloture", "ending debit"],
    "closing_credit": ["cloture credit", "clo credit", "clo c", "solde final credit",
                       "closing credit", "sf credit", "credit cloture", "ending credit"],
}

# Net-balance synonyms (single signed column per period)
_NET_OPENING = ["initial balance", "solde initial", "solde ouverture", "balance ouverture",
                "opening balance", "balance d ouverture", "solde initial net"]
_NET_CLOSING = ["end balance", "final balance", "solde final", "solde cloture", "ending balance",
                "closing balance", "balance cloture", "solde net"]


def _net_to_dc(net: Decimal) -> tuple[Decimal, Decimal]:
    """Convert a signed net balance into (debit, credit) — positive → debit, negative → credit."""
    if net > 0:
        return net, Decimal("0")
    if net < 0:
        return Decimal("0"), -net
    return Decimal("0"), Decimal("0")


def parse(data: bytes, filename: str) -> tuple[list[ParsedTBLine], dict]:
    """Parse a trial balance file. Returns (rows, column_mapping)."""
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

    if not mapping["account_name"]:
        # Fallback: first text-y column other than account_code
        for c in df.columns:
            if c != mapping["account_code"]:
                mapping["account_name"] = c
                break

    # ── Net-balance fallback for opening/closing ─────────────────────────────
    net_opening_col = None
    net_closing_col = None
    if not (mapping["opening_debit"] or mapping["opening_credit"]):
        net_opening_col = find_column(df, _NET_OPENING)
    if not (mapping["closing_debit"] or mapping["closing_credit"]):
        net_closing_col = find_column(df, _NET_CLOSING)

    # ── Duplicate "Balance" column fallback (Odoo / Wave format) ─────────────
    # When the file has exactly two columns called "Balance" (or "Solde") and no
    # explicit Initial/End names, treat the first as opening and the second as closing.
    if not net_opening_col and not net_closing_col:
        balance_cols = find_all_columns(df, ["balance", "solde"])
        if len(balance_cols) >= 2:
            net_opening_col = balance_cols[0]
            net_closing_col = balance_cols[-1]

    # ── Iterate rows ─────────────────────────────────────────────────────────
    rows: list[ParsedTBLine] = []
    for _, r in df.iterrows():
        code = str(r[mapping["account_code"]]).strip()
        # Skip blank rows, totals, and the residual sub-header row (e.g. "Code")
        if not code or code.lower() in ("nan", "none", "total", "totaux", "code"):
            continue
        # Skip rows where the code isn't numeric-ish (e.g. "Total 101300 Capital")
        if not any(ch.isdigit() for ch in code[:6]):
            continue

        opening_d = to_decimal(r[mapping["opening_debit"]])  if mapping["opening_debit"]  else Decimal("0")
        opening_c = to_decimal(r[mapping["opening_credit"]]) if mapping["opening_credit"] else Decimal("0")
        closing_d = to_decimal(r[mapping["closing_debit"]])  if mapping["closing_debit"]  else Decimal("0")
        closing_c = to_decimal(r[mapping["closing_credit"]]) if mapping["closing_credit"] else Decimal("0")

        if net_opening_col:
            opening_d, opening_c = _net_to_dc(to_decimal(r[net_opening_col]))
        if net_closing_col:
            closing_d, closing_c = _net_to_dc(to_decimal(r[net_closing_col]))

        rows.append(
            ParsedTBLine(
                account_code=code,
                account_name=str(r[mapping["account_name"]]).strip() if mapping["account_name"] else "",
                opening_debit=opening_d,
                opening_credit=opening_c,
                period_debit=to_decimal(r[mapping["period_debit"]]) if mapping["period_debit"] else Decimal("0"),
                period_credit=to_decimal(r[mapping["period_credit"]]) if mapping["period_credit"] else Decimal("0"),
                closing_debit=closing_d,
                closing_credit=closing_c,
            )
        )

    # Build a clean mapping dict for the response
    out_mapping = {k: v for k, v in mapping.items() if v}
    if net_opening_col:
        out_mapping["opening_net"] = net_opening_col
    if net_closing_col:
        out_mapping["closing_net"] = net_closing_col
    return rows, out_mapping
