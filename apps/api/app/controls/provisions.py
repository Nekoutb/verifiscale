"""Provisions — rollforward par compte.

    Ouverture (balance)
      + Dotations   (mouvements du compte de provision dont l'écriture porte
                     une contrepartie 69XX au grand livre)
      − Reprises    (… dont l'écriture porte une contrepartie 79XX)
      = Clôture attendue        →  comparée à la clôture réelle (balance)

Le rapprochement dotation/reprise se fait par le N° d'écriture (la pièce, qui
groupe le débit et le crédit). Les mouvements sans contrepartie 69XX/79XX sont
isolés dans « non classés » : ce sont eux qui expliquent l'essentiel des écarts.

Périmètre (SYSCOHADA / demande de l'auditeur) :
    19XX  provisions financières pour risques et charges (long terme)
    29XX  provisions pour dépréciation des immobilisations
    39XX  provisions pour dépréciation des stocks
    419XX provisions pour dépréciation des créances clients
    497   provisions pour dépréciation des comptes débiteurs divers
    59XX  provisions pour dépréciation des comptes de trésorerie
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

PROVISION_GROUPS: list[tuple[str, tuple[str, ...], str]] = [
    ("19", ("19",),   "Provisions financières pour risques et charges"),
    ("29", ("29",),   "Provisions pour dépréciation des immobilisations"),
    ("39", ("39",),   "Provisions pour dépréciation des stocks"),
    ("419", ("419",), "Provisions pour dépréciation des créances clients"),
    ("497", ("497",), "Provisions pour dépréciation des comptes débiteurs divers"),
    ("59", ("59",),   "Provisions pour dépréciation des comptes de trésorerie"),
]
ALL_PREFIXES: tuple[str, ...] = tuple(p for _, ps, _ in PROVISION_GROUPS for p in ps)

DOTATION_PREFIX = "69"
REPRISE_PREFIX = "79"
TOLERANCE = Decimal("100")


@dataclass
class ProvisionRow:
    account_code: str
    account_name: str
    group_key: str
    group_label: str
    opening_xaf: Decimal
    additions_xaf: Decimal = Decimal("0")       # dotations (contrepartie 69XX)
    reversals_xaf: Decimal = Decimal("0")       # reprises  (contrepartie 79XX)
    unclassified_xaf: Decimal = Decimal("0")    # mouvements sans 69XX/79XX (net, crédit-positif)
    expected_closing_xaf: Decimal = Decimal("0")
    actual_closing_xaf: Decimal = Decimal("0")
    variance_xaf: Decimal = Decimal("0")
    entries: list[dict] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "ALIGNED" if abs(self.variance_xaf) <= TOLERANCE else "DISCREPANCY"


def analyze_provisions(tb_lines: Iterable[Any], gl_lines: Iterable[Any]) -> tuple[list[ProvisionRow], dict]:
    """`gl_lines` must be ALL lines of the GL (the counterpart 69XX/79XX lines
    are needed to classify each entry) with a `piece_number` attribute."""
    # 1. Classify each journal entry by the presence of a 69XX / 79XX line.
    entry_kind: dict[str, str] = {}
    for l in gl_lines:
        code = str(l.account_code or "").strip()
        piece = str(getattr(l, "piece_number", "") or "")
        if not piece:
            continue
        if code.startswith(DOTATION_PREFIX):
            entry_kind[piece] = "DOTATION"
        elif code.startswith(REPRISE_PREFIX) and entry_kind.get(piece) != "DOTATION":
            entry_kind[piece] = "REPRISE"

    # 2. Opening / closing per provision account, from the trial balance
    #    (provisions are credit-nature → crédit-positif).
    opening: dict[str, Decimal] = {}
    closing: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    for tb in tb_lines:
        code = str(tb.account_code).strip()
        if not code.startswith(ALL_PREFIXES):
            continue
        opening[code] = (Decimal(str(tb.opening_credit or 0)) - Decimal(str(tb.opening_debit or 0)))
        closing[code] = (Decimal(str(tb.closing_credit or 0)) - Decimal(str(tb.closing_debit or 0)))
        names[code] = tb.account_name or ""

    # 3. Movements on the provision accounts, split by entry kind.
    adds: dict[str, Decimal] = defaultdict(Decimal)
    revs: dict[str, Decimal] = defaultdict(Decimal)
    unc: dict[str, Decimal] = defaultdict(Decimal)
    detail: dict[str, list[dict]] = defaultdict(list)
    for l in gl_lines:
        code = str(l.account_code or "").strip()
        if not code.startswith(ALL_PREFIXES):
            continue
        names.setdefault(code, l.account_name or "")
        piece = str(getattr(l, "piece_number", "") or "")
        d = Decimal(str(l.debit or 0))
        c = Decimal(str(l.credit or 0))
        net_credit = c - d                     # crédit-positif : + = dotation
        kind = entry_kind.get(piece)
        if kind == "DOTATION":
            adds[code] += net_credit
        elif kind == "REPRISE":
            revs[code] += -net_credit          # reprise = débit du compte → positif
        else:
            unc[code] += net_credit
        detail[code].append({
            "piece_number": piece,
            "entry_date": str(getattr(l, "entry_date", "") or "") or None,
            "libelle": (getattr(l, "libelle", None) or "")[:200],
            "debit_xaf": float(d), "credit_xaf": float(c),
            "kind": kind or "NON_CLASSE",
        })

    rows: list[ProvisionRow] = []
    for code in sorted(set(list(opening.keys()) + list(adds.keys()) + list(revs.keys()) + list(unc.keys()))):
        gk, gl_label = "autres", "Autres provisions"
        for key, prefixes, label in PROVISION_GROUPS:
            if code.startswith(prefixes):
                gk, gl_label = key, label
                break
        r = ProvisionRow(
            account_code=code, account_name=names.get(code, ""),
            group_key=gk, group_label=gl_label,
            opening_xaf=opening.get(code, Decimal("0")),
            additions_xaf=adds.get(code, Decimal("0")),
            reversals_xaf=revs.get(code, Decimal("0")),
            unclassified_xaf=unc.get(code, Decimal("0")),
            actual_closing_xaf=closing.get(code, Decimal("0")),
            entries=sorted(detail.get(code, []), key=lambda e: (e["entry_date"] or "", e["piece_number"])),
        )
        r.expected_closing_xaf = r.opening_xaf + r.additions_xaf - r.reversals_xaf
        r.variance_xaf = r.actual_closing_xaf - r.expected_closing_xaf
        rows.append(r)

    summary = {
        "opening_xaf": float(sum((r.opening_xaf for r in rows), Decimal("0"))),
        "additions_xaf": float(sum((r.additions_xaf for r in rows), Decimal("0"))),
        "reversals_xaf": float(sum((r.reversals_xaf for r in rows), Decimal("0"))),
        "unclassified_xaf": float(sum((r.unclassified_xaf for r in rows), Decimal("0"))),
        "expected_closing_xaf": float(sum((r.expected_closing_xaf for r in rows), Decimal("0"))),
        "actual_closing_xaf": float(sum((r.actual_closing_xaf for r in rows), Decimal("0"))),
        "variance_xaf": float(sum((r.variance_xaf for r in rows), Decimal("0"))),
        "account_count": len(rows),
        "discrepancy_count": sum(1 for r in rows if r.status == "DISCREPANCY"),
    }
    return rows, summary


def serialize(rows: list[ProvisionRow]) -> list[dict]:
    return [
        {
            "account_code": r.account_code, "account_name": r.account_name,
            "group_key": r.group_key, "group_label": r.group_label,
            "opening_xaf": float(r.opening_xaf),
            "additions_xaf": float(r.additions_xaf),
            "reversals_xaf": float(r.reversals_xaf),
            "unclassified_xaf": float(r.unclassified_xaf),
            "expected_closing_xaf": float(r.expected_closing_xaf),
            "actual_closing_xaf": float(r.actual_closing_xaf),
            "variance_xaf": float(r.variance_xaf),
            "status": r.status,
            "entries": r.entries[:200],
        }
        for r in rows
    ]
