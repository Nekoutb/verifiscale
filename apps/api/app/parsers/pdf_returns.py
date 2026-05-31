"""Claude Vision-based PDF extraction for Cameroon tax returns.

For each tax type, a small Pydantic schema tells Claude exactly what to extract
from a DSF-M / quittance PDF. The system prompt is prompt-cached per tax type
(stable text >1024 tokens not required here, but we tag it for forward-compat
when we add few-shot examples).

Operating modes:
  - **Live**  : real Claude Vision call when ANTHROPIC_API_KEY is set.
  - **Mock**  : returns realistic synthetic data so the rest of the system
                (controls, UI, reconciliation) can be demonstrated without
                an API key.

Mock mode is the default for local dev. To use the real API, set
ANTHROPIC_API_KEY in apps/api/.env.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import TaxType


log = logging.getLogger("fiscaudit.parser.pdf")

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic extraction schemas (one per logical document type)
# ─────────────────────────────────────────────────────────────────────────────


class ExtractedMonthlyReturn(BaseModel):
    """Schema Claude Vision returns for a monthly tax return PDF."""

    tax_type: str = Field(description="One of: TVA, IRPP_SALAIRES, CNPS, TSR, "
                                       "PRECOMPTE_LOYERS, PRECOMPTE_ACHATS, IRCM, "
                                       "ACOMPTE_IS, CFC, FNE, RAV, DROIT_TIMBRE")
    period_year: int = Field(description="Fiscal year of the declaration, e.g. 2024")
    period_month: int | None = Field(default=None, description="Month 1-12, null for quarterly/annual")
    period_quarter: int | None = Field(default=None, description="Quarter 1-4, null for monthly/annual")
    filing_date: str | None = Field(default=None, description="Date the return was filed, ISO 8601 YYYY-MM-DD")
    declared_amount: float = Field(description="Net tax payable as declared, in FCFA (no decimals)")
    base_amount: float | None = Field(default=None, description="Taxable base, e.g. CA HT for TVA, in FCFA")
    credit_reporte: float | None = Field(default=None, description="TVA credit carried forward, if applicable")
    notes: str | None = Field(default=None, description="Any anomaly worth flagging to the auditor")


class ExtractedPaymentProof(BaseModel):
    """Schema Claude Vision returns for a payment receipt (quittance) PDF."""

    payment_date: str = Field(description="Date of payment, ISO 8601 YYYY-MM-DD")
    amount_paid: float = Field(description="Amount paid in FCFA")
    reference: str | None = Field(default=None, description="Quittance number or bordereau reference")
    method: str = Field(default="VIREMENT", description="One of: VIREMENT, ESPECES, CHEQUE, MOBILE_MONEY, COMPENSATION")
    bank: str | None = Field(default=None, description="Bank name if visible")
    tax_type_hint: str | None = Field(default=None, description="If the receipt indicates which tax was paid")
    period_hint: str | None = Field(default=None, description="Free-form period text from the receipt, e.g. 'Janvier 2024'")
    notes: str | None = Field(default=None, description="Anything else worth flagging")


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses (parser → caller contract)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParsedReturn:
    tax_type: TaxType
    period_year: int
    period_month: int | None
    period_quarter: int | None
    filing_date: date | None
    declared_amount: Decimal
    base_amount: Decimal | None
    credit_reporte: Decimal | None
    raw: dict[str, Any]
    source: str  # "claude_vision" | "mock"


@dataclass
class ParsedPayment:
    payment_date: date
    amount_paid: Decimal
    reference: str | None
    method: str
    bank: str | None
    tax_type_hint: TaxType | None
    period_hint: str | None
    raw: dict[str, Any]
    source: str


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic client (lazy)
# ─────────────────────────────────────────────────────────────────────────────


def _get_client():
    """Lazy import + construct the Anthropic client. Returns None if no API key."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # type: ignore
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except ImportError:
        log.warning("anthropic SDK not installed — falling back to mock mode")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# System prompts (cached server-side via prompt caching)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_MONTHLY_RETURN = """You are an expert auditor at the Cameroon
Direction Générale des Impôts (DGI). You extract structured data from monthly
tax return PDFs (DSF-M format) filed by Cameroonian taxpayers.

Common tax types you will see:
- TVA (Taxe sur la Valeur Ajoutée) — monthly VAT
- IRPP_SALAIRES — monthly income tax withholding on salaries
- CNPS — social security contributions
- TSR — special tax on services paid to non-residents
- PRECOMPTE_LOYERS — withholding on rents paid
- PRECOMPTE_ACHATS — withholding on purchases
- IRCM — withholding on dividends/interest
- ACOMPTE_IS — quarterly corporate income tax installment
- CFC / FNE / RAV — payroll-based contributions
- DROIT_TIMBRE — stamp duty

For each PDF, return strict JSON with the period, declared amount, taxable base,
and (for TVA) any credit carried forward. Amounts are in FCFA — no decimals.

If the document is ambiguous or you cannot determine a field with high
confidence, set it to null and explain in 'notes'. Never invent values."""

SYSTEM_PROMPT_PAYMENT_PROOF = """You are an expert auditor at the Cameroon DGI.
You extract structured data from payment receipts (quittances) for tax payments.

A typical quittance shows:
- Date of payment
- Amount paid (in FCFA)
- Reference number (quittance n°, bordereau n°)
- Payment method (virement bancaire, espèces, chèque, mobile money)
- Bank or DGI window where it was paid
- Often the tax type and period it covers

Return strict JSON. If a field is unclear, set it to null and explain in 'notes'.
Never invent values."""


# ─────────────────────────────────────────────────────────────────────────────
# Live extraction (Claude Vision)
# ─────────────────────────────────────────────────────────────────────────────


def _build_pdf_content(pdf_bytes: bytes) -> list[dict]:
    """Build the Anthropic Messages API user-content list with the PDF document."""
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    return [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        },
        {"type": "text", "text": "Extract the structured data per the schema."},
    ]


def _extract_with_claude(
    pdf_bytes: bytes,
    schema_class: type[BaseModel],
    system_prompt: str,
    hint_tax_type: TaxType | None = None,
) -> dict[str, Any]:
    """Call Claude Vision and return the parsed structured output as a dict."""
    client = _get_client()
    if client is None:
        raise RuntimeError("No Anthropic client available (no API key)")

    settings = get_settings()
    hint_text = ""
    if hint_tax_type:
        hint_text = f"\n\nThe auditor has tagged this document as type: {hint_tax_type.value}. " \
                    f"Use this as a hint but verify against the PDF content."

    # Prompt caching on the system prompt — same text per tax type across many docs
    response = client.messages.parse(
        model=settings.anthropic_model or "claude-opus-4-7",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt + hint_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": _build_pdf_content(pdf_bytes)}],
        output_format=schema_class,
    )

    parsed = response.parsed_output  # Pydantic instance or None
    if parsed is None:
        raise RuntimeError("Claude Vision returned no structured output")
    return parsed.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# Mock mode — realistic synthetic data
# ─────────────────────────────────────────────────────────────────────────────


def _mock_monthly_return(
    pdf_bytes: bytes,
    hint_tax_type: TaxType | None,
    audit_case_period: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Generate plausible synthetic data for a monthly return.

    Uses the file size as a stable seed so re-parsing the same PDF gives the same
    answer (handy when testing reconciliation).
    """
    import hashlib
    h = int(hashlib.sha256(pdf_bytes).hexdigest()[:8], 16)

    tax_type = hint_tax_type or TaxType.TVA
    year = audit_case_period[0] if audit_case_period else 2024
    month = (h % 12) + 1

    # Plausible amounts per tax type (varies with hash)
    base_amounts = {
        TaxType.TVA: 28_700_000 + (h % 5_000_000),
        TaxType.IRPP_SALAIRES: 6_200_000 + (h % 800_000),
        TaxType.CNPS: 5_800_000 + (h % 600_000),
        TaxType.TSR: 1_500_000 + (h % 500_000),
        TaxType.ACOMPTE_IS: 4_500_000 + (h % 1_000_000),
        TaxType.CFC: 750_000 + (h % 100_000),
        TaxType.FNE: 750_000 + (h % 100_000),
    }
    base = base_amounts.get(tax_type, 2_000_000 + (h % 500_000))

    # Filing date = the 12th of the month following the period (slight slack)
    if month == 12:
        filing = date(year + 1, 1, 12)
    else:
        filing = date(year, month + 1, 12)

    return {
        "tax_type": tax_type.value,
        "period_year": year,
        "period_month": month,
        "period_quarter": None,
        "filing_date": filing.isoformat(),
        "declared_amount": float(base),
        "base_amount": float(base * 6) if tax_type == TaxType.TVA else None,  # TVA: base ≈ 6× tax @ 17.5%
        "credit_reporte": None,
        "notes": "MOCK DATA — extraction synthesized for demo. Set ANTHROPIC_API_KEY to use Claude Vision.",
    }


def _mock_payment_proof(pdf_bytes: bytes) -> dict[str, Any]:
    import hashlib
    h = int(hashlib.sha256(pdf_bytes).hexdigest()[:8], 16)

    return {
        "payment_date": date(2024, ((h % 11) + 1), 12).isoformat(),
        "amount_paid": float(5_000_000 + (h % 25_000_000)),
        "reference": f"QTC-{h:08d}",
        "method": "VIREMENT",
        "bank": "Société Générale Cameroun",
        "tax_type_hint": None,
        "period_hint": None,
        "notes": "MOCK DATA — payment proof synthesized for demo.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def extract_monthly_return(
    pdf_bytes: bytes,
    hint_tax_type: TaxType | None = None,
    audit_case_period: tuple[int, int] | None = None,
) -> ParsedReturn:
    """Extract a monthly tax return from a PDF.

    Args:
        pdf_bytes: raw bytes of the PDF.
        hint_tax_type: if the auditor tagged the dataset with a specific kind,
            pass it as a hint to Claude (and as a fallback for mock mode).
        audit_case_period: (year, month) of the audit case period for mock mode.

    Returns:
        ParsedReturn with normalized fields ready to insert as a MonthlyReturn row.
    """
    client = _get_client()
    raw: dict[str, Any]
    source: str

    if client is None:
        raw = _mock_monthly_return(pdf_bytes, hint_tax_type, audit_case_period)
        source = "mock"
    else:
        try:
            raw = _extract_with_claude(
                pdf_bytes,
                ExtractedMonthlyReturn,
                SYSTEM_PROMPT_MONTHLY_RETURN,
                hint_tax_type=hint_tax_type,
            )
            source = "claude_vision"
        except Exception as e:  # noqa: BLE001
            log.warning("Claude Vision extraction failed (%s) — falling back to mock", e)
            raw = _mock_monthly_return(pdf_bytes, hint_tax_type, audit_case_period)
            source = "mock_fallback"

    # Normalize → ParsedReturn
    try:
        tax_type = TaxType(raw["tax_type"])
    except (KeyError, ValueError):
        tax_type = hint_tax_type or TaxType.TVA

    filing = _parse_date(raw.get("filing_date"))

    return ParsedReturn(
        tax_type=tax_type,
        period_year=int(raw.get("period_year") or 2024),
        period_month=raw.get("period_month"),
        period_quarter=raw.get("period_quarter"),
        filing_date=filing,
        declared_amount=Decimal(str(raw.get("declared_amount") or 0)),
        base_amount=Decimal(str(raw["base_amount"])) if raw.get("base_amount") is not None else None,
        credit_reporte=Decimal(str(raw["credit_reporte"])) if raw.get("credit_reporte") is not None else None,
        raw=raw,
        source=source,
    )


def extract_payment_proof(pdf_bytes: bytes) -> ParsedPayment:
    """Extract a payment receipt from a PDF."""
    client = _get_client()
    raw: dict[str, Any]
    source: str

    if client is None:
        raw = _mock_payment_proof(pdf_bytes)
        source = "mock"
    else:
        try:
            raw = _extract_with_claude(pdf_bytes, ExtractedPaymentProof, SYSTEM_PROMPT_PAYMENT_PROOF)
            source = "claude_vision"
        except Exception as e:  # noqa: BLE001
            log.warning("Claude Vision extraction failed (%s) — falling back to mock", e)
            raw = _mock_payment_proof(pdf_bytes)
            source = "mock_fallback"

    pay_date = _parse_date(raw.get("payment_date")) or date.today()

    tax_hint = None
    if raw.get("tax_type_hint"):
        try:
            tax_hint = TaxType(raw["tax_type_hint"])
        except ValueError:
            pass

    return ParsedPayment(
        payment_date=pay_date,
        amount_paid=Decimal(str(raw.get("amount_paid") or 0)),
        reference=raw.get("reference"),
        method=raw.get("method") or "VIREMENT",
        bank=raw.get("bank"),
        tax_type_hint=tax_hint,
        period_hint=raw.get("period_hint"),
        raw=raw,
        source=source,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def filing_deadline_for(tax_type: TaxType, year: int, month: int | None) -> date:
    """Return the legal filing deadline for a given tax / period.

    Monthly taxes: 15 of N+1. Quarterly acomptes IS: 15 of month after the quarter.
    Annual taxes: 15 March of N+1 for IS, 28 Feb for Patente, 30 June for Foncier.
    """
    if month and 1 <= month <= 12:
        # Monthly — deadline is 15 of next month
        nm = month + 1 if month < 12 else 1
        ny = year if month < 12 else year + 1
        return date(ny, nm, 15)

    # Annual fallbacks
    if tax_type == TaxType.IS_ANNUEL:
        return date(year + 1, 3, 15)
    if tax_type == TaxType.PATENTE:
        return date(year + 1, 2, 28)
    if tax_type == TaxType.FONCIER:
        return date(year + 1, 6, 30)

    # Default — 15 January of N+1
    return date(year + 1, 1, 15)
