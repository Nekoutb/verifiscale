"""Parsed trial balance lines (6 columns) — SYSCOHADA art. 19."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class TrialBalanceLine(Base):
    __tablename__ = "trial_balance_lines"
    __table_args__ = (
        Index("ix_tb_dataset_acct", "dataset_id", "account_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    account_code: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(String(512), nullable=False)

    opening_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    opening_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    period_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    period_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    closing_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    closing_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
