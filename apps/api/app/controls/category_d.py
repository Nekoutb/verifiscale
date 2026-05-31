"""Category D — TVA (Taxe sur la Valeur Ajoutée).

Operational audit controls executed against:
  ctx.extra["monthly_returns"]  — list of MonthlyReturn dicts (injected by orchestrator)
  ctx.trial_balance              — for annual reconciliation against GL accounts
  ctx.extra["lpf_dates"]         — for fiscal_year

These controls implement the universal audit pattern (existence → timeliness →
reconciliation) for TVA. See docs/tax-controls-design.md for the full design.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.controls.base import ControlContext, Finding
from app.models.control_run import ControlSeverity

# ── TVA constants ────────────────────────────────────────────────────────────
TVA_RATE_STANDARD = Decimal("0.175")          # 17.5% (CAC included) — CGI art. 142
DELAI_DEPOT_TVA_JOURS = 15                    # CGI art. 149-150
TVA_ACCOUNTS = {
    "collectee":         ["4431"],            # TVA facturée (collected)
    "deductible_bs":     ["4452"],            # TVA déductible biens et services
    "deductible_immo":   ["4456"],            # TVA déductible sur immobilisations
}
TOLERANCE_RECONCILIATION = Decimal("100")     # FCFA tolerance for rounding


# ── Helpers ──────────────────────────────────────────────────────────────────
def _returns(ctx: ControlContext) -> list[dict]:
    """Filter ctx.extra['monthly_returns'] to TVA only."""
    all_returns = ctx.extra.get("monthly_returns", [])
    return [r for r in all_returns if r.get("tax_type") == "TVA"]


def _fiscal_year(ctx: ControlContext) -> int | None:
    return ctx.extra.get("lpf_dates", {}).get("fiscal_year")


def _sum_account_movements(ctx: ControlContext, prefixes: list[str], side: str) -> Decimal:
    """Sum period movements (period_debit or period_credit) for accounts matching prefixes."""
    total = Decimal("0")
    for line in ctx.trial_balance:
        if not any(line["account_code"].startswith(p) for p in prefixes):
            continue
        val = line.get(side, 0)
        total += Decimal(str(val))
    return total


# ── D17 — Existence of 12 monthly TVA returns ────────────────────────────────
def d17_existence_returns(ctx: ControlContext) -> list[Finding]:
    """Verify the 12 monthly TVA returns were filed (one per month)."""
    fy = _fiscal_year(ctx)
    if not fy:
        return [Finding(
            control_code="D17",
            title="Exercice fiscal non renseigné",
            description="Impossible de vérifier l'existence des déclarations TVA mensuelles.",
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 149",
        )]

    returns = _returns(ctx)
    months_with_return = {r["period_month"] for r in returns if r.get("period_month")}
    missing = [m for m in range(1, 13) if m not in months_with_return]

    if not missing:
        return [Finding(
            control_code="D17",
            title=f"12/12 déclarations TVA mensuelles présentes ({fy})",
            description=f"Toutes les déclarations TVA mensuelles de l'exercice {fy} sont enregistrées.",
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 149",
            evidence={"months_present": sorted(months_with_return), "fiscal_year": fy},
        )]

    month_names = ["janv", "févr", "mars", "avril", "mai", "juin",
                   "juil", "août", "sept", "oct", "nov", "déc"]
    missing_labels = [f"{month_names[m-1]} {fy}" for m in missing]
    return [Finding(
        control_code="D17",
        title=f"{len(missing)} déclaration(s) TVA manquante(s) : {', '.join(missing_labels)}",
        description=(
            f"L'exercice {fy} doit comporter 12 déclarations TVA mensuelles (CGI art. 149). "
            f"Manquantes : {', '.join(missing_labels)}. "
            "Le contribuable doit déposer une déclaration NÉANT même en l'absence d'opérations."
        ),
        severity=ControlSeverity.BLOCKING,
        legal_reference="CGI art. 149",
        evidence={"missing_months": missing, "present_months": sorted(months_with_return), "fiscal_year": fy},
    )]


# ── D18 — Délai de dépôt ≤ 15 du mois suivant ────────────────────────────────
def d18_delai_depot(ctx: ControlContext) -> list[Finding]:
    """For each TVA return, check filing_date ≤ deadline."""
    returns = _returns(ctx)
    if not returns:
        return []

    late = []
    on_time = 0
    for r in returns:
        filing = r.get("filing_date")
        deadline = r.get("filing_deadline")
        if not filing or not deadline:
            continue
        if isinstance(filing, str):
            filing = date.fromisoformat(filing)
        if isinstance(deadline, str):
            deadline = date.fromisoformat(deadline)
        if filing > deadline:
            late.append({
                "month": r.get("period_month"),
                "filing_date": str(filing),
                "deadline": str(deadline),
                "days_late": (filing - deadline).days,
            })
        else:
            on_time += 1

    if not late:
        return [Finding(
            control_code="D18",
            title=f"Délais de dépôt TVA respectés ({on_time}/{len(returns)})",
            description=f"Toutes les déclarations TVA examinées ont été déposées au plus tard le 15 du mois suivant.",
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 149-150",
            evidence={"on_time": on_time, "total_examined": len(returns)},
        )]

    findings = []
    for l in late:
        findings.append(Finding(
            control_code="D18",
            title=f"Dépôt TVA tardif — mois {l['month']:02d} ({l['days_late']} j de retard)",
            description=(
                f"La déclaration TVA du mois {l['month']:02d} a été déposée le {l['filing_date']} "
                f"alors que l'échéance légale était le {l['deadline']} ({l['days_late']} jours de retard). "
                "Pénalité applicable : 25 % + intérêt 1.5 %/mois (LPF art. M 1 + L 95)."
            ),
            severity=ControlSeverity.HIGH,
            legal_reference="CGI art. 149-150 + LPF M 1",
            evidence=l,
        ))
    return findings


# ── D22 — TVA collectée déclarée Σ = Σ mouvements crédit GL 4431 ─────────────
def d22_recoupement_tva_collectee(ctx: ControlContext) -> list[Finding]:
    """Sum of TVA collectée declared in 12 monthly returns vs GL 4431 period_credit."""
    returns = _returns(ctx)
    if not returns:
        return []
    if not ctx.trial_balance:
        return [Finding(
            control_code="D22",
            title="Balance non chargée — recoupement TVA collectée impossible",
            description="Importer une balance générale pour recouper la TVA collectée déclarée vs comptabilité.",
            severity=ControlSeverity.INFO,
            legal_reference="Cross-control",
        )]

    declared_total = sum(
        (Decimal(str(r.get("declared_amount") or 0)) for r in returns),
        Decimal("0"),
    )
    gl_collectee = _sum_account_movements(ctx, TVA_ACCOUNTS["collectee"], "period_credit")
    diff = declared_total - gl_collectee

    if abs(diff) <= TOLERANCE_RECONCILIATION:
        return [Finding(
            control_code="D22",
            title=f"TVA collectée recoupée : Σ déclarée = Σ GL ({declared_total:,.0f} FCFA)",
            description=(
                f"Σ TVA collectée déclarée ({declared_total:,.0f} FCFA) = "
                f"Σ mouvements crédit compte 4431 ({gl_collectee:,.0f} FCFA). Écart : {diff:+,.0f} FCFA."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="Cross-control",
            evidence={"declared_total": float(declared_total), "gl_total": float(gl_collectee), "diff": float(diff)},
        )]

    return [Finding(
        control_code="D22",
        title=f"Écart TVA collectée déclarée vs GL : {diff:+,.0f} FCFA",
        description=(
            f"Σ TVA collectée déclarée dans les {len(returns)} déclarations mensuelles : "
            f"{declared_total:,.0f} FCFA. "
            f"Σ mouvements crédit compte 4431 (TVA facturée) : {gl_collectee:,.0f} FCFA. "
            f"Écart de {diff:+,.0f} FCFA → "
            f"{'sous-déclaration' if diff < 0 else 'sur-déclaration'} à investiguer."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="Cross-control · CGI art. 149",
        evidence={
            "declared_total": float(declared_total),
            "gl_total": float(gl_collectee),
            "diff": float(diff),
            "returns_count": len(returns),
        },
        estimated_impact_xaf=float(abs(diff)),
    )]


# ── D23 — TVA déductible BS déclarée Σ = Σ mouvements débit GL 4452 ──────────
def d23_recoupement_tva_deductible_bs(ctx: ControlContext) -> list[Finding]:
    returns = _returns(ctx)
    if not returns or not ctx.trial_balance:
        return []

    # base_amount on returns isn't TVA déductible — that's the taxable base.
    # For a v1, we read the declared TVA déductible if extracted into raw notes;
    # otherwise we just report what the GL shows.
    gl_deductible = _sum_account_movements(ctx, TVA_ACCOUNTS["deductible_bs"], "period_debit")
    return [Finding(
        control_code="D23",
        title=f"TVA déductible biens & services — mouvements GL 4452 : {gl_deductible:,.0f} FCFA",
        description=(
            f"Cumul annuel des mouvements débit du compte 4452 : {gl_deductible:,.0f} FCFA. "
            "À comparer manuellement avec la TVA déductible déclarée dans les 12 bordereaux TVA mensuels. "
            "Tout écart > 100 000 FCFA constitue un point d'audit (CGI art. 143-149)."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="Cross-control · CGI art. 143",
        evidence={"gl_total": float(gl_deductible), "returns_count": len(returns)},
    )]


# ── D24 — TVA déductible immo déclarée Σ = Σ mouvements débit GL 4456 ────────
def d24_recoupement_tva_deductible_immo(ctx: ControlContext) -> list[Finding]:
    if not ctx.trial_balance:
        return []
    gl_immo = _sum_account_movements(ctx, TVA_ACCOUNTS["deductible_immo"], "period_debit")
    if gl_immo == 0:
        return []  # No immo TVA — skip
    return [Finding(
        control_code="D24",
        title=f"TVA déductible sur immobilisations (GL 4456) : {gl_immo:,.0f} FCFA",
        description=(
            f"Cumul annuel : {gl_immo:,.0f} FCFA. "
            "Vérifier la cohérence avec les bordereaux TVA mensuels (ligne immobilisations) "
            "et la facturation des immobilisations acquises pendant l'exercice."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="CGI art. 143-145",
        evidence={"gl_total": float(gl_immo)},
    )]


# ── D26 — Crédit TVA reporté — solde 4431 fin N-1 = report ouvert N ──────────
def d26_credit_tva_reporte(ctx: ControlContext) -> list[Finding]:
    """Verify TVA credit carried forward from N-1 matches January N report."""
    returns = _returns(ctx)
    jan = next((r for r in returns if r.get("period_month") == 1), None)
    if not jan or not jan.get("credit_reporte"):
        return []
    cr = Decimal(str(jan["credit_reporte"]))
    if cr == 0:
        return []
    return [Finding(
        control_code="D26",
        title=f"Crédit TVA reporté ouverture {cr:,.0f} FCFA — à vérifier vs solde 4431 clôture N-1",
        description=(
            f"La déclaration TVA de janvier mentionne un crédit reporté de {cr:,.0f} FCFA. "
            "Vérifier que ce montant correspond au solde du compte 4431 à la clôture de l'exercice précédent."
        ),
        severity=ControlSeverity.MEDIUM,
        legal_reference="CGI art. 149",
        evidence={"credit_reporte_ouverture": float(cr)},
    )]


# ── D27 — Synthèse ──────────────────────────────────────────────────────────
def d27_synthese(ctx: ControlContext) -> list[Finding]:
    returns = _returns(ctx)
    if not returns:
        return [Finding(
            control_code="D27",
            title="Aucune déclaration TVA chargée pour ce dossier",
            description=(
                "Pour exécuter les contrôles TVA opérationnels, importez les 12 déclarations "
                "TVA mensuelles via l'onglet « Déclarations mensuelles » du dossier."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 149",
        )]

    declared_total = sum(
        (Decimal(str(r.get("declared_amount") or 0)) for r in returns),
        Decimal("0"),
    )
    base_total = sum(
        (Decimal(str(r.get("base_amount") or 0)) for r in returns if r.get("base_amount")),
        Decimal("0"),
    )

    return [Finding(
        control_code="D27",
        title=f"Synthèse TVA — {len(returns)}/12 déclarations · {declared_total:,.0f} FCFA cumulés",
        description=(
            f"{len(returns)} déclarations TVA chargées sur 12 attendues. "
            f"TVA nette cumulée déclarée : {declared_total:,.0f} FCFA "
            f"sur une base déclarée de {base_total:,.0f} FCFA "
            f"(taux effectif : {float(declared_total/base_total*100):.2f} %)."
            if base_total > 0 else
            f"{len(returns)} déclarations TVA chargées. "
            f"TVA nette cumulée déclarée : {declared_total:,.0f} FCFA."
        ),
        severity=ControlSeverity.INFO,
        legal_reference="CGI art. 142-150",
        evidence={
            "returns_count": len(returns),
            "declared_total": float(declared_total),
            "base_total": float(base_total),
        },
    )]


# ── D28 — VAT year-end reconciliation: TB closing 443x/445x vs Jan N+1 VAT ──
def d28_recoupement_ye_vs_jan_n1(ctx: ControlContext) -> list[Finding]:
    """SYSCOHADA + CGI art. 149 — la déclaration TVA de janvier N+1 doit refléter
    le solde des comptes TVA à la clôture N : solde net dû / créance vis-à-vis
    de l'État = TVA collectée − TVA déductible BS − TVA déductible immo.

    Ce contrôle compare :
      - Solde des comptes 4431 (collectée) − 4452/4456 (déductible) à la clôture N
      - Montant net déclaré sur la DSF-M TVA de janvier N+1
    """
    if not ctx.trial_balance:
        return []

    fy = _fiscal_year(ctx)
    if not fy:
        return []

    # TB closing balances
    tva_collectee_clo = (
        _sum_account_movements(ctx, ["443"], "closing_credit") -
        _sum_account_movements(ctx, ["443"], "closing_debit")
    )
    tva_deductible_clo = (
        _sum_account_movements(ctx, ["445"], "closing_debit") -
        _sum_account_movements(ctx, ["445"], "closing_credit")
    )
    solde_tb_net = tva_collectee_clo - tva_deductible_clo

    # Jan N+1 declaration
    returns = _returns(ctx)
    jan_next = next(
        (r for r in returns
         if r.get("period_year") == fy + 1 and r.get("period_month") == 1),
        None,
    )

    if not jan_next:
        return [Finding(
            control_code="D28",
            title=f"Déclaration TVA de janvier {fy + 1} non chargée — recoupement YE impossible",
            description=(
                f"À la clôture {fy}, le solde net des comptes TVA (443X collectée moins "
                f"445X déductible) ressort à {solde_tb_net:,.0f} FCFA. "
                f"Pour valider ce solde, importer la déclaration TVA de janvier {fy + 1} "
                "(qui reflète l'écart de TVA dû ou le crédit reporté au début de N+1)."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 149 · SYSCOHADA Cohérence",
            evidence={
                "fiscal_year": fy,
                "tva_collectee_cloture_443x": float(tva_collectee_clo),
                "tva_deductible_cloture_445x": float(tva_deductible_clo),
                "solde_tb_net": float(solde_tb_net),
            },
        )]

    jan_declared = Decimal(str(jan_next.get("declared_amount") or 0))
    diff = solde_tb_net - jan_declared
    tolerance = Decimal("1000")

    if abs(diff) <= tolerance:
        return [Finding(
            control_code="D28",
            title=f"TVA YE recoupée : solde TB ({solde_tb_net:,.0f}) ≈ déclaré jan {fy+1} ({jan_declared:,.0f} FCFA)",
            description=(
                f"Solde TB clôture {fy} (443X − 445X) : {solde_tb_net:,.0f} FCFA. "
                f"TVA nette déclarée en janvier {fy + 1} : {jan_declared:,.0f} FCFA. "
                f"Écart : {diff:+,.0f} FCFA — cohérent."
            ),
            severity=ControlSeverity.INFO,
            legal_reference="CGI art. 149 · SYSCOHADA Cohérence",
            evidence={
                "fiscal_year": fy,
                "solde_tb_net": float(solde_tb_net),
                "jan_next_declared": float(jan_declared),
                "diff": float(diff),
            },
        )]

    return [Finding(
        control_code="D28",
        title=f"Écart TVA YE : {diff:+,.0f} FCFA entre TB clôture {fy} et déclaration de janvier {fy + 1}",
        description=(
            f"Comptes TVA à la clôture {fy} : "
            f"443X (collectée nette) = {tva_collectee_clo:,.0f} FCFA · "
            f"445X (déductible nette) = {tva_deductible_clo:,.0f} FCFA · "
            f"Solde net dû à l'État = {solde_tb_net:,.0f} FCFA. "
            f"TVA nette déclarée en janvier {fy + 1} : {jan_declared:,.0f} FCFA. "
            f"Écart de {diff:+,.0f} FCFA → "
            f"{'TVA non déclarée' if diff > 0 else 'sur-déclaration ou crédit reporté incorrect'} "
            "à investiguer (régularisation YE manquante, écritures hors période, "
            "ou compte de TVA non soldé en fin d'exercice)."
        ),
        severity=ControlSeverity.HIGH,
        legal_reference="CGI art. 149 · SYSCOHADA Cohérence",
        evidence={
            "fiscal_year": fy,
            "tva_collectee_cloture_443x": float(tva_collectee_clo),
            "tva_deductible_cloture_445x": float(tva_deductible_clo),
            "solde_tb_net": float(solde_tb_net),
            "jan_next_declared": float(jan_declared),
            "diff": float(diff),
        },
        estimated_impact_xaf=float(abs(diff)),
    )]


CATEGORY_D_CONTROLS = [
    ("D17", "Existence des 12 déclarations TVA mensuelles",        d17_existence_returns),
    ("D18", "Délai de dépôt ≤ 15 du mois suivant",                 d18_delai_depot),
    ("D22", "Recoupement TVA collectée déclarée ↔ GL 4431",        d22_recoupement_tva_collectee),
    ("D23", "Recoupement TVA déductible BS ↔ GL 4452",             d23_recoupement_tva_deductible_bs),
    ("D24", "Recoupement TVA déductible immo ↔ GL 4456",           d24_recoupement_tva_deductible_immo),
    ("D26", "Crédit TVA reporté ouverture vs clôture N-1",         d26_credit_tva_reporte),
    ("D27", "Synthèse TVA cumulée",                                d27_synthese),
    ("D28", "Recoupement YE TVA : TB clôture vs déclaration jan N+1", d28_recoupement_ye_vs_jan_n1),
]


def run_category_d(ctx: ControlContext) -> list[Finding]:
    all_findings: list[Finding] = []
    for _, _, fn in CATEGORY_D_CONTROLS:
        try:
            all_findings.extend(fn(ctx))
        except Exception as e:  # noqa: BLE001
            all_findings.append(Finding(
                control_code="D-ERR",
                title=f"Erreur dans {fn.__name__}",
                description=str(e),
                severity=ControlSeverity.INFO,
                legal_reference="—",
            ))
    return all_findings
