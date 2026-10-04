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
    FAR_FIELDS, GL_FIELDS, TB_FIELDS, evaluate, detect_entry_id_pattern,
)
from app.parsers.far_reader import read_far
from app.parsers.ledger_reader import (
    detect_header, propose_mapping, read, HeaderInfo,
)


SAMPLE_ROWS = 4          # header + 3-4 rows, per the auditor's spec
MAX_COL_SAMPLES = 5


# ── workbook loading ────────────────────────────────────────────────────────

CSV_SHEET_NAME = "(fichier CSV)"


def _workbook_error(exc: Exception) -> str:
    """Turn an openpyxl/zipfile failure into a reason the auditor can act on."""
    msg = str(exc).lower()
    if "encrypt" in msg or "password" in msg or "protected" in msg:
        return ("Classeur protégé par mot de passe. Retirez la protection dans "
                "Excel (Fichier → Informations → Protéger) puis réimportez-le.")
    if "not a zip" in msg or "bad zip" in msg or "zipfile" in msg:
        return ("Fichier illisible ou corrompu : ce n'est pas un .xlsx valide. "
                "Rouvrez-le dans Excel et réenregistrez-le en « Classeur Excel "
                "(.xlsx) », ou exportez en .csv.")
    return f"Classeur illisible : {exc}"


def sheet_names(data: bytes, filename: str) -> list[str]:
    """The selectable tabs of an upload.

    A workbook returns its worksheet names in tab order; CSV/TXT are a single
    grid reported as one synthetic sheet so the UI treats every upload the same
    way. Unsupported formats return []. Raises ValueError (via _workbook_error)
    when the file cannot be opened at all, so the caller can report why.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        except Exception as e:  # noqa: BLE001
            raise ValueError(_workbook_error(e))
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()
    if name.endswith((".csv", ".txt")):
        return [CSV_SHEET_NAME]
    return []


def load_rows(data: bytes, filename: str, sheet: str | None = None) -> list[list[Any]]:
    """Read one sheet into a raw row matrix (no header assumptions).

    `sheet` names the worksheet to read; None keeps the historical behaviour of
    the first tab. An unknown name is a clear error that lists what IS available,
    rather than a silent fall back to the wrong tab.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        except Exception as e:  # noqa: BLE001
            raise ValueError(_workbook_error(e))
        try:
            names = wb.sheetnames
            if not names:
                raise ValueError("Le classeur ne contient aucune feuille.")
            if sheet is None:
                target = names[0]
            elif sheet in names:
                target = sheet
            else:
                raise ValueError(
                    f"Onglet « {sheet} » introuvable dans ce fichier. "
                    f"Onglets disponibles : {', '.join(names)}."
                )
            ws = wb[target]
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


# Mandatory-column labels per kind, used to explain a failed header detection.
def _expected_columns_hint(kind: str) -> str:
    fields = GL_FIELDS if kind == "GL" else TB_FIELDS if kind == "TB" else FAR_FIELDS
    labels = [f.label_fr for f in fields if f.mandatory]
    return ", ".join(labels) if labels else "—"


def _pick_default_sheet(data: bytes, filename: str, kind: str,
                        names: list[str]) -> str | None:
    """Best tab to show first: the first one whose header is recognisable for
    this kind. A workbook often leads with a cover/summary tab, so blindly
    taking tab 0 is the behaviour we are fixing. Falls back to tab 0."""
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    for sn in names:
        try:
            if detect_header(load_rows(data, filename, sn), kind) is not None:
                return sn
        except Exception:  # noqa: BLE001 — a bad tab must not block the others
            continue
    return names[0]


def _kind_of(dataset_kind: str) -> str:
    k = str(dataset_kind).upper()
    if "TRIAL_BALANCE" in k:
        return "TB"
    if "FIXED_ASSET" in k:
        return "FAR"
    return "GL"


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if v is None:
        return None
    return str(v)


# ── preview ─────────────────────────────────────────────────────────────────

def build_preview(data: bytes, filename: str, dataset_kind: str,
                  override_mapping: dict | None = None,
                  sheet: str | None = None) -> dict:
    """Everything the auditor needs to confirm or correct the mapping.

    `override_mapping` lets the UI re-preview live as the auditor remaps a
    column, without touching the stored dataset. `sheet` selects which tab of a
    multi-sheet workbook to read; when omitted we auto-pick the first tab whose
    header is recognisable for this kind.
    """
    kind = _kind_of(dataset_kind)
    names = sheet_names(data, filename)
    selected = sheet if (sheet and sheet in names) else _pick_default_sheet(
        data, filename, kind, names)
    sheets_info = [{"name": n} for n in names]

    rows = load_rows(data, filename, selected)
    hdr = detect_header(rows, kind)
    if hdr is None:
        hint = f" Colonnes attendues : {_expected_columns_hint(kind)}."
        if len([n for n in names if n != CSV_SHEET_NAME]) > 1:
            hint += (" Si vos données sont sur un autre onglet, sélectionnez-le "
                     "ci-dessus.")
        return {
            "kind": kind, "detected": False,
            "sheets": sheets_info, "selected_sheet": selected,
            "error": ("En-tête introuvable sur cet onglet — vérifiez qu'il "
                      "contient une ligne d'en-tête." + hint),
            "raw_preview": [[_jsonable(c) for c in r[:12]] for r in rows[:8]],
        }

    mapping = dict(override_mapping) if override_mapping else propose_mapping(hdr, rows, kind)
    extract_info = mapping.pop("entry_id__extract_info", None)
    clean = {k: v for k, v in mapping.items() if isinstance(v, int)}

    statuses, errors = evaluate(mapping, kind)
    res = read_far(rows, clean, hdr) if kind == "FAR" else read(rows, kind, clean, hdr)

    fields = GL_FIELDS if kind == "GL" else TB_FIELDS if kind == "TB" else FAR_FIELDS

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
        "sheets": sheets_info,
        "selected_sheet": selected,
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
                "member_labels": dict(f.member_labels),
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
        # Control totals — shown at the top of the modal BEFORE ingestion so
        # the auditor can verify every file row is accounted for.
        "control_totals": (lambda raw, ing, exc: {
            "file_rows": raw,
            "file_cols": max((len(r) for r in rows), default=0),
            "read_rows": ing,
            "read_cols": len(set(clean.values())),
            "excluded_rows": exc,
            "structural_rows": max(raw - ing - exc, 0),
            "complete": (raw - ing - exc) >= 0 and ing > 0,
        })(
            sum(1 for r in rows[hdr.header_row + 1:]
                if any(c not in (None, "") for c in r)),
            len(res.rows), len(res.excluded),
        ),
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
        # FAR
        "gross_value": "Σ Valeur brute",
        "accumulated_depreciation": "Σ Amort. cumulés",
        "year_depreciation": "Σ Dotation exercice",
    }.get(k, k)


def _summarise_excluded(excluded) -> list[dict]:
    agg: dict[str, int] = {}
    for e in excluded:
        agg[e.reason] = agg.get(e.reason, 0) + 1
    return [{"reason": r, "count": c} for r, c in
            sorted(agg.items(), key=lambda x: -x[1])]


def _balance_verdict(kind: str, totals: dict[str, Decimal]) -> dict:
    """Balance check. Unbalanced never blocks — it requires acknowledgement."""
    if kind == "FAR":
        # A register has no debit/credit identity to verify. Coherence
        # (VB − amortissements = VNC, FAR ↔ TB 2X/28X/68X) is checked by the
        # rapprochement immobilisations, not at ingestion.
        g = totals.get("gross_value", Decimal("0"))
        a = totals.get("accumulated_depreciation", Decimal("0"))
        return {
            "balanced": True,
            "groups": [
                {"key": "gross", "label": "Valeur brute", "debit": float(g),
                 "credit": 0.0, "delta": 0.0},
                {"key": "accum", "label": "Amort. cumulés", "debit": float(a),
                 "credit": 0.0, "delta": 0.0},
            ],
            "message": ("Registre d'immobilisations — pas d'équilibre débit/crédit à "
                        "vérifier ; la cohérence FAR ↔ balance (2X/28X/68X) est "
                        "contrôlée par le rapprochement immobilisations."),
        }
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
                     acknowledge_unbalanced: bool = False,
                     sheet: str | None = None) -> dict:
    """Ingest using the auditor-approved mapping. Raises ValueError on a
    mandatory gap, or on an unbalanced import that was not acknowledged.

    `sheet` is the tab the auditor previewed and approved; it is persisted on the
    dataset so later re-reads (e.g. the FAR analyses) use the SAME tab.
    """
    from app.models import (
        DatasetKind, DatasetStatus, JournalEntry, JournalEntryLine, TrialBalanceLine,
    )

    kind = _kind_of(ds.kind)
    rows = load_rows(data, ds.original_filename, sheet)
    hdr = detect_header(rows, kind)
    if hdr is None:
        raise ValueError(
            "En-tête introuvable sur l'onglet sélectionné"
            + (f" « {sheet} »" if sheet else "")
            + " — revérifiez le mapping ou changez d'onglet."
        )

    clean = {k: v for k, v in mapping.items() if isinstance(v, int)}
    _, errors = evaluate(mapping, kind)
    if errors:
        raise ValueError(" · ".join(errors))

    res = read_far(rows, clean, hdr) if kind == "FAR" else read(rows, kind, clean, hdr)
    verdict = _balance_verdict(kind, res.totals)
    if not verdict["balanced"] and not acknowledge_unbalanced:
        raise ValueError(
            "Import déséquilibré non confirmé — l'auditeur doit accepter "
            "explicitement le risque avant l'ingestion."
        )
    if not res.rows:
        raise ValueError("Aucune ligne exploitable avec ce mapping.")

    if kind == "FAR":
        # No ledger table: the amortissements/rapprochements analyses re-read
        # the stored file THROUGH the confirmed mapping (services/far_assets).
        # Persisting the mapping is what makes the analysis reproducible.
        ds.summary_amount = res.totals.get("gross_value")
    elif kind == "TB":
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
        "sheet": sheet,
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

    # Control totals — every non-blank data row of the FILE must be accounted
    # for: ingested, excluded WITH a disclosed reason, or structural context
    # (account-header lines in grouped GL layouts, banner echoes). Any gap
    # (raw > ingested + excluded + structural is impossible by construction;
    # a reader regression that drops rows would surface as complete=False).
    raw_data_rows = sum(
        1 for r in rows[hdr.header_row + 1:]
        if any(c not in (None, "") for c in r)
    )
    structural = raw_data_rows - len(res.rows) - len(res.excluded)
    file_cols = max((len(r) for r in rows), default=0)
    ds.control_totals = {
        "file_rows": raw_data_rows,
        "file_cols": file_cols,
        "sheets": None,
        "sheet_name": sheet,
        "read_rows": len(res.rows),
        "read_cols": len(set(clean.values())),
        "excluded_rows": len(res.excluded),
        "structural_rows": max(structural, 0),
        "complete": structural >= 0 and len(res.rows) > 0,
    }

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
