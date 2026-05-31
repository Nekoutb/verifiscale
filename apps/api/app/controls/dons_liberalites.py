"""Dons et libéralités — CGI Cameroun, Art. 7.

Principle: dons et libéralités are **not deductible**.
Exception: versements à des œuvres ou organismes d'intérêt général à caractère
philanthropique, éducatif, sportif, scientifique, social, culturel ou familial
situés au Cameroun, dans la limite de **5‰ du chiffre d'affaires HT** de
l'exercice.

Pipeline:
  1. Pull GL lines from donation-bearing accounts (658X + 6713 + 838X).
  2. Score each line VERT / ORANGE / ROUGE on confidence of beneficiary
     identification from the libellé.
  3. Apply persisted DonationEvidence verdicts (per-line override from
     uploaded justificatifs or auditor decision).
  4. Compute CA HT from the latest TB (class 7 net) — fallback to GL.
  5. Aggregate: total_engagé / total_éligible / total_non_éligible
     vs plafond 5‰ × CA HT → réintégration.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    Dataset,
    DatasetKind,
    DatasetStatus,
    JournalEntry,
    JournalEntryLine,
    TrialBalanceLine,
    DonationEvidence,
    DonationGroup,
    DonationGroupLine,
    DonationLibelleAnalysis,
    DonationVerdict,
    AiConfidence,
)
from app.services.dons_ai_analyzer import analyze_libelle, libelle_hash


# ── Configuration ────────────────────────────────────────────────────────────

# Comptes SYSCOHADA Révisé clairement dédiés aux dons/libéralités
DONATION_ACCOUNT_PREFIXES: tuple[str, ...] = ("6582", "6583", "6713")
# Comptes susceptibles d'inclure des dons (à examiner ligne par ligne)
DONATION_CANDIDATE_PREFIXES: tuple[str, ...] = ("6588", "8388")

# Plafond légal — 5‰ du CA HT
PLAFOND_PER_MILLE = Decimal("5")          # 5 / 1000
PLAFOND_DIVISOR   = Decimal("1000")

# CA HT = somme nette de la classe 7 (produits) — Ventes biens & services
REVENUE_ACCOUNT_PREFIXES: tuple[str, ...] = ("70",)
# Élargir à 70-77 si nécessaire (le compte 70 suffit pour le CA d'exploitation)

# Cameroon NIU pattern
NIU_RE = re.compile(r"\b([MPmp]\d{9,12}[A-Z])\b")

# Mots-clés signalant un risque "non-éligible" dès le libellé
NON_ELIGIBLE_KEYWORDS = (
    "parti politique", "campagne electorale", "campagne électorale",
    "associe", "associé", "dirigeant", "gerant", "gérant",
    "etranger", "étranger",
)

# Mots-clés caractéristiques d'œuvres d'intérêt général
IG_HINT_KEYWORDS = (
    "orphelinat", "hopital", "hôpital", "ecole", "école", "universite",
    "université", "fondation", "ong", "association", "œuvre", "oeuvre",
    "croix-rouge", "croix rouge", "unicef",
)


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class DonationLine:
    piece_number: str
    entry_date: str | None
    line_number: int
    account_code: str
    account_name: str | None
    libelle: str | None
    amount_xaf: Decimal
    beneficiary_niu: str | None
    beneficiary_name_guess: str | None
    confidence: str           # VERT | ORANGE | ROUGE
    verdict: str              # ELIGIBLE | NON_ELIGIBLE | A_REINSTRUIRE
    verdict_reason: str
    verdict_source: str       # AUTO_GL | DOC_EXTRACTED | MANUAL_OVERRIDE
    has_evidence: bool
    evidence_count: int
    account_category: str     # "DON_DIRECT" | "DON_HAO" | "DON_CANDIDATE"
    # ── Analyse IA Claude ────────────────────────────────────────────────
    ai_verdict: str = "A_REINSTRUIRE"
    ai_confidence: str = "LOW"
    ai_reason: str = ""
    ai_indicators: list[str] = field(default_factory=list)
    # ── Groupement par nature ────────────────────────────────────────────
    group_id: str | None = None
    group_name: str | None = None
    group_verdict: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "piece_number": self.piece_number,
            "entry_date": self.entry_date,
            "line_number": self.line_number,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "libelle": self.libelle,
            "amount_xaf": float(self.amount_xaf),
            "beneficiary_niu": self.beneficiary_niu,
            "beneficiary_name_guess": self.beneficiary_name_guess,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "verdict_source": self.verdict_source,
            "has_evidence": self.has_evidence,
            "evidence_count": self.evidence_count,
            "account_category": self.account_category,
            "ai_verdict": self.ai_verdict,
            "ai_confidence": self.ai_confidence,
            "ai_reason": self.ai_reason,
            "ai_indicators": self.ai_indicators,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "group_verdict": self.group_verdict,
        }


@dataclass
class BeneficiaryAggregate:
    key: str
    name: str
    niu: str | None
    line_count: int
    total_xaf: Decimal
    eligible_xaf: Decimal
    non_eligible_xaf: Decimal
    to_reinstruct_xaf: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "niu": self.niu,
            "line_count": self.line_count,
            "total_xaf": float(self.total_xaf),
            "eligible_xaf": float(self.eligible_xaf),
            "non_eligible_xaf": float(self.non_eligible_xaf),
            "to_reinstruct_xaf": float(self.to_reinstruct_xaf),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _starts_with_any(account: str | None, prefixes: tuple[str, ...]) -> bool:
    if not account:
        return False
    return any(account.startswith(p) for p in prefixes)


def _account_category(account: str | None) -> str:
    if not account:
        return "DON_CANDIDATE"
    if account.startswith("6713") or account.startswith("8388"):
        return "DON_HAO"
    if account.startswith("6582") or account.startswith("6583"):
        return "DON_DIRECT"
    return "DON_CANDIDATE"


def _extract_niu(text: str | None) -> str | None:
    if not text:
        return None
    m = NIU_RE.search(text)
    return m.group(1).upper() if m else None


def _beneficiary_guess(libelle: str | None, account_name: str | None) -> str | None:
    """Best-effort beneficiary name out of the libellé."""
    src = (libelle or "").strip() or (account_name or "").strip()
    if not src:
        return None
    s = NIU_RE.sub("", src).strip()
    # Drop common GL noise
    s = re.sub(r"\b(don|liberalite|libéralité|versement|sub\.?|subvention)\b",
               "", s, flags=re.I)
    s = re.sub(r"\b\d{2,4}[/.-]\d{1,2}[/.-]\d{1,4}\b", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -:,;")
    return s[:80] or None


def _score_confidence(
    libelle: str | None,
    account_name: str | None,
    niu: str | None,
    name_guess: str | None,
) -> str:
    """VERT  = NIU + name; ORANGE = name only; ROUGE = nothing usable."""
    if niu and name_guess:
        return "VERT"
    if name_guess and len(name_guess) >= 6:
        return "ORANGE"
    return "ROUGE"


def _libelle_signals(libelle: str | None) -> tuple[bool, bool]:
    """Returns (has_non_eligible_hint, has_ig_hint)."""
    if not libelle:
        return (False, False)
    low = libelle.lower()
    non_elig = any(k in low for k in NON_ELIGIBLE_KEYWORDS)
    ig_hint = any(k in low for k in IG_HINT_KEYWORDS)
    return (non_elig, ig_hint)


# ── CA HT (turnover) computation ─────────────────────────────────────────────


def _compute_ca_ht(db: Session, case_id: UUID) -> tuple[Decimal, str]:
    """Compute CA HT for the case.

    Preference order:
      1. Latest PARSED Trial Balance — Σ (period_credit − period_debit)
         on class 7 accounts.
      2. Latest PARSED General Ledger — Σ (credit − debit) on class 7 lines.

    Returns (ca_ht_xaf, source_label).
    """
    # Trial balance first
    tb_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.TRIAL_BALANCE,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    if tb_ds is not None:
        rows = (
            db.query(TrialBalanceLine)
            .filter(TrialBalanceLine.dataset_id == tb_ds.id)
            .all()
        )
        total = Decimal("0")
        for r in rows:
            if _starts_with_any(r.account_code, REVENUE_ACCOUNT_PREFIXES):
                total += Decimal(str(r.period_credit or 0)) - Decimal(str(r.period_debit or 0))
        if total > 0:
            return (total, f"trial_balance:{tb_ds.original_filename}")

    # Fallback to GL
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
    if gl_ds is not None:
        lines = (
            db.query(JournalEntryLine)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .filter(JournalEntry.dataset_id == gl_ds.id)
            .all()
        )
        total = Decimal("0")
        for l in lines:
            if _starts_with_any(l.account_code, REVENUE_ACCOUNT_PREFIXES):
                total += Decimal(str(l.credit or 0)) - Decimal(str(l.debit or 0))
        if total > 0:
            return (total, f"general_ledger:{gl_ds.original_filename}")

    return (Decimal("0"), "unknown")


# ── Evidence lookup ──────────────────────────────────────────────────────────


def _load_evidence_by_line(
    db: Session, case_id: UUID
) -> dict[tuple[str, int], list[DonationEvidence]]:
    """Index every uploaded DonationEvidence by (piece_number, line_number)."""
    rows = (
        db.query(DonationEvidence)
        .filter(DonationEvidence.audit_case_id == case_id)
        .all()
    )
    out: dict[tuple[str, int], list[DonationEvidence]] = {}
    for r in rows:
        out.setdefault((r.piece_number, r.line_number), []).append(r)
    return out


def _resolve_verdict(
    evidence_for_line: list[DonationEvidence] | None,
    libelle: str | None,
    niu: str | None,
    name_guess: str | None,
) -> tuple[str, str, str]:
    """Returns (verdict, reason, source)."""
    if evidence_for_line:
        # Manual override wins; otherwise the most recent doc verdict
        manual = [
            e for e in evidence_for_line
            if e.verdict_source and e.verdict_source.value == "MANUAL_OVERRIDE"
        ]
        if manual:
            e = max(manual, key=lambda x: x.verdict_at or x.uploaded_at)
            return (e.verdict.value, e.verdict_reason or "Décision motivée du vérificateur",
                    "MANUAL_OVERRIDE")
        latest = max(evidence_for_line, key=lambda x: x.uploaded_at)
        return (latest.verdict.value,
                latest.verdict_reason or "Verdict établi à partir des justificatifs",
                "DOC_EXTRACTED")

    # No evidence yet — infer from GL
    non_elig, ig_hint = _libelle_signals(libelle)
    if non_elig:
        return (DonationVerdict.NON_ELIGIBLE.value,
                "Libellé évoque un bénéficiaire non-éligible (parti politique, associé, étranger…).",
                "AUTO_GL")
    if not name_guess:
        return (DonationVerdict.A_REINSTRUIRE.value,
                "Bénéficiaire non identifiable depuis le grand-livre — justificatif à produire.",
                "AUTO_GL")
    # Has a name guess but no docs — pending evidence
    if ig_hint:
        return (DonationVerdict.A_REINSTRUIRE.value,
                "Bénéficiaire possible (ONG/association/œuvre) — reçu et agrément requis.",
                "AUTO_GL")
    return (DonationVerdict.A_REINSTRUIRE.value,
            "Bénéficiaire identifié mais éligibilité à confirmer (statut, agrément, NIU).",
            "AUTO_GL")


# ── Main entrypoint ──────────────────────────────────────────────────────────


def _get_or_create_ai_analysis(
    db: Session, case_id: UUID, piece: str, line_no: int,
    libelle: str | None, account_code: str | None,
    ca_ht_xaf: float, fiscal_year: int | None,
    do_call: bool = False,
) -> DonationLibelleAnalysis | None:
    """Fetch cached AI analysis (matched on libellé hash) or create a fresh one.

    When `do_call=False` and no cached entry exists, returns None (UI can later
    trigger a fresh analysis explicitly via the dedicated endpoint).
    """
    h = libelle_hash(libelle, account_code)
    existing = (
        db.query(DonationLibelleAnalysis)
        .filter(
            DonationLibelleAnalysis.audit_case_id == case_id,
            DonationLibelleAnalysis.piece_number == piece,
            DonationLibelleAnalysis.line_number == line_no,
        )
        .first()
    )
    if existing and existing.libelle_hash == h:
        return existing
    if not do_call:
        # Stale entry exists but libellé changed → drop; do not call here unless requested
        if existing:
            db.delete(existing)
            db.flush()
        return None
    # Run Claude
    v = analyze_libelle(libelle, account_code, ca_ht_xaf, fiscal_year)
    if existing:
        db.delete(existing)
        db.flush()
    row = DonationLibelleAnalysis(
        audit_case_id=case_id,
        piece_number=piece,
        line_number=line_no,
        libelle_hash=h,
        verdict_ai=v.verdict,
        confidence=AiConfidence(v.confidence),
        reason=v.reason,
        indicators={"items": v.indicators},
        model=v.model,
    )
    db.add(row)
    db.flush()
    return row


def _load_group_membership(
    db: Session, case_id: UUID,
) -> tuple[dict[tuple[str, int], DonationGroup], dict[str, DonationGroup]]:
    """Returns: (line_key → group, group_id → group)."""
    groups = (
        db.query(DonationGroup)
        .filter(DonationGroup.audit_case_id == case_id)
        .all()
    )
    by_id = {str(g.id): g for g in groups}
    if not groups:
        return {}, {}
    assocs = (
        db.query(DonationGroupLine)
        .filter(DonationGroupLine.group_id.in_([g.id for g in groups]))
        .all()
    )
    by_line: dict[tuple[str, int], DonationGroup] = {}
    for a in assocs:
        g = by_id.get(str(a.group_id))
        if g is not None:
            by_line[(a.piece_number, a.line_number)] = g
    return by_line, by_id


def analyze_dons_liberalites(db: Session, case_id: UUID) -> dict[str, Any]:
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
    if gl_ds is None:
        return {
            "source_dataset_id": None,
            "source_filename": None,
            "ca_ht_xaf": 0.0,
            "ca_ht_source": "unknown",
            "plafond_per_mille": float(PLAFOND_PER_MILLE),
            "plafond_xaf": 0.0,
            "lines": [],
            "by_beneficiary": [],
            "summary": None,
            "note": (
                "Aucun grand-livre chargé. Importez-le dans Données › Grand-livre "
                "pour activer le contrôle des dons et libéralités."
            ),
        }

    # 1) Pull all GL lines on donation-bearing accounts
    all_prefixes = DONATION_ACCOUNT_PREFIXES + DONATION_CANDIDATE_PREFIXES
    raw_lines = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .filter(JournalEntry.dataset_id == gl_ds.id)
        .order_by(JournalEntry.piece_number, JournalEntryLine.line_number)
        .all()
    )

    candidate_lines: list[tuple[JournalEntryLine, JournalEntry]] = []
    for line, entry in raw_lines:
        if _starts_with_any(line.account_code, all_prefixes):
            debit = Decimal(str(line.debit or 0))
            credit = Decimal(str(line.credit or 0))
            net = debit - credit
            if net > 0:
                candidate_lines.append((line, entry))

    # 2) Load any uploaded evidence keyed by (piece, line)
    evidence_index = _load_evidence_by_line(db, case_id)

    # 2bis) Load AI cache (no fresh Claude calls here — UI triggers them on demand)
    ai_cache = {
        (a.piece_number, a.line_number): a
        for a in db.query(DonationLibelleAnalysis).filter(
            DonationLibelleAnalysis.audit_case_id == case_id).all()
    }
    # 2ter) Load groups + members
    groups_by_line, groups_by_id = _load_group_membership(db, case_id)

    # 3) Build per-line view
    out_lines: list[DonationLine] = []
    for line, entry in candidate_lines:
        amount = Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        niu = _extract_niu(line.libelle) or _extract_niu(line.account_name)
        name_guess = _beneficiary_guess(line.libelle, line.account_name)
        confidence = _score_confidence(line.libelle, line.account_name, niu, name_guess)
        evid = evidence_index.get((entry.piece_number, line.line_number)) or []
        verdict, reason, source = _resolve_verdict(evid, line.libelle, niu, name_guess)

        # AI verdict from cache (if any) — match on libellé hash
        ai_row = ai_cache.get((entry.piece_number, line.line_number))
        ai_verdict_val = "A_REINSTRUIRE"
        ai_conf = "LOW"
        ai_reason = ""
        ai_inds: list[str] = []
        if ai_row is not None:
            expected = libelle_hash(line.libelle, line.account_code)
            if ai_row.libelle_hash == expected:
                ai_verdict_val = ai_row.verdict_ai
                ai_conf = ai_row.confidence.value
                ai_reason = ai_row.reason or ""
                ai_inds = list((ai_row.indicators or {}).get("items", []))

        # Group propagation : if the line is in a group with a verdict set
        # and the line has NO manual override, the group verdict applies.
        g = groups_by_line.get((entry.piece_number, line.line_number))
        g_id = str(g.id) if g else None
        g_name = g.name if g else None
        g_verdict = g.group_verdict if g else None
        has_manual = any(
            e.verdict_source and e.verdict_source.value == "MANUAL_OVERRIDE"
            for e in evid
        )
        if g and g_verdict and not has_manual:
            verdict = g_verdict
            reason = (g.group_verdict_reason or
                      f"Verdict propagé du groupe « {g.name} ».")
            source = "GROUP"

        out_lines.append(DonationLine(
            piece_number=entry.piece_number,
            entry_date=entry.entry_date.isoformat() if entry.entry_date else None,
            line_number=line.line_number,
            account_code=line.account_code,
            account_name=line.account_name,
            libelle=line.libelle,
            amount_xaf=amount,
            beneficiary_niu=niu,
            beneficiary_name_guess=name_guess,
            confidence=confidence,
            verdict=verdict,
            verdict_reason=reason,
            verdict_source=source,
            has_evidence=bool(evid),
            evidence_count=len(evid),
            account_category=_account_category(line.account_code),
            ai_verdict=ai_verdict_val,
            ai_confidence=ai_conf,
            ai_reason=ai_reason,
            ai_indicators=ai_inds,
            group_id=g_id,
            group_name=g_name,
            group_verdict=g_verdict,
        ))

    # 4) CA HT + plafond
    ca_ht, ca_source = _compute_ca_ht(db, case_id)
    plafond = (ca_ht * PLAFOND_PER_MILLE / PLAFOND_DIVISOR).quantize(Decimal("0.01"))

    # 5) Aggregates
    total_engage = sum((l.amount_xaf for l in out_lines), Decimal("0"))
    total_eligible_avant_plafond = sum(
        (l.amount_xaf for l in out_lines if l.verdict == "ELIGIBLE"), Decimal("0")
    )
    total_non_eligible = sum(
        (l.amount_xaf for l in out_lines if l.verdict == "NON_ELIGIBLE"), Decimal("0")
    )
    total_a_reinstruire = sum(
        (l.amount_xaf for l in out_lines if l.verdict == "A_REINSTRUIRE"), Decimal("0")
    )

    # Plafond test on the eligible sub-pool
    excedent_plafond = max(Decimal("0"), total_eligible_avant_plafond - plafond)
    reintegration_xaf = total_non_eligible + excedent_plafond

    # 6) Per-beneficiary roll-up
    agg: dict[str, BeneficiaryAggregate] = {}
    for l in out_lines:
        key = (l.beneficiary_niu
               or (l.beneficiary_name_guess or "—").lower()[:40])
        ba = agg.get(key)
        if ba is None:
            ba = BeneficiaryAggregate(
                key=key,
                name=l.beneficiary_name_guess or "Bénéficiaire non identifié",
                niu=l.beneficiary_niu,
                line_count=0,
                total_xaf=Decimal("0"),
                eligible_xaf=Decimal("0"),
                non_eligible_xaf=Decimal("0"),
                to_reinstruct_xaf=Decimal("0"),
            )
            agg[key] = ba
        ba.line_count += 1
        ba.total_xaf += l.amount_xaf
        if l.verdict == "ELIGIBLE":
            ba.eligible_xaf += l.amount_xaf
        elif l.verdict == "NON_ELIGIBLE":
            ba.non_eligible_xaf += l.amount_xaf
        else:
            ba.to_reinstruct_xaf += l.amount_xaf

    beneficiaries = sorted(agg.values(), key=lambda b: -float(b.total_xaf))

    summary = {
        "ca_ht_xaf": float(ca_ht),
        "ca_ht_source": ca_source,
        "plafond_per_mille": float(PLAFOND_PER_MILLE),
        "plafond_xaf": float(plafond),
        "line_count": len(out_lines),
        "beneficiary_count": len(beneficiaries),
        "total_engage_xaf": float(total_engage),
        "total_eligible_avant_plafond_xaf": float(total_eligible_avant_plafond),
        "total_non_eligible_xaf": float(total_non_eligible),
        "total_a_reinstruire_xaf": float(total_a_reinstruire),
        "excedent_plafond_xaf": float(excedent_plafond),
        "reintegration_xaf": float(reintegration_xaf),
        "evidence_uploaded_count": sum(1 for l in out_lines if l.has_evidence),
        "confidence_breakdown": {
            "VERT": sum(1 for l in out_lines if l.confidence == "VERT"),
            "ORANGE": sum(1 for l in out_lines if l.confidence == "ORANGE"),
            "ROUGE": sum(1 for l in out_lines if l.confidence == "ROUGE"),
        },
        "verdict_breakdown": {
            "ELIGIBLE": sum(1 for l in out_lines if l.verdict == "ELIGIBLE"),
            "NON_ELIGIBLE": sum(1 for l in out_lines if l.verdict == "NON_ELIGIBLE"),
            "A_REINSTRUIRE": sum(1 for l in out_lines if l.verdict == "A_REINSTRUIRE"),
        },
    }

    # Groups summary (one entry per group with member count)
    groups_payload: list[dict[str, Any]] = []
    group_to_members: dict[str, list[tuple[str, int]]] = {}
    for k, g in groups_by_line.items():
        group_to_members.setdefault(str(g.id), []).append(k)
    for gid, g in groups_by_id.items():
        members = group_to_members.get(gid, [])
        total = sum(
            (l.amount_xaf for l in out_lines
             if (l.piece_number, l.line_number) in members),
            Decimal("0"),
        )
        groups_payload.append({
            "id": gid,
            "name": g.name,
            "description": g.description,
            "member_count": len(members),
            "total_xaf": float(total),
            "group_verdict": g.group_verdict,
            "group_verdict_reason": g.group_verdict_reason,
            "group_verdict_source": g.group_verdict_source,
            "ai_confidence": g.ai_confidence.value if g.ai_confidence else None,
            "members": [{"piece_number": p, "line_number": ln} for (p, ln) in members],
        })

    return {
        "source_dataset_id": str(gl_ds.id),
        "source_filename": gl_ds.original_filename,
        "account_prefixes": list(DONATION_ACCOUNT_PREFIXES),
        "candidate_prefixes": list(DONATION_CANDIDATE_PREFIXES),
        "ca_ht_xaf": float(ca_ht),
        "ca_ht_source": ca_source,
        "plafond_per_mille": float(PLAFOND_PER_MILLE),
        "plafond_xaf": float(plafond),
        "lines": [l.to_dict() for l in out_lines],
        "by_beneficiary": [b.to_dict() for b in beneficiaries],
        "groups": groups_payload,
        "summary": summary,
    }
