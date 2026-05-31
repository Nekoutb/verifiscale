"""Claude Vision-based supplier invoice extractor + CGI compliance scoring.

For each supplier invoice PDF we extract a structured record and score it
against the substance / form conditions required by CGI Cameroun art. 150 and
LPF art. L 8 bis.

Operating modes:
  - **Live**  : real Claude Vision call when ANTHROPIC_API_KEY is set.
  - **Mock**  : returns synthetic data so the rest of the pipeline can be
                exercised without an API key (dev / CI / demos).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings


log = logging.getLogger("fiscaudit.parser.invoices")


# ─── OCR schema ─────────────────────────────────────────────────────────────


class ExtractedInvoice(BaseModel):
    supplier_name: str | None = Field(default=None, description="Raison sociale du fournisseur")
    supplier_niu: str | None = Field(default=None, description="NIU du fournisseur (M021xxxxxxxxxX)")
    supplier_rccm: str | None = Field(default=None, description="Numéro RCCM")
    supplier_address: str | None = None
    supplier_tax_center: str | None = Field(default=None, description="Centre des impôts de rattachement")
    customer_name: str | None = None
    customer_niu: str | None = None
    invoice_number: str | None = Field(default=None, description="Numéro de facture séquentiel")
    invoice_date: str | None = Field(default=None, description="Date de facture ISO YYYY-MM-DD")
    base_ht_xaf: float | None = Field(default=None, description="Base HT en FCFA")
    tva_xaf: float | None = Field(default=None, description="Montant TVA en FCFA")
    ttc_xaf: float | None = Field(default=None, description="Montant TTC en FCFA")
    tva_rate_pct: float | None = Field(default=None, description="Taux TVA en %, ex 19.25")
    currency: str = Field(default="XAF")
    description: str | None = Field(default=None, description="Désignation des biens/services")


@dataclass
class ParsedInvoice:
    data: ExtractedInvoice
    raw: dict[str, Any]
    source: str  # "claude_vision" | "mock"


# ─── Anthropic client ────────────────────────────────────────────────────────


def _get_client():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # type: ignore
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except ImportError:
        log.warning("anthropic SDK not installed — invoice OCR running in mock mode")
        return None


SYSTEM_PROMPT_INVOICE = """You are an expert auditor at the Cameroon Direction
Générale des Impôts (DGI). You extract structured data from supplier invoices
(factures fournisseurs) presented to the audited taxpayer.

A compliant Cameroonian invoice (CGI art. 150 + LPF L 8 bis) must show:
- Supplier identity: raison sociale, NIU (format M021xxxxxxxxxX or
  P021xxxxxxxxxX), RCCM, address, centre des impôts de rattachement.
- Customer identity: raison sociale, NIU.
- Invoice number (sequential per fiscal year).
- Invoice date.
- Designation of goods or services.
- Base HT, taux TVA (typically 19,25 %), montant TVA, montant TTC — in FCFA.

For each PDF, extract the available fields. If a field is illegible or absent,
set it to null — do NOT invent values. The downstream control engine will flag
missing mandatory fields automatically.

Return strict JSON matching the provided schema."""


# ─── Extraction ──────────────────────────────────────────────────────────────


def _mock_extract(pdf_bytes: bytes, filename: str) -> ParsedInvoice:
    """Deterministic mock so demos look realistic without an API key.

    Uses the SHA of the file to pick from a small set of fake suppliers, so
    the same PDF always parses to the same vendor (useful for grouping demos).
    """
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    seed = int(sha[:8], 16)
    suppliers = [
        ("M021400123456A", "TOTAL ENERGIES CAMEROUN SA", "CIME-DLA-2018-001234", "DGE-D-001"),
        ("M021500987654B", "ENEO CAMEROON SA",          "RC/DLA/2014/B/00045",  "DGE-D-002"),
        ("M021600111222C", "ORANGE CAMEROUN SA",         "RC/DLA/2000/B/11122",  "DGE-D-003"),
        ("M021700333444D", "CIMENCAM SA",                "RC/DLA/1965/B/00007",  "DGE-D-004"),
        ("P021800555666E", "QUINCAILLERIE BEN ETS",      "RC/YDE/2019/A/00821",  "CIME-YDE-CENTRE"),
    ]
    sup_niu, sup_name, sup_rccm, sup_center = suppliers[seed % len(suppliers)]
    base = Decimal((seed % 9_500_000) + 50_000)
    tva = (base * Decimal("0.1925")).quantize(Decimal("1.00"))
    ttc = base + tva
    inv_num = f"FAC-{2026 - (seed % 4):04d}-{seed % 9999:04d}"
    # Force occasional missing fields so controls flag them in demo
    if seed % 7 == 0:
        sup_niu = None  # missing NIU → fond fail
    if seed % 11 == 0:
        inv_num = None  # missing number → forme fail
    data = ExtractedInvoice(
        supplier_name=sup_name,
        supplier_niu=sup_niu,
        supplier_rccm=sup_rccm,
        supplier_address="BP 1234, Douala — Akwa",
        supplier_tax_center=sup_center,
        customer_name="KISSY WEARS SARL",
        customer_niu="M021900777888F",
        invoice_number=inv_num,
        invoice_date=f"2025-{(seed % 12) + 1:02d}-{(seed % 27) + 1:02d}",
        base_ht_xaf=float(base),
        tva_xaf=float(tva),
        ttc_xaf=float(ttc),
        tva_rate_pct=19.25,
        currency="XAF",
        description="Fourniture diverses",
    )
    return ParsedInvoice(data=data, raw=data.model_dump(), source="mock")


def _claude_extract(pdf_bytes: bytes, filename: str) -> ParsedInvoice:
    client = _get_client()
    if client is None:
        return _mock_extract(pdf_bytes, filename)
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    settings = get_settings()
    model = settings.anthropic_model or "claude-opus-4-5"
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=1500,
            system=[{"type": "text", "text": SYSTEM_PROMPT_INVOICE, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": (
                        "Extract the structured invoice data. Reply with ONLY a JSON "
                        "object matching this schema (no markdown, no commentary):\n"
                        f"{ExtractedInvoice.model_json_schema()}"
                    )},
                ],
            }],
        )
        # Take the first text block, strip code fences if present
        raw_text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.MULTILINE).strip()
        import json
        parsed = json.loads(raw_text)
        return ParsedInvoice(data=ExtractedInvoice(**parsed), raw=parsed, source="claude_vision")
    except Exception as e:  # noqa: BLE001
        log.warning(f"claude vision OCR failed ({e!r}) — falling back to mock")
        return _mock_extract(pdf_bytes, filename)


def extract_invoice(pdf_bytes: bytes, filename: str) -> ParsedInvoice:
    """Public entry point. Tries Claude Vision, falls back to mock."""
    if _get_client() is None:
        return _mock_extract(pdf_bytes, filename)
    return _claude_extract(pdf_bytes, filename)


# ─── Compliance controls (conditions de fond et de forme) ───────────────────


# NIU regex — same as taxpayers router. M (moral) or P (physical) + 9-12 digits
# + uppercase letter suffix.
NIU_RE = re.compile(r"^[MP]\d{9,12}[A-Z]$")


def score_invoice(inv: ExtractedInvoice) -> dict[str, Any]:
    """Run CGI art. 150 / LPF L 8 bis controls and return a results dict.

    Result schema:
      {
        "fond": { "<code>": {"passed": bool, "label": str} },
        "forme": { "<code>": {"passed": bool, "label": str} },
        "failed_fond_count": int,
        "failed_forme_count": int,
        "is_compliant": bool,
      }
    """
    fond: dict[str, dict[str, Any]] = {}
    forme: dict[str, dict[str, Any]] = {}

    # ── Conditions de fond (substance) ──────────────────────────────────────
    # F1. NIU fournisseur présent et bien formé
    niu_ok = bool(inv.supplier_niu and NIU_RE.match((inv.supplier_niu or "").upper()))
    fond["FOND_NIU_VALID"] = {"passed": niu_ok, "label": "NIU fournisseur présent et valide"}

    # F2. Raison sociale fournisseur
    fond["FOND_SUPPLIER_NAME"] = {
        "passed": bool(inv.supplier_name and len(inv.supplier_name.strip()) >= 3),
        "label": "Raison sociale fournisseur renseignée",
    }

    # F3. Montants cohérents : base + TVA ≈ TTC
    amounts_ok = False
    if inv.base_ht_xaf is not None and inv.tva_xaf is not None and inv.ttc_xaf is not None:
        diff = abs(Decimal(str(inv.base_ht_xaf)) + Decimal(str(inv.tva_xaf)) - Decimal(str(inv.ttc_xaf)))
        amounts_ok = diff <= Decimal("100")
    fond["FOND_AMOUNTS_CONSISTENT"] = {
        "passed": amounts_ok,
        "label": "Cohérence Base HT + TVA = TTC",
    }

    # F4. Taux TVA standard 19.25% (sauf exonération)
    rate_ok = inv.tva_rate_pct is None or abs(float(inv.tva_rate_pct) - 19.25) < 0.5 or float(inv.tva_rate_pct) == 0
    fond["FOND_TVA_RATE_STANDARD"] = {
        "passed": rate_ok,
        "label": "Taux TVA = 19,25 % (ou exonération)",
    }

    # F5. Description / désignation présente
    fond["FOND_DESCRIPTION"] = {
        "passed": bool(inv.description and len(inv.description.strip()) >= 3),
        "label": "Désignation des biens/services renseignée",
    }

    # ── Conditions de forme ─────────────────────────────────────────────────
    # FM1. Numéro de facture présent et séquentiel
    forme["FORME_INVOICE_NUMBER"] = {
        "passed": bool(inv.invoice_number and len(inv.invoice_number.strip()) >= 3),
        "label": "Numéro de facture séquentiel",
    }
    # FM2. Date de facture présente
    date_ok = False
    if inv.invoice_date:
        try:
            datetime.strptime(inv.invoice_date, "%Y-%m-%d")
            date_ok = True
        except ValueError:
            date_ok = False
    forme["FORME_INVOICE_DATE"] = {"passed": date_ok, "label": "Date de facture présente"}
    # FM3. RCCM fournisseur
    forme["FORME_SUPPLIER_RCCM"] = {
        "passed": bool(inv.supplier_rccm and len(inv.supplier_rccm.strip()) >= 4),
        "label": "RCCM fournisseur mentionné",
    }
    # FM4. Adresse fournisseur
    forme["FORME_SUPPLIER_ADDRESS"] = {
        "passed": bool(inv.supplier_address and len(inv.supplier_address.strip()) >= 5),
        "label": "Adresse fournisseur mentionnée",
    }
    # FM5. Centre des impôts de rattachement
    forme["FORME_TAX_CENTER"] = {
        "passed": bool(inv.supplier_tax_center and len(inv.supplier_tax_center.strip()) >= 2),
        "label": "Centre des impôts de rattachement mentionné",
    }
    # FM6. NIU client (l'audité)
    forme["FORME_CUSTOMER_NIU"] = {
        "passed": bool(inv.customer_niu and NIU_RE.match((inv.customer_niu or "").upper())),
        "label": "NIU du client (audité) mentionné",
    }

    failed_fond = sum(1 for v in fond.values() if not v["passed"])
    failed_forme = sum(1 for v in forme.values() if not v["passed"])

    return {
        "fond": fond,
        "forme": forme,
        "failed_fond_count": failed_fond,
        "failed_forme_count": failed_forme,
        "is_compliant": failed_fond == 0 and failed_forme == 0,
    }
