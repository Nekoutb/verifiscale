"""SQLAlchemy ORM models for FiscAudit Pro."""
from app.models.user import User, UserRole
from app.models.brigade import Brigade
from app.models.audit_case import AuditCase, AuditStatus, AuditType, RiskLevel
from app.models.taxpayer import Taxpayer, TaxRegime
from app.models.dataset import Dataset, DatasetKind, DatasetStatus
from app.models.trial_balance import TrialBalanceLine
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.control_run import ControlRun, ControlFinding, ControlSeverity, ControlStatus
from app.models.audit_log import AuditLog
from app.models.tax_return import (
    MonthlyReturn, PaymentProof, TaxType, ReturnStatus, PaymentMethod,
)
from app.models.invoice import Invoice, InvoiceStatus
from app.models.donation import (
    RegistreOrganismeAgree,
    DonationEvidence,
    DonationDocKind,
    DonationVerdict,
    DonationVerdictSource,
    OrgNature,
    OrgStatut,
    DonationLibelleAnalysis,
    DonationGroup,
    DonationGroupLine,
    AiConfidence,
)
from app.models.insurance import (
    RegistreAssureurAgree,
    ContratAssurance,
    InsuranceBenefType,
    InsuranceType,
    InsuranceVerdict,
    InsuranceVerdictSource,
    InsurerStatut,
)
from app.models.charges_fin import (
    BeacRateCache,
    ChargesFinCaseParams,
    ChargesFinAssocie,
    ChgFinVerdict,
    ChgFinVerdictSource,
)
from app.models.petit_materiel import (
    PetitMaterielLine,
    PetitMatQualif,
    PetitMatBasis,
)
from app.models.cash_assessment import (
    CashPaymentAssessment,
    CashCurrentYear,
    CashDecisionSrc,
    CashExclusionKind,
)

__all__ = [
    "User", "UserRole",
    "Brigade",
    "AuditCase", "AuditStatus", "AuditType", "RiskLevel",
    "Taxpayer", "TaxRegime",
    "Dataset", "DatasetKind", "DatasetStatus",
    "TrialBalanceLine",
    "JournalEntry", "JournalEntryLine",
    "ControlRun", "ControlFinding", "ControlSeverity", "ControlStatus",
    "AuditLog",
    "MonthlyReturn", "PaymentProof", "TaxType", "ReturnStatus", "PaymentMethod",
    "Invoice", "InvoiceStatus",
    "RegistreOrganismeAgree", "DonationEvidence",
    "DonationDocKind", "DonationVerdict", "DonationVerdictSource",
    "OrgNature", "OrgStatut",
    "DonationLibelleAnalysis", "DonationGroup", "DonationGroupLine", "AiConfidence",
    "RegistreAssureurAgree", "ContratAssurance",
    "InsuranceBenefType", "InsuranceType", "InsuranceVerdict",
    "InsuranceVerdictSource", "InsurerStatut",
    "BeacRateCache", "ChargesFinCaseParams", "ChargesFinAssocie",
    "ChgFinVerdict", "ChgFinVerdictSource",
    "PetitMaterielLine", "PetitMatQualif", "PetitMatBasis",
    "CashPaymentAssessment", "CashCurrentYear", "CashDecisionSrc", "CashExclusionKind",
]
