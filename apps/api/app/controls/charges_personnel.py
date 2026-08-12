"""Charges de personnel — CGI Cameroun, Art. 7 A 1 a) b) c).

Deterministic layer + AI layer (Claude, article text verbatim in the prompt).

Périmètre GL : classe 66 (charges de personnel SYSCOHADA — 661 rémunérations
nationales, 662 non nationales, 663 indemnités forfaitaires, 664 charges
sociales, 666/667/668) + comptes 658 dont le libellé évoque des jetons de
présence (7 A 1 b).

Verdicts par ligne agrégée (compte × libellé) :
  NON_DEDUCTIBLE — chasse, pêche sportive, bateaux de plaisance, avions de
                   tourisme, résidences d'agrément (7 A 1 c, dernier alinéa)
  A_INSTRUIRE    — jetons de présence (travail effectué ?), allocations
                   forfaitaires de représentation/déplacement (cumul avec
                   remboursements réels ?), cotisations retraite expatriés
                   (plafond 15 % du salaire de base), rémunérations
                   potentiellement excessives
  DEDUCTIBLE     — le reste (travail effectif présumé, normes conventionnelles)
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

log = logging.getLogger("fiscaudit.controls.charges_personnel")

ARTICLE_7A1 = """Article 7 A 1 (CGI Cameroun) :
a) Les rémunérations allouées à un salarié ne sont admises en déduction des
résultats que dans la mesure où, n'étant pas excessives par rapport au service
rendu, elles correspondent à un travail effectif et sont conformes aux normes
conventionnelles. Cette disposition s'applique à toutes les rémunérations
directes et indirectes, y compris les indemnités, allocations, avantages en
nature et remboursements de frais. Toutefois, sont déductibles dans la limite
de 15 % du salaire de base et à l'exclusion des autres cotisations sociales,
les seules cotisations patronales versées à l'étranger en vue de la
constitution de la retraite d'un expatrié ayant un caractère obligatoire.
b) Les jetons de présence alloués aux membres du Conseil d'Administration ne
sont déductibles que pour autant qu'ils représentent la rémunération du
travail effectué.
c) Les allocations forfaitaires qu'une société attribue à ses dirigeants ou
aux cadres de son entreprise pour frais de représentation et de déplacement
sont exclues de ses charges déductibles pour l'assiette de l'impôt lorsque,
parmi ces charges, figurent les frais habituels de cette nature remboursés aux
intéressés. Sont réintégrées aux résultats de l'exploitation, les sommes
versées aux dirigeants ou aux cadres d'une société à titre d'indemnité de
frais d'emploi ou de service et ne correspondant pas à une charge réelle de la
fonction exercée. Sont également exclues des charges déductibles, que ce soit
sous la forme d'allocations forfaitaires ou de remboursement de frais, les
dépenses et charges de toute nature ayant trait à l'exercice de la chasse, de
la pêche sportive, à l'utilisation de bateaux de plaisance, d'avions de
tourisme ou de résidences d'agrément."""


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


#: (regex sur libellé normalisé, verdict, motif, référence)
_RULES: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"chasse|peche sportive|bateau|plaisance|yacht|avion de tourisme|jet prive|residence d.?agrement|villa d.?agrement"),
     "NON_DEDUCTIBLE",
     "Dépense liée à la chasse, pêche sportive, bateau de plaisance, avion de tourisme ou résidence d'agrément — exclusion expresse.",
     "Art. 7 A 1 c (dernier alinéa)"),
    (re.compile(r"jeton"),
     "A_INSTRUIRE",
     "Jetons de présence — déductibles seulement s'ils rémunèrent un travail effectué (PV du CA à produire).",
     "Art. 7 A 1 b"),
    (re.compile(r"allocation forfaitaire|forfait (de )?(representation|deplacement)|frais de representation|indemnite de representation"),
     "A_INSTRUIRE",
     "Allocation forfaitaire de représentation/déplacement — non déductible si des remboursements réels de même nature existent par ailleurs.",
     "Art. 7 A 1 c"),
    (re.compile(r"(retraite|pension|prevoyance).*(expatri|etranger)|(expatri).*(retraite|pension)"),
     "A_INSTRUIRE",
     "Cotisations retraite d'expatriés versées à l'étranger — déductibles dans la limite de 15 % du salaire de base et si obligatoires.",
     "Art. 7 A 1 a (plafond 15 %)"),
    (re.compile(r"prime exceptionnelle|bonus exceptionnel|gratification exceptionnelle"),
     "A_INSTRUIRE",
     "Rémunération exceptionnelle — vérifier qu'elle n'est pas excessive par rapport au service rendu et correspond à un travail effectif.",
     "Art. 7 A 1 a"),
]


@dataclass
class PersonnelRow:
    account_code: str
    account_name: str
    libelle: str
    montant_xaf: Decimal
    entry_count: int
    verdict: str = "DEDUCTIBLE"
    motif: str = "Travail effectif présumé — conforme aux normes conventionnelles."
    article: str = "Art. 7 A 1 a"
    source: str = "regle"  # "regle" | "ia"


def _apply_rules(row: PersonnelRow) -> None:
    n = _norm(f"{row.account_name} {row.libelle}")
    for rx, verdict, motif, article in _RULES:
        if rx.search(n):
            row.verdict, row.motif, row.article = verdict, motif, article
            return


def _ai_refine(rows: list[PersonnelRow]) -> None:
    """Ask Claude to verify the lines against the article text (verbatim).

    Only refines rows still DEDUCTIBLE/A_INSTRUIRE — the deterministic
    NON_DEDUCTIBLE exclusions of 7 A 1 c are final. Silent no-op without an
    API key (mock mode) or on any API failure.
    """
    from app.config import get_settings
    settings = get_settings()
    if not settings.anthropic_api_key:
        return
    try:
        import anthropic
        import json as _json
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        cand = [r for r in rows if r.verdict != "NON_DEDUCTIBLE"][:80]
        if not cand:
            return
        listing = "\n".join(
            f"{i}|{r.account_code}|{(r.account_name or '')[:40]}|{(r.libelle or '')[:90]}|{float(r.montant_xaf):,.0f}"
            for i, r in enumerate(cand)
        )
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=3000,
            system=("Tu es un vérificateur de la DGI Cameroun. Tu appliques STRICTEMENT "
                    "l'article suivant aux charges de personnel :\n\n" + ARTICLE_7A1 +
                    "\n\nRéponds UNIQUEMENT en JSON: {\"verdicts\": [{\"i\": int, "
                    "\"verdict\": \"DEDUCTIBLE|A_INSTRUIRE|NON_DEDUCTIBLE\", "
                    "\"motif\": str (français, cite le point a/b/c), \"article\": str}]} "
                    "— seulement pour les lignes où tu changes ou précises le verdict."),
            messages=[{"role": "user", "content":
                       "Lignes (i|compte|intitulé|libellé|montant FCFA):\n" + listing}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return
        for v in _json.loads(m.group(0)).get("verdicts", []):
            i = v.get("i")
            if isinstance(i, int) and 0 <= i < len(cand) and v.get("verdict") in (
                    "DEDUCTIBLE", "A_INSTRUIRE", "NON_DEDUCTIBLE"):
                cand[i].verdict = v["verdict"]
                cand[i].motif = str(v.get("motif") or cand[i].motif)[:400]
                cand[i].article = str(v.get("article") or cand[i].article)[:80]
                cand[i].source = "ia"
    except Exception as e:  # noqa: BLE001
        log.warning("AI refine charges personnel failed: %s", e)


def analyze_personnel(lines: list[Any]) -> tuple[list[PersonnelRow], dict[str, Any]]:
    """`lines` = JournalEntryLine-like objects (account_code, account_name,
    libelle, debit, credit). Aggregates by (compte, libellé normalisé)."""
    agg: dict[tuple[str, str], PersonnelRow] = {}
    for l in lines:
        code = str(l.account_code or "").strip()
        is_66 = code.startswith("66")
        is_jeton = code.startswith("65") and "jeton" in _norm(f"{l.account_name} {l.libelle}")
        if not (is_66 or is_jeton):
            continue
        net = (l.debit or Decimal("0")) - (l.credit or Decimal("0"))
        key = (code, _norm(l.libelle)[:80] or _norm(l.account_name)[:80])
        row = agg.get(key)
        if row is None:
            row = PersonnelRow(code, l.account_name or "", (l.libelle or l.account_name or "")[:160],
                               Decimal("0"), 0)
            agg[key] = row
        row.montant_xaf += net
        row.entry_count += 1

    rows = [r for r in agg.values() if r.montant_xaf != 0]
    for r in rows:
        _apply_rules(r)
    _ai_refine(rows)
    rows.sort(key=lambda r: (r.verdict != "NON_DEDUCTIBLE", r.verdict != "A_INSTRUIRE",
                             -abs(r.montant_xaf)))

    total = sum((r.montant_xaf for r in rows), Decimal("0"))
    nd = sum((r.montant_xaf for r in rows if r.verdict == "NON_DEDUCTIBLE"), Decimal("0"))
    ai_ = sum((r.montant_xaf for r in rows if r.verdict == "A_INSTRUIRE"), Decimal("0"))
    summary = {
        "total_xaf": float(total),
        "non_deductible_xaf": float(nd),
        "a_instruire_xaf": float(ai_),
        "deductible_xaf": float(total - nd - ai_),
        "row_count": len(rows),
        "non_deductible_count": sum(1 for r in rows if r.verdict == "NON_DEDUCTIBLE"),
        "a_instruire_count": sum(1 for r in rows if r.verdict == "A_INSTRUIRE"),
        "ai_used": any(r.source == "ia" for r in rows),
    }
    return rows, summary
