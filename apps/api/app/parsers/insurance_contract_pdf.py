"""Insurance contract PDF extractor — Claude Vision.

Extracts the key fields from an uploaded insurance policy:
  - numero police, assureur (nom + NIU + pays),
  - souscripteur, bénéficiaire (nom + nature),
  - type d'assurance, dates de couverture, prime annuelle,
  - clauses notables (homme-clé, etc.).

Same architecture as dmm_pdf.py — Claude Vision when ANTHROPIC_API_KEY is set,
mock mode otherwise.
"""
from __future__ import annotations

import base64
import json as _json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings


log = logging.getLogger("fiscaudit.parser.insurance_contract")


# ── Pydantic schema ──────────────────────────────────────────────────────────


class ExtractedInsuranceContract(BaseModel):
    numero_police: str | None = Field(default=None, description="Numéro de police d'assurance")
    assureur_nom: str | None = Field(default=None, description="Raison sociale de la compagnie d'assurance")
    assureur_niu: str | None = Field(default=None, description="NIU (Cameroun, format M0xxxxxxxxxxX) si présent")
    assureur_pays: str = Field(default="CM", description="Pays de l'assureur (code ISO 2 lettres) — CM si Cameroun")
    assureur_adresse: str | None = Field(default=None)
    souscripteur: str | None = Field(default=None, description="Personne / entité qui souscrit le contrat")
    beneficiaire_nom: str | None = Field(default=None, description="Bénéficiaire désigné")
    beneficiaire_type: str = Field(
        default="INCONNU",
        description=(
            "Nature du bénéficiaire : ENTREPRISE (la société souscriptrice), "
            "DIRIGEANT (PDG / Gérant nommé), FAMILLE_DIRIGEANT (conjoint, enfants), "
            "PERSONNEL (employés en collectif), MIXTE, INCONNU"
        ),
    )
    type_assurance: str = Field(
        default="AUTRE",
        description=(
            "Type d'assurance : MULTIRISQUE, MATERIEL_TRANSPORT, "
            "RISQUES_EXPLOITATION, RESP_PRODUCTEUR, INSOLVABILITE_CLIENT, "
            "TRANSPORT_VENTES, SANTE_PERSONNEL, RETRAITE_FIN_CARRIERE, "
            "VIE_HOMME_CLE, VIE_DIRIGEANT, RC, AUTRE"
        ),
    )
    date_debut: str | None = Field(default=None, description="Date début de couverture, ISO YYYY-MM-DD")
    date_fin: str | None = Field(default=None, description="Date fin de couverture, ISO YYYY-MM-DD")
    prime_annuelle_ttc: float | None = Field(
        default=None, description="Prime annuelle TTC en FCFA (no decimals)"
    )
    clauses_notables: str | None = Field(
        default=None,
        description="Clauses notables (homme-clé, exclusion, plafond) — texte libre",
    )
    notes: str | None = Field(default=None)


# ── Mapping type d'assurance → compte SYSCOHADA Révisé ───────────────────────


SYSCOHADA_ACCOUNT_MAP: dict[str, str] = {
    "MULTIRISQUE":           "6251",
    "MATERIEL_TRANSPORT":    "6252",
    "RISQUES_EXPLOITATION":  "6253",
    "RESP_PRODUCTEUR":       "6254",
    "INSOLVABILITE_CLIENT":  "6255",
    "TRANSPORT_VENTES":      "6257",
    "SANTE_PERSONNEL":       "6685",   # Classe 66 — charges de personnel
    "RETRAITE_FIN_CARRIERE": "6686",   # Classe 66
    "VIE_HOMME_CLE":         "6258",   # « Autres primes d'assurance »
    "VIE_DIRIGEANT":         "6258",
    "RC":                    "6258",
    "AUTRE":                 "6258",
}


@dataclass
class ParsedInsuranceContract:
    numero_police: str | None
    assureur_nom: str | None
    assureur_niu: str | None
    assureur_pays: str
    assureur_adresse: str | None
    souscripteur: str | None
    beneficiaire_nom: str | None
    beneficiaire_type: str
    type_assurance: str
    date_debut: date | None
    date_fin: date | None
    prime_annuelle_ttc: Decimal | None
    compte_syscohada: str | None
    clauses_notables: str | None
    raw: dict[str, Any] = field(default_factory=dict)
    source: str = "claude_vision"


# ── Claude client ────────────────────────────────────────────────────────────


def _get_client():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # type: ignore
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except ImportError:
        return None


SYSTEM_PROMPT_CONTRACT = """You are an expert tax auditor at the Cameroon DGI
examining insurance contracts (polices d'assurance) for deductibility under
Article 7, A (4) of the CGI Cameroun.

For each contract PDF you receive, extract the structured fields per the
schema. Pay particular attention to:

  - The INSURER ("assureur") — its legal name, NIU if visible, and country.
    A Cameroonian insurer typically has a NIU like M0xxxxxxxxxxX.
  - The POLICY NUMBER ("numéro de police", "police N°", "contrat N°").
  - The BENEFICIARY — who receives the indemnity?
      • ENTREPRISE   : the subscribing company itself (typical IARD, RC,
                       multirisque, transport, fire, key-man life pour société)
      • DIRIGEANT    : a named director / officer (key-man life pour dirigeant,
                       santé dirigeant, vie dirigeant)
      • FAMILLE_DIRIGEANT : spouse, children of director
      • PERSONNEL    : group of employees (collective health, group life)
      • MIXTE        : both
  - The TYPE of insurance:
      MULTIRISQUE / MATERIEL_TRANSPORT (auto fleet, ships, aircraft) /
      RISQUES_EXPLOITATION (business interruption, machine breakdown) /
      RESP_PRODUCTEUR (product liability) /
      INSOLVABILITE_CLIENT (credit insurance) /
      TRANSPORT_VENTES (marine cargo on sales) /
      SANTE_PERSONNEL (employee health) /
      RETRAITE_FIN_CARRIERE (end-of-career retirement scheme) /
      VIE_HOMME_CLE (key-man life insurance on a director, paid to company) /
      VIE_DIRIGEANT (life insurance on a director, paid to himself/family) /
      RC (responsabilité civile pro/exploitation) /
      AUTRE
  - The COVERAGE PERIOD : date_debut, date_fin (ISO 8601).
  - The ANNUAL PREMIUM TTC in FCFA (no decimals).

If the document is illegible or critical fields are missing, set them to null
and explain in `notes`. Never invent data."""


def _extract_with_claude(pdf_bytes: bytes) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        raise RuntimeError("No Anthropic client")
    settings = get_settings()
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    schema_str = _json.dumps(
        ExtractedInsuranceContract.model_json_schema(),
        ensure_ascii=False, indent=2,
    )
    user_text = (
        "Extract the structured fields from this insurance contract.\n\n"
        "Return ONE valid JSON object matching this schema (no markdown fence, "
        "no commentary — just the raw JSON):\n\n"
        f"```json\n{schema_str}\n```"
    )

    response = client.messages.create(
        model=settings.anthropic_model or "claude-sonnet-4-5",
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT_CONTRACT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                {"type": "text", "text": user_text},
            ],
        }],
    )

    text_out = "".join(
        getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    if not text_out:
        raise RuntimeError("Claude returned no text")
    if text_out.startswith("```"):
        text_out = text_out.strip("`")
        if text_out.lower().startswith("json"):
            text_out = text_out[4:].lstrip("\n")
    start = text_out.find("{")
    end = text_out.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"No JSON object: {text_out[:200]}")
    data = _json.loads(text_out[start : end + 1])
    return ExtractedInsuranceContract.model_validate(data).model_dump()


# ── Mock for dev without API key ─────────────────────────────────────────────


def _mock_contract(pdf_bytes: bytes) -> dict[str, Any]:
    import hashlib
    h = int(hashlib.sha256(pdf_bytes).hexdigest()[:8], 16)
    types = list(SYSCOHADA_ACCOUNT_MAP.keys())
    tt = types[h % len(types)]
    return {
        "numero_police": f"POL-{h % 100000:05d}",
        "assureur_nom": "ASSUREUR MOCK SARL",
        "assureur_niu": "M021000000001X",
        "assureur_pays": "CM",
        "assureur_adresse": "Douala, Cameroun",
        "souscripteur": "KISSYWEARS SARL",
        "beneficiaire_nom": "KISSYWEARS SARL",
        "beneficiaire_type": "ENTREPRISE",
        "type_assurance": tt,
        "date_debut": "2026-01-01",
        "date_fin": "2026-12-31",
        "prime_annuelle_ttc": float(500_000 + (h % 1_500_000)),
        "clauses_notables": None,
        "notes": "MOCK DATA — set ANTHROPIC_API_KEY for real extraction.",
    }


# ── Public API ───────────────────────────────────────────────────────────────


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def extract_insurance_contract(pdf_bytes: bytes) -> ParsedInsuranceContract:
    """Extract an insurance contract into a ParsedInsuranceContract."""
    client = _get_client()
    source = "mock"
    if client is not None:
        try:
            raw = _extract_with_claude(pdf_bytes)
            source = "claude_vision"
        except Exception as e:  # noqa: BLE001
            log.warning("Claude contract extraction failed (%s) — falling back to mock", e)
            raw = _mock_contract(pdf_bytes)
    else:
        raw = _mock_contract(pdf_bytes)

    type_assurance = (raw.get("type_assurance") or "AUTRE").upper()
    if type_assurance not in SYSCOHADA_ACCOUNT_MAP:
        type_assurance = "AUTRE"

    benef_type = (raw.get("beneficiaire_type") or "INCONNU").upper()
    valid_benef = {"ENTREPRISE", "DIRIGEANT", "FAMILLE_DIRIGEANT", "PERSONNEL", "MIXTE", "INCONNU"}
    if benef_type not in valid_benef:
        benef_type = "INCONNU"

    pays = (raw.get("assureur_pays") or "CM").upper()

    prime = raw.get("prime_annuelle_ttc")
    try:
        prime_dec = Decimal(str(prime)) if prime is not None else None
    except Exception:  # noqa: BLE001
        prime_dec = None

    return ParsedInsuranceContract(
        numero_police=raw.get("numero_police"),
        assureur_nom=raw.get("assureur_nom"),
        assureur_niu=raw.get("assureur_niu"),
        assureur_pays=pays,
        assureur_adresse=raw.get("assureur_adresse"),
        souscripteur=raw.get("souscripteur"),
        beneficiaire_nom=raw.get("beneficiaire_nom"),
        beneficiaire_type=benef_type,
        type_assurance=type_assurance,
        date_debut=_parse_date(raw.get("date_debut")),
        date_fin=_parse_date(raw.get("date_fin")),
        prime_annuelle_ttc=prime_dec,
        compte_syscohada=SYSCOHADA_ACCOUNT_MAP.get(type_assurance),
        clauses_notables=raw.get("clauses_notables"),
        raw=raw,
        source=source,
    )
