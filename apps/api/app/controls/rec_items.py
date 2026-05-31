"""Reconciliation-skill methodology.

When a rec card has a non-zero variance, this module asks Claude to categorize
the reconciling items per standard reconciliation methodology:

  - TIMING                — in-transit / unposted / cut-off differences
  - POSTING_ERROR         — wrong amount / wrong account / wrong period
  - OMISSION              — entry missing in one of the two books
  - FX_GAIN_LOSS          — translation difference
  - INTERCOMPANY_UNMATCHED — IC counterparty mismatch
  - OTHER                 — anything else worth surfacing

Each item gets a likelihood (HIGH/MEDIUM/LOW), an estimated amount, an aging
bucket (0-30/31-60/61-90/>90 days), and an escalation flag when the rec
delta exceeds the materiality threshold.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.config import get_settings


log = logging.getLogger("fiscaudit.rec_items")


# Materiality default — auditor will tune per case.
DEFAULT_MATERIALITY_XAF = Decimal("500000")  # 500 000 FCFA


SYSTEM_PROMPT = """You are an expert auditor performing account reconciliation
analysis. Your output drives a SaaS used by Cameroon DGI tax auditors.

You will receive a reconciliation summary: the reference total (typically a
trial-balance / GL closing balance), the counter total (subledger or
third-party source), and the variance between them.

Apply standard reconciliation methodology to identify and categorize likely
RECONCILING ITEMS — the entries that, if posted, would close the variance.

For each suspected item, return:
  - category: one of TIMING, POSTING_ERROR, OMISSION, FX_GAIN_LOSS,
              INTERCOMPANY_UNMATCHED, OTHER
  - description: 1 short French sentence (auditor-readable) explaining the
                 suspected nature, citing the specific GL account or subledger
                 line when it can be inferred from the data provided
  - estimated_amount_xaf: best estimate in FCFA (the absolute amount, no sign)
  - likelihood: HIGH | MEDIUM | LOW
  - aging_bucket: ZERO_TO_30 | THIRTY_ONE_TO_60 | SIXTY_ONE_TO_90 | OVER_90
                  | UNKNOWN
  - action: 1 short imperative in French — what the auditor should request
            from the contribuable to clear this item.

Methodology cues you must apply:
  - If the variance is large and round (e.g. 1 000 000), suspect a single
    posting error or omission.
  - If many GL accounts contribute to the breakdown, suspect timing across
    several entries.
  - If a class 47 (intercompany) account is in the breakdown, prefer
    INTERCOMPANY_UNMATCHED.
  - If amounts in a foreign-currency-sounding account exist, prefer
    FX_GAIN_LOSS.
  - If the subledger total is below the GL, OMISSION in the subledger is
    likely; if GL is below, OMISSION in the GL.
  - When you cannot infer aging, return UNKNOWN — never invent it.

Return STRICT JSON with this shape (no markdown, no prose around it):
{
  "items": [
    {
      "category": "TIMING",
      "description": "Encaissement client en transit non posté au GL au 31/12",
      "estimated_amount_xaf": 320000,
      "likelihood": "HIGH",
      "aging_bucket": "ZERO_TO_30",
      "action": "Obtenir l'avis de crédit bancaire de janvier pour justification."
    }
  ],
  "summary": "Short 1-sentence overall conclusion."
}

If the variance is zero or below the materiality threshold given to you, return
an empty items list and a summary saying the reconciliation is clean."""


@dataclass
class RecItem:
    category: str
    description: str
    estimated_amount_xaf: float
    likelihood: str
    aging_bucket: str
    action: str


@dataclass
class RecItemsAnalysis:
    items: list[RecItem] = field(default_factory=list)
    summary: str = ""
    escalation: bool = False
    materiality_xaf: float = 0.0
    source: str = "claude"  # or "mock"

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "category": i.category,
                    "description": i.description,
                    "estimated_amount_xaf": i.estimated_amount_xaf,
                    "likelihood": i.likelihood,
                    "aging_bucket": i.aging_bucket,
                    "action": i.action,
                }
                for i in self.items
            ],
            "summary": self.summary,
            "escalation": self.escalation,
            "materiality_xaf": self.materiality_xaf,
            "source": self.source,
        }


def categorize_variance(
    *,
    rec_key: str,
    rec_title: str,
    ref_label: str,
    ref_amount: Decimal,
    counter_label: str,
    counter_amount: Decimal | None,
    variance_xaf: Decimal,
    account_breakdown: list[dict[str, Any]] | None = None,
    materiality_xaf: Decimal = DEFAULT_MATERIALITY_XAF,
) -> RecItemsAnalysis | None:
    """Return categorized reconciling items for the given rec.

    None if no variance or no API key. Always sets `escalation=True` when
    |variance| >= materiality.
    """
    if counter_amount is None:
        return None
    if abs(variance_xaf) < materiality_xaf:
        # Clean rec — nothing to categorize
        return RecItemsAnalysis(
            items=[],
            summary="Aucun écart matériel détecté — rapprochement conforme.",
            escalation=False,
            materiality_xaf=float(materiality_xaf),
            source="trivial",
        )

    settings = get_settings()
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return RecItemsAnalysis(
            items=[],
            summary="Analyse IA indisponible — ANTHROPIC_API_KEY non configurée. Saisir manuellement les éléments de rapprochement.",
            escalation=True,
            materiality_xaf=float(materiality_xaf),
            source="no_key",
        )

    payload = {
        "rec_key": rec_key,
        "rec_title": rec_title,
        "ref_label": ref_label,
        "ref_amount_xaf": float(ref_amount),
        "counter_label": counter_label,
        "counter_amount_xaf": float(counter_amount),
        "variance_xaf": float(variance_xaf),
        "materiality_xaf": float(materiality_xaf),
        "account_breakdown": (account_breakdown or [])[:30],  # cap for token cost
    }

    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=settings.anthropic_model or "claude-sonnet-4-5",
            max_tokens=1200,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    "Analyse the following reconciliation and return JSON per the schema.\n\n"
                    + json.dumps(payload, ensure_ascii=False, indent=2)
                ),
            }],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            log.warning("Rec-items: no JSON in Claude response: %s", text[:300])
            return RecItemsAnalysis(
                items=[],
                summary="Réponse IA non exploitable — réessayer plus tard.",
                escalation=True,
                materiality_xaf=float(materiality_xaf),
                source="parse_error",
            )
        data = json.loads(m.group(0))
        items_raw = data.get("items", []) or []
        items = [
            RecItem(
                category=str(it.get("category", "OTHER")),
                description=str(it.get("description", "")),
                estimated_amount_xaf=float(it.get("estimated_amount_xaf", 0) or 0),
                likelihood=str(it.get("likelihood", "MEDIUM")),
                aging_bucket=str(it.get("aging_bucket", "UNKNOWN")),
                action=str(it.get("action", "")),
            )
            for it in items_raw
        ]
        return RecItemsAnalysis(
            items=items,
            summary=str(data.get("summary", "")),
            escalation=abs(variance_xaf) >= materiality_xaf,
            materiality_xaf=float(materiality_xaf),
            source="claude",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Rec-items Claude call failed: %s", e)
        return RecItemsAnalysis(
            items=[],
            summary=f"Erreur d'appel à Claude : {e}",
            escalation=True,
            materiality_xaf=float(materiality_xaf),
            source="api_error",
        )
