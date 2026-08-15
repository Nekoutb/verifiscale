"""Pydantic schemas — wire formats for API requests/responses."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Auth ---

class LoginRequest(BaseModel):
    # Accept either a real email or a short username (e.g. 'admin')
    email: str
    password: str
    # Optional prospection capture — saved on user profile if provided
    phone_number: str | None = None
    organization: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str  # plain str — allows username-style logins like 'admin'
    full_name: str
    role: str
    brigade_id: UUID | None = None
    is_active: bool
    phone_number: str | None = None
    organization: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    is_superadmin: bool = False
    organization_id: UUID | None = None
    must_change_password: bool = False



# --- Brigades ---

class BrigadeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    region: str | None = None


# --- Taxpayers ---

class TaxpayerCreate(BaseModel):
    niu: str = Field(..., min_length=10, max_length=32)
    raison_sociale: str
    address: str | None = None
    sector: str | None = None
    sector_code: str = "DROIT_COMMUN"
    regime: str = "REEL"
    # Identification fiscale étendue (CGI Cameroun)
    tax_center: str | None = None
    legal_form: str | None = None
    capital_social: Decimal | None = None
    activity_start_date: date | None = None
    rccm: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None


class TaxpayerOut(TaxpayerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    fca_active: bool | None = None


# --- Audit cases ---

class AuditCaseCreate(BaseModel):
    reference: str
    taxpayer_id: UUID
    brigade_id: UUID
    assignee_id: UUID | None = None
    fiscal_year: int
    period_start: date
    period_end: date
    risk_level: str = "MOYEN"


class AuditCaseQuickCreate(BaseModel):
    """One-shot case creation: upserts the taxpayer by NIU, picks the user's brigade,
    auto-generates a reference. Used by the dashboard 'Nouveau dossier' wizard.
    """
    # Taxpayer (upserted by NIU)
    niu: str = Field(..., min_length=10, max_length=32)
    raison_sociale: str
    address: str | None = None
    sector: str | None = None
    sector_code: str = "DROIT_COMMUN"
    regime: str = "REEL"
    # Extended taxpayer identification (CGI Cameroun)
    tax_center: str | None = None
    legal_form: str | None = None
    capital_social: Decimal | None = None
    activity_start_date: date | None = None
    rccm: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    # Audit scope
    audit_type: str = "VGC"
    starting_year: int
    number_of_years: int = 1
    risk_level: str = "MOYEN"
    reference: str | None = None  # auto-generated if omitted
    # LPF — optional, sets the timeline if provided
    avis_verification_date: date | None = None


class AuditCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    reference: str
    taxpayer: TaxpayerOut
    brigade_id: UUID
    assignee_id: UUID | None
    fiscal_year: int
    period_start: date
    period_end: date
    audit_type: str
    starting_year: int | None
    number_of_years: int | None
    status: str
    risk_level: str
    avis_verification_date: date | None
    debut_intervention_date: date | None
    fin_intervention_date: date | None
    notification_date: date | None
    reponse_contribuable_date: date | None
    created_at: datetime


# --- Datasets ---

class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    audit_case_id: UUID
    kind: str
    original_filename: str
    size_bytes: int
    status: str
    rows_count: int | None
    parse_error: str | None
    period_year: int | None = None
    bank_account_code: str | None = None
    summary_amount: Decimal | None = None
    # Auto-detection report — what columns the AI parser identified, used by
    # the /audit-data page to show a green check-list per uploaded file.
    column_mapping: dict | None = None
    # Control totals — file rows/cols vs read rows/cols (+ excluded/structural)
    # proving nothing was silently dropped at ingestion.
    control_totals: dict | None = None
    uploaded_at: datetime
    parsed_at: datetime | None


class DatasetPatch(BaseModel):
    """Manual updates to a dataset's metadata (notably summary_amount for reconciliations)."""
    summary_amount: Decimal | None = None
    period_year: int | None = None
    bank_account_code: str | None = None


# --- Trial balance ---

class TrialBalanceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    account_code: str
    account_name: str
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_debit: Decimal
    closing_credit: Decimal


# --- Control runs / findings ---

class ControlFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    control_code: str
    title: str
    description: str | None
    severity: str
    legal_reference: str | None
    evidence: dict | None
    estimated_impact_xaf: float | None
    created_at: datetime


class ControlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    audit_case_id: UUID
    category: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    summary: dict | None
    findings: list[ControlFindingOut]


# --- Monthly tax returns & payment proofs ---

class PaymentProofOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    monthly_return_id: UUID
    payment_date: date
    amount_paid: Decimal
    reference: str | None
    method: str
    bank: str | None
    notes: str | None
    created_at: datetime


class MonthlyReturnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    audit_case_id: UUID
    tax_type: str
    period_year: int
    period_month: int | None
    period_quarter: int | None
    filing_date: date | None
    filing_deadline: date
    declared_amount: Decimal
    base_amount: Decimal | None
    credit_reporte: Decimal | None
    status: str
    source_dataset_id: UUID | None
    notes: str | None
    created_at: datetime
    payment_proofs: list[PaymentProofOut] = []


class MonthlyReturnCreate(BaseModel):
    audit_case_id: UUID
    tax_type: str
    period_year: int
    period_month: int | None = None
    period_quarter: int | None = None
    filing_date: date | None = None
    declared_amount: Decimal
    base_amount: Decimal | None = None
    notes: str | None = None


class ParseReturnRequest(BaseModel):
    dataset_id: UUID
    tax_type_hint: str | None = None  # MUST match a TaxType enum value


TokenResponse.model_rebuild()
