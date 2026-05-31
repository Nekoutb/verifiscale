// Domain types — mirror app/api/app/schemas.py

export type Role = 'AUDITEUR' | 'SUPERVISEUR' | 'CHEF_BRIGADE' | 'ADMIN';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  brigade_id: string | null;
  is_active: boolean;
  phone_number: string | null;
  organization: string | null;
  last_login_at: string | null;
  created_at: string | null;
}

export interface Brigade {
  id: string;
  code: string;
  name: string;
  region: string | null;
}

export interface Taxpayer {
  id: string;
  niu: string;
  raison_sociale: string;
  address: string | null;
  sector: string | null;
  regime: 'REEL' | 'SIMPLIFIE' | 'LIBERATOIRE' | 'INCONNU';
  fca_active: boolean | null;
  tax_center?: string | null;
  legal_form?: string | null;
  capital_social?: number | null;
  activity_start_date?: string | null;
  rccm?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
}

export type AuditType = 'VGC' | 'VP' | 'CSP' | 'CI' | 'CT' | 'EF';

export const AUDIT_TYPE_LABELS: Record<AuditType, { short: string; full: string; ref: string }> = {
  VGC: { short: 'VGC',  full: 'Vérification Générale de Comptabilité',   ref: 'LPF art. L 8' },
  VP:  { short: 'VP',   full: 'Vérification Ponctuelle',                  ref: 'LPF art. L 9' },
  CSP: { short: 'CSP',  full: 'Contrôle Sur Pièces',                      ref: 'LPF art. L 10' },
  CI:  { short: 'CI',   full: 'Contrôle Inopiné',                         ref: 'LPF art. L 11' },
  CT:  { short: 'CT',   full: 'Contrôle Thématique',                      ref: '—' },
  EF:  { short: 'EF',   full: 'Enquête Fiscale',                          ref: 'LPF art. L 18' },
};

export interface AuditCase {
  id: string;
  reference: string;
  taxpayer: Taxpayer;
  brigade_id: string;
  assignee_id: string | null;
  fiscal_year: number;
  period_start: string;
  period_end: string;
  audit_type: AuditType;
  starting_year: number | null;
  number_of_years: number | null;
  status: 'PLANIFICATION' | 'EN_COURS' | 'CONTRADICTOIRE' | 'RAPPORT' | 'NOTIFIE' | 'CLOS';
  risk_level: 'FAIBLE' | 'MOYEN' | 'ELEVE';
  avis_verification_date: string | null;
  debut_intervention_date: string | null;
  fin_intervention_date: string | null;
  notification_date: string | null;
  reponse_contribuable_date: string | null;
  created_at: string;
}

export type DatasetKind =
  | 'TRIAL_BALANCE' | 'GENERAL_LEDGER' | 'FEC' | 'JOURNAL'
  | 'SUB_LEDGER_AP' | 'SUB_LEDGER_AR' | 'MONTHLY_RETURN'
  | 'ANNUAL_RETURN' | 'INVOICE' | 'CONTRACT' | 'PAYROLL'
  | 'PAYMENT_PROOF' | 'DIPE' | 'PATENTE_AVIS' | 'FONCIER_AVIS'
  | 'ACCOUNTS_PAYABLE_AGING' | 'ACCOUNTS_RECEIVABLE_AGING'
  | 'FIXED_ASSETS_REGISTER' | 'BANK_STATEMENT'
  | 'INVENTORY_LISTING';

export interface DatasetColumnMapping {
  source?: 'ai' | 'keyword';
  rationale?: string;
  detected?: Record<string, boolean>;
  column_indices?: Record<string, number | null>;
  header_row_index?: number;
  // Aging / inventory / bank parsers expose ad-hoc keys (auto_total_xaf, closing_balance_xaf …)
  [k: string]: unknown;
}

export interface Dataset {
  id: string;
  audit_case_id: string;
  kind: DatasetKind;
  original_filename: string;
  size_bytes: number;
  status: 'UPLOADED' | 'PARSING' | 'PARSED' | 'PARSE_ERROR';
  rows_count: number | null;
  parse_error: string | null;
  period_year: number | null;
  bank_account_code: string | null;
  summary_amount: number | null;
  column_mapping: DatasetColumnMapping | null;
  uploaded_at: string;
  parsed_at: string | null;
}

export interface ReconciliationSub {
  account_code: string;
  account_name: string;
  ref_amount: number;
  counter_amount: number | null;
  counter_dataset_id?: string | null;
  counter_filename?: string | null;
  diff: number | null;
  status: 'ALIGNED' | 'DISCREPANCY' | 'MISSING';
  // TB↔GL rollforward extras (only present on key === "TB_GL")
  opening_amount?: number;
  movement_amount?: number;
  expected_close?: number;
  actual_close?: number;
}

export interface ReconciliationRollforwardSummary {
  accounts_examined: number;
  accounts_in_variance: number;
  total_variance_abs: number;
  gl_loaded: boolean;
  gl_filename: string | null;
}

export interface AccountBreakdownRow {
  account_code: string;
  account_name: string;
  amount: number;
}

export interface RecItem {
  category: 'TIMING' | 'POSTING_ERROR' | 'OMISSION' | 'FX_GAIN_LOSS' | 'INTERCOMPANY_UNMATCHED' | 'OTHER';
  description: string;
  estimated_amount_xaf: number;
  likelihood: 'HIGH' | 'MEDIUM' | 'LOW';
  aging_bucket: 'ZERO_TO_30' | 'THIRTY_ONE_TO_60' | 'SIXTY_ONE_TO_90' | 'OVER_90' | 'UNKNOWN';
  action: string;
}

export interface RecItemsAnalysis {
  items: RecItem[];
  summary: string;
  escalation: boolean;
  materiality_xaf: number;
  source: 'claude' | 'mock' | 'no_key' | 'trivial' | 'parse_error' | 'api_error';
}

export interface ReconciliationResult {
  key: string;
  title: string;
  subtitle: string;
  ref_label: string;
  ref_amount: number;
  counter_label: string;
  counter_amount: number | null;
  counter_dataset_id?: string | null;
  counter_filename?: string | null;
  diff: number | null;
  status: 'ALIGNED' | 'DISCREPANCY' | 'MISSING';
  is_count?: boolean;
  sub_items?: ReconciliationSub[];
  rollforward_summary?: ReconciliationRollforwardSummary;
  account_breakdown?: AccountBreakdownRow[];
  rec_items?: RecItemsAnalysis;
}

export interface ReconciliationsResponse {
  tb_dataset_id: string | null;
  tb_filename: string | null;
  fiscal_year: number;
  tolerance_fcfa?: number;
  reconciliations: ReconciliationResult[];
  note?: string;
}

export interface BankAccount {
  account_code: string;
  account_name: string;
  closing_debit: number;
  closing_credit: number;
}

export interface BankAccountsResponse {
  bank_accounts: BankAccount[];
  source_dataset_id: string | null;
  source_filename?: string;
  note?: string;
}

export interface TrialBalanceLine {
  account_code: string;
  account_name: string;
  opening_debit: number;
  opening_credit: number;
  period_debit: number;
  period_credit: number;
  closing_debit: number;
  closing_credit: number;
}

export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'BLOCKING';

export interface ControlFinding {
  id: string;
  control_code: string;
  title: string;
  description: string | null;
  severity: Severity;
  legal_reference: string | null;
  evidence: Record<string, unknown> | null;
  estimated_impact_xaf: number | null;
  created_at: string;
}

export interface ControlRunSummary {
  findings_count: number;
  blocking: number;
  high: number;
  medium: number;
  low?: number;
  info?: number;
  estimated_total_impact_xaf: number;
}

export interface ControlRun {
  id: string;
  audit_case_id: string;
  category: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED';
  started_at: string;
  finished_at: string | null;
  summary: ControlRunSummary | null;
  findings: ControlFinding[];
}

export interface CatalogCategory {
  name: string;
  controls: { code: string; title: string }[];
}

export type CatalogResponse = Record<string, CatalogCategory>;

export const CATEGORY_LABELS: Record<string, { short: string; full: string; color: string }> = {
  SYSCOHADA_A:  { short: 'A · Intégrité',  full: 'SYSCOHADA — Intégrité comptable',    color: 'bg-black text-white' },
  SYSCOHADA_B:  { short: 'B · Évaluation', full: 'SYSCOHADA — Évaluation & SIG',       color: 'bg-neutral-700 text-white' },
  FISCAL_C:     { short: 'C · IS',         full: 'Fiscal — Impôt sur les Sociétés',    color: 'bg-white text-black border border-black' },
  FISCAL_D:     { short: 'D · TVA',        full: 'Fiscal — Taxe sur la Valeur Ajoutée', color: 'bg-neutral-200 text-black' },
  PROCEDURAL_H: { short: 'H · Procédure',  full: 'Procédure LPF — Délais & pénalités', color: 'bg-black text-white border-2 border-black' },
};

// ── Monthly returns ──────────────────────────────────────────────────────────
export type TaxType =
  | 'TVA' | 'IRPP_SALAIRES' | 'CNPS' | 'TSR' | 'PRECOMPTE_LOYERS' | 'PRECOMPTE_ACHATS'
  | 'IRCM' | 'DROIT_TIMBRE' | 'CFC' | 'FNE' | 'RAV'
  | 'ACOMPTE_IS' | 'IS_ANNUEL' | 'PATENTE' | 'FONCIER';

export type ReturnStatus = 'PENDING' | 'FILED' | 'PAID' | 'AMENDED' | 'LITIGATION';

export interface PaymentProof {
  id: string;
  monthly_return_id: string;
  payment_date: string;
  amount_paid: number;
  reference: string | null;
  method: string;
  bank: string | null;
  notes: string | null;
  created_at: string;
}

export interface MonthlyReturn {
  id: string;
  audit_case_id: string;
  tax_type: TaxType;
  period_year: number;
  period_month: number | null;
  period_quarter: number | null;
  filing_date: string | null;
  filing_deadline: string;
  declared_amount: number;
  base_amount: number | null;
  credit_reporte: number | null;
  status: ReturnStatus;
  source_dataset_id: string | null;
  notes: string | null;
  created_at: string;
  payment_proofs: PaymentProof[];
}

export const TAX_TYPE_LABELS: Record<TaxType, { short: string; full: string; periodicity: 'monthly' | 'quarterly' | 'annual' }> = {
  TVA:              { short: 'TVA',          full: 'Taxe sur la Valeur Ajoutée',                periodicity: 'monthly' },
  IRPP_SALAIRES:    { short: 'IRPP sal.',    full: 'IRPP retenue sur salaires',                 periodicity: 'monthly' },
  CNPS:             { short: 'CNPS',         full: 'Cotisations Caisse Nationale Prévoyance',   periodicity: 'monthly' },
  TSR:              { short: 'TSR',          full: 'Taxe Spéciale sur le Revenu (non-résidents)', periodicity: 'monthly' },
  PRECOMPTE_LOYERS: { short: 'Prc. loyers',  full: 'Précompte sur loyers',                       periodicity: 'monthly' },
  PRECOMPTE_ACHATS: { short: 'Prc. achats',  full: 'Précompte sur achats',                       periodicity: 'monthly' },
  IRCM:             { short: 'IRCM',         full: 'Revenus de capitaux mobiliers',              periodicity: 'monthly' },
  DROIT_TIMBRE:     { short: 'Timbre',       full: 'Droit de timbre',                            periodicity: 'monthly' },
  CFC:              { short: 'CFC',          full: 'Crédit Foncier 1%',                          periodicity: 'monthly' },
  FNE:              { short: 'FNE',          full: 'Fonds National Emploi 1%',                   periodicity: 'monthly' },
  RAV:              { short: 'RAV',          full: 'Redevance audiovisuelle',                    periodicity: 'monthly' },
  ACOMPTE_IS:       { short: 'Acompte IS',   full: 'Acompte trimestriel IS',                     periodicity: 'quarterly' },
  IS_ANNUEL:        { short: 'IS annuel',    full: 'Impôt sur les Sociétés (annuel)',            periodicity: 'annual' },
  PATENTE:          { short: 'Patente',      full: 'Patente (annuelle)',                         periodicity: 'annual' },
  FONCIER:          { short: 'Foncier',      full: 'Taxe foncière',                              periodicity: 'annual' },
};
