"""Reconciliations — compare auditor-uploaded files against trial balance totals.

Five reconciliation types per the user's audit framework:

1. **TB ↔ GL**       — opening + period movements = closing per account
2. **AP ↔ 401X**     — Σ supplier balances from AP ageing file ≈ TB cl. 401 closing
3. **AR ↔ 411X**     — Σ customer balances from AR ageing file ≈ TB cl. 411 closing
4. **Inventory ↔ 3X** — Σ inventory listing ≈ TB cl. 3 closing
5. **Bank ↔ 52/51X**  — closing balance per bank statement ≈ TB closing of that account

For 2-5 the "counter" amount is the auditor-entered `summary_amount` on the
relevant Dataset row (auto-extraction is a future enhancement).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AuditCase, Dataset, DatasetKind, DatasetStatus, JournalEntry,
    JournalEntryLine, MonthlyReturn, TaxType, TrialBalanceLine, User,
)
from app.controls.rec_items import categorize_variance
from app.parsers.aging import sum_aging_total, sum_inventory_value
from app.parsers.aging_ai import sum_aging_total_ai, sum_inventory_value_ai
from app.parsers.bank_statement import parse_bank_statement_closing
from app.services.far_assets import load_far_assets
from app.security import get_current_user
from app.storage import get_object
from sqlalchemy.orm import joinedload


router = APIRouter(prefix="/audit-cases", tags=["reconciliations"])

TOLERANCE = Decimal("100")  # FCFA — rounding tolerance


def _latest_parsed_tb(db: Session, case_id: UUID) -> Dataset | None:
    return (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.TRIAL_BALANCE,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )


def _tb_lines(db: Session, tb_ds: Dataset) -> list[TrialBalanceLine]:
    return db.query(TrialBalanceLine).filter(TrialBalanceLine.dataset_id == tb_ds.id).all()


def _sum_class_closing_net(rows: list[TrialBalanceLine], prefixes: tuple[str, ...]) -> Decimal:
    """Net closing balance (debit − credit) summed across rows matching any prefix."""
    total = Decimal("0")
    for r in rows:
        if any(r.account_code.startswith(p) for p in prefixes):
            total += Decimal(str(r.closing_debit)) - Decimal(str(r.closing_credit))
    return total


def _accounts_breakdown(
    rows: list[TrialBalanceLine],
    include_prefixes: tuple[str, ...],
    exclude_prefixes: tuple[str, ...] = (),
    sign_flip: bool = False,
) -> list[dict[str, Any]]:
    """Return per-account breakdown for the TB side of a reconciliation.

    sign_flip → for liabilities (AP), the closing balance is a credit; flip
    to surface it as a positive amount in the breakdown.

    Sorted by absolute amount descending so the most material accounts come first.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        if any(r.account_code.startswith(p) for p in exclude_prefixes):
            continue
        if not any(r.account_code.startswith(p) for p in include_prefixes):
            continue
        net = Decimal(str(r.closing_debit)) - Decimal(str(r.closing_credit))
        if sign_flip:
            net = -net
        # Skip rows that are completely zero (avoid noise)
        if net == 0 and Decimal(str(r.opening_debit)) + Decimal(str(r.opening_credit)) + \
           Decimal(str(r.period_debit)) + Decimal(str(r.period_credit)) == 0:
            continue
        out.append({
            "account_code": r.account_code,
            "account_name": r.account_name,
            "amount": float(net),
        })
    # Largest absolute amount first
    out.sort(key=lambda x: -abs(x["amount"]))
    return out


def _status(diff: Decimal, has_counter: bool) -> str:
    if not has_counter:
        return "MISSING"
    if abs(diff) <= TOLERANCE:
        return "ALIGNED"
    return "DISCREPANCY"


def _auto_total_bank(ds: Dataset | None) -> Decimal | None:
    """Bank statement closing balance — cached on the dataset row."""
    if ds is None:
        return None
    if ds.summary_amount is not None:
        return Decimal(str(ds.summary_amount))
    try:
        data = get_object(ds.storage_key)
    except FileNotFoundError:
        return None
    closing = parse_bank_statement_closing(data, ds.original_filename)
    if closing is not None:
        ds.summary_amount = closing
    return closing


def _auto_total_far_aggregates(ds: Dataset | None) -> tuple[Decimal, Decimal, Decimal] | None:
    """Sum the FAR's (gross, accumulated dep, year dep). None if no FAR."""
    if ds is None:
        return None
    try:
        data = get_object(ds.storage_key)
    except FileNotFoundError:
        return None
    assets = load_far_assets(ds, data)
    if not assets:
        return None
    g = sum((a.get("gross_value_xaf") or Decimal("0")) for a in assets)
    accum = sum((a.get("accumulated_depreciation_xaf") or Decimal("0")) for a in assets)
    yr = sum((a.get("register_year_depreciation_xaf") or Decimal("0")) for a in assets)
    return Decimal(str(g)), Decimal(str(accum)), Decimal(str(yr))


def _auto_total(ds: Dataset | None, *, kind: str = "AP") -> Decimal | None:
    """Σ the balance column of an AP/AR/Inventory file — AI-first with cache.

    `kind` is one of: "AP", "AR", "INVENTORY". The AI parser is called first;
    on any failure (no API key, bad JSON, parse error) we fall back to the
    keyword-based parser. Result is persisted as `summary_amount` for cheap
    subsequent reads.
    """
    if ds is None:
        return None
    if ds.summary_amount is not None:
        return Decimal(str(ds.summary_amount))
    try:
        data = get_object(ds.storage_key)
    except FileNotFoundError:
        return None
    if kind == "INVENTORY":
        total = sum_inventory_value_ai(data, ds.original_filename)
    else:
        total = sum_aging_total_ai(data, ds.original_filename, kind=kind)
    if total is not None:
        ds.summary_amount = total
    return total


@router.get("/{case_id}/reconciliations")
def get_reconciliations(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    refresh: bool = Query(False, description="Force recompute even if cache is fresh"),
) -> dict[str, Any]:
    """Compute all 5 reconciliations — cached per case, invalidated on new uploads."""
    case = db.get(AuditCase, case_id)
    if not case:
        raise HTTPException(404, "Dossier introuvable")

    # ── Cache lookup: return the stored payload when no dataset has been
    # uploaded since computed_at. The Refresh button on the UI sends ?refresh=true
    # to bypass this.
    if not refresh:
        row = db.execute(
            text("SELECT computed_at, payload FROM reconciliation_cache WHERE audit_case_id = :id"),
            {"id": str(case_id)},
        ).first()
        if row is not None:
            computed_at, payload = row
            latest_upload = db.execute(
                text("SELECT MAX(uploaded_at) FROM datasets WHERE audit_case_id = :id"),
                {"id": str(case_id)},
            ).scalar()
            if latest_upload is None or latest_upload <= computed_at:
                # Annotate so the UI can show 'cached' vs 'fresh' if needed
                if isinstance(payload, dict):
                    payload["cached"] = True
                    payload["computed_at"] = computed_at.isoformat()
                return payload

    tb_ds = _latest_parsed_tb(db, case_id)
    if not tb_ds:
        return {
            "tb_dataset_id": None,
            "tb_filename": None,
            "fiscal_year": case.fiscal_year,
            "reconciliations": [],
            "note": "Aucune balance générale chargée — importer une balance pour activer les rapprochements.",
        }
    rows = _tb_lines(db, tb_ds)

    # All non-TB datasets for this case (used to pull counter amounts)
    datasets = (
        db.query(Dataset)
        .filter(Dataset.audit_case_id == case_id)
        .order_by(Dataset.uploaded_at.desc())
        .all()
    )

    def latest_ds(kind: DatasetKind, bank_code: str | None = None) -> Dataset | None:
        for d in datasets:
            if d.kind != kind:
                continue
            if bank_code and d.bank_account_code != bank_code:
                continue
            return d
        return None

    results: list[dict[str, Any]] = []

    # ─── 1. TB ↔ GL rollforward — opening + GL movements = closing ─────────
    # Find the latest PARSED GL dataset and sum movements per account_code.
    gl_ds = (
        db.query(Dataset)
        .filter(
            Dataset.audit_case_id == case_id,
            Dataset.kind == DatasetKind.GENERAL_LEDGER,
            Dataset.status == DatasetStatus.PARSED,
        )
        .order_by(Dataset.uploaded_at.desc())
        .first()
    )
    gl_movements: dict[str, Decimal] = {}
    if gl_ds:
        gl_lines = (
            db.query(JournalEntryLine)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .filter(JournalEntry.dataset_id == gl_ds.id)
            .all()
        )
        for line in gl_lines:
            acct = (line.account_code or "").strip()
            if not acct:
                continue
            d = Decimal(str(line.debit or 0))
            c = Decimal(str(line.credit or 0))
            gl_movements[acct] = gl_movements.get(acct, Decimal("0")) + (d - c)

    # Build per-account rollforward and surface variances
    rollforward_subs: list[dict[str, Any]] = []
    sum_opening = Decimal("0")
    sum_movement = Decimal("0")
    sum_closing_actual = Decimal("0")
    sum_closing_expected = Decimal("0")
    accounts_in_variance = 0
    total_variance_abs = Decimal("0")

    for r in rows:
        opening = Decimal(str(r.opening_debit)) - Decimal(str(r.opening_credit))
        movement = gl_movements.get(r.account_code, Decimal("0"))
        expected_close = opening + movement
        actual_close = Decimal(str(r.closing_debit)) - Decimal(str(r.closing_credit))
        variance = actual_close - expected_close
        sum_opening += opening
        sum_movement += movement
        sum_closing_actual += actual_close
        sum_closing_expected += expected_close
        is_var = abs(variance) > TOLERANCE
        if is_var:
            accounts_in_variance += 1
            total_variance_abs += abs(variance)
        rollforward_subs.append({
            "account_code": r.account_code,
            "account_name": r.account_name,
            "opening_amount": float(opening),
            "movement_amount": float(movement),
            "expected_close": float(expected_close),
            "actual_close": float(actual_close),
            "ref_amount": float(expected_close),   # generic compat
            "counter_amount": float(actual_close), # generic compat
            "diff": float(variance),
            "status": "DISCREPANCY" if is_var else "ALIGNED",
        })

    # If no GL was uploaded, only the variances stemming from TB-internal
    # inconsistency would surface. Tell the user we ran in degraded mode.
    if not gl_ds:
        # When GL is missing, "movement" is zero everywhere. The rollforward
        # then reduces to: opening = closing? — the legacy TB-internal check.
        # Surface a notice so the auditor knows to upload a GL.
        rollforward_subtitle = (
            "Aucun grand-livre chargé — le contrôle se rabat sur la cohérence "
            "interne TB (ouverture = clôture en l'absence de mouvements). "
            "Importer un grand-livre pour un vrai rollforward."
        )
    else:
        rollforward_subtitle = (
            f"TB ouverture + mouvements GL = TB clôture attendue. "
            f"Source GL : {gl_ds.original_filename}."
        )

    # Sort sub_items so variances appear first
    rollforward_subs.sort(key=lambda x: (x["status"] != "DISCREPANCY", x["account_code"]))

    results.append({
        "key": "TB_GL",
        "title": "Balance Générale — Cohérence ouverture + Mouvements = Clôture",
        "subtitle": rollforward_subtitle,
        "ref_label": "Σ TB clôture attendue",
        "ref_amount": float(sum_closing_expected),
        "counter_label": "Σ TB clôture réelle",
        "counter_amount": float(sum_closing_actual),
        "diff": float(sum_closing_actual - sum_closing_expected),
        "status": "ALIGNED" if accounts_in_variance == 0 else "DISCREPANCY",
        "sub_items": rollforward_subs,
        "rollforward_summary": {
            "accounts_examined": len(rows),
            "accounts_in_variance": accounts_in_variance,
            "total_variance_abs": float(total_variance_abs),
            "gl_loaded": gl_ds is not None,
            "gl_filename": gl_ds.original_filename if gl_ds else None,
        },
    })

    # ─── 2. AP ↔ 401X ──────────────────────────────────────────────────────
    ap_ds = latest_ds(DatasetKind.ACCOUNTS_PAYABLE_AGING)
    tb_401 = _sum_class_closing_net(rows, ("401",))
    # AP is typically a credit (liability); flip sign for comparison
    ap_counter = _auto_total(ap_ds, kind="AP")
    ap_tb_value = -tb_401  # liability → positive value
    diff_ap = (ap_counter or Decimal("0")) - ap_tb_value
    results.append({
        "key": "AP_401",
        "title": "Balance âgée fournisseurs ↔ TB comptes 401XXX",
        "subtitle": "Σ soldes fournisseurs (AP) = Σ soldes créditeurs 401",
        "ref_label": "TB clôture 401 (passif)",
        "ref_amount": float(ap_tb_value),
        "counter_label": "AP ageing total",
        "counter_amount": float(ap_counter) if ap_counter is not None else None,
        "counter_dataset_id": str(ap_ds.id) if ap_ds else None,
        "counter_filename": ap_ds.original_filename if ap_ds else None,
        "diff": float(diff_ap) if ap_counter is not None else None,
        "status": _status(diff_ap, ap_counter is not None),
        "account_breakdown": _accounts_breakdown(rows, ("401",), sign_flip=True),
    })

    # ─── 3. AR ↔ 41X (clients — exclude 419 which is a liability) ───────────
    ar_ds = latest_ds(DatasetKind.ACCOUNTS_RECEIVABLE_AGING)
    # All class 41 except 419 (clients créditeurs = customer advances, a liability)
    tb_ar = _sum_class_closing_net(rows, ("41",)) - _sum_class_closing_net(rows, ("419",))
    ar_counter = _auto_total(ar_ds, kind="AR")
    diff_ar = (ar_counter or Decimal("0")) - tb_ar
    results.append({
        "key": "AR_411",
        "title": "Balance âgée clients ↔ TB comptes 41XXX",
        "subtitle": "Σ soldes clients (AR) = Σ soldes débiteurs cl. 41 (hors 419 avances clients)",
        "ref_label": "TB clôture cl. 41 (actif)",
        "ref_amount": float(tb_ar),
        "counter_label": "AR ageing total",
        "counter_amount": float(ar_counter) if ar_counter is not None else None,
        "counter_dataset_id": str(ar_ds.id) if ar_ds else None,
        "counter_filename": ar_ds.original_filename if ar_ds else None,
        "diff": float(diff_ar) if ar_counter is not None else None,
        "status": _status(diff_ar, ar_counter is not None),
        "account_breakdown": _accounts_breakdown(rows, ("41",), exclude_prefixes=("419",)),
    })

    # ─── 4. Inventory ↔ class 3 (stocks, exclude 39 depreciation) ──────────
    inv_ds = latest_ds(DatasetKind.INVENTORY_LISTING)
    # All class 3 except 39 (dépréciation des stocks — contra-asset)
    tb_inv = _sum_class_closing_net(rows, ("3",)) - _sum_class_closing_net(rows, ("39",))
    inv_counter = _auto_total(inv_ds, kind="INVENTORY")
    diff_inv = (inv_counter or Decimal("0")) - tb_inv
    results.append({
        "key": "INVENTORY_3X",
        "title": "État d'inventaire ↔ TB classe 3X (stocks)",
        "subtitle": "Σ stock physique inventorié = Σ soldes débiteurs cl. 31 → 38 (hors 39 dépréciations)",
        "ref_label": "TB clôture cl. 3 (hors 39)",
        "ref_amount": float(tb_inv),
        "counter_label": "Inventaire physique total",
        "counter_amount": float(inv_counter) if inv_counter is not None else None,
        "counter_dataset_id": str(inv_ds.id) if inv_ds else None,
        "counter_filename": inv_ds.original_filename if inv_ds else None,
        "diff": float(diff_inv) if inv_counter is not None else None,
        "status": _status(diff_inv, inv_counter is not None),
        "account_breakdown": _accounts_breakdown(rows, ("3",), exclude_prefixes=("39",)),
    })

    # ─── 4bis. Fixed assets register ↔ TB classes 2X / 28X / 68X ─────────
    far_ds = latest_ds(DatasetKind.FIXED_ASSETS_REGISTER)
    far_totals = _auto_total_far_aggregates(far_ds)
    # TB sides
    # Gross value = class 2 excluding 25 (advances), 26 (financial part.), 27 (other fin.), 28 (accumulated dep.)
    tb_gross = (
        _sum_class_closing_net(rows, ("2",))
        - _sum_class_closing_net(rows, ("25", "26", "27", "28"))
    )
    # Accumulated depreciation = class 28X (contra-asset → credit balance, flip sign)
    tb_accum = -_sum_class_closing_net(rows, ("28",))
    # Year depreciation expense = class 68X (dotations aux amortissements — debit balance)
    tb_yr_dep = _sum_class_closing_net(rows, ("68",))

    if far_totals is not None:
        far_gross, far_accum, far_yr = far_totals
    else:
        far_gross, far_accum, far_yr = (None, None, None)

    def _far_card(key, title, subtitle, ref_label, ref_amount, counter_label,
                  counter_amount, prefixes, exclude=()):
        diff = (counter_amount or Decimal("0")) - ref_amount
        return {
            "key": key,
            "title": title,
            "subtitle": subtitle,
            "ref_label": ref_label,
            "ref_amount": float(ref_amount),
            "counter_label": counter_label,
            "counter_amount": float(counter_amount) if counter_amount is not None else None,
            "counter_dataset_id": str(far_ds.id) if far_ds else None,
            "counter_filename": far_ds.original_filename if far_ds else None,
            "diff": float(diff) if counter_amount is not None else None,
            "status": _status(diff, counter_amount is not None),
            "account_breakdown": _accounts_breakdown(rows, prefixes, exclude_prefixes=exclude),
        }

    results.append(_far_card(
        key="FAR_GROSS_2X",
        title="Registre immobilisations ↔ TB classe 2 (valeur brute)",
        subtitle="Σ valeur brute des immobilisations = Σ soldes débiteurs cl. 2 (hors 25, 26, 27, 28)",
        ref_label="TB clôture cl. 2 (hors 25-28)",
        ref_amount=tb_gross,
        counter_label="Σ valeur brute (registre)",
        counter_amount=far_gross,
        prefixes=("2",),
        exclude=("25", "26", "27", "28"),
    ))
    results.append(_far_card(
        key="FAR_ACCUM_28X",
        title="Registre immobilisations ↔ TB classe 28X (amortissements cumulés)",
        subtitle="Σ amortissements cumulés du registre = Σ soldes créditeurs cl. 28",
        ref_label="TB clôture cl. 28 (amort. cumulés)",
        ref_amount=tb_accum,
        counter_label="Σ amort. cumulés (registre)",
        counter_amount=far_accum,
        prefixes=("28",),
    ))
    results.append(_far_card(
        key="FAR_YR_68X",
        title="Registre immobilisations ↔ TB classe 68X (dotations exercice)",
        subtitle="Σ dotation aux amortissements du registre = Σ soldes débiteurs cl. 68",
        ref_label="TB clôture cl. 68 (dotations)",
        ref_amount=tb_yr_dep,
        counter_label="Σ dotation exercice (registre)",
        counter_amount=far_yr,
        prefixes=("68",),
    ))

    # ─── 5. Bank statements ↔ TB 52/51X (per bank) ─────────────────────────
    bank_rows = [
        r for r in rows
        if r.account_code.startswith(("52", "51"))
        or "banq" in (r.account_name or "").lower()
    ]
    bank_subs: list[dict[str, Any]] = []
    total_tb_bank = Decimal("0")
    total_counter_bank = Decimal("0")
    counter_present = False
    for r in bank_rows:
        bank_tb_value = Decimal(str(r.closing_debit)) - Decimal(str(r.closing_credit))
        total_tb_bank += bank_tb_value
        bank_ds = latest_ds(DatasetKind.BANK_STATEMENT, bank_code=r.account_code)
        bank_counter = _auto_total_bank(bank_ds)
        if bank_counter is not None:
            counter_present = True
            total_counter_bank += bank_counter
        diff_b = (bank_counter or Decimal("0")) - bank_tb_value
        bank_subs.append({
            "account_code": r.account_code,
            "account_name": r.account_name,
            "ref_amount": float(bank_tb_value),
            "counter_amount": float(bank_counter) if bank_counter is not None else None,
            "counter_dataset_id": str(bank_ds.id) if bank_ds else None,
            "counter_filename": bank_ds.original_filename if bank_ds else None,
            "diff": float(diff_b) if bank_counter is not None else None,
            "status": _status(diff_b, bank_counter is not None),
        })

    diff_bank_total = total_counter_bank - total_tb_bank
    results.append({
        "key": "BANK_52",
        "title": "Relevés bancaires ↔ TB classe 52/51X (Banques)",
        "subtitle": f"Σ soldes de clôture des {len(bank_rows)} relevés = Σ soldes clôture comptes Banques",
        "ref_label": "Σ TB clôture Banques",
        "ref_amount": float(total_tb_bank),
        "counter_label": "Σ relevés bancaires (clôture)",
        "counter_amount": float(total_counter_bank) if counter_present else None,
        "diff": float(diff_bank_total) if counter_present else None,
        "status": _status(diff_bank_total, counter_present),
        "sub_items": bank_subs,
    })

    # ─── 6/7/8. Reconciliations fiscales (Acompte IS · TVA collectée · TVA déductible)
    # ─────────────────────────────────────────────────────────────────────────
    ACOMPTE_RATE = Decimal("0.022")   # 2,2 % (régime réel) — paramétrable plus tard
    TVA_RATE = Decimal("0.1925")      # 19,25 %

    # CA HT = Σ class 70 net (créditeur positif)
    ca_ht = Decimal("0")
    tva_collectee_gl = Decimal("0")   # cpt 4434X (TVA facturée, créditeur)
    tva_deductible_gl = Decimal("0")  # cpt 4452X + 4456X (TVA récup., débiteur)
    if gl_ds:
        for line in gl_lines:  # gl_lines already loaded above
            acct = (line.account_code or "").strip()
            d = Decimal(str(line.debit or 0))
            c = Decimal(str(line.credit or 0))
            if acct.startswith("70"):
                ca_ht += c - d
            if acct.startswith("4434"):
                tva_collectee_gl += c - d
            if acct.startswith("4452") or acct.startswith("4456"):
                tva_deductible_gl += d - c

    fiscal_year = case.fiscal_year

    # Pour TVA collectée/déductible : on dérive depuis l'extracted_data
    # (le DMM L36 = TVA à payer = collectée − déductible ; base = CA HT)
    tva_payer_dmm = Decimal("0")
    tva_collectee_dmm = Decimal("0")
    tva_deductible_dmm = Decimal("0")
    tva_rows = (
        db.query(MonthlyReturn)
        .filter(
            MonthlyReturn.audit_case_id == case_id,
            MonthlyReturn.tax_type == TaxType.TVA,
            MonthlyReturn.period_year == fiscal_year,
        )
        .all()
    )
    for r in tva_rows:
        payer = Decimal(str(r.declared_amount or 0))
        tva_payer_dmm += payer
        base = Decimal(str(r.base_amount or 0))
        if base > 0:
            implied_coll = (base * TVA_RATE)
            tva_collectee_dmm += implied_coll
            tva_deductible_dmm += (implied_coll - payer)

    # Rec 6 — Acompte IS (2,2 % du CA HT)
    expected_acompte = (ca_ht * ACOMPTE_RATE).quantize(Decimal("1"))
    acompte_rows = (
        db.query(MonthlyReturn)
        .filter(
            MonthlyReturn.audit_case_id == case_id,
            MonthlyReturn.tax_type == TaxType.ACOMPTE_IS,
            MonthlyReturn.period_year == fiscal_year,
        )
        .all()
    )
    declared_acompte = sum(
        (Decimal(str(r.declared_amount or 0)) for r in acompte_rows),
        Decimal("0"),
    )
    has_acompte = bool(acompte_rows)
    diff_acompte = declared_acompte - expected_acompte
    results.append({
        "key": "ACOMPTE_IS",
        "title": "Acompte IS déclaré ↔ 2,2 % × CA HT (Grand-livre)",
        "subtitle": "Σ acomptes mensuels DMM = 2,2 % × Σ classe 70XX (CA HT)",
        "ref_label": "Théorique GL (2,2 % × CA HT)",
        "ref_amount": float(expected_acompte),
        "counter_label": f"Σ acomptes DMM ({fiscal_year})",
        "counter_amount": float(declared_acompte) if has_acompte else None,
        "diff": float(diff_acompte) if has_acompte else None,
        "status": _status(diff_acompte, has_acompte),
        "context": {
            "ca_ht_xaf": float(ca_ht),
            "rate_pct": float(ACOMPTE_RATE * 100),
            "fiscal_year": fiscal_year,
            "n_dmm_rows": len(acompte_rows),
        },
    })

    # Rec 7 — TVA collectée
    diff_tva_coll = tva_collectee_dmm - tva_collectee_gl
    results.append({
        "key": "TVA_COLLECTEE",
        "title": "TVA collectée DMM ↔ Grand-livre (compte 4434X)",
        "subtitle": "Σ base DMM × 19,25 % = Σ crédits du compte 4434X (TVA facturée)",
        "ref_label": "GL cpt 4434X (TVA facturée)",
        "ref_amount": float(tva_collectee_gl),
        "counter_label": f"TVA collectée DMM ({fiscal_year}) — base × 19,25 %",
        "counter_amount": float(tva_collectee_dmm) if tva_rows else None,
        "diff": float(diff_tva_coll) if tva_rows else None,
        "status": _status(diff_tva_coll, bool(tva_rows)),
        "context": {
            "tva_rate_pct": float(TVA_RATE * 100),
            "ca_dmm_base_xaf": float(sum(
                (Decimal(str(r.base_amount or 0)) for r in tva_rows), Decimal("0"))),
            "ca_ht_gl_xaf": float(ca_ht),
        },
    })

    # Rec 8 — TVA déductible
    diff_tva_ded = tva_deductible_dmm - tva_deductible_gl
    results.append({
        "key": "TVA_DEDUCTIBLE",
        "title": "TVA déductible DMM ↔ Grand-livre (comptes 4452X + 4456X)",
        "subtitle": "Σ TVA collectée DMM − TVA à payer DMM = Σ débits 445X (TVA récup.)",
        "ref_label": "GL cpt 4452X + 4456X (TVA récup.)",
        "ref_amount": float(tva_deductible_gl),
        "counter_label": f"TVA déductible DMM ({fiscal_year}) — implicite",
        "counter_amount": float(tva_deductible_dmm) if tva_rows else None,
        "diff": float(diff_tva_ded) if tva_rows else None,
        "status": _status(diff_tva_ded, bool(tva_rows)),
        "context": {
            "tva_payer_dmm_xaf": float(tva_payer_dmm),
            "tva_collectee_gl_xaf": float(tva_collectee_gl),
            "tva_collectee_dmm_xaf": float(tva_collectee_dmm),
        },
    })

    # ─── Apply reconciliation-skill methodology to every rec with a variance ─
    # For each DISCREPANCY card, call Claude to categorize reconciling items
    # per standard methodology (TIMING, POSTING_ERROR, OMISSION, FX,
    # INTERCOMPANY_UNMATCHED, OTHER) with aging buckets + escalation.
    for r in results:
        if r.get("status") != "DISCREPANCY":
            continue
        diff_val = r.get("diff")
        if diff_val is None:
            continue
        analysis = categorize_variance(
            rec_key=r["key"],
            rec_title=r["title"],
            ref_label=r["ref_label"],
            ref_amount=Decimal(str(r["ref_amount"])),
            counter_label=r["counter_label"],
            counter_amount=Decimal(str(r["counter_amount"])) if r.get("counter_amount") is not None else None,
            variance_xaf=Decimal(str(diff_val)),
            account_breakdown=r.get("account_breakdown"),
        )
        if analysis is not None:
            r["rec_items"] = analysis.to_dict()

    # Persist any auto-extracted aging totals so subsequent requests are cheap.
    db.commit()

    payload = {
        "tb_dataset_id": str(tb_ds.id),
        "tb_filename": tb_ds.original_filename,
        "fiscal_year": case.fiscal_year,
        "tolerance_fcfa": float(TOLERANCE),
        "reconciliations": results,
        "cached": False,
    }

    # Upsert into reconciliation_cache so subsequent calls are instant until
    # a new dataset is uploaded for this case.
    import json as _json
    db.execute(
        text("""
            INSERT INTO reconciliation_cache (audit_case_id, computed_at, payload)
            VALUES (:id, NOW(), CAST(:payload AS JSONB))
            ON CONFLICT (audit_case_id)
            DO UPDATE SET computed_at = NOW(), payload = EXCLUDED.payload
        """),
        {"id": str(case_id), "payload": _json.dumps(payload, default=str)},
    )
    db.commit()

    return payload


# ──────────────────────────────────────────────────────────────────────────────
# One-page synthesis report — summarises all reconciliations + conclusions
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/{case_id}/reconciliations/report")
def get_reconciliation_report(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Return a structured one-page report covering every reconciliation
    performed for the case, with status counters and a conclusion paragraph.

    The frontend renders this as a printable A4 sheet.
    """
    payload = get_reconciliations(case_id, db, user, refresh=False)
    case = db.get(AuditCase, case_id)
    taxpayer = case.taxpayer if case else None

    recs: list[dict[str, Any]] = payload.get("reconciliations") or []
    total = len(recs)
    by_status = {"ALIGNED": 0, "DISCREPANCY": 0, "MISSING": 0}
    for r in recs:
        s = r.get("status") or "MISSING"
        by_status[s] = by_status.get(s, 0) + 1

    total_variance_abs = sum(
        (abs(Decimal(str(r.get("diff") or 0))) for r in recs
         if r.get("status") == "DISCREPANCY"), Decimal("0"),
    )

    # Conclusion
    if by_status["DISCREPANCY"] == 0 and by_status["ALIGNED"] > 0:
        verdict = "FAVORABLE"
        conclusion = (
            "L'ensemble des rapprochements aboutissent sans écart significatif. "
            "Les sources comptables (TB, GL) et fiscales (DMM) sont cohérentes. "
            "Aucun ajustement n'est proposé sur cette base."
        )
    elif by_status["DISCREPANCY"] >= 3 or total_variance_abs > Decimal("10000000"):
        verdict = "RÉSERVÉE"
        conclusion = (
            f"{by_status['DISCREPANCY']} rapprochement(s) présentent des écarts "
            f"significatifs cumulés à {float(total_variance_abs):,.0f} FCFA. "
            "Demande de justifications au contribuable recommandée avant clôture."
        ).replace(",", " ")
    else:
        verdict = "À INSTRUIRE"
        conclusion = (
            f"{by_status['DISCREPANCY']} écart(s) à instruire. "
            "Examen complémentaire requis sur les postes concernés."
        )

    # Mini-summary per rec (1 ligne par rec)
    items = []
    for r in recs:
        items.append({
            "key": r.get("key"),
            "title": r.get("title"),
            "ref_label": r.get("ref_label"),
            "ref_amount": r.get("ref_amount"),
            "counter_label": r.get("counter_label"),
            "counter_amount": r.get("counter_amount"),
            "diff": r.get("diff"),
            "status": r.get("status"),
        })

    return {
        "case_id": str(case_id),
        "case_reference": getattr(case, "reference", None),
        "fiscal_year": case.fiscal_year if case else None,
        "taxpayer": {
            "raison_sociale": getattr(taxpayer, "raison_sociale", None),
            "niu": getattr(taxpayer, "niu", None),
        } if taxpayer else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": user.email,
        "summary": {
            "total_recs": total,
            "by_status": by_status,
            "total_variance_abs_xaf": float(total_variance_abs),
        },
        "verdict": verdict,
        "conclusion": conclusion,
        "items": items,
        "tb_filename": payload.get("tb_filename"),
        "legal_reference": "CGI Cameroun · LPF · SYSCOHADA Révisé",
    }
