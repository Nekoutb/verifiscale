"""Monthly running-balance engine for account-position analyses.

Serves two modules that ask the same question — « at each month end, is this
account on the wrong side? »:

  * comptes d'associés 46XX  — a DEBIT position is forbidden: it means funds
    were made available to the shareholder (revenu réputé distribué).
  * comptes divers 4711/4712 — a DEBIT position = créances sur tiers non
    identifiés, a CREDIT position = dettes envers tiers non identifiés; both
    expose the taxpayer to fines and penalties.

Sign convention: `balance` is DEBIT-POSITIVE (débit − crédit), the way an
auditor reads a running balance.

Per account it returns:
  * 12 month-end balances, each flagged when on the wrong side;
  * every transaction, ordered so the one that DRIVES the wrong-side position
    (largest debit for a debit position, largest credit for a credit one) comes
    first, and marked `drives_position` when it is the tipping entry;
  * offsetting pairs (same absolute amount, opposite direction) grouped by
    `offset_group`, so the UI can hide them with one tick.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Literal

MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
             "juil.", "août", "sept.", "oct.", "nov.", "déc."]

Side = Literal["DEBIT", "CREDIT", "BOTH"]


@dataclass
class Tx:
    piece_number: str
    line_number: int
    entry_date: str | None
    month: int | None
    libelle: str
    debit: Decimal
    credit: Decimal
    running_after: Decimal = Decimal("0")
    #: this entry is what pushes / keeps the balance on the wrong side
    drives_position: bool = False
    #: id shared by two lines that cancel each other out (same amount, opposite way)
    offset_group: int | None = None


@dataclass
class MonthPoint:
    month: int
    label: str
    debit: Decimal
    credit: Decimal
    balance: Decimal          # débit-positif
    flagged: bool = False
    nature: str | None = None  # "DEBIT" | "CREDIT"


@dataclass
class AccountAnalysis:
    account_code: str
    account_name: str
    opening_balance: Decimal
    closing_balance: Decimal
    months: list[MonthPoint] = field(default_factory=list)
    transactions: list[Tx] = field(default_factory=list)
    flagged_months: int = 0
    max_wrong_side_xaf: Decimal = Decimal("0")


def _month_of(d: Any) -> int | None:
    if d is None:
        return None
    try:
        return int(getattr(d, "month", None) or str(d)[5:7])
    except (ValueError, TypeError):
        return None


def _detect_offsets(txs: list[Tx]) -> None:
    """Pair up lines that cancel each other out on amount (débit X ↔ crédit X).

    Greedy one-to-one matching per absolute amount, so three 500 000 debits
    against one 500 000 credit yield exactly one pair, not three.
    """
    by_amount: dict[Decimal, dict[str, list[Tx]]] = defaultdict(lambda: {"d": [], "c": []})
    for t in txs:
        if t.debit > 0:
            by_amount[t.debit]["d"].append(t)
        elif t.credit > 0:
            by_amount[t.credit]["c"].append(t)
    gid = 0
    for amount, sides in by_amount.items():
        if amount <= 0:
            continue
        for d, c in zip(sides["d"], sides["c"]):
            gid += 1
            d.offset_group = gid
            c.offset_group = gid


def analyze_account(
    account_code: str,
    account_name: str,
    opening_balance: Decimal,
    lines: Iterable[Any],
    flag_side: Side,
) -> AccountAnalysis:
    """`lines` = JournalEntryLine-like objects for THIS account."""
    txs: list[Tx] = []
    for l in lines:
        txs.append(Tx(
            piece_number=str(getattr(l, "piece_number", "") or ""),
            line_number=int(getattr(l, "line_number", 0) or 0),
            entry_date=(str(getattr(l, "entry_date", "") or "") or None),
            month=_month_of(getattr(l, "entry_date", None)),
            libelle=(getattr(l, "libelle", None) or getattr(l, "account_name", None) or "")[:300],
            debit=Decimal(str(getattr(l, "debit", 0) or 0)),
            credit=Decimal(str(getattr(l, "credit", 0) or 0)),
        ))
    # chronological running balance
    txs.sort(key=lambda t: (t.entry_date or "9999", t.piece_number, t.line_number))
    running = opening_balance
    for t in txs:
        running += t.debit - t.credit
        t.running_after = running
    closing = running

    # month-end points
    months: list[MonthPoint] = []
    running = opening_balance
    idx = 0
    for m in range(1, 13):
        md = mc = Decimal("0")
        while idx < len(txs) and (txs[idx].month or 13) <= m:
            md += txs[idx].debit
            mc += txs[idx].credit
            running += txs[idx].debit - txs[idx].credit
            idx += 1
        flagged = (
            (flag_side in ("DEBIT", "BOTH") and running > 0)
            or (flag_side in ("CREDIT", "BOTH") and running < 0)
        )
        months.append(MonthPoint(
            m, MONTHS_FR[m - 1], md, mc, running, flagged,
            ("DEBIT" if running > 0 else "CREDIT" if running < 0 else None) if flagged else None,
        ))
    # trailing entries with no parseable date land in December
    while idx < len(txs):
        months[-1].debit += txs[idx].debit
        months[-1].credit += txs[idx].credit
        idx += 1

    _detect_offsets(txs)

    # Which transactions drive the wrong-side position? Debit-driven when the
    # account ever sits debit, credit-driven when it ever sits credit.
    ever_debit = any(mp.flagged and mp.nature == "DEBIT" for mp in months)
    ever_credit = any(mp.flagged and mp.nature == "CREDIT" for mp in months)
    ordered = list(txs)
    if ever_debit:
        ordered.sort(key=lambda t: (-t.debit, t.entry_date or ""))
    elif ever_credit:
        ordered.sort(key=lambda t: (-t.credit, t.entry_date or ""))
    for t in ordered[:3]:
        if (ever_debit and t.debit > 0) or (ever_credit and t.credit > 0):
            t.drives_position = True

    flagged_n = sum(1 for mp in months if mp.flagged)
    worst = max((abs(mp.balance) for mp in months if mp.flagged), default=Decimal("0"))
    return AccountAnalysis(account_code, account_name, opening_balance, closing,
                           months, ordered, flagged_n, worst)


def run_analysis(
    tb_lines: Iterable[Any],
    gl_lines: Iterable[Any],
    prefixes: tuple[str, ...],
    flag_side: Side,
) -> list[AccountAnalysis]:
    """Analyse every account matching `prefixes`.

    Opening balances come from the trial balance; movements from the GL.
    """
    opening: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    for tb in tb_lines:
        code = str(tb.account_code).strip()
        if not code.startswith(prefixes):
            continue
        opening[code] = (Decimal(str(tb.opening_debit or 0))
                         - Decimal(str(tb.opening_credit or 0)))
        names[code] = tb.account_name or ""

    per_account: dict[str, list[Any]] = defaultdict(list)
    for l in gl_lines:
        code = str(l.account_code or "").strip()
        if code.startswith(prefixes):
            per_account[code].append(l)
            names.setdefault(code, l.account_name or "")

    out: list[AccountAnalysis] = []
    for code in sorted(set(list(opening.keys()) + list(per_account.keys()))):
        out.append(analyze_account(
            code, names.get(code, ""), opening.get(code, Decimal("0")),
            per_account.get(code, []), flag_side,
        ))
    return out


def serialize(analyses: list[AccountAnalysis], reviews: dict[tuple[str, int], Any]) -> list[dict]:
    """JSON view; `reviews` maps (piece_number, line_number) -> LedgerLineReview."""
    out = []
    for a in analyses:
        out.append({
            "account_code": a.account_code,
            "account_name": a.account_name,
            "opening_balance_xaf": float(a.opening_balance),
            "closing_balance_xaf": float(a.closing_balance),
            "flagged_months": a.flagged_months,
            "max_wrong_side_xaf": float(a.max_wrong_side_xaf),
            "months": [
                {"month": m.month, "label": m.label, "debit_xaf": float(m.debit),
                 "credit_xaf": float(m.credit), "balance_xaf": float(m.balance),
                 "flagged": m.flagged, "nature": m.nature}
                for m in a.months
            ],
            "transactions": [
                {
                    "piece_number": t.piece_number, "line_number": t.line_number,
                    "entry_date": t.entry_date, "month": t.month, "libelle": t.libelle,
                    "debit_xaf": float(t.debit), "credit_xaf": float(t.credit),
                    "running_after_xaf": float(t.running_after),
                    "drives_position": t.drives_position, "offset_group": t.offset_group,
                    "justified": bool(getattr(reviews.get((t.piece_number, t.line_number)),
                                              "justified", False)),
                    "hidden_offset": bool(getattr(reviews.get((t.piece_number, t.line_number)),
                                                  "hidden_offset", False)),
                }
                for t in a.transactions
            ],
        })
    return out
