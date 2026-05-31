"""Base types for the controls engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models.control_run import ControlSeverity


@dataclass
class Finding:
    control_code: str
    title: str
    description: str
    severity: ControlSeverity
    legal_reference: str
    evidence: dict[str, Any] = field(default_factory=dict)
    estimated_impact_xaf: float | None = None


@dataclass
class ControlContext:
    """Data passed to a control runner.

    A control reads whatever data it needs from the context; the orchestrator
    is responsible for loading the relevant rows from DB before calling controls.
    """
    audit_case_id: str
    trial_balance: list[dict] = field(default_factory=list)
    general_ledger: list[dict] = field(default_factory=list)
    journal_entries: list[dict] = field(default_factory=list)  # {piece, date, journal, lines: [...]}
    extra: dict[str, Any] = field(default_factory=dict)


class Control(Protocol):
    """A control is a callable that emits zero or more findings."""
    code: str
    title: str
    legal_reference: str
    severity: ControlSeverity

    def run(self, ctx: ControlContext) -> list[Finding]: ...
