"""Règlements en espèces — CGI Cameroun, Art. 7 bis.

Rule: any charge ≥ 100 000 FCFA HT settled in cash (compte 57X) is
NOT deductible from the corporate income tax base.

Tests applied per the audit plan signed off by the user:

  - PER-LINE  : each individual class-6 debit > 100 000 FCFA in a pièce that
                also credits a 57X account is flagged.
  - PER-PIECE : the sum of ALL class-6 debits in a pièce that credits a 57X
                account is also tested against the threshold. This catches
                schemes that split a charge into several < 100K lines on
                the same payment.

Both are surfaced. Edge cases (transfers between cash accounts, refunds,
petty-cash replenishment from bank) are deliberately excluded — see
`_is_excluded`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    AuditCase, CashPaymentAssessment, Dataset, DatasetKind, DatasetStatus,
    JournalEntry, JournalEntryLine,
)


THRESHOLD_XAF = Decimal("100000")  # CGI Cameroun, Art. 7 bis — fixed
CASH_ACCOUNT_PREFIX = "57"          # All 57XXX accounts

# ── Lettre DGI 5333/MINFI/DGI/LC/L du 04 août 2011 ────────────────────────────
# Exceptions explicites au contrôle Art. 7 bis :
EXCEPTION_PREFIXES: dict[str, str] = {
    "661": "SALARY", "662": "SALARY", "663": "SALARY", "664": "SALARY",
    "665": "SALARY", "666": "SALARY", "667": "SALARY", "668": "SALARY",
    "6384": "MISSION",                  # Missions
    "6581": "ADMIN_FEE",                # Jetons de présence / indemnités administrateurs
}

# Taux fiscaux applicables (Art. 17 CGI : IS 30 % + 10 % CAC = 33 %)
IS_RATE_PCT = Decimal("33.0")      # IS additionnel si charge rattachée à l'exercice
IRCM_RATE_PCT = Decimal("16.5")    # IRCM (toujours dû, distribution déguisée)

# Debit-side classes that, when funded by cash, must be tested under Art. 7 bis.
# Includes balance-sheet uses of cash (class 1, 2, 3, 4) because they ultimately
# flow through the P&L (depreciation, COGS, expense reclassification) and the
# non-deductibility rule attaches to the underlying cash outflow regardless of
# the immediate accounting entry.
DEBIT_PREFIXES_TESTED: tuple[str, ...] = ("1", "2", "3", "4", "6")

# Map a SYSCOHADA class prefix to a human-readable tag.
_CLASS_LABELS = {
    "1": "Capitaux / dettes",
    "2": "Immobilisations",
    "3": "Stocks",
    "4": "Tiers",
    "6": "Charges",
}


def _account_class(account: str | None) -> str:
    if not account:
        return "?"
    return account[0]


# Cameroon NIU pattern (M021xxxxxxxxxX / P0xxxxxxxxxX) — see routers/taxpayers.py
NIU_RE = re.compile(r"\b([MPmp]\d{9,12}[A-Z])\b")


@dataclass
class CashLine:
    pi_number: str
    pi_date: str | None        # ISO date string
    line_number: int
    account_code: str
    account_name: str | None
    libelle: str | None
    amount_xaf: Decimal         # the qualifying debit amount (class 1/2/3/4 or class 6 HT)
    counter_supplier_niu: str | None
    counter_supplier_name: str | None
    tag: str                    # CONFIRMED | LIKELY | REVIEW
    per_piece_total_xaf: Decimal  # sum of qualifying debits in this pièce
    per_piece_breach: bool       # True when per-pièce sum > threshold
    cash_credit_total_xaf: Decimal  # Σ 57X credit on the same pièce
    cash_credit_breach: bool        # True when the cash credit itself > threshold
    account_class_code: str      # "1" / "2" / "3" / "4" / "6"
    account_class_label: str     # localized class label
    # ── Lettre DGI 2011 + bifurcation pénalité ───────────────────────────────
    excluded: bool = False
    exclusion_kind: str | None = None       # SALARY | MISSION | ADMIN_FEE | OTHER
    current_year: str = "UNKNOWN"           # YES | NO | UNKNOWN
    current_year_source: str = "AUTO"       # AUTO | MANUAL
    current_year_confidence: str = "LOW"    # HIGH | MEDIUM | LOW
    current_year_reason: str = ""
    similar_entries: list[dict[str, Any]] = field(default_factory=list)
    is_supplement_xaf: Decimal = Decimal("0")
    ircm_xaf: Decimal = Decimal("0")
    total_penalty_xaf: Decimal = Decimal("0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pi_number": self.pi_number,
            "pi_date": self.pi_date,
            "line_number": self.line_number,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "libelle": self.libelle,
            "amount_xaf": float(self.amount_xaf),
            "counter_supplier_niu": self.counter_supplier_niu,
            "counter_supplier_name": self.counter_supplier_name,
            "tag": self.tag,
            "per_piece_total_xaf": float(self.per_piece_total_xaf),
            "per_piece_breach": self.per_piece_breach,
            "cash_credit_total_xaf": float(self.cash_credit_total_xaf),
            "cash_credit_breach": self.cash_credit_breach,
            "account_class_code": self.account_class_code,
            "account_class_label": self.account_class_label,
            "estimated_reintegration_xaf": float(self.amount_xaf if self.current_year == "YES" and not self.excluded else 0),
            "excluded": self.excluded,
            "exclusion_kind": self.exclusion_kind,
            "current_year": self.current_year,
            "current_year_source": self.current_year_source,
            "current_year_confidence": self.current_year_confidence,
            "current_year_reason": self.current_year_reason,
            "similar_entries": self.similar_entries,
            "is_supplement_xaf": float(self.is_supplement_xaf),
            "ircm_xaf": float(self.ircm_xaf),
            "total_penalty_xaf": float(self.total_penalty_xaf),
        }


@dataclass
class SupplierAggregate:
    key: str                    # the grouping key (NIU or libellé prefix)
    counter_supplier_niu: str | None
    counter_supplier_name: str
    line_count: int
    total_amount_xaf: Decimal
    pieces: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "counter_supplier_niu": self.counter_supplier_niu,
            "counter_supplier_name": self.counter_supplier_name,
            "line_count": self.line_count,
            "piece_count": len(self.pieces),
            "total_amount_xaf": float(self.total_amount_xaf),
            "estimated_reintegration_xaf": float(self.total_amount_xaf),
        }


@dataclass
class ByClassAggregate:
    class_code: str
    class_label: str
    line_count: int
    total_amount_xaf: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_code": self.class_code,
            "class_label": self.class_label,
            "line_count": self.line_count,
            "total_amount_xaf": float(self.total_amount_xaf),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _is_class(account: str | None, prefix: str) -> bool:
    return bool(account) and account.startswith(prefix)


def _is_excluded_libelle(lib: str | None) -> bool:
    """Drop obviously non-charge payments visible from the libellé."""
    if not lib:
        return False
    n = lib.lower()
    for kw in ("transfert caisse", "transfert bancaire", "alimentation caisse",
               "approvisionnement caisse", "virement interne"):
        if kw in n:
            return True
    return False


def _extract_niu(text: str | None) -> str | None:
    if not text:
        return None
    m = NIU_RE.search(text)
    if m:
        return m.group(1).upper()
    return None


def _supplier_name_from_libelle(lib: str | None) -> str:
    """Best-effort supplier name from the libellé.

    Strips trailing pièce numbers and dates, drops the NIU itself when present,
    and returns the first ~60 chars.
    """
    if not lib:
        return ""
    s = NIU_RE.sub("", lib).strip()
    # Drop trailing 'FAC 1234' / 'F 1234' patterns
    s = re.sub(r"\b(F|FA|FAC|FACT|FACTURE|INV)\s*[°N]?\.?\s*\d+\b", "", s, flags=re.I).strip()
    # Drop ISO and FR dates
    s = re.sub(r"\b\d{2,4}[/.-]\d{1,2}[/.-]\d{1,4}\b", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip(" -:,;")
    return s[:60] or lib[:60]


def _classify(amount: Decimal, libelle: str | None) -> str:
    if amount <= THRESHOLD_XAF:
        return "REVIEW"  # not even above threshold, surfaced for transparency
    n = (libelle or "").lower()
    invoice_hint = any(k in n for k in ("facture", "fac", "invoice", "fact"))
    borderline = (amount >= THRESHOLD_XAF * Decimal("0.95")
                  and amount <= THRESHOLD_XAF * Decimal("1.10"))
    if borderline:
        return "REVIEW"
    if invoice_hint:
        return "LIKELY"
    return "CONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# Lettre DGI 2011 — exceptions automatiques + matching exercice/non-exercice
# ─────────────────────────────────────────────────────────────────────────────


def _classify_exception(account_code: str | None) -> str | None:
    """Return SALARY / MISSION / ADMIN_FEE / None per lettre DGI 04/08/2011."""
    if not account_code:
        return None
    for prefix, kind in EXCEPTION_PREFIXES.items():
        if account_code.startswith(prefix):
            return kind
    return None


def _build_charges_index(
    all_rows: list[tuple[JournalEntryLine, JournalEntry]],
) -> list[dict[str, Any]]:
    """Index every class-6 (charge) line — used to find matches for cash payments
    on balance-sheet accounts.
    """
    out: list[dict[str, Any]] = []
    for line, entry in all_rows:
        acc = line.account_code or ""
        if not acc.startswith("6"):
            continue
        amount = Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        if amount <= 0:
            continue
        out.append({
            "id": str(line.id),
            "piece_number": entry.piece_number,
            "line_number": line.line_number,
            "account_code": acc,
            "account_name": line.account_name,
            "libelle": line.libelle,
            "libelle_low": (line.libelle or "").lower(),
            "supplier": (_supplier_name_from_libelle(line.libelle) or "").lower()[:40],
            "niu": _extract_niu(line.libelle),
            "amount": amount,
            "year": entry.entry_date.year if entry.entry_date else None,
            "date": entry.entry_date.isoformat() if entry.entry_date else None,
        })
    return out


def _find_similar_charges(
    target_libelle: str | None,
    target_amount: Decimal,
    charges_index: list[dict[str, Any]],
    max_matches: int = 5,
) -> list[tuple[int, dict[str, Any], list[str]]]:
    """Score each candidate charge against the target. Returns top N (score, candidate, reasons)."""
    target_sup = (_supplier_name_from_libelle(target_libelle) or "").lower()[:40]
    target_niu = _extract_niu(target_libelle)
    target_lib_low = (target_libelle or "").lower()

    scored: list[tuple[int, dict[str, Any], list[str]]] = []
    for c in charges_index:
        score = 0
        reasons: list[str] = []
        # NIU exact match — strongest signal
        if target_niu and c["niu"] == target_niu:
            score += 50
            reasons.append("NIU identique")
        # Supplier name match (either way contains)
        if target_sup and c["supplier"]:
            if target_sup == c["supplier"]:
                score += 30
                reasons.append("fournisseur identique")
            elif len(target_sup) >= 5 and (target_sup in c["libelle_low"] or c["supplier"] in target_lib_low):
                score += 20
                reasons.append("fournisseur correspondant (libellé)")
        # Amount match
        if target_amount > 0:
            if c["amount"] == target_amount:
                score += 40
                reasons.append("montant identique")
            else:
                delta = abs(c["amount"] - target_amount) / target_amount
                if delta < Decimal("0.01"):
                    score += 25
                    reasons.append("montant ≈ (±1%)")
                elif delta < Decimal("0.05"):
                    score += 12
                    reasons.append("montant ≈ (±5%)")
        if score > 0:
            scored.append((score, c, reasons))
    scored.sort(key=lambda x: -x[0])
    return scored[:max_matches]


def _charge_summary(candidate: dict[str, Any], reasons: list[str], score: int) -> dict[str, Any]:
    return {
        "piece_number": candidate["piece_number"],
        "line_number": candidate["line_number"],
        "account_code": candidate["account_code"],
        "account_name": candidate["account_name"],
        "libelle": candidate["libelle"],
        "amount_xaf": float(candidate["amount"]),
        "year": candidate["year"],
        "date": candidate["date"],
        "match_score": score,
        "match_reasons": reasons,
    }


def _suggest_current_year(
    account_code: str,
    libelle: str | None,
    amount: Decimal,
    fiscal_year: int | None,
    charges_index: list[dict[str, Any]],
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Return (decision YES/NO, confidence HIGH/MEDIUM/LOW, reason, top similar charges)."""
    acc = account_code or ""
    # Règles dures
    if acc.startswith("6"):
        return ("YES", "HIGH", "Compte de charge classe 6 — rattachée à l'exercice par construction.", [])
    if acc.startswith("462") or acc.startswith("4621") or acc.startswith("4711"):
        return ("NO", "HIGH", "Compte courant associé — mouvement de capital, hors charge déductible de l'exercice.", [])
    if acc.startswith("16") or acc.startswith("17"):
        return ("NO", "HIGH", "Remboursement d'emprunt — la charge se matérialise via les intérêts (compte 67).", [])
    if acc.startswith("2"):
        return ("NO", "HIGH", "Compte d'immobilisation — la déduction transite par l'amortissement.", [])

    # Class 1, 3, 4 (notamment 401/408 fournisseurs) — analyse par matching GL
    if acc.startswith("4") or acc.startswith("1") or acc.startswith("3"):
        matches = _find_similar_charges(libelle, amount, charges_index)
        in_year = [m for m in matches if m[1]["year"] == fiscal_year]
        prior = [m for m in matches if m[1]["year"] is not None and m[1]["year"] < (fiscal_year or 0)]
        if in_year:
            best_score = in_year[0][0]
            confidence = "HIGH" if best_score >= 70 else ("MEDIUM" if best_score >= 40 else "LOW")
            top_reasons = ", ".join(in_year[0][2])
            reason = (
                f"{len(in_year)} charge(s) similaire(s) trouvée(s) dans l'exercice "
                f"({top_reasons}). → présomption de paiement d'une charge de l'exercice."
            )
            return ("YES", confidence, reason, [_charge_summary(c, r, s) for s, c, r in matches[:5]])
        if prior:
            return ("NO", "MEDIUM",
                    f"{len(prior)} charge(s) similaire(s) trouvée(s) uniquement en exercice(s) antérieur(s) "
                    f"— présomption de paiement d'une dette ancienne.",
                    [_charge_summary(c, r, s) for s, c, r in matches[:5]])
        return ("NO", "LOW",
                "Aucune charge similaire dans le GL — présomption de dette antérieure ou paiement non-courant.",
                [])
    return ("UNKNOWN", "LOW", "Compte non couvert par les règles automatiques — décision auditeur requise.", [])


# ─────────────────────────────────────────────────────────────────────────────
# Main analysis
# ─────────────────────────────────────────────────────────────────────────────


def analyze_cash_payments(
    db: Session,
    case_id: UUID,
) -> dict[str, Any]:
    """Run the full cash-payments analysis against the latest PARSED GL."""
    gl_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.GENERAL_LEDGER,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if not gl_ds:
        return {
            "threshold_xaf": float(THRESHOLD_XAF),
            "source_dataset_id": None,
            "source_filename": None,
            "lines": [],
            "by_supplier": [],
            "summary": None,
            "note": (
                "Aucun grand-livre chargé. Importez-le dans Données › Grand-livre "
                "pour activer ce contrôle."
            ),
        }

    # Pull every line of this GL — efficient enough for hundreds of thousands
    # of rows on a 1-GB server; a future optimization can stream by chunks.
    lines = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .order_by(JournalEntry.piece_number, JournalEntryLine.line_number)
        .all()
    )

    # ── Group lines by JOURNAL ENTRY (piece_number is the unique key) ──────
    # Per pièce we track:
    #   - cash_credit_total  : Σ credits to 57X
    #   - qualifying_debits  : every debit > 0 to class 1/2/3/4/6
    by_piece: dict[str, dict[str, Any]] = {}
    for line, entry in lines:
        key = f"{entry.id}"
        bucket = by_piece.setdefault(key, {
            "entry": entry,
            "cash_credit_total": Decimal("0"),
            "qualifying_debits": [],   # list of JournalEntryLine
        })
        if _is_class(line.account_code, CASH_ACCOUNT_PREFIX):
            credit_amount = Decimal(str(line.credit or 0))
            if credit_amount > 0:
                bucket["cash_credit_total"] += credit_amount
        else:
            debit_amount = Decimal(str(line.debit or 0))
            if debit_amount > 0 and any(
                _is_class(line.account_code, p) for p in DEBIT_PREFIXES_TESTED
            ):
                bucket["qualifying_debits"].append(line)

    out_lines: list[CashLine] = []
    lines_tested = 0

    for key, bucket in by_piece.items():
        cash_credit_total: Decimal = bucket["cash_credit_total"]
        debits: list[JournalEntryLine] = bucket["qualifying_debits"]
        # Pièce must (a) credit cash, and (b) have at least one qualifying debit
        if cash_credit_total <= 0 or not debits:
            continue
        entry: JournalEntry = bucket["entry"]

        # Two independent triggers per the audit plan:
        #   - cash_credit_breach : the cash credit on the pièce > 100K
        #   - per_piece_breach   : the sum of qualifying debits > 100K
        cash_credit_breach = cash_credit_total > THRESHOLD_XAF
        per_piece_total = sum(
            (Decimal(str(d.debit or 0)) for d in debits),
            Decimal("0"),
        )
        per_piece_breach = per_piece_total > THRESHOLD_XAF

        lines_tested += len(debits)

        for d in debits:
            amount = Decimal(str(d.debit or 0))
            if amount <= 0:
                continue
            if _is_excluded_libelle(d.libelle):
                continue

            # A debit is surfaced when ANY of these triggers fire:
            #   - the line itself > 100K
            #   - the per-pièce sum of qualifying debits > 100K
            #   - the cash credit on the pièce > 100K
            per_line_breach = amount > THRESHOLD_XAF
            if not (per_line_breach or per_piece_breach or cash_credit_breach):
                continue

            niu = _extract_niu(d.libelle) or _extract_niu(d.account_name)
            supplier_name = _supplier_name_from_libelle(d.libelle) or d.account_name or ""
            cls = _account_class(d.account_code)

            out_lines.append(CashLine(
                pi_number=entry.piece_number,
                pi_date=entry.entry_date.isoformat() if entry.entry_date else None,
                line_number=d.line_number,
                account_code=d.account_code,
                account_name=d.account_name,
                libelle=d.libelle,
                amount_xaf=amount,
                counter_supplier_niu=niu,
                counter_supplier_name=supplier_name or None,
                tag=_classify(amount, d.libelle),
                per_piece_total_xaf=per_piece_total,
                per_piece_breach=per_piece_breach,
                cash_credit_total_xaf=cash_credit_total,
                cash_credit_breach=cash_credit_breach,
                account_class_code=cls,
                account_class_label=_CLASS_LABELS.get(cls, cls),
            ))

    # ── Enrichissement « Lettre DGI 2011 » : exceptions + matching + bifurcation ──
    case = db.get(AuditCase, case_id)
    fiscal_year = getattr(case, "fiscal_year", None) or (
        getattr(case, "starting_year", None) or None
    )
    charges_index = _build_charges_index(lines)
    # Overrides indexed by (piece, line)
    overrides = {
        (a.piece_number, a.line_number): a
        for a in db.query(CashPaymentAssessment).filter(
            CashPaymentAssessment.audit_case_id == case_id).all()
    }

    for cl in out_lines:
        ov = overrides.get((cl.pi_number, cl.line_number))

        # 1) Exclusions Lettre DGI 2011 — auto, surchargeables via override
        auto_exc = _classify_exception(cl.account_code)
        if ov and ov.excluded:
            cl.excluded = True
            cl.exclusion_kind = ov.exclusion_kind.value if ov.exclusion_kind else (auto_exc or "OTHER")
        elif auto_exc:
            cl.excluded = True
            cl.exclusion_kind = auto_exc

        # 2) Suggestion automatique du rattachement à l'exercice
        if cl.excluded:
            cl.current_year = "NO"
            cl.current_year_source = "AUTO"
            cl.current_year_confidence = "HIGH"
            cl.current_year_reason = "Hors périmètre Art. 7 bis (Lettre DGI 04/08/2011)."
            cl.similar_entries = []
        else:
            decision, confidence, reason, sims = _suggest_current_year(
                cl.account_code, cl.libelle, cl.amount_xaf, fiscal_year, charges_index,
            )
            cl.current_year = decision
            cl.current_year_source = "AUTO"
            cl.current_year_confidence = confidence
            cl.current_year_reason = reason
            cl.similar_entries = sims

        # 3) Override manuel auditeur
        if ov and ov.current_year_decision is not None:
            cl.current_year = ov.current_year_decision.value
            cl.current_year_source = "MANUAL"
            cl.current_year_confidence = "HIGH"
            if ov.decision_reason:
                cl.current_year_reason = ov.decision_reason

        # 4) Bifurcation des pénalités
        if cl.excluded:
            cl.is_supplement_xaf = Decimal("0")
            cl.ircm_xaf = Decimal("0")
        else:
            cl.is_supplement_xaf = (
                cl.amount_xaf * IS_RATE_PCT / 100
                if cl.current_year == "YES" else Decimal("0")
            )
            cl.ircm_xaf = cl.amount_xaf * IRCM_RATE_PCT / 100
        cl.total_penalty_xaf = cl.is_supplement_xaf + cl.ircm_xaf

    # Sort: CONFIRMED first, then by amount desc
    tag_rank = {"CONFIRMED": 0, "LIKELY": 1, "REVIEW": 2}
    out_lines.sort(key=lambda l: (tag_rank.get(l.tag, 9), -float(l.amount_xaf)))

    # ── Per-supplier roll-up ───────────────────────────────────────────────
    agg: dict[str, SupplierAggregate] = {}
    for cl in out_lines:
        if cl.tag == "REVIEW":
            continue
        key2 = cl.counter_supplier_niu or (cl.counter_supplier_name or "—").lower()[:30]
        sa = agg.get(key2)
        if sa is None:
            sa = SupplierAggregate(
                key=key2,
                counter_supplier_niu=cl.counter_supplier_niu,
                counter_supplier_name=cl.counter_supplier_name or "—",
                line_count=0,
                total_amount_xaf=Decimal("0"),
            )
            agg[key2] = sa
        sa.line_count += 1
        sa.total_amount_xaf += cl.amount_xaf
        sa.pieces.add(cl.pi_number)

    suppliers = sorted(agg.values(), key=lambda s: -float(s.total_amount_xaf))

    # ── Per-debit-class roll-up (new) ──────────────────────────────────────
    by_class: dict[str, ByClassAggregate] = {}
    for cl in out_lines:
        if cl.tag == "REVIEW":
            continue
        bc = by_class.get(cl.account_class_code)
        if bc is None:
            bc = ByClassAggregate(
                class_code=cl.account_class_code,
                class_label=cl.account_class_label,
                line_count=0,
                total_amount_xaf=Decimal("0"),
            )
            by_class[cl.account_class_code] = bc
        bc.line_count += 1
        bc.total_amount_xaf += cl.amount_xaf

    class_breakdown = sorted(by_class.values(), key=lambda c: c.class_code)

    # Σ pénalités selon décision rattachement à l'exercice
    excluded_lines = [l for l in out_lines if l.excluded]
    active_lines = [l for l in out_lines if not l.excluded and l.tag != "REVIEW"]
    current_year_yes = [l for l in active_lines if l.current_year == "YES"]
    current_year_no = [l for l in active_lines if l.current_year == "NO"]

    summary = {
        "threshold_xaf": float(THRESHOLD_XAF),
        "debit_classes_tested": list(DEBIT_PREFIXES_TESTED),
        "lines_tested_count": lines_tested,
        "confirmed_count": sum(1 for l in out_lines if l.tag == "CONFIRMED"),
        "likely_count":    sum(1 for l in out_lines if l.tag == "LIKELY"),
        "review_count":    sum(1 for l in out_lines if l.tag == "REVIEW"),
        "supplier_count": len(suppliers),
        "cash_credit_breach_piece_count": sum(
            1 for b in by_piece.values()
            if b["cash_credit_total"] > THRESHOLD_XAF and b["qualifying_debits"]
        ),
        "total_amount_xaf": float(
            sum((l.amount_xaf for l in active_lines), Decimal("0"))
        ),
        # Bifurcation Lettre DGI 2011
        "excluded_count": len(excluded_lines),
        "excluded_by_kind": {
            "SALARY": sum(1 for l in excluded_lines if l.exclusion_kind == "SALARY"),
            "MISSION": sum(1 for l in excluded_lines if l.exclusion_kind == "MISSION"),
            "ADMIN_FEE": sum(1 for l in excluded_lines if l.exclusion_kind == "ADMIN_FEE"),
            "OTHER": sum(1 for l in excluded_lines if l.exclusion_kind == "OTHER"),
        },
        "current_year_yes_count": len(current_year_yes),
        "current_year_no_count": len(current_year_no),
        "current_year_unknown_count": sum(
            1 for l in active_lines if l.current_year == "UNKNOWN"
        ),
        "reintegration_xaf": float(
            sum((l.amount_xaf for l in current_year_yes), Decimal("0"))
        ),
        "is_supplement_xaf": float(
            sum((l.is_supplement_xaf for l in active_lines), Decimal("0"))
        ),
        "ircm_xaf": float(
            sum((l.ircm_xaf for l in active_lines), Decimal("0"))
        ),
        "total_penalty_xaf": float(
            sum((l.total_penalty_xaf for l in active_lines), Decimal("0"))
        ),
        "is_rate_pct": float(IS_RATE_PCT),
        "ircm_rate_pct": float(IRCM_RATE_PCT),
        # legacy field kept for backward compatibility (= rate × réintégration)
        "estimated_reintegration_xaf": float(
            sum((l.amount_xaf for l in current_year_yes), Decimal("0"))
        ),
    }

    return {
        "threshold_xaf": float(THRESHOLD_XAF),
        "debit_classes_tested": list(DEBIT_PREFIXES_TESTED),
        "source_dataset_id": str(gl_ds.id),
        "source_filename": gl_ds.original_filename,
        "fiscal_year": fiscal_year,
        "lines": [l.to_dict() for l in out_lines],
        "by_supplier": [s.to_dict() for s in suppliers],
        "by_class": [c.to_dict() for c in class_breakdown],
        "summary": summary,
        "legal_reference": (
            "CGI Cameroun, Art. 7 bis + Art. 8 — Lettre DGI N° 5333/MINFI/DGI/LC/L "
            "du 04/08/2011 (exceptions salaires/missions/jetons CA)"
        ),
    }
