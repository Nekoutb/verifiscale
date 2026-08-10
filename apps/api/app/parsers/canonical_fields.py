"""Canonical field spec for ledger ingestion (GL & TB).

Single source of truth shared by:
  - the parsers (what to look for, what may be missing)
  - the mapping-preview endpoint (mandatory checklist shown to the auditor)
  - the mapping UI (dropdown options per canonical field)

Design rules agreed with the auditor:
  * Only the fields marked MANDATORY may block an upload. Everything else is
    ingested when present and is NEVER a blocker.
  * Amount-like concepts accept TWO shapes:
        - SIGNED : one column, debit less credit (may be negative)
        - PAIR   : two columns, debit + credit
    A group is satisfied when EITHER shape resolves. If only one column of a
    pair is present that is acceptable too (the other is treated as 0).
  * `entry_id` stays mandatory but may be satisfied by PATTERN EXTRACTION from
    another column — real exports (Odoo) bury the reference in the label, e.g.
    "CSHOM/2026/00237 Retrait..." / "INV/2026/00073 (S00080)".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Shape(str, Enum):
    SINGLE = "SINGLE"   # exactly one column carries the value
    SIGNED = "SIGNED"   # one column, debit less credit (sign carries direction)
    PAIR = "PAIR"       # two columns: debit + credit


@dataclass(frozen=True)
class CanonicalField:
    key: str
    label_fr: str
    label_en: str
    mandatory: bool
    shape: Shape
    #: For PAIR/SIGNED groups — the sub-keys the mapping may carry.
    members: tuple[str, ...] = ()
    #: Header tokens (normalised) that hint at this field.
    hints: tuple[str, ...] = ()
    #: True when the field may be satisfied by extracting a pattern from
    #: another column instead of having a dedicated column.
    allow_pattern_extraction: bool = False


# ── Journal-entry reference patterns ────────────────────────────────────────
# Odoo: CSHOM/2026/00237, INV/2026/00073, BILL/2026/0004, MISC/2026/00012
# Sage/SAP-ish: PI-2026-0001, 2026/JV/0007
# NOTE: journal prefixes routinely contain digits — real Odoo data has CSH4,
# CSH1, BNK2 alongside CSHOM/INV/BILL. The prefix must start with a letter but
# may then be alphanumeric, otherwise ~30% of a real GL silently fails to
# resolve an entry id (observed on Kissywears: 1 125 of 3 914 rows).
ENTRY_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b([A-Z][A-Z0-9]{1,9}/\d{4}/\d{2,8})\b"),
    re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{4}-\d{2,8})\b"),
    re.compile(r"\b(\d{4}/[A-Z][A-Z0-9]{1,5}/\d{2,8})\b"),
)


def extract_entry_id(text: str | None) -> str | None:
    """Pull a journal-entry reference out of a free-text label.

    Returns None when no known pattern matches — callers must NOT invent an id.
    """
    if not text:
        return None
    s = str(text).strip()
    for pat in ENTRY_ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1)
    return None


def detect_entry_id_pattern(samples: list[str | None]) -> dict | None:
    """Given sample values of a column, report whether an entry id can be
    extracted and with what hit-rate. Drives the UI's suggestion:
        "Extraire depuis « Account Name » (motif détecté : CSHOM/2026/00237)"
    """
    vals = [s for s in samples if s not in (None, "")]
    if not vals:
        return None
    hits = [(v, extract_entry_id(v)) for v in vals]
    found = [(v, e) for v, e in hits if e]
    if not found:
        return None
    return {
        "hit_rate": round(len(found) / len(vals), 3),
        "sample_source": str(found[0][0])[:80],
        "sample_extracted": found[0][1],
        "n_matched": len(found),
        "n_total": len(vals),
    }


# ── GENERAL LEDGER ──────────────────────────────────────────────────────────

GL_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField(
        "account_number", "Numéro de compte", "Account number", True, Shape.SINGLE,
        hints=("compte", "numerocompte", "ncompte", "code", "accountcode",
               "accountnumber", "glaccount"),
    ),
    CanonicalField(
        "account_description", "Libellé du compte", "Account description", True, Shape.SINGLE,
        hints=("libellecompte", "intitulecompte", "accountname", "accountdescription",
               "nomcompte", "designation"),
    ),
    CanonicalField(
        "entry_id", "N° écriture / pièce", "Journal entry identifier", True, Shape.SINGLE,
        hints=("piece", "npiece", "numeropiece", "ecriture", "necriture", "journalentry",
               "entryid", "entryno", "move", "movename", "reference", "ref"),
        allow_pattern_extraction=True,
    ),
    CanonicalField(
        "amount", "Montant", "Journal entry amount", True, Shape.PAIR,
        members=("debit", "credit", "amount_signed"),
        hints=("debit", "credit", "montant", "amount", "debitcredit"),
    ),
    CanonicalField(
        "transaction_description", "Libellé de l'écriture", "Transaction description", True, Shape.SINGLE,
        hints=("libelle", "libelleecriture", "description", "narration", "label", "memo"),
    ),
    CanonicalField(
        "entry_date", "Date d'effet", "Journal entry effective date", True, Shape.SINGLE,
        hints=("date", "dateecriture", "dateeffet", "effectivedate", "entrydate",
               "datecomptable", "postingdate"),
    ),
    # ── optional — never blocks ──
    CanonicalField("journal_code", "Code journal", "Journal code", False, Shape.SINGLE,
                   hints=("journal", "codejournal", "journalcode")),
    CanonicalField("partner", "Tiers / partenaire", "Partner", False, Shape.SINGLE,
                   hints=("tiers", "partner", "client", "fournisseur", "contact")),
    CanonicalField("lettrage", "Lettrage", "Reconciliation mark", False, Shape.SINGLE,
                   hints=("lettrage", "lettre", "matching", "reconciled")),
    CanonicalField("running_balance", "Solde progressif", "Running balance", False, Shape.SINGLE,
                   hints=("solde", "balance", "runningbalance")),
    CanonicalField("currency", "Devise", "Currency", False, Shape.SINGLE,
                   hints=("devise", "currency", "monnaie")),
)


# ── TRIAL BALANCE ───────────────────────────────────────────────────────────

TB_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField(
        "account_number", "Numéro de compte", "Account number", True, Shape.SINGLE,
        hints=("compte", "code", "accountcode", "accountnumber", "numerocompte"),
    ),
    CanonicalField(
        "account_description", "Libellé du compte", "Account description", True, Shape.SINGLE,
        hints=("libelle", "intitule", "accountname", "designation", "nomcompte"),
    ),
    CanonicalField(
        "opening", "Solde d'ouverture", "Opening balance", True, Shape.PAIR,
        members=("opening_debit", "opening_credit", "opening_signed"),
        hints=("aouverture", "ouverture", "initial", "initialbalance", "soldeinitial",
               "anouveau", "opening", "openingbalance", "balanceinitiale"),
    ),
    CanonicalField(
        "movements", "Mouvements de la période", "Movements", True, Shape.PAIR,
        members=("movement_debit", "movement_credit", "movement_signed"),
        hints=("mouvement", "mouvements", "periode", "debit", "credit", "movement",
               "activity", "period"),
    ),
    CanonicalField(
        "closing", "Solde de clôture", "Closing balance", True, Shape.PAIR,
        members=("closing_debit", "closing_credit", "closing_signed"),
        hints=("cloture", "final", "endbalance", "soldefinal", "closing",
               "closingbalance", "soldecloture", "end"),
    ),
    # ── optional ──
    CanonicalField("annotations", "Annotations", "Annotations", False, Shape.SINGLE,
                   hints=("annotation", "annotations", "note", "notes", "commentaire")),
    CanonicalField("currency", "Devise", "Currency", False, Shape.SINGLE,
                   hints=("devise", "currency", "monnaie")),
)


# ── FIXED ASSET REGISTER ────────────────────────────────────────────────────
# Key columns agreed with the auditor. Truly blocking: description + gross
# value. The other "key" fields are displayed as required in the checklist but
# an absence only warns — real registers routinely lack an explicit GL account
# or rate column (the rate is then implied from dotation ÷ valeur brute).
# Opening/closing pairs are tolerated as a single column (same rule as the TB).

FAR_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField(
        "account_number", "N° de compte (immobilisation)", "Account number", False, Shape.SINGLE,
        hints=("compte", "ncompte", "numerocompte", "comptegeneral", "codecompte",
               "account", "accountcode", "accountnumber", "glaccount"),
    ),
    CanonicalField(
        "reference", "N° d'immobilisation", "Fixed asset number", False, Shape.SINGLE,
        hints=("reference", "ref", "nimmobilisation", "immobilisation", "code",
               "assetnumber", "assetcode", "assetid", "tag", "fiche"),
    ),
    CanonicalField(
        "name", "Désignation de l'immobilisation", "Fixed asset description", True, Shape.SINGLE,
        hints=("designation", "libelle", "description", "nature", "intitule",
               "assetname", "assetdescription", "immobilisation"),
    ),
    CanonicalField(
        "acquisition_date", "Date d'acquisition", "Acquisition date", False, Shape.SINGLE,
        hints=("dateacquisition", "dacquisition", "acquisition", "datemiseenservice",
               "miseenservice", "dateentree", "purchasedate", "acquisitiondate"),
    ),
    CanonicalField(
        "disposal_date", "Date de cession / sortie", "Disposal date", False, Shape.SINGLE,
        hints=("datecession", "cession", "datesortie", "sortie", "rebut",
               "disposaldate", "disposal", "retirement"),
    ),
    CanonicalField(
        "gross_value", "Valeur brute (base amortissable)", "Gross book value", True, Shape.PAIR,
        members=("gross_value", "opening_gross_value", "closing_gross_value"),
        hints=("valeurbrute", "valeurorigine", "valeuracquisition", "vab", "vb",
               "brute", "cout", "cost", "grossvalue", "grossbookvalue", "prixacquisition"),
    ),
    CanonicalField(
        "accumulated_depreciation", "Amortissements cumulés", "Accumulated depreciation", False, Shape.PAIR,
        members=("accumulated_depreciation", "opening_accumulated_depreciation",
                 "closing_accumulated_depreciation"),
        hints=("amortissementscumules", "cumulamortissement", "cumulamort", "amortcumules",
               "accumulateddepreciation", "accumdep", "cumul"),
    ),
    CanonicalField(
        "year_depreciation", "Dotation de l'exercice", "Depreciation for the year", False, Shape.SINGLE,
        hints=("dotation", "dotationexercice", "dotationannuelle", "amortissementexercice",
               "depreciationfortheyear", "yeardepreciation", "annualdepreciation", "charge"),
    ),
    CanonicalField(
        "depreciation_on_disposals", "Amort. repris sur cessions", "Depreciation written off on disposals",
        False, Shape.SINGLE,
        hints=("reprisecession", "amortissementcession", "reprises", "writtenoff",
               "depreciationondisposal", "sortieamortissement"),
    ),
    CanonicalField(
        "nbv", "Valeur nette comptable", "Net book value", False, Shape.PAIR,
        members=("nbv", "opening_nbv", "closing_nbv"),
        hints=("vnc", "valeurnette", "valeurnettecomptable", "netbookvalue", "nbv", "netvalue"),
    ),
    CanonicalField(
        "rate", "Taux d'amortissement", "Depreciation rate", False, Shape.SINGLE,
        hints=("taux", "tauxamortissement", "rate", "depreciationrate", "duree",
               "dureevie", "vieutile", "usefullife", "periodes", "nbmois"),
    ),
)

#: FAR fields displayed as REQUIRED in the checklist. Missing ⇒ warning, not a
#: block (except the truly mandatory ones above). Keep in sync with the
#: auditor's key-column list.
FAR_KEY_FIELDS: frozenset[str] = frozenset({
    "account_number", "reference", "name", "gross_value",
    "accumulated_depreciation", "year_depreciation", "rate",
})


# ── Rows that are never transactions / never accounts ───────────────────────
# Normalised label prefixes marking a subtotal, an opening balance, or a
# grand total. These rows are EXCLUDED from ingestion but surfaced to the
# auditor in the preview (with their balance impact).
NON_DATA_LABEL_PREFIXES: tuple[str, ...] = (
    "total", "totaux", "soustotal", "sousttotal",
    "initialbalance", "balanceinitiale", "soldeinitial", "soldeinit", "soldeouv",
    "openingbalance", "aouveau", "anouveau", "reportanouveau", "report",
    "endingbalance", "endbalance", "soldefinal", "soldecloture",
    "cumul", "grandtotal",
)


def normalize(s: str | None) -> str:
    """Lowercase, strip accents/punctuation/space — for header & label matching."""
    if s is None:
        return ""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t.lower())


def is_non_data_label(label: str | None) -> bool:
    n = normalize(label)
    if not n:
        return False
    return any(n.startswith(p) for p in NON_DATA_LABEL_PREFIXES)


# ── Mandatory-satisfaction logic ────────────────────────────────────────────

@dataclass
class FieldStatus:
    key: str
    label_fr: str
    mandatory: bool
    satisfied: bool
    shape_used: str | None = None
    detail: str | None = None


def _group_satisfied(mapping: dict, f: CanonicalField) -> tuple[bool, str | None]:
    """A PAIR group resolves when the signed column is mapped, OR when at least
    one of debit/credit is mapped (a lone column is acceptable — the other is 0).
    """
    if f.shape is not Shape.PAIR:
        return (mapping.get(f.key) is not None, Shape.SINGLE.value if mapping.get(f.key) is not None else None)
    signed = next((m for m in f.members if m.endswith("_signed") or m == "amount_signed"), None)
    if signed and mapping.get(signed) is not None:
        return True, Shape.SIGNED.value
    pair_members = [m for m in f.members if m != signed]
    if any(mapping.get(m) is not None for m in pair_members):
        return True, Shape.PAIR.value
    return False, None


def evaluate(mapping: dict, kind: str) -> tuple[list[FieldStatus], list[str]]:
    """Return (per-field status, list of blocking errors).

    `mapping` maps canonical keys (or PAIR member keys) -> column index.
    `kind` is "GL", "TB" or "FAR". Only mandatory fields can produce blocking
    errors. For the FAR, the auditor's key columns are DISPLAYED as required
    but a gap only warns (detail explains it) — except name + gross value,
    which truly block: without them nothing meaningful can be computed.
    """
    k = kind.upper()
    fields = GL_FIELDS if k == "GL" else TB_FIELDS if k == "TB" else FAR_FIELDS
    statuses: list[FieldStatus] = []
    errors: list[str] = []

    for f in fields:
        ok, shape_used = _group_satisfied(mapping, f)
        detail = None
        # entry_id may be satisfied by pattern extraction
        if not ok and f.allow_pattern_extraction and mapping.get(f"{f.key}__extract_from") is not None:
            ok = True
            shape_used = "EXTRACTED"
            detail = f"Extrait depuis la colonne {mapping[f'{f.key}__extract_from']}"

        if k == "FAR":
            display_required = f.mandatory or f.key in FAR_KEY_FIELDS
            if not ok and display_required and not f.mandatory:
                detail = ("Colonne clé absente du fichier — l'analyse reste possible "
                          "mais sera moins précise"
                          + (" (taux déduit de dotation ÷ valeur brute)" if f.key == "rate" else ""))
            statuses.append(FieldStatus(f.key, f.label_fr, display_required, ok, shape_used, detail))
        else:
            statuses.append(FieldStatus(f.key, f.label_fr, f.mandatory, ok, shape_used, detail))

        if f.mandatory and not ok:
            errors.append(f"Champ obligatoire non mappé : « {f.label_fr} »")

    return statuses, errors
