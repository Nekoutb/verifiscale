"""Source-agnostic ledger reader (GL & TB).

Handles the real-world shapes we've hit, independent of the exporting system:

  * TWO-ROW HEADERS — Odoo stamps a banner row above the real header, and the
    banner is the ONLY thing disambiguating duplicate labels:

        r1 |      |              | Initial Balance | 2026  |        | End Balance
        r3 | Code | Account Name | Balance         | Debit | Credit | Balance
                                   ^^^^^^^ opening                    ^^^^^^^ closing

    Reading r3 alone maps both "Balance" columns to the same field. We compose
    the effective header as "banner + header" per column.

  * GROUPED EXPORTS — the account code appears ONLY on the account's header
    row and is blank on the transaction rows beneath it -> forward-fill.

  * SUBTOTAL ROWS THAT CARRY AMOUNTS — the account header row holds the
    account's period totals. Skipping only "zero-amount" rows is not enough:
    the rule that actually works is STRUCTURAL —

        a real transaction ALWAYS has an effective date;
        account subtotals / opening balances / grand totals NEVER do.

Nothing here invents data: rows that cannot be resolved are reported as
`excluded` with a reason, never silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Any

from app.parsers.canonical_fields import (
    GL_FIELDS, TB_FIELDS, CanonicalField, normalize, is_non_data_label,
    extract_entry_id, detect_entry_id_pattern,
)


MAX_HEADER_SCAN = 12          # rows to scan when hunting for the header
MIN_HEADER_HITS = 2           # min canonical hints on a row to call it a header


# ── helpers ─────────────────────────────────────────────────────────────────

def to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace(" ", "")
    if not s:
        return Decimal("0")
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    # 1.234.567,89 | 1,234,567.89 | 1234567.89
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return -d if neg else d


def to_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y",
                "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def looks_like_account_code(v: Any) -> bool:
    """SYSCOHADA codes are numeric-ish, 3+ chars (101300, 401100, 6111)."""
    if v is None:
        return False
    s = str(v).strip()
    if not s or len(s) < 3:
        return False
    return s[:3].isdigit()


# ── header detection ────────────────────────────────────────────────────────

@dataclass
class HeaderInfo:
    header_row: int                       # 0-based index of the real header row
    banner_row: int | None                # 0-based index of a banner row above it
    effective: list[str]                  # composed header text per column
    raw_header: list[Any]
    raw_banner: list[Any] | None


def _score_row_as_header(row: list[Any], fields: tuple[CanonicalField, ...]) -> int:
    hits = 0
    for cell in row:
        n = normalize(cell)
        if not n:
            continue
        for f in fields:
            if any(n == h or n.startswith(h) or h in n for h in f.hints):
                hits += 1
                break
    return hits


def detect_header(rows: list[list[Any]], kind: str) -> HeaderInfo | None:
    """Find the header row and compose it with a banner row when present."""
    fields = GL_FIELDS if kind.upper() == "GL" else TB_FIELDS
    best_idx, best_score = None, 0
    for i, row in enumerate(rows[:MAX_HEADER_SCAN]):
        s = _score_row_as_header(row, fields)
        if s > best_score:
            best_idx, best_score = i, s
    if best_idx is None or best_score < MIN_HEADER_HITS:
        return None

    header = rows[best_idx]
    # A banner is a sparse, non-empty row above the header whose labels sit over
    # value columns (Odoo: "Initial Balance" / "End Balance").
    banner_idx = None
    for j in range(best_idx - 1, max(-1, best_idx - 4), -1):
        if j < 0:
            break
        cand = rows[j]
        filled = [c for c in cand if c not in (None, "")]
        if 0 < len(filled) < max(2, len(header)):
            banner_idx = j
            break

    banner = rows[banner_idx] if banner_idx is not None else None
    width = len(header)
    effective: list[str] = []
    for c in range(width):
        h = str(header[c]).strip() if c < len(header) and header[c] not in (None, "") else ""
        b = ""
        if banner and c < len(banner) and banner[c] not in (None, ""):
            b = str(banner[c]).strip()
        effective.append((b + " " + h).strip() if b else h)

    return HeaderInfo(best_idx, banner_idx, effective, list(header),
                      list(banner) if banner else None)


def propose_mapping(hdr: HeaderInfo, rows: list[list[Any]], kind: str) -> dict[str, int]:
    """Heuristic column mapping from the composed header.

    Deliberately conservative: only maps what it can justify. Whatever it
    cannot resolve is left unmapped for the auditor to fix in the preview UI.
    """
    fields = GL_FIELDS if kind.upper() == "GL" else TB_FIELDS
    eff = [normalize(h) for h in hdr.effective]
    mapping: dict[str, int] = {}
    taken: set[int] = set()

    def claim(key: str, idx: int) -> None:
        mapping[key] = idx
        taken.add(idx)

    if kind.upper() == "TB":
        # Resolve the three balance groups using the composed header, so
        # "Initial Balance Balance" != "End Balance Balance".
        groups = {
            "opening": ("aouverture", "ouverture", "initial", "initialbalance",
                        "soldeinitial", "anouveau", "opening", "balanceinitiale"),
            "closing": ("cloture", "final", "endbalance", "soldefinal", "closing",
                        "soldecloture", "end"),
        }
        for gkey, toks in groups.items():
            for i, h in enumerate(eff):
                if i in taken or not h:
                    continue
                if any(t in h for t in toks):
                    if "debit" in h:
                        claim(f"{gkey}_debit", i)
                    elif "credit" in h:
                        claim(f"{gkey}_credit", i)
                    else:
                        claim(f"{gkey}_signed", i)
        # Movements = the debit/credit columns not already claimed by a group.
        for i, h in enumerate(eff):
            if i in taken or not h:
                continue
            if "debit" in h:
                claim("movement_debit", i)
            elif "credit" in h:
                claim("movement_credit", i)

    else:  # GL
        for i, h in enumerate(eff):
            if i in taken or not h:
                continue
            if "debit" in h:
                claim("debit", i)
            elif "credit" in h:
                claim("credit", i)

    # Remaining single-valued fields, by hint match.
    for f in fields:
        if f.key in mapping or f.shape.name == "PAIR":
            continue
        for i, h in enumerate(eff):
            if i in taken or not h:
                continue
            if any(h == x or h.startswith(x) or x in h for x in f.hints):
                claim(f.key, i)
                break

    # GL grouped exports reuse ONE label column for three roles: account name on
    # the account header row, transaction description + entry id on the lines
    # beneath it. Refusing to reuse the column would block a mandatory field on
    # a file that is perfectly readable, so share it explicitly.
    if (kind.upper() == "GL" and "transaction_description" not in mapping
            and mapping.get("account_description") is not None):
        mapping["transaction_description"] = mapping["account_description"]

    # GL: no dedicated entry_id column -> offer pattern extraction from the
    # richest text column (Odoo buries "CSHOM/2026/00237" in the label).
    if kind.upper() == "GL" and "entry_id" not in mapping:
        data = rows[hdr.header_row + 1:hdr.header_row + 200]
        best_col, best = None, None
        for i in range(len(hdr.effective)):
            samples = [r[i] if i < len(r) else None for r in data]
            info = detect_entry_id_pattern([None if s is None else str(s) for s in samples])
            if info and (best is None or info["hit_rate"] > best["hit_rate"]):
                best_col, best = i, info
        if best_col is not None and best and best["hit_rate"] >= 0.30:
            mapping["entry_id__extract_from"] = best_col
            mapping["entry_id__extract_info"] = best  # type: ignore[assignment]

    return mapping


# ── row classification ──────────────────────────────────────────────────────

@dataclass
class ExcludedRow:
    row_index: int
    reason: str
    label: str
    impact: dict[str, str] = field(default_factory=dict)


@dataclass
class ReadResult:
    kind: str
    header: HeaderInfo
    mapping: dict[str, int]
    rows: list[dict[str, Any]]
    excluded: list[ExcludedRow]
    totals: dict[str, Decimal]
    stated_totals: dict[str, Decimal] | None
    warnings: list[str]


def _get(row: list[Any], mapping: dict[str, int], key: str) -> Any:
    i = mapping.get(key)
    if i is None or i >= len(row):
        return None
    return row[i]


def read(rows: list[list[Any]], kind: str, mapping: dict[str, int],
         hdr: HeaderInfo) -> ReadResult:
    """Apply an APPROVED mapping and return resolved rows + excluded rows.

    Structural rules:
      GL — a real transaction has an effective date. Rows with an account code
           but no date are account subtotals. Rows whose label is a known
           non-data label (Total / Initial Balance / Report à nouveau) are out.
      TB — every row with an account code is an account. Rows without a code
           but carrying amounts are surfaced (never silently dropped): they are
           usually "Result Brought Forward" and dropping them unbalances the TB.
    """
    out: list[dict[str, Any]] = []
    excluded: list[ExcludedRow] = []
    warnings: list[str] = []
    stated: dict[str, Decimal] | None = None

    data = rows[hdr.header_row + 1:]
    cur_code: str | None = None
    cur_name: str | None = None

    for n, row in enumerate(data, start=hdr.header_row + 2):  # 1-based, for humans
        if not any(c not in (None, "") for c in row):
            continue

        raw_code = _get(row, mapping, "account_number")
        desc = _get(row, mapping, "account_description")
        label_txt = str(desc or "").strip()

        # Grand-total / summary row -> capture stated totals, then exclude.
        if is_non_data_label(label_txt) and not looks_like_account_code(raw_code):
            n_lbl = normalize(label_txt)
            if n_lbl.startswith(("total", "totaux", "grandtotal", "cumul")):
                stated = {}
                for k, i in mapping.items():
                    if isinstance(i, int) and i < len(row) and k not in (
                        "account_number", "account_description", "entry_id",
                        "transaction_description", "entry_date",
                    ):
                        stated[k] = to_decimal(row[i])
                excluded.append(ExcludedRow(n, "Ligne de total du fichier", label_txt))
            else:
                excluded.append(ExcludedRow(n, "Solde d'ouverture / report (non transactionnel)", label_txt))
            continue

        if kind.upper() == "GL":
            edate = to_date(_get(row, mapping, "entry_date"))

            # Account grouping header: carries the code, no date -> subtotal.
            if looks_like_account_code(raw_code):
                cur_code = str(raw_code).strip()
                cur_name = label_txt or cur_name
                if edate is None:
                    excluded.append(ExcludedRow(
                        n, "Sous-total de compte (code sans date)", f"{cur_code} {label_txt}"[:80]))
                    continue

            if edate is None:
                excluded.append(ExcludedRow(n, "Ligne sans date d'effet — non transactionnelle", label_txt[:80]))
                continue

            # entry_id: dedicated column, else confirmed pattern extraction.
            eid = _get(row, mapping, "entry_id")
            eid = str(eid).strip() if eid not in (None, "") else None
            if not eid and "entry_id__extract_from" in mapping:
                src = row[mapping["entry_id__extract_from"]] if mapping["entry_id__extract_from"] < len(row) else None
                eid = extract_entry_id(None if src is None else str(src))
            if not eid:
                excluded.append(ExcludedRow(n, "N° écriture introuvable (jamais inventé)", label_txt[:80]))
                continue

            if mapping.get("amount_signed") is not None:
                amt = to_decimal(_get(row, mapping, "amount_signed"))
                debit, credit = (amt, Decimal("0")) if amt >= 0 else (Decimal("0"), -amt)
            else:
                debit = to_decimal(_get(row, mapping, "debit"))
                credit = to_decimal(_get(row, mapping, "credit"))

            out.append({
                "row": n, "entry_id": eid, "entry_date": edate,
                "account_number": cur_code, "account_description": cur_name,
                "transaction_description": str(_get(row, mapping, "transaction_description") or label_txt)[:512],
                "debit": debit, "credit": credit,
                "journal_code": str(_get(row, mapping, "journal_code") or "").strip() or None,
                "partner": str(_get(row, mapping, "partner") or "").strip() or None,
            })

        else:  # TB
            if not looks_like_account_code(raw_code):
                amounts = [to_decimal(_get(row, mapping, k)) for k in
                           ("opening_signed", "opening_debit", "opening_credit",
                            "movement_debit", "movement_credit",
                            "closing_signed", "closing_debit", "closing_credit")]
                if any(a != 0 for a in amounts):
                    # Carries money but has no code — surface it, don't drop it.
                    excluded.append(ExcludedRow(
                        n, "Ligne sans numéro de compte mais porteuse de montants "
                           "— à rattacher (ex. Report à nouveau → cpt 11) ou exclure en connaissance de cause",
                        label_txt[:80],
                        {"opening": str(amounts[0] or amounts[1] - amounts[2]),
                         "closing": str(amounts[5] or amounts[6] - amounts[7])},
                    ))
                continue

            rec: dict[str, Any] = {
                "row": n,
                "account_number": str(raw_code).strip(),
                "account_description": label_txt,
            }
            for grp in ("opening", "movement", "closing"):
                sgn = mapping.get(f"{grp}_signed")
                if sgn is not None:
                    v = to_decimal(_get(row, mapping, f"{grp}_signed"))
                    rec[f"{grp}_debit"] = v if v >= 0 else Decimal("0")
                    rec[f"{grp}_credit"] = -v if v < 0 else Decimal("0")
                    rec[f"{grp}_signed"] = v
                else:
                    d = to_decimal(_get(row, mapping, f"{grp}_debit"))
                    c = to_decimal(_get(row, mapping, f"{grp}_credit"))
                    rec[f"{grp}_debit"], rec[f"{grp}_credit"] = d, c
                    rec[f"{grp}_signed"] = d - c
            out.append(rec)

    # Column totals (computed from what will ACTUALLY be ingested).
    totals: dict[str, Decimal] = {}
    if kind.upper() == "GL":
        totals["debit"] = sum((r["debit"] for r in out), Decimal("0"))
        totals["credit"] = sum((r["credit"] for r in out), Decimal("0"))
    else:
        for grp in ("opening", "movement", "closing"):
            totals[f"{grp}_debit"] = sum((r[f"{grp}_debit"] for r in out), Decimal("0"))
            totals[f"{grp}_credit"] = sum((r[f"{grp}_credit"] for r in out), Decimal("0"))

    if not out:
        warnings.append("Aucune ligne exploitable — vérifiez le mappage des colonnes.")

    return ReadResult(kind.upper(), hdr, mapping, out, excluded, totals, stated, warnings)
