"""AuditCase = one tax audit engagement on a specific taxpayer for a specific period."""
import enum
import uuid
from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Enum, Date, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.brigade import Brigade
    from app.models.user import User
    from app.models.taxpayer import Taxpayer
    from app.models.dataset import Dataset
    from app.models.control_run import ControlRun


class AuditStatus(str, enum.Enum):
    PLANIFICATION = "PLANIFICATION"
    EN_COURS = "EN_COURS"
    CONTRADICTOIRE = "CONTRADICTOIRE"
    RAPPORT = "RAPPORT"
    NOTIFIE = "NOTIFIE"
    CLOS = "CLOS"


class RiskLevel(str, enum.Enum):
    FAIBLE = "FAIBLE"
    MOYEN = "MOYEN"
    ELEVE = "ELEVE"


class AuditType(str, enum.Enum):
    """Types of fiscal control per LPF Cameroun (Livre des Procédures Fiscales)."""
    VGC = "VGC"   # Vérification Générale de Comptabilité — full multi-year audit (LPF L 8)
    VP  = "VP"    # Vérification Ponctuelle — single tax / specific period (LPF L 9)
    CSP = "CSP"   # Contrôle Sur Pièces — desk audit (LPF L 10)
    CI  = "CI"    # Contrôle Inopiné — unannounced spot check (LPF L 11)
    CT  = "CT"    # Contrôle Thématique — themed cross-cutting audit
    EF  = "EF"    # Enquête Fiscale — investigation (LPF L 18)


class AuditCase(Base):
    __tablename__ = "audit_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    taxpayer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taxpayers.id", ondelete="RESTRICT"), nullable=False
    )
    taxpayer: Mapped["Taxpayer"] = relationship(back_populates="audit_cases")

    brigade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brigades.id", ondelete="RESTRICT"), nullable=False
    )
    brigade: Mapped["Brigade"] = relationship(back_populates="audit_cases")

    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignee: Mapped["User | None"] = relationship(
        back_populates="audit_cases", foreign_keys=[assignee_id]
    )

    # Exercice fiscal contrôlé (legacy single-year; superseded by starting_year + number_of_years)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Multi-year audit scope (LPF prescription 4 ans → up to 10 years for thematic / fraud)
    audit_type: Mapped[AuditType] = mapped_column(
        Enum(AuditType), nullable=False, default=AuditType.VGC,
    )
    starting_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_years: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)

    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus), nullable=False, default=AuditStatus.PLANIFICATION
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel), nullable=False, default=RiskLevel.MOYEN
    )

    # LPF — délais procéduraux (art. L 13, L 24, L 26)
    avis_verification_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    debut_intervention_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fin_intervention_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notification_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reponse_contribuable_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="audit_case", cascade="all, delete-orphan"
    )
    control_runs: Mapped[list["ControlRun"]] = relationship(
        back_populates="audit_case", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
