"""Registry of all control categories — single dispatch point."""
from __future__ import annotations

from app.controls.aggregates import compute_tb_aggregates
from app.controls.base import ControlContext, Finding
from app.controls.category_a import CATEGORY_A_CONTROLS, run_category_a
from app.controls.category_b import CATEGORY_B_CONTROLS, run_category_b
from app.controls.category_c import CATEGORY_C_CONTROLS, run_category_c
from app.controls.category_d import CATEGORY_D_CONTROLS, run_category_d
from app.controls.category_h import CATEGORY_H_CONTROLS, run_category_h


CATEGORY_RUNNERS = {
    "SYSCOHADA_A":  run_category_a,
    "SYSCOHADA_B":  run_category_b,
    "FISCAL_C":     run_category_c,
    "FISCAL_D":     run_category_d,
    "PROCEDURAL_H": run_category_h,
}

CATEGORY_METADATA = {
    "SYSCOHADA_A":  {"name": "SYSCOHADA — Intégrité comptable",     "controls": CATEGORY_A_CONTROLS},
    "SYSCOHADA_B":  {"name": "SYSCOHADA — Évaluation & SIG",        "controls": CATEGORY_B_CONTROLS},
    "FISCAL_C":     {"name": "Fiscal — Impôt sur les Sociétés",     "controls": CATEGORY_C_CONTROLS},
    "FISCAL_D":     {"name": "Fiscal — TVA",                        "controls": CATEGORY_D_CONTROLS},
    "PROCEDURAL_H": {"name": "Procédure LPF",                       "controls": CATEGORY_H_CONTROLS},
}


def run_category(category: str, ctx: ControlContext) -> list[Finding]:
    """Dispatch to the right runner, pre-computing aggregates once."""
    if "tb_aggregates" not in ctx.extra:
        ctx.extra["tb_aggregates"] = compute_tb_aggregates(ctx.trial_balance)
    runner = CATEGORY_RUNNERS.get(category)
    if not runner:
        raise ValueError(f"Catégorie inconnue : {category}")
    return runner(ctx)


def run_all_categories(ctx: ControlContext) -> dict[str, list[Finding]]:
    """Run every registered category and return findings grouped by category."""
    if "tb_aggregates" not in ctx.extra:
        ctx.extra["tb_aggregates"] = compute_tb_aggregates(ctx.trial_balance)
    return {cat: runner(ctx) for cat, runner in CATEGORY_RUNNERS.items()}
