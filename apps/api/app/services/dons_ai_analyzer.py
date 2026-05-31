"""Claude analyzer for dons & libéralités — Art. 7 A (4) CGI Cameroun.

Two functions :
  - analyze_libelle(libelle, account_code, ca_ht, fiscal_year) → AiVerdict
       For each ambiguous GL line, asks Claude to grade deductibility based
       on the libellé text alone.
  - analyze_group_with_docs(group_name, lines, evidence_docs) → AiVerdict
       For a group of similar lines + uploaded supporting docs (PDF/images),
       asks Claude to read everything and produce a consolidated verdict.

Falls back to a deterministic heuristic if no API key.
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
import logging
from dataclasses import dataclass, asdict
from typing import Any

import httpx  # noqa: F401  (kept for symmetry)

from app.config import get_settings


log = logging.getLogger("fiscaudit.services.dons_ai")


@dataclass
class AiVerdict:
    verdict: str             # ELIGIBLE | NON_ELIGIBLE | A_REINSTRUIRE
    confidence: str          # HIGH | MEDIUM | LOW
    reason: str
    indicators: list[str]    # signaux extraits du libellé
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_VALID_VERDICTS = {"ELIGIBLE", "NON_ELIGIBLE", "A_REINSTRUIRE"}
_VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}


def libelle_hash(libelle: str | None, account_code: str | None) -> str:
    raw = f"{(account_code or '').strip()}|{(libelle or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_client():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # type: ignore
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except ImportError:
        return None


SYSTEM_PROMPT_LIBELLE = """Tu es un vérificateur fiscal expert de la DGI Cameroun.
Tu analyses des libellés de grand-livre comptable pour qualifier la déductibilité
des dons et libéralités au titre de l'article 7, A (4) du CGI Cameroun.

Règle légale (texte exact) :
« Les libéralités, dons et subventions ne constituent pas des charges déductibles.
Cependant, les versements à des organismes de recherche/développement et à des
œuvres ou organismes d'intérêt général à caractère philanthropique, éducatif,
sportif, scientifique, social et familial sont admis en déduction à condition
qu'ils soient SITUÉS AU CAMEROUN, justifiés, et dans la limite de 0,5 % du CA.
Les dons aux clubs participant aux compétitions nationales sont admis dans la
limite de 5 % du CA. »

Pour chaque libellé, identifie des indices :
  • Nature du bénéficiaire (orphelinat, ONG, fondation, club, parti politique,
    dirigeant, particulier, association d'intérêt général…)
  • Localisation (camerounaise vs étrangère)
  • Caractère d'intérêt général
  • Risques d'inéligibilité (politique, personnel, étranger, sans justificatif…)

Tu retournes UN OBJET JSON STRICT (pas de markdown, pas de texte autour) :
{
  "verdict": "ELIGIBLE" | "NON_ELIGIBLE" | "A_REINSTRUIRE",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "reason": "phrase concise expliquant le verdict",
  "indicators": ["liste", "des", "signaux", "détectés"]
}

Règles de verdict :
  - ELIGIBLE : indices clairs d'œuvre d'intérêt général au Cameroun avec
    nature alignée (philanthropique/éducatif/etc.).
  - NON_ELIGIBLE : indices clairs d'inéligibilité (parti politique, bénéficiaire
    personnel, étranger, libellé révélant un caractère non philanthropique).
  - A_REINSTRUIRE : libellé trop vague ou ambigu — exiger pièces justificatives.

Sois CONSERVATEUR : en l'absence d'indices forts, mets A_REINSTRUIRE."""


def _parse_claude_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip("\n")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return _json.loads(text[start: end + 1])
    except _json.JSONDecodeError:
        return None


def _normalize(parsed: dict[str, Any] | None, model: str) -> AiVerdict:
    verdict = (parsed or {}).get("verdict", "A_REINSTRUIRE")
    if verdict not in _VALID_VERDICTS:
        verdict = "A_REINSTRUIRE"
    conf = (parsed or {}).get("confidence", "LOW")
    if conf not in _VALID_CONFIDENCES:
        conf = "LOW"
    reason = (parsed or {}).get("reason") or ""
    indicators = (parsed or {}).get("indicators") or []
    if not isinstance(indicators, list):
        indicators = [str(indicators)]
    return AiVerdict(verdict=verdict, confidence=conf, reason=reason[:2000],
                     indicators=[str(x)[:200] for x in indicators[:10]], model=model)


def _fallback_libelle(libelle: str | None) -> AiVerdict:
    """Heuristique mots-clés (mode sans API key)."""
    low = (libelle or "").lower()
    bad_keywords = ("parti", "politique", "campagne", "dirigeant", "gerant", "gérant",
                    "associe", "associé", "personnel", "etranger", "étranger")
    good_keywords = ("orphelinat", "ong ", "fondation", "œuvre", "oeuvre",
                     "philanthrop", "humanitair", "croix-rouge", "ecole", "école",
                     "hopital", "hôpital")
    indicators = []
    for kw in bad_keywords:
        if kw in low:
            indicators.append(f"signal négatif: {kw}")
    for kw in good_keywords:
        if kw in low:
            indicators.append(f"signal positif: {kw}")
    if any("négatif" in i for i in indicators):
        return AiVerdict("NON_ELIGIBLE", "MEDIUM",
                         "Indices d'inéligibilité dans le libellé (heuristique fallback).",
                         indicators, model="heuristic")
    if any("positif" in i for i in indicators):
        return AiVerdict("ELIGIBLE", "LOW",
                         "Indices d'éligibilité dans le libellé (heuristique fallback) — confirmer par pièces.",
                         indicators, model="heuristic")
    return AiVerdict("A_REINSTRUIRE", "LOW",
                     "Libellé non concluant — justificatifs requis (mode heuristique).",
                     indicators, model="heuristic")


def analyze_libelle(
    libelle: str | None, account_code: str | None,
    ca_ht_xaf: float | None = None, fiscal_year: int | None = None,
) -> AiVerdict:
    """Analyse Claude d'une seule ligne. Fallback heuristique si pas d'API key."""
    client = _get_client()
    if client is None:
        return _fallback_libelle(libelle)
    settings = get_settings()
    model = settings.anthropic_model or "claude-sonnet-4-5"

    user_text = (
        f"Compte SYSCOHADA : {account_code or '?'}\n"
        f"Libellé GL : {libelle or '(vide)'}\n"
        f"Exercice : {fiscal_year or '?'}\n"
        f"CA HT du dossier (contexte) : {ca_ht_xaf or '?'} FCFA\n\n"
        "Qualifie la déductibilité au titre de l'Art. 7 A (4) CGI Cameroun. "
        "Retourne uniquement l'objet JSON."
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT_LIBELLE,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_text}],
        )
        text = "".join(
            getattr(b, "text", "") for b in response.content
            if getattr(b, "type", None) == "text"
        )
        parsed = _parse_claude_json(text)
        return _normalize(parsed, model=model)
    except Exception as e:  # noqa: BLE001
        log.warning("Claude libellé analysis failed: %s", e)
        return _fallback_libelle(libelle)


# ─────────────────────────────────────────────────────────────────────────────
# Group analysis with uploaded documents
# ─────────────────────────────────────────────────────────────────────────────


SYSTEM_PROMPT_GROUP = """Tu es un vérificateur fiscal expert de la DGI Cameroun.
On te soumet un GROUPE de lignes de grand-livre représentant un type homogène
de dons, accompagné de PIÈCES JUSTIFICATIVES (PDF/images).

Règle légale identique à l'analyse par ligne (Art. 7 A (4) CGI Cameroun).

Examine les pièces fournies pour :
  1. Vérifier si le(s) bénéficiaire(s) sont des œuvres d'intérêt général
     situées au Cameroun (statut, agrément, NIU).
  2. Vérifier la cohérence montant pièces ↔ libellés GL fournis.
  3. Identifier toute irrégularité ou exclusion automatique.

Retourne UN OBJET JSON STRICT :
{
  "verdict": "ELIGIBLE" | "NON_ELIGIBLE" | "A_REINSTRUIRE",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "reason": "synthèse motivée",
  "indicators": ["...","..."]
}

Si les pièces sont insuffisantes ou contradictoires, A_REINSTRUIRE."""


def analyze_group_with_docs(
    group_name: str,
    lines: list[dict[str, Any]],          # [{piece, line, libelle, amount, account}]
    docs: list[tuple[bytes, str]],         # [(pdf_or_image_bytes, mime)]
) -> AiVerdict:
    """Per-group analysis with uploaded supporting documents."""
    client = _get_client()
    if client is None:
        return AiVerdict("A_REINSTRUIRE", "LOW",
                         "Pas d'IA disponible — décision auditeur requise.", [],
                         model="no-client")
    settings = get_settings()
    model = settings.anthropic_model or "claude-sonnet-4-5"

    # Build the content blocks: short JSON of lines + each document
    line_summary = _json.dumps([
        {"piece": ln.get("piece"), "line": ln.get("line"),
         "compte": ln.get("account"), "libelle": ln.get("libelle"),
         "montant": ln.get("amount")} for ln in lines
    ], ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [
        {"type": "text", "text":
            f"Groupe : {group_name}\n\n"
            f"Lignes GL :\n```json\n{line_summary}\n```\n\n"
            f"Pièces jointes : {len(docs)} document(s)."},
    ]
    for data, mime in docs[:5]:   # max 5 docs to keep prompt size
        b64 = base64.standard_b64encode(data).decode("utf-8")
        if mime and mime.startswith("application/pdf"):
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            })
        elif mime and mime.startswith("image/"):
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            })

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT_GROUP,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(
            getattr(b, "text", "") for b in response.content
            if getattr(b, "type", None) == "text"
        )
        parsed = _parse_claude_json(text)
        return _normalize(parsed, model=model)
    except Exception as e:  # noqa: BLE001
        log.warning("Claude group analysis failed: %s", e)
        return AiVerdict("A_REINSTRUIRE", "LOW",
                         f"Échec analyse IA : {e}", [], model="error")
