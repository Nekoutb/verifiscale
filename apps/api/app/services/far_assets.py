"""Single entry point for reading a fixed-asset register dataset.

Two paths, in order of preference:

  1. CONFIRMED MAPPING (ingest-v2): the auditor approved a column mapping in
     the /confirm-mapping gate. Deterministic — the exact mapping they saw is
     re-applied by far_reader. Reproducible and auditable.
  2. LEGACY / AI: no confirmed mapping (dataset ingested before the gate
     existed). Fall back to the Claude-inferred parser.

Every consumer of FAR rows (amortissements, rapprochement immobilisations)
must go through here so both paths stay consistent.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("fiscaudit.services.far_assets")


def load_far_assets(ds, data: bytes) -> list[dict[str, Any]]:
    """Return canonical asset dicts for a FIXED_ASSETS_REGISTER dataset."""
    cm = ds.column_mapping or {}
    if cm.get("source") == "INGEST_V2_CONFIRMED" and cm.get("kind") == "FAR" \
            and isinstance(cm.get("mapping"), dict):
        try:
            from app.parsers.far_reader import read_far
            from app.parsers.ledger_reader import detect_header
            from app.services.ingest_preview import load_rows

            rows = load_rows(data, ds.original_filename, cm.get("sheet"))
            hdr = detect_header(rows, "FAR")
            if hdr is not None:
                mapping = {k: v for k, v in cm["mapping"].items()
                           if isinstance(v, int)}
                res = read_far(rows, mapping, hdr)
                if res.rows:
                    return res.rows
                log.warning("Confirmed FAR mapping yielded 0 rows — AI fallback")
        except Exception as e:  # noqa: BLE001
            log.warning("Confirmed FAR mapping failed (%s) — AI fallback", e)

    from app.parsers.fixed_assets_ai import parse_fixed_assets_ai
    return parse_fixed_assets_ai(data, ds.original_filename)
