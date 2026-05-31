"""Charges financières — associés prêteurs + params + BEAC cache (CGI Art. 7 B)."""
import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase


class ChgFinVerdict(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    NON_ELIGIBLE = "NON_ELIGIBLE"
    A_REINSTRUIRE = "A_REINSTRUIRE"


class ChgFinVerdictSource(str, enum.Enum):
    AUTO = "AUTO"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class BeacRateCache(Base):
    __tablename__ = "beac_rate_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tiao_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    marginal_lending_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    deposit_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_url: Mapped[str | None] = mapped_column(String(256))


class ChargesFinCaseParams(Base):
    __tablename__ = "charges_fin_case_params"

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"), primary_key=True
    )
    capitaux_propres_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ebitda_fiscal_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    rate_basis: Mapped[str] = mapped_column(String(16), default="TIAO")
    taux_beac_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    notes: Mapped[str | None] = mapped_column(String(2048))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChargesFinAssocie(Base):
    __tablename__ = "charges_fin_associe"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audit_case: Mapped["AuditCase"] = relationship()

    nom: Mapped[str] = mapped_column(String(512), nullable=False)
    niu: Mapped[str | None] = mapped_column(String(32))
    pct_detention: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    is_resident: Mapped[bool] = mapped_column(Boolean, default=True)
    avance_moyenne_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    interet_servi_xaf: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    compte_gl: Mapped[str | None] = mapped_column(String(16))

    convention_enregistree: Mapped[bool] = mapped_column(Boolean, default=False)
    convention_filename: Mapped[str | None] = mapped_column(String(512))
    convention_storage_path: Mapped[str | None] = mapped_column(String(1024))

    verdict: Mapped[ChgFinVerdict] = mapped_column(
        Enum(ChgFinVerdict), nullable=False, default=ChgFinVerdict.A_REINSTRUIRE
    )
    verdict_reason: Mapped[str | None] = mapped_column(String(2048))
    verdict_source: Mapped[ChgFinVerdictSource] = mapped_column(
        Enum(ChgFinVerdictSource), nullable=False, default=ChgFinVerdictSource.AUTO
    )
    verdict_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
