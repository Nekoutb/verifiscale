"""Auditor review flags on individual GL lines.

Used by the account-analysis modules (comptes d'associés 46XX, comptes divers
4711/4712): the auditor ticks « justification reçue » per transaction and may
hide transactions that offset each other. Keyed by (case, module, pièce, ligne)
so the flags survive a GL re-import.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewModule(str, enum.Enum):
    SHAREHOLDER = "SHAREHOLDER"   # comptes d'associés 46XX
    SUNDRY = "SUNDRY"             # comptes divers 4711 / 4712


class LedgerLineReview(Base):
    __tablename__ = "ledger_line_review"
    __table_args__ = (
        UniqueConstraint("audit_case_id", "module", "piece_number", "line_number",
                         name="uq_ledger_review_line"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module: Mapped[ReviewModule] = mapped_column(Enum(ReviewModule), nullable=False)

    piece_number: Mapped[str] = mapped_column(String(128), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)

    #: « justification reçue » — an unticked line with a debit position is a finding
    justified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: auditor hid this line as part of an offsetting pair
    hidden_offset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
