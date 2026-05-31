"""Cash-payments — per-line current-year decision + exclusions."""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Boolean, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase


class CashCurrentYear(str, enum.Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class CashDecisionSrc(str, enum.Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class CashExclusionKind(str, enum.Enum):
    SALARY = "SALARY"
    MISSION = "MISSION"
    ADMIN_FEE = "ADMIN_FEE"
    OTHER = "OTHER"


class CashPaymentAssessment(Base):
    __tablename__ = "cash_payment_assessment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audit_case: Mapped["AuditCase"] = relationship()
    piece_number: Mapped[str] = mapped_column(String(64), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    current_year_decision: Mapped[CashCurrentYear | None] = mapped_column(Enum(CashCurrentYear))
    decision_source: Mapped[CashDecisionSrc] = mapped_column(
        Enum(CashDecisionSrc), nullable=False, default=CashDecisionSrc.AUTO
    )
    decision_reason: Mapped[str | None] = mapped_column(String(2048))
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_kind: Mapped[CashExclusionKind | None] = mapped_column(Enum(CashExclusionKind))

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
