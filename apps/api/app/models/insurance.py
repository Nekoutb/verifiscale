"""Primes d'assurance — contrats + registre assureurs (CGI Art. 7 A 4)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    String, DateTime, Date, ForeignKey, Numeric, Boolean, Enum, BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase
    from app.models.dataset import Dataset
    from app.models.user import User


class InsuranceBenefType(str, enum.Enum):
    ENTREPRISE = "ENTREPRISE"
    DIRIGEANT = "DIRIGEANT"
    FAMILLE_DIRIGEANT = "FAMILLE_DIRIGEANT"
    PERSONNEL = "PERSONNEL"
    MIXTE = "MIXTE"
    INCONNU = "INCONNU"


class InsuranceType(str, enum.Enum):
    MULTIRISQUE = "MULTIRISQUE"
    MATERIEL_TRANSPORT = "MATERIEL_TRANSPORT"
    RISQUES_EXPLOITATION = "RISQUES_EXPLOITATION"
    RESP_PRODUCTEUR = "RESP_PRODUCTEUR"
    INSOLVABILITE_CLIENT = "INSOLVABILITE_CLIENT"
    TRANSPORT_VENTES = "TRANSPORT_VENTES"
    SANTE_PERSONNEL = "SANTE_PERSONNEL"
    RETRAITE_FIN_CARRIERE = "RETRAITE_FIN_CARRIERE"
    VIE_HOMME_CLE = "VIE_HOMME_CLE"
    VIE_DIRIGEANT = "VIE_DIRIGEANT"
    RC = "RC"
    AUTRE = "AUTRE"


class InsuranceVerdict(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    NON_ELIGIBLE = "NON_ELIGIBLE"
    A_REINSTRUIRE = "A_REINSTRUIRE"


class InsuranceVerdictSource(str, enum.Enum):
    AUTO_CONTRACT = "AUTO_CONTRACT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class InsurerStatut(str, enum.Enum):
    AGREE = "AGREE"
    EXPIRE = "EXPIRE"
    REFUSE = "REFUSE"
    INCONNU = "INCONNU"


class RegistreAssureurAgree(Base):
    """Master data of locally-approved insurance companies (ASAC list)."""

    __tablename__ = "registre_assureurs_agrees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nom: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    niu: Mapped[str | None] = mapped_column(String(32), unique=True)
    pays: Mapped[str] = mapped_column(String(8), nullable=False, default="CM")
    agrement_asac: Mapped[str | None] = mapped_column(String(128))
    statut: Mapped[InsurerStatut] = mapped_column(
        Enum(InsurerStatut), nullable=False, default=InsurerStatut.INCONNU
    )
    notes: Mapped[str | None] = mapped_column(String(2048))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContratAssurance(Base):
    """Single insurance policy uploaded by the auditor — extracted via Claude Vision."""

    __tablename__ = "contrats_assurance"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audit_case: Mapped["AuditCase"] = relationship()

    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"),
    )
    dataset: Mapped["Dataset | None"] = relationship()

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    # Contract fields (extracted by Claude)
    numero_police: Mapped[str | None] = mapped_column(String(128), index=True)
    assureur_nom: Mapped[str | None] = mapped_column(String(512), index=True)
    assureur_niu: Mapped[str | None] = mapped_column(String(32))
    assureur_pays: Mapped[str] = mapped_column(String(8), default="CM")
    assureur_local: Mapped[bool] = mapped_column(Boolean, default=False)
    assureur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registre_assureurs_agrees.id", ondelete="SET NULL"),
    )
    assureur: Mapped["RegistreAssureurAgree | None"] = relationship()

    souscripteur: Mapped[str | None] = mapped_column(String(512))
    beneficiaire_nom: Mapped[str | None] = mapped_column(String(512))
    beneficiaire_type: Mapped[InsuranceBenefType] = mapped_column(
        Enum(InsuranceBenefType), nullable=False, default=InsuranceBenefType.INCONNU
    )
    type_assurance: Mapped[InsuranceType] = mapped_column(
        Enum(InsuranceType), nullable=False, default=InsuranceType.AUTRE
    )

    date_debut: Mapped[date | None] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date)
    prime_annuelle_ttc: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    prime_exercice: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    compte_syscohada: Mapped[str | None] = mapped_column(String(8))

    # Verdict
    verdict: Mapped[InsuranceVerdict] = mapped_column(
        Enum(InsuranceVerdict), nullable=False, default=InsuranceVerdict.A_REINSTRUIRE
    )
    verdict_reason: Mapped[str | None] = mapped_column(String(2048))
    verdict_source: Mapped[InsuranceVerdictSource] = mapped_column(
        Enum(InsuranceVerdictSource), nullable=False, default=InsuranceVerdictSource.AUTO_CONTRACT
    )
    verdict_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    extracted: Mapped[dict | None] = mapped_column(JSONB)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
