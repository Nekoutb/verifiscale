"""Petit matériel et outillage — overrides par ligne (seuil 500K CGI)."""
import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Boolean, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase


class PetitMatQualif(str, enum.Enum):
    HAND_TOOL = "HAND_TOOL"      # outillage à main → 100 %
    IT = "IT"                    # informatique → 25 %
    REPRO = "REPRO"              # reprographie → 33,33 %
    FURNITURE = "FURNITURE"      # mobilier → 10 %
    EQUIPMENT = "EQUIPMENT"      # matériel/machine → 20 %
    OTHER = "OTHER"              # autre → 20 % par défaut
    EXCLUDED = "EXCLUDED"        # exclu du contrôle (consommable réel, etc.)


class PetitMatBasis(str, enum.Enum):
    DIFFERENTIAL = "DIFFERENTIAL"   # réintégration = coût − amort. 1ère année
    TOTAL = "TOTAL"                 # réintégration = coût total
    THIRD = "THIRD"                 # 1/3 déductible, 2/3 réintégré → réint. = 2/3 × coût


class PetitMaterielLine(Base):
    __tablename__ = "petit_materiel_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audit_case: Mapped["AuditCase"] = relationship()

    piece_number: Mapped[str] = mapped_column(String(64), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    qualification: Mapped[PetitMatQualif | None] = mapped_column(Enum(PetitMatQualif))
    depreciation_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    reintegration_basis: Mapped[PetitMatBasis] = mapped_column(
        Enum(PetitMatBasis), default=PetitMatBasis.DIFFERENTIAL
    )
    verdict_reason: Mapped[str | None] = mapped_column(String(2048))
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
