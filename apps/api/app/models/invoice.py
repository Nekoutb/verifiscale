"""Supplier invoice — one parsed PDF, with substance/form control results."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Date, ForeignKey, Numeric, Boolean, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase
    from app.models.dataset import Dataset


class InvoiceStatus(str, enum.Enum):
    PENDING = "PENDING"      # uploaded, awaiting OCR
    PROCESSING = "PROCESSING"
    PARSED = "PARSED"
    OCR_ERROR = "OCR_ERROR"


class Invoice(Base):
    """One supplier invoice — extracted from a PDF + scored against CGI art. 150 / LPF L 8 bis."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audit_case: Mapped["AuditCase"] = relationship()

    # The underlying PDF lives in storage; we point to the Dataset row.
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset: Mapped["Dataset"] = relationship()

    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.PENDING, index=True
    )
    ocr_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # ── Extracted invoice fields ────────────────────────────────────────────
    supplier_niu: Mapped[str | None] = mapped_column(String(32), index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(512), index=True)
    supplier_rccm: Mapped[str | None] = mapped_column(String(64))
    supplier_address: Mapped[str | None] = mapped_column(String(512))
    supplier_tax_center: Mapped[str | None] = mapped_column(String(128))

    customer_niu: Mapped[str | None] = mapped_column(String(32))
    customer_name: Mapped[str | None] = mapped_column(String(512))

    invoice_number: Mapped[str | None] = mapped_column(String(128), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, index=True)

    base_ht_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    tva_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ttc_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    tva_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 19.25 typical

    currency: Mapped[str] = mapped_column(String(8), default="XAF")
    description: Mapped[str | None] = mapped_column(String(2048))

    # ── Control results ────────────────────────────────────────────────────
    # JSON: { "FOND_NIU_VALID": true, "FORME_NUMERO_SEQUENTIEL": false, ... }
    control_results: Mapped[dict | None] = mapped_column(JSONB)
    failed_fond_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_forme_count: Mapped[int] = mapped_column(Integer, default=0)
    is_compliant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    raw_ocr: Mapped[dict | None] = mapped_column(JSONB)  # raw model output for audit trail

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
