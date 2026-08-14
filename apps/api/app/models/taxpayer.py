"""Contribuable (taxpayer)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, DateTime, Date, Enum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase


class TaxRegime(str, enum.Enum):
    REEL = "REEL"
    SIMPLIFIE = "SIMPLIFIE"
    LIBERATOIRE = "LIBERATOIRE"
    INCONNU = "INCONNU"


class Taxpayer(Base):
    __tablename__ = "taxpayers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    niu: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    raison_sociale: Mapped[str] = mapped_column(String(512), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)  # libellé libre (précision)
    # Secteur d'activité structuré — régimes fiscaux spécifiques (Tier A).
    # Pilote le branchement sectoriel des contrôles (provisions COBAC/CIMA,
    # redevances forestières/minières, IS pétrolier, etc.). String (non-enum)
    # pour ajouter les secteurs Tier B/C sans migration de type.
    #   DROIT_COMMUN | PETROLE_AMONT | MINES | FORET_BOIS | BANQUE | ASSURANCES
    sector_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DROIT_COMMUN", server_default="DROIT_COMMUN"
    )
    regime: Mapped[TaxRegime] = mapped_column(Enum(TaxRegime), nullable=False, default=TaxRegime.REEL)
    # Cached FCA status — refreshed via DGI integration
    fca_active: Mapped[bool | None] = mapped_column(default=None, nullable=True)

    # Identification fiscale (CGI Cameroun — informations nécessaires à l'audit)
    tax_center: Mapped[str | None] = mapped_column(String(128), nullable=True)
    legal_form: Mapped[str | None] = mapped_column(String(32), nullable=True)  # SARL, SA, SAS, EI, etc.
    capital_social: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    activity_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rccm: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Registre du Commerce
    contact_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    audit_cases: Mapped[list["AuditCase"]] = relationship(back_populates="taxpayer")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
