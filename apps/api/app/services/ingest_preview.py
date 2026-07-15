"""Mapping preview + confirmed ingestion for GL / TB (Ingest-v2).

Flow enforced here:

    upload  ->  status = PENDING_MAPPING   (file stored, NOTHING ingested)
      |
      v
    GET  /datasets/{id}/mapping-preview    proposed mapping + totals + samples
      |                                    + mandatory checklist + excluded rows
      v
    POST /datasets/{id}/confirm-mapping    auditor-approved mapping -> ingest
                                           status = PARSED

Nothing reaches `trial_balance_lines` / `journal_entries` until the auditor
approves the mapping. The mapping they approve is persisted on the dataset, so
the ingestion is reproducible and auditable.
"""
from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from app.parsers.canonical_fields import (
    GL_FIELDS, TB_FIELDS, evaluate, detect_entry_id_pattern,
)
from app.parsers.ledger_reader import (
    detect_header, propose_mapping, read, HeaderInfo,
)


SAMPLE_ROWS = 4          # header + 3-4 rows, per the auditor's spec
MAX_COL_SAMPLES = 5


# ── workbook loading ────────────────────────────────────────────────────────

def load_rows(data: bytes, filename: str) -> list[list[Any]]:
    """Read the first sheet into a raw row matrix (no header assumptions)."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        try:
            ws = wb[wb.sheetnames[0]]
            return [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    if name.endswith((".csv", ".txt")):
        import csv
        text = data.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        except csv.Error:
            dialect = csv.excel
        return [list(r) for r in csv.reader(io.StringIO(text), dialect)]
    raise ValueError("Format non pris en charge — fournissez un .xlsx ou un .csv")


def _kind_of(dataset_kind: str) -> str:
    return "TB" if "TRIAL_BALANCE" in str(dataset_kind).upper() else "GL"


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if v is None:
        return None
    return str(v)


# ── preview ─────────────────────────────────────────────────────────────────

def build_preview(data: bytes, filename: str, dataset_kind: str,
                  override_mapping: dict | None = None) -> dict:
    """Everything the auditor needs to confirm or correct the mapping.

    `override_mapping` lets the UI re-preview live as the auditor remaps a
    column, without touching the stored dataset.
    """
    kind = _kind_of(dataset_kind)
    rows = load_rows(data, filename)
    hdr = detect_header(rows, kind)
    if hdr is None:
        return {
            "kind": kind, "detected": False,
            "error": "En-tête introuvable — vérifiez que le fichier contient une ligne d'en-tête.",
            "raw_preview": [[_jsonable(c) for c in r[:12]] for r in rows[:8]],
        }

    mapping = dict(override_mapping) if override_mapping else propose_mapping(hdr, rows, kind)
    extract_info = mapping.pop("entry_id__extract_info", None)
    clean = {k: v for k, v in mapping.items() if isinstance(v, int)}

    statuses, errors = evaluate(mapping, kind)
    res = read(rows, kind, clean, hdr)

    fields = GL_FIELDS if kind == "GL" else TB_FIELDS

    # Per-column sample values — drives the remap dropdowns.
    data_rows = rows[hdr.header_row + 1:]
    columns = []
    for i, h in enumerate(hdr.effective):
        samples = [r[i] if i < len(r) else None for r in data_rows[:40]]
        non_empty = [s for s in samples if s not in (None, "")][:MAX_COL_SAMPLES]
        assigned = [k for k, v in clean.items() if v == i]
        columns.append({
            "index": i,
            "header": h,
            "raw_header": _jsonable(hdr.raw_header[i]) if i < len(hdr.raw_header) else None,
            "banner": _jsonable(hdr.raw_banner[i]) if hdr.raw_banner and i < len(hdr.raw_banner) else None,
            "samples": [_jsonable(s) for s in non_empty],
            "assigned_to": assigned,
        })

    # Totals pinned at the top, computed from what will ACTUALLY be ingested.
    totals = [{"key": k, "label": _total_label(k), "value": float(v)}
              for k, v in res.totals.items()]

    balance = _balance_verdict(kind, res.totals)

    # The file's own Total row. Informational only: Odoo's GL total double-counts
    # (it sums account subtotals AND their lines AND opening balances), so a
    # strict comparison would raise a false alarm on every Odoo export.
    stated = None
    if res.stated_totals:
        stated = {
            "values": {k: float(v) for k, v in res.stated_totals.items()},
            "note": ("Total tel qu'indiqué dans le fichier. Informatif : certains "
                     "exports (Odoo) additionnent les sous-totaux de compte et les "
                     "lignes, donc un écart avec le total calculé est normal."),
        }

    return {
        "kind": kind,
        "detected": True,
        "header_row": hdr.header_row + 1,        # 1-based for humans
        "banner_row": None if hdr.banner_row is None else hdr.banner_row + 1,
        "columns": columns,
        "mapping": clean,
        "entry_id_extraction": (
            {"from_column": mapping.get("entry_id__extract_from"), **extract_info}
            if extract_info and mapping.get("entry_id__extract_from") is not None else None
        ),
        "fields": [
            {
                "key": f.key, "label_fr": f.label_fr, "mandatory": f.mandatory,
                "shape": f.shape.value, "members": list(f.members),
                "allow_pattern_extraction": f.allow_pattern_extraction,
            } for f in fields
        ],
        "checklist": [
            {"key": s.key, "label_fr": s.label_fr, "mandatory": s.mandatory,
             "satisfied": s.satisfied, "shape_used": s.shape_used, "detail": s.detail}
            for s in statuses
        ],
        "blocking_errors": errors,
        "can_confirm": not errors,
        "rows_to_ingest": len(res.rows),
        "sample_rows": [
            {k: _jsonable(v) for k, v in r.items()} for r in res.rows[:SAMPLE_ROWS]
        ],
        "excluded_count": len(res.excluded),
        "excluded": [
            {"row": e.row_index, "reason": e.reason, "label": e.label,
             "impact": e.impact or None}
            for e in res.excluded[:60]
        ],
        "excluded_summary": _summarise_excluded(res.excluded),
        "totals": totals,
        "stated_totals": stated,
        "balance": balance,
        "warnings": res.warnings,
    }


def _total_label(k: str) -> str:
    return {
        "debit": "Σ Débit", "credit": "Σ Crédit",
        "opening_debit": "Σ Ouverture — Débit", "opening_credit": "Σ Ouverture — Crédit",
        "movement_debit": "Σ Mouvements — Débit", "movement_credit": "Σ Mouvements — Crédit",
        "closing_debit": "Σ Clôture — Débit", "closing_credit": "Σ Clôture — Crédit",
    }.get(k, k)


def _summarise_excluded(excluded) -> list[dict]:
    agg: dict[str, int] = {}
    for e in excluded:
        agg[e.reason] = agg.get(e.reason, 0) + 1
    return [{"reason": r, "count": c} for r, c in
            sorted(agg.items(), key=lambda x: -x[1])]


def _balance_verdict(kind: str, totals: dict[str, Decimal]) -> dict:
    """Balance check. Unbalanced never blocks — it requires acknowledgement."""
    if kind == "GL":
        d, c = totals.get("debit", Decimal("0")), totals.get("credit", Decimal("0"))
        delta = d - c
        return {
            "balanced": delta == 0,
            "groups": [{"key": "movements", "label": "Écritures",
                        "debit": float(d), "credit": float(c), "delta": float(delta)}],
            "message": ("Débit = Crédit — le grand livre est équilibré."
                        if delta == 0 else
                        f"Grand livre déséquilibré de {float(delta):,.0f} FCFA.".replace(",", " ")),
        }
    groups = []
    ok = True
    for grp, label in (("opening", "Ouverture"), ("movement", "Mouvements"), ("closing", "Clôture")):
        d = totals.get(f"{grp}_debit", Decimal("0"))
        c = totals.get(f"{grp}_credit", Decimal("0"))
        delta = d - c
        if delta != 0:
            ok = False
        groups.append({"key": grp, "label": label, "debit": float(d),
                       "credit": float(c), "delta": float(delta)})
    return {
        "balanced": ok,
        "groups": groups,
        "message": ("Balance équilibrée sur les trois groupes."
                    if ok else
                    "Balance déséquilibrée — vérifiez les lignes exclues ci-dessous "
                    "avant de poursuivre. L'import restera possible après acceptation "
                    "explicite du risque."),
    }


# ── confirmed ingestion ─────────────────────────────────────────────────────

def ingest_confirmed(db, ds, data: bytes, mapping: dict,
                     acknowledge_unbalanced: bool = False) -> dict:
    """Ingest using the auditor-approved mapping. Raises ValueError on a
    mandatory gap, or on an unbalanced import that was not acknowledged.
    """
    from app.models import (
        DatasetKind, DatasetStatus, JournalEntry, JournalEntryLine, TrialBalanceLine,
    )

    kind = _kind_of(ds.kind)
    rows = load_rows(data, ds.original_filename)
    hdr = detect_header(rows, kind)
    if hdr is None:
        raise ValueError("En-tête introuvable")

    clean = {k: v for k, v in mapping.items() if isinstance(v, int)}
    _, errors = evaluate(mapping, kind)
    if errors:
        raise ValueError(" · ".join(errors))

    res = read(rows, kind, clean, hdr)
    verdict = _balance_verdict(kind, res.totals)
    if not verdict["balanced"] and not acknowledge_unbalanced:
        raise ValueError(
            "Import déséquilibré non confirmé — l'auditeur doit accepter "
            "explicitement le risque avant l'ingestion."
        )
    if not res.rows:
        raise ValueError("Aucune ligne exploitable avec ce mappage.")

    if kind == "TB":
        for r in res.rows:
            db.add(TrialBalanceLine(
                dataset_id=ds.id,
                account_code=r["account_number"],
                account_name=r["account_description"],
                opening_debit=r["opening_debit"], opening_credit=r["opening_credit"],
                period_debit=r["movement_debit"], period_credit=r["movement_credit"],
                closing_debit=r["closing_debit"], closing_credit=r["closing_credit"],
            ))
    else:
        entries: dict[str, Any] = {}
        seq: dict[str, int] = {}
        for r in res.rows:
            key = r["entry_id"]
            if key not in entries:
                entries[key] = JournalEntry(
                    dataset_id=ds.id, piece_number=key,
                    journal_code=r.get("journal_code") or "OD",
                    entry_date=r["entry_date"],
                )
                db.add(entries[key])
                db.flush()
                seq[key] = 0
            seq[key] += 1
            db.add(JournalEntryLine(
                entry_id=entries[key].id, line_number=seq[key],
                account_code=r["account_number"], account_name=r["account_description"],
                libelle=r["transaction_description"],
                debit=r["debit"], credit=r["credit"], lettrage=None,
            ))

    ds.column_mapping = {
        "source": "INGEST_V2_CONFIRMED",
        "kind": kind,
        "header_row": hdr.header_row + 1,
        "banner_row": None if hdr.banner_row is None else hdr.banner_row + 1,
        "mapping": clean,
        "effective_header": hdr.effective,
        "excluded_summary": _summarise_excluded(res.excluded),
        "excluded_count": len(res.excluded),
        "totals": {k: float(v) for k, v in res.totals.items()},
        "balanced": verdict["balanced"],
        "acknowledged_unbalanced": bool(acknowledge_unbalanced and not verdict["balanced"]),
    }
    ds.rows_count = len(res.rows)
    ds.status = DatasetStatus.PARSED
    ds.parse_error = None
    from sqlalchemy.sql import func
    ds.parsed_at = func.now()
    db.commit()

    return {
        "rows_ingested": len(res.rows),
        "excluded_count": len(res.excluded),
        "balanced": verdict["balanced"],
        "totals": {k: float(v) for k, v in res.totals.items()},
    }
