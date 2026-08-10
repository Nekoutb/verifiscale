"""Raw file dimensions — the auditor-facing control total for every upload.

Counts what the FILE physically contains (non-empty rows, used columns,
sheets) independently of any parser, so the UI can prove « fichier N lignes ×
M colonnes / lues N × M » and surface silent data loss immediately.

Spreadsheets (xlsx/xls/xlsm): all sheets are counted (rows summed, columns =
max across sheets) because the GL reader consumes every sheet. CSV/TSV: one
grid. Non-tabular files (PDF, images) return None — extraction counts are
reported by their own parsers instead.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger("fiscaudit.parser.file_dims")

_SPREADSHEET_EXT = (".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt")


def _grid_dims(df) -> tuple[int, int]:
    """Non-empty rows and max used column index+1 of one raw grid."""
    import pandas as pd

    mask = df.notna() & (df.astype(str).apply(lambda s: s.str.strip()) != "")
    rows = int(mask.any(axis=1).sum())
    used_cols = mask.any(axis=0)
    cols = int(used_cols[used_cols].index.max() + 1) if used_cols.any() else 0
    return rows, cols


def file_dims(data: bytes, filename: str) -> dict | None:
    """Return {"rows": R, "cols": C, "sheets": S} or None when not tabular."""
    name = (filename or "").lower()
    if not name.endswith(_SPREADSHEET_EXT):
        return None
    try:
        import pandas as pd

        if name.endswith((".xlsx", ".xls", ".xlsm")):
            sheets = pd.read_excel(io.BytesIO(data), sheet_name=None,
                                   header=None, dtype=object)
            total_rows, max_cols = 0, 0
            for df in sheets.values():
                r, c = _grid_dims(df)
                total_rows += r
                max_cols = max(max_cols, c)
            return {"rows": total_rows, "cols": max_cols, "sheets": len(sheets)}

        text = data.decode("utf-8-sig", errors="replace")
        first = text.split("\n", 1)[0]
        sep = ";" if first.count(";") > first.count(",") else ","
        if name.endswith(".tsv"):
            sep = "\t"
        df = pd.read_csv(io.StringIO(text), sep=sep, header=None,
                         dtype=object, keep_default_na=False)
        df = df.replace("", None)
        r, c = _grid_dims(df)
        return {"rows": r, "cols": c, "sheets": 1}
    except Exception as e:  # noqa: BLE001 — control totals must never block upload
        log.warning("file_dims failed for %s: %s", filename, e)
        return None
