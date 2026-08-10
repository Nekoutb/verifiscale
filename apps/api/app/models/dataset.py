"""Dataset = a file uploaded by the auditor (TB, GL, FEC, monthly returns, invoices, etc.)."""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from decimal import Decimal

from sqlalchemy import String, DateTime, ForeignKey, Enum, Integer, BigInteger, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audit_case import AuditCase


class DatasetKind(str, enum.Enum):
    TRIAL_BALANCE = "TRIAL_BALANCE"      # Balance 6 colonnes
    GENERAL_LEDGER = "GENERAL_LEDGER"    # Grand livre
    FEC = "FEC"                          # Fichier Écritures Comptables
    JOURNAL = "JOURNAL"                  # Journaux comptables
    SUB_LEDGER_AP = "SUB_LEDGER_AP"      # Auxiliaire fournisseurs
    SUB_LEDGER_AR = "SUB_LEDGER_AR"      # Auxiliaire clients
    MONTHLY_RETURN = "MONTHLY_RETURN"    # Déclaration mensuelle (TVA, IRPP, …)
    ANNUAL_RETURN = "ANNUAL_RETURN"      # DSF
    INVOICE = "INVOICE"                  # Facture fournisseur
    CONTRACT = "CONTRACT"                # Contrat
    PAYROLL = "PAYROLL"                  # Bulletins / livre de paie
    # Newer kinds — Sprint 2 (PDF parsing)
    PAYMENT_PROOF = "PAYMENT_PROOF"      # Quittance / preuve de paiement (PDF/image)
    DIPE = "DIPE"                        # Déclaration Individuelle des Personnels et Émoluments (annuel)
    PATENTE_AVIS = "PATENTE_AVIS"        # Avis d'imposition Patente
    FONCIER_AVIS = "FONCIER_AVIS"        # Avis taxe foncière
    # Multi-year structured uploads — added with the Audit Data page
    ACCOUNTS_PAYABLE_AGING = "ACCOUNTS_PAYABLE_AGING"      # Balance âgée fournisseurs
    ACCOUNTS_RECEIVABLE_AGING = "ACCOUNTS_RECEIVABLE_AGING"  # Balance âgée clients
    FIXED_ASSETS_REGISTER = "FIXED_ASSETS_REGISTER"        # Registre / tableau d'immobilisations
    BANK_STATEMENT = "BANK_STATEMENT"                      # Relevé bancaire (1 par compte 52x par exercice)
    INVENTORY_LISTING = "INVENTORY_LISTING"                # État d'inventaire physique (cl. 3X)
    # LPF — Procédural milestone documents (PDF / scan)
    AVIS_VERIFICATION = "AVIS_VERIFICATION"                # Avis de vérification (LPF art. L 8)
    NOTIFICATION_REDRESSEMENT = "NOTIFICATION_REDRESSEMENT"  # Notification de redressement
    REPONSE_CONTRIBUABLE = "REPONSE_CONTRIBUABLE"          # Réponse du contribuable
    DEBUT_INTERVENTION_PV = "DEBUT_INTERVENTION_PV"        # PV de début d'intervention
    FIN_INTERVENTION_PV = "FIN_INTERVENTION_PV"            # PV de fin d'intervention


class DatasetStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    # Ingest-v2: the file is stored and a mapping has been proposed, but NOTHING
    # has been ingested yet — the auditor must confirm (or correct) the column
    # mapping first. Nothing enters the ledger tables until they approve.
    PENDING_MAPPING = "PENDING_MAPPING"
    PARSING = "PARSING"
    PARSED = "PARSED"
    PARSE_ERROR = "PARSE_ERROR"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audit_case: Mapped["AuditCase"] = relationship(back_populates="datasets")

    kind: Mapped[DatasetKind] = mapped_column(Enum(DatasetKind), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)  # MinIO object key
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # SHA-256
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[DatasetStatus] = mapped_column(
        Enum(DatasetStatus), nullable=False, default=DatasetStatus.UPLOADED
    )
    rows_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Control totals — proves nothing was silently dropped at ingestion.
    # {"file_rows": N, "file_cols": M, "read_rows": I, "read_cols": K,
    #  "excluded_rows": E, "structural_rows": S, "complete": bool}
    # file_* = raw non-empty grid dims; read_* = what the tool ingested;
    # excluded = rows dropped WITH a disclosed reason; structural = context
    # rows (banners, account-header lines in grouped GL layouts).
    control_totals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    column_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Multi-year scoping: which fiscal year does this dataset cover?
    period_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # For BANK_STATEMENT only — the SYSCOHADA account code (e.g. "521000") this statement covers.
    bank_account_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Summary total — used by reconciliations (AP/AR/inventory/bank statement total).
    # Either auto-extracted on parse or manually entered by the auditor.
    summary_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
