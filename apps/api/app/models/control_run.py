"""Control runs and findings.

A ControlRun is the execution of one or more controls against an AuditCase's data.
A ControlFinding is a single anomaly detected by a single control.
"""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase


class ControlSeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKING = "BLOCKING"


class ControlStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ControlRun(Base):
    __tablename__ = "control_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audit_case: Mapped["AuditCase"] = relationship(back_populates="control_runs")

    # e.g. "SYSCOHADA_A" or specific code "A1_DOUBLE_ENTRY"
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[ControlStatus] = mapped_column(
        Enum(ControlStatus), nullable=False, default=ControlStatus.PENDING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings: Mapped[list["ControlFinding"]] = relationship(
        back_populates="control_run", cascade="all, delete-orphan"
    )


class ControlFinding(Base):
    __tablename__ = "control_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    control_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    control_run: Mapped["ControlRun"] = relationship(back_populates="findings")

    # Control identifier from the catalog (e.g. "A1", "B4", "D6")
    control_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[ControlSeverity] = mapped_column(Enum(ControlSeverity), nullable=False)

    # Legal reference (e.g. "SYSCOHADA art. 17.2" or "CGI art. 143")
    legal_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Structured evidence: piece number, account code, amount, etc.
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    estimated_impact_xaf: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
