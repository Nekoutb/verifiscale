"""Tax return models — what was filed by the auditee.

MonthlyReturn   : one row per (audit_case, tax_type, period). The legal filing.
PaymentProof    : quittance / bank receipt attached to a MonthlyReturn.

Populated either by Claude Vision PDF extraction (background job)
or manually entered by the auditor (admin endpoint).
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Date, ForeignKey, Enum, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase
    from app.models.dataset import Dataset


class TaxType(str, enum.Enum):
    """All tax/contribution types this platform recognizes."""
    # Monthly
    TVA = "TVA"
    IRPP_SALAIRES = "IRPP_SALAIRES"
    CNPS = "CNPS"
    TSR = "TSR"
    PRECOMPTE_LOYERS = "PRECOMPTE_LOYERS"
    PRECOMPTE_ACHATS = "PRECOMPTE_ACHATS"
    IRCM = "IRCM"
    DROIT_TIMBRE = "DROIT_TIMBRE"
    CFC = "CFC"
    FNE = "FNE"
    RAV = "RAV"
    # Quarterly
    ACOMPTE_IS = "ACOMPTE_IS"
    # Annual
    IS_ANNUEL = "IS_ANNUEL"
    PATENTE = "PATENTE"
    FONCIER = "FONCIER"


class ReturnStatus(str, enum.Enum):
    PENDING = "PENDING"        # No return uploaded yet for this period
    FILED = "FILED"            # PDF received, parsed, but no payment proof
    PAID = "PAID"              # Filed + paid (quittance attached)
    AMENDED = "AMENDED"        # Original superseded by an amendment
    LITIGATION = "LITIGATION"  # Disputed by taxpayer or under contradictoire


class PaymentMethod(str, enum.Enum):
    VIREMENT = "VIREMENT"
    ESPECES = "ESPECES"
    CHEQUE = "CHEQUE"
    MOBILE_MONEY = "MOBILE_MONEY"
    COMPENSATION = "COMPENSATION"


# ────────────────────────────────────────────────────────────────────────────
# MonthlyReturn — one per (audit_case × tax_type × period)
# ────────────────────────────────────────────────────────────────────────────
class MonthlyReturn(Base):
    """A tax return filed by the auditee for a given period and tax type."""
    __tablename__ = "monthly_returns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audit_case: Mapped["AuditCase"] = relationship()

    tax_type: Mapped[TaxType] = mapped_column(Enum(TaxType), nullable=False, index=True)

    # Period identification
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 1-12 for monthly
    period_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-4 for quarterly

    # Filing dates
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filing_deadline: Mapped[date] = mapped_column(Date, nullable=False)

    # Amounts (in FCFA)
    declared_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)  # taxable base
    credit_reporte: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)  # for TVA

    # Source document (the PDF)
    source_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True,
    )
    source_dataset: Mapped["Dataset | None"] = relationship()

    # Raw Claude Vision extraction (full JSON) — for traceability and re-parsing
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[ReturnStatus] = mapped_column(
        Enum(ReturnStatus), nullable=False, default=ReturnStatus.PENDING,
    )
    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Payment proofs attached to this return
    payment_proofs: Mapped[list["PaymentProof"]] = relationship(
        back_populates="monthly_return", cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


# ────────────────────────────────────────────────────────────────────────────
# PaymentProof — one per quittance (a return can have multiple if split)
# ────────────────────────────────────────────────────────────────────────────
class PaymentProof(Base):
    __tablename__ = "payment_proofs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    monthly_return_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monthly_returns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    monthly_return: Mapped["MonthlyReturn"] = relationship(back_populates="payment_proofs")

    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)  # n° quittance / bordereau
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), nullable=False, default=PaymentMethod.VIREMENT,
    )
    bank: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Source document
    source_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True,
    )
    source_dataset: Mapped["Dataset | None"] = relationship()

    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
