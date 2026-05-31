"""BEAC policy-rate fetcher.

Scrapes the current key rates from https://www.beac.int/ :
  - TIAO  (Taux d'Intérêt des Appels d'Offres) — the main refinancing rate
  - Taux de la facilité de prêt marginal
  - Taux de la facilité de dépôt

The CGI Cameroun, Art. 7 B caps deductible shareholder interest at the
"taux des avances de la Banque Centrale + 2 points". The standard reading
of "taux des avances" is the TIAO, so the deductibility cap = TIAO + 2.
Both the TIAO and the marginal-lending rate are returned so the auditor can
choose the basis.

Strategy:
  - Fetch the BEAC homepage (rates are exposed there).
  - Parse the three rates with tolerant regex over the stripped text.
  - Persist to the `beac_rate_cache` table.
  - On any failure, fall back to the last cached value, then to a hardcoded
    default (TIAO 4.75 % — last known May 2026).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session


log = logging.getLogger("fiscaudit.services.beac")

BEAC_URL = "https://www.beac.int/"
CACHE_TTL_HOURS = 24

# Hardcoded fallback — last known values (mai 2026)
FALLBACK_TIAO = Decimal("4.75")
FALLBACK_MARGINAL = Decimal("6.25")
FALLBACK_DEPOSIT = Decimal("0.00")

# Art. 7 B uplift over the central-bank advance rate
ART7B_UPLIFT_POINTS = Decimal("2.0")


@dataclass
class BeacRates:
    tiao_pct: float
    marginal_lending_pct: float
    deposit_pct: float
    fetched_at: str
    source: str  # "live" | "cache" | "fallback"
    source_url: str = BEAC_URL

    @property
    def art7b_cap_pct(self) -> float:
        """Deductibility cap for shareholder interest = TIAO + 2 points."""
        return float(Decimal(str(self.tiao_pct)) + ART7B_UPLIFT_POINTS)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["art7b_cap_pct"] = self.art7b_cap_pct
        d["art7b_uplift_points"] = float(ART7B_UPLIFT_POINTS)
        return d


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    txt = _TAG_RE.sub(" ", html)
    txt = txt.replace("&nbsp;", " ").replace("&#160;", " ")
    return _WS_RE.sub(" ", txt)


def _find_pct_near(text_blob: str, *labels: str, window: int = 80) -> Decimal | None:
    """Find a percentage value appearing within `window` chars after any label."""
    low = text_blob.lower()
    for label in labels:
        idx = low.find(label.lower())
        if idx < 0:
            continue
        segment = text_blob[idx: idx + window]
        # Match e.g. "4,75 %" / "4.75%" / "6,25 %"
        m = re.search(r"(\d{1,2}[.,]\d{1,2})\s*%", segment)
        if m:
            return Decimal(m.group(1).replace(",", "."))
        # Some pages show integer percents
        m = re.search(r"\b(\d{1,2})\s*%", segment)
        if m:
            return Decimal(m.group(1))
    return None


def fetch_live_rates() -> BeacRates | None:
    """Fetch & parse the BEAC homepage. Returns None on any failure."""
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (FiscAuditPro)"}) as client:
            resp = client.get(BEAC_URL)
            resp.raise_for_status()
            blob = _strip_html(resp.text)
    except Exception as e:  # noqa: BLE001
        log.warning("BEAC live fetch failed: %s", e)
        return None

    tiao = _find_pct_near(blob, "TIAO", "Taux d'Intérêt des Appels d'Offres",
                          "Taux d’Intérêt des Appels d’Offres")
    marginal = _find_pct_near(blob, "facilité de prêt marginal", "prêt marginal")
    deposit = _find_pct_near(blob, "facilité de dépôt", "dépôt")

    if tiao is None:
        log.warning("BEAC fetch: TIAO not found in page")
        return None

    return BeacRates(
        tiao_pct=float(tiao),
        marginal_lending_pct=float(marginal) if marginal is not None else float(FALLBACK_MARGINAL),
        deposit_pct=float(deposit) if deposit is not None else float(FALLBACK_DEPOSIT),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        source="live",
    )


def _read_cache(db: Session) -> BeacRates | None:
    row = db.execute(text(
        "SELECT tiao_pct, marginal_lending_pct, deposit_pct, fetched_at "
        "FROM beac_rate_cache ORDER BY fetched_at DESC LIMIT 1"
    )).first()
    if not row:
        return None
    tiao, marginal, deposit, fetched_at = row
    return BeacRates(
        tiao_pct=float(tiao),
        marginal_lending_pct=float(marginal),
        deposit_pct=float(deposit),
        fetched_at=fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else str(fetched_at),
        source="cache",
    )


def _cache_is_fresh(cached: BeacRates | None) -> bool:
    if cached is None:
        return False
    try:
        ts = datetime.fromisoformat(cached.fetched_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts < timedelta(hours=CACHE_TTL_HOURS)
    except (ValueError, TypeError):
        return False


def _write_cache(db: Session, rates: BeacRates) -> None:
    db.execute(text(
        "INSERT INTO beac_rate_cache (tiao_pct, marginal_lending_pct, deposit_pct, "
        "fetched_at, source_url) VALUES (:t, :m, :d, NOW(), :u)"
    ), {"t": rates.tiao_pct, "m": rates.marginal_lending_pct,
        "d": rates.deposit_pct, "u": rates.source_url})
    db.commit()


def get_beac_rates(db: Session, force_refresh: bool = False) -> BeacRates:
    """Return current BEAC rates — live (cached daily), else cache, else fallback."""
    cached = _read_cache(db)
    if not force_refresh and _cache_is_fresh(cached):
        return cached  # type: ignore[return-value]

    live = fetch_live_rates()
    if live is not None:
        try:
            _write_cache(db, live)
        except Exception as e:  # noqa: BLE001
            log.warning("BEAC cache write failed: %s", e)
            db.rollback()
        return live

    if cached is not None:
        return cached

    return BeacRates(
        tiao_pct=float(FALLBACK_TIAO),
        marginal_lending_pct=float(FALLBACK_MARGINAL),
        deposit_pct=float(FALLBACK_DEPOSIT),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        source="fallback",
    )
