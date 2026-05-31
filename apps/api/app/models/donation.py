"""Dons & libéralités — evidence + beneficiary master data (CGI Art. 7)."""
import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    String, DateTime, Date, ForeignKey, Enum, Integer, BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase
    from app.models.journal_entry import JournalEntryLine
    from app.models.user import User


class DonationDocKind(str, enum.Enum):
    RECU = "RECU"               # reçu de l'organisme bénéficiaire
    CONVENTION = "CONVENTION"   # convention de don
    STATUTS = "STATUTS"         # statuts de l'organisme
    AGREMENT = "AGREMENT"       # décret/arrêté d'utilité publique
    VIREMENT = "VIREMENT"       # preuve de versement bancaire
    AUTRE = "AUTRE"


class DonationVerdict(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"             # entre dans le plafond 5‰ CA HT
    NON_ELIGIBLE = "NON_ELIGIBLE"     # réintégration intégrale
    A_REINSTRUIRE = "A_REINSTRUIRE"   # documents manquants / contradictoires


class DonationVerdictSource(str, enum.Enum):
    AUTO_GL = "AUTO_GL"                   # verdict inferred from GL only
    DOC_EXTRACTED = "DOC_EXTRACTED"       # verdict from uploaded document(s)
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"   # auditor override


class OrgNature(str, enum.Enum):
    PHILANTHROPIQUE = "PHILANTHROPIQUE"
    EDUCATIF = "EDUCATIF"
    SPORTIF = "SPORTIF"
    SCIENTIFIQUE = "SCIENTIFIQUE"
    SOCIAL = "SOCIAL"
    CULTUREL = "CULTUREL"
    FAMILIAL = "FAMILIAL"
    RECHERCHE = "RECHERCHE"
    AUTRE = "AUTRE"


class OrgStatut(str, enum.Enum):
    AGREE = "AGREE"
    EN_INSTRUCTION = "EN_INSTRUCTION"
    REFUSE = "REFUSE"
    EXPIRE = "EXPIRE"
    INCONNU = "INCONNU"


class RegistreOrganismeAgree(Base):
    """Master data for approved beneficiary organisations — shared across cases."""

    __tablename__ = "registre_organismes_agrees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nom: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    niu: Mapped[str | None] = mapped_column(String(32), unique=True)
    pays: Mapped[str] = mapped_column(String(8), nullable=False, default="CM")
    adresse: Mapped[str | None] = mapped_column(String(1024))
    nature: Mapped[OrgNature] = mapped_column(
        Enum(OrgNature), nullable=False, default=OrgNature.AUTRE
    )
    agrement_num: Mapped[str | None] = mapped_column(String(128))
    agrement_date: Mapped[date | None] = mapped_column(Date)
    agrement_autorite: Mapped[str | None] = mapped_column(String(256))
    statut: Mapped[OrgStatut] = mapped_column(
        Enum(OrgStatut), nullable=False, default=OrgStatut.INCONNU
    )
    notes: Mapped[str | None] = mapped_column(String(2048))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DonationEvidence(Base):
    """One uploaded justificatif attached to a GL line of category 658X/6713/838X."""

    __tablename__ = "donation_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audit_case: Mapped["AuditCase"] = relationship()

    gl_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry_lines.id", ondelete="SET NULL"),
    )
    gl_line: Mapped["JournalEntryLine | None"] = relationship()

    # Business key — survives GL re-imports (line UUIDs change but piece+line stable)
    piece_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    slip_id: Mapped[str | None] = mapped_column(String(64), index=True)

    doc_kind: Mapped[DonationDocKind] = mapped_column(
        Enum(DonationDocKind), nullable=False, default=DonationDocKind.AUTRE
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    extracted: Mapped[dict | None] = mapped_column(JSONB)

    organisme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registre_organismes_agrees.id", ondelete="SET NULL"),
    )
    organisme: Mapped["RegistreOrganismeAgree | None"] = relationship()

    verdict: Mapped[DonationVerdict] = mapped_column(
        Enum(DonationVerdict), nullable=False, default=DonationVerdict.A_REINSTRUIRE
    )
    verdict_reason: Mapped[str | None] = mapped_column(String(2048))
    verdict_source: Mapped[DonationVerdictSource] = mapped_column(
        Enum(DonationVerdictSource), nullable=False, default=DonationVerdictSource.AUTO_GL
    )
    verdict_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Lien optionnel vers un groupe (preuve commune à plusieurs lignes)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("donation_group.id", ondelete="SET NULL")
    )


class AiConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DonationLibelleAnalysis(Base):
    """Cache de l'analyse Claude sur le libellé GL d'une ligne de don."""

    __tablename__ = "donation_libelle_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    piece_number: Mapped[str] = mapped_column(String(64), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    libelle_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict_ai: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[AiConfidence] = mapped_column(
        Enum(AiConfidence), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(4096))
    indicators: Mapped[dict | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DonationGroup(Base):
    """Regroupement de lignes GL par nature — porteur de pièces partagées."""

    __tablename__ = "donation_group"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2048))
    group_verdict: Mapped[str | None] = mapped_column(String(32))
    group_verdict_reason: Mapped[str | None] = mapped_column(String(4096))
    group_verdict_source: Mapped[str] = mapped_column(String(32), default="A_REINSTRUIRE")
    ai_confidence: Mapped[AiConfidence | None] = mapped_column(Enum(AiConfidence))
    ai_indicators: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DonationGroupLine(Base):
    """Association group ↔ ligne GL (piece + line_number)."""

    __tablename__ = "donation_group_line"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("donation_group.id", ondelete="CASCADE"),
        primary_key=True,
    )
    piece_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
