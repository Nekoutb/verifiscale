"""Journal entries (pièces comptables) and their lines.

Each JournalEntry must satisfy SYSCOHADA art. 17.2:
    SUM(debit lines) = SUM(credit lines)
This invariant is checked by control A1.
"""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_je_dataset_piece", "dataset_id", "piece_number"),
        Index("ix_je_dataset_date", "dataset_id", "entry_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    piece_number: Mapped[str] = mapped_column(String(128), nullable=False)
    journal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)

    lines: Mapped[list["JournalEntryLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="JournalEntryLine.line_number"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    entry: Mapped["JournalEntry"] = relationship(back_populates="lines")

    line_number: Mapped[int] = mapped_column(nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    libelle: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    # Lettrage / matricule for closure of customer-supplier accounts
    lettrage: Mapped[str | None] = mapped_column(String(64), nullable=True)
