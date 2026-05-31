"""DMM (Déclaration Mensuelle Multi-impôts) — Claude Vision extractor.

A DMM is a single PDF that aggregates SEVERAL tax declarations for one month:
TVA, Acompte IS, IRPP/salaires, IRCM, précomptes, etc. This module extracts
ALL of them in one Claude call and returns them as separate ExtractedTaxLine
records, ready to be persisted as N MonthlyReturn rows in the database.

Mock mode kicks in when ANTHROPIC_API_KEY is unset (so devs can wire the UI
without a key).
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import TaxType


log = logging.getLogger("fiscaudit.parser.dmm")


# ── Pydantic schemas for Claude structured output ────────────────────────────


class DmmTaxLine(BaseModel):
    """One tax type's line as extracted from a DMM PDF."""
    tax_type: str = Field(description=(
        "One of: TVA, ACOMPTE_IS, IRPP_SALAIRES, CNPS, TSR, "
        "PRECOMPTE_LOYERS, PRECOMPTE_ACHATS, IRCM, CFC, FNE, RAV, DROIT_TIMBRE"
    ))
    base_amount: float | None = Field(default=None, description=(
        "Base imposable / chiffre d'affaires for this tax line, in FCFA (no decimals). "
        "For ACOMPTE_IS this is the CA HT déclaré that produced the acompte."
    ))
    principal_amount: float = Field(default=0.0, description=(
        "Principal amount (without CAC and without penalties), in FCFA"
    ))
    cac_amount: float | None = Field(default=None, description=(
        "Centimes Additionnels Communaux (CAC), in FCFA"
    ))
    penalty_amount: float | None = Field(default=None, description=(
        "Pénalités, intérêts de retard, in FCFA"
    ))
    declared_amount: float = Field(description=(
        "Total amount due for this tax line (principal + CAC + penalties), in FCFA"
    ))
    line_code: str | None = Field(default=None, description=(
        "Form line code (e.g. L50 for acompte IS, L36 for TVA à payer, L76 for RTS salaires)"
    ))
    notes: str | None = Field(default=None)


class ExtractedDmm(BaseModel):
    """Full extraction of a DMM PDF."""
    taxpayer_niu: str | None = Field(default=None, description="NIU of the taxpayer")
    taxpayer_name: str | None = Field(default=None)
    regime: str | None = Field(default=None, description="REEL | SIMPLIFIE | …")
    period_year: int = Field(description="Fiscal year (e.g. 2026)")
    period_month: int = Field(description="Month 1-12")
    filing_date: str | None = Field(default=None, description="ISO 8601 date the DMM was filed")
    document_number: str | None = Field(default=None, description="Numéro de réception DGI (e.g. 44011315951)")
    total_to_pay: float | None = Field(default=None, description=(
        "TOTAL À PAYER as shown in the recap section, in FCFA"
    ))
    tax_lines: list[DmmTaxLine] = Field(
        description="One entry per non-zero tax type detected on the DMM",
    )
    notes: str | None = Field(default=None, description="Any anomaly or remark")


# ── Result dataclass (parser → caller contract) ──────────────────────────────


@dataclass
class ParsedDmm:
    taxpayer_niu: str | None
    taxpayer_name: str | None
    regime: str | None
    period_year: int
    period_month: int
    filing_date: date | None
    document_number: str | None
    total_to_pay: Decimal | None
    tax_lines: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    source: str = "claude_vision"   # "claude_vision" | "mock" | "regex_fallback"


# ── Claude client (lazy) ─────────────────────────────────────────────────────


def _get_client():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # type: ignore
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except ImportError:
        log.warning("anthropic SDK not installed")
        return None


SYSTEM_PROMPT_DMM = """You are an expert tax auditor at the Cameroon Direction
Générale des Impôts (DGI). You extract structured data from monthly multi-tax
declarations (DMM — Déclaration Mensuelle Multi-impôts) filed by Cameroonian
taxpayers.

The DMM is a single document that bundles ALL the taxes a company owes for
one month. The form has numbered lines (L1, L10, L15, L36, L44, L50, L54,
L62, L69, L76, …). Common sections you will see:

  Section 1  — TSR (Prélèvement Spécial Revenus à l'Étranger)       → L1
  Section 3  — TVA (CA réalisé)                                      → L10..L15
  Section 6  — TVA à payer / Crédit de TVA                          → L32..L35
  Section 7  — Total TVA à payer                                     → L36..L39
  Section 8  — Acomptes et précomptes à reverser                     → L40..L44
  Section 10 — Liquidation acompte IS (Art. 21 CGI)                  → L50..L55
  Section 11 — IRCM (Revenus de capitaux mobiliers)                  → L56..L62
  Section 12 — Retenues sur rémunérations agents commerciaux         → L63..L65
  Section 13 — Impôts sur revenus non commerciaux                    → L66..L69
  Section 14 — Impôts retenus sur salaires (RTS / IRPP)              → L70..L76
  Section 15 — Impôts sur plus-values                                → L77..L80
  Section 16 — Droit de timbre d'aéroport                            → L81..L83
  Section finale — RÉCAPITULATIF / TOTAL À PAYER

Map each section to a tax_type:
  Section 3+6+7 (TVA)                → tax_type = "TVA"
  Section 10 (Acompte IS, L50/L54)   → tax_type = "ACOMPTE_IS"
                                       base_amount = CA HT déclaré
                                                   = L50 Principal / 0.02
  Section 11 (IRCM, L62)             → tax_type = "IRCM"
  Section 14 (RTS salaires, L76)     → tax_type = "IRPP_SALAIRES"
  Section 8 — Précomptes (L41/L42/L43) → "PRECOMPTE_ACHATS" / "PRECOMPTE_LOYERS"
  Section 1 (TSR, L1)                → tax_type = "TSR"

For EACH tax type with a non-zero amount, return ONE DmmTaxLine. Skip tax types
where principal AND total are both zero.

Important rules:
- Always set period_year and period_month from the header ("Mois de : …" /
  "Exercice fiscal : …"). These are mandatory.
- For ACOMPTE_IS, set base_amount = CA HT déclaré (you can compute it from L50
  Principal / 0.02 if not directly visible).
- declared_amount is the TOTAL column (principal + CAC + penalties).
- Amounts are FCFA, no decimals. If a number has spaces (1 613 750), strip them.
- If the document is illegible or critical fields are missing, set period_year
  to 0 and explain in `notes`.
- Never invent data."""


# ── Mock mode (for dev without API key) ──────────────────────────────────────


def _mock_dmm(pdf_bytes: bytes) -> dict[str, Any]:
    """Generate plausible synthetic DMM data."""
    import hashlib
    h = int(hashlib.sha256(pdf_bytes).hexdigest()[:8], 16)
    month = (h % 12) + 1
    year = 2026

    # Plausible CA + acompte
    ca = 1_000_000 + (h % 5_000_000)
    acompte_principal = int(ca * 0.02)
    acompte_cac = int(acompte_principal * 0.10)
    acompte_total = acompte_principal + acompte_cac

    tva_collectee = int(ca * 0.1925)
    tva_deductible = int(tva_collectee * 0.95)
    tva_due = max(0, tva_collectee - tva_deductible)

    rts_principal = 800_000 + (h % 200_000)
    rts_cac = int(rts_principal * 0.10)
    rts_total = rts_principal + rts_cac

    return {
        "taxpayer_niu": "M105929849503U",
        "taxpayer_name": "MOCK SARL",
        "regime": "REEL",
        "period_year": year,
        "period_month": month,
        "filing_date": date(year, min(month + 1, 12), 14).isoformat(),
        "document_number": f"4401131{h % 10000:04d}",
        "total_to_pay": float(acompte_total + tva_due + rts_total),
        "tax_lines": [
            {
                "tax_type": "ACOMPTE_IS",
                "base_amount": float(ca),
                "principal_amount": float(acompte_principal),
                "cac_amount": float(acompte_cac),
                "penalty_amount": 0,
                "declared_amount": float(acompte_total),
                "line_code": "L50",
                "notes": None,
            },
            {
                "tax_type": "TVA",
                "base_amount": float(ca),
                "principal_amount": float(tva_due),
                "cac_amount": None,
                "penalty_amount": 0,
                "declared_amount": float(tva_due),
                "line_code": "L36",
                "notes": None,
            },
            {
                "tax_type": "IRPP_SALAIRES",
                "base_amount": None,
                "principal_amount": float(rts_principal),
                "cac_amount": float(rts_cac),
                "penalty_amount": 0,
                "declared_amount": float(rts_total),
                "line_code": "L76",
                "notes": None,
            },
        ],
        "notes": "MOCK DATA — set ANTHROPIC_API_KEY for real extraction.",
    }


# ── Live extraction ──────────────────────────────────────────────────────────


def _extract_with_claude(pdf_bytes: bytes) -> dict[str, Any]:
    """Call Claude Vision via standard messages.create + JSON parsing.

    Works with anthropic SDK >= 0.34 (no need for messages.parse).
    """
    import json as _json
    client = _get_client()
    if client is None:
        raise RuntimeError("No Anthropic client available")
    settings = get_settings()
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    # Embed the JSON schema right in the prompt so the model knows exactly
    # what shape to return.
    schema_str = _json.dumps(ExtractedDmm.model_json_schema(), ensure_ascii=False, indent=2)
    user_text = (
        "Extract every non-zero tax line from this DMM PDF.\n\n"
        "Return ONE valid JSON object matching this schema (no markdown fence, "
        "no commentary — just the raw JSON):\n\n"
        f"```json\n{schema_str}\n```"
    )

    response = client.messages.create(
        model=settings.anthropic_model or "claude-sonnet-4-5",
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT_DMM,
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

    # Concatenate all text blocks then locate the JSON object
    text_out = "".join(
        getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    if not text_out:
        raise RuntimeError("Claude returned no text")

    # Strip markdown fence if present
    if text_out.startswith("```"):
        text_out = text_out.strip("`")
        if text_out.lower().startswith("json"):
            text_out = text_out[4:].lstrip("\n")

    # Extract first {...} balanced block
    start = text_out.find("{")
    end = text_out.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"No JSON object in Claude response: {text_out[:200]}")
    payload = text_out[start : end + 1]
    try:
        data = _json.loads(payload)
    except _json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from Claude ({e}): {payload[:200]}")

    # Validate via Pydantic (raises if shape is off)
    parsed = ExtractedDmm.model_validate(data)
    return parsed.model_dump()


# ── Regex fallback (very lightweight, just for ACOMPTE_IS) ───────────────────


_RE_MONTH = re.compile(r"Mois\s*de\s*[:\-]?\s*(\w+)", re.I)
_RE_YEAR  = re.compile(r"Exercice\s*fiscal\s*[:\-]?\s*(\d{4})", re.I)
_RE_NIU   = re.compile(r"\b(M0\d{10,12}[A-Z])\b")
_RE_L50   = re.compile(r"L50\s+([\d\s]+)\s+([\d\s]+)", re.I)
_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def _regex_fallback(pdf_text: str) -> dict[str, Any] | None:
    """Last-resort fallback when Claude is unavailable AND mock isn't acceptable."""
    if not pdf_text:
        return None
    m_year = _RE_YEAR.search(pdf_text)
    m_month = _RE_MONTH.search(pdf_text)
    if not m_year or not m_month:
        return None
    year = int(m_year.group(1))
    mlabel = m_month.group(1).lower().strip()
    month = _MONTHS_FR.get(mlabel)
    if month is None:
        return None
    return {
        "taxpayer_niu": (_RE_NIU.search(pdf_text) or [None])[0] if _RE_NIU.search(pdf_text) else None,
        "taxpayer_name": None,
        "regime": "REEL",
        "period_year": year,
        "period_month": month,
        "filing_date": None,
        "document_number": None,
        "total_to_pay": None,
        "tax_lines": [],
        "notes": "Regex fallback — only period extracted.",
    }


# ── Public API ───────────────────────────────────────────────────────────────


def _to_decimal(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def extract_dmm(pdf_bytes: bytes) -> ParsedDmm:
    """Extract a full DMM into a ParsedDmm. Tries Claude, then mock, then regex."""
    client = _get_client()
    source = "mock"
    raw: dict[str, Any]
    if client is not None:
        try:
            raw = _extract_with_claude(pdf_bytes)
            source = "claude_vision"
        except Exception as e:  # noqa: BLE001
            log.warning("Claude Vision extraction failed (%s) — falling back to mock", e)
            raw = _mock_dmm(pdf_bytes)
    else:
        raw = _mock_dmm(pdf_bytes)

    filing_date_iso = raw.get("filing_date")
    filing_date = None
    if filing_date_iso:
        try:
            filing_date = datetime.fromisoformat(filing_date_iso).date()
        except (ValueError, TypeError):
            filing_date = None

    return ParsedDmm(
        taxpayer_niu=raw.get("taxpayer_niu"),
        taxpayer_name=raw.get("taxpayer_name"),
        regime=raw.get("regime"),
        period_year=int(raw.get("period_year") or 0),
        period_month=int(raw.get("period_month") or 0),
        filing_date=filing_date,
        document_number=raw.get("document_number"),
        total_to_pay=_to_decimal(raw.get("total_to_pay")),
        tax_lines=raw.get("tax_lines") or [],
        raw=raw,
        source=source,
    )
