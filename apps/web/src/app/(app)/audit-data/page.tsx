'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Scale, BookOpen, FileDown, Building2, Banknote, FileText, Receipt, Users,
  AlertCircle, CheckCircle2, Loader2, Upload, Boxes, ScanLine,
} from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MappingConfirmModal } from '@/components/mapping-confirm-modal';
import { api, apiUploadForm } from '@/lib/api';
import { useApp, caseYearRange } from '@/lib/store';
import { useT, type MessageKey } from '@/lib/i18n';
import { cn, formatDate, formatXAF } from '@/lib/utils';
import {
  type Dataset, type DatasetKind, type BankAccountsResponse,
} from '@/lib/types';

interface DocSection {
  kind: DatasetKind;
  titleKey: MessageKey;
  hintKey: MessageKey;
  Icon: React.ComponentType<{ className?: string }>;
  perBankAccount?: boolean;
}

const SECTIONS: DocSection[] = [
  { kind: 'TRIAL_BALANCE',             titleKey: 'data.trialBalance',     hintKey: 'data.trialBalanceHint',     Icon: Scale },
  { kind: 'GENERAL_LEDGER',            titleKey: 'data.generalLedger',    hintKey: 'data.generalLedgerHint',    Icon: BookOpen },
  { kind: 'ACCOUNTS_PAYABLE_AGING',    titleKey: 'data.apAging',          hintKey: 'data.apAgingHint',          Icon: FileDown },
  { kind: 'ACCOUNTS_RECEIVABLE_AGING', titleKey: 'data.arAging',          hintKey: 'data.arAgingHint',          Icon: FileDown },
  { kind: 'FIXED_ASSETS_REGISTER',     titleKey: 'data.fixedAssets',      hintKey: 'data.fixedAssetsHint',      Icon: Building2 },
  { kind: 'INVENTORY_LISTING',         titleKey: 'data.inventory',        hintKey: 'data.inventoryHint',        Icon: Boxes },
  { kind: 'BANK_STATEMENT',            titleKey: 'data.bankStatements',   hintKey: 'data.bankStatementsHint',   Icon: Banknote, perBankAccount: true },
  { kind: 'FINANCIAL_STATEMENTS',      titleKey: 'data.financialStatements', hintKey: 'data.financialStatementsHint', Icon: FileText },
  { kind: 'MONTHLY_RETURN',            titleKey: 'data.monthlyReturns',   hintKey: 'data.monthlyReturnsHint',   Icon: Receipt },
  { kind: 'DIPE',                      titleKey: 'data.dipe',             hintKey: 'data.dipeHint',             Icon: Users },
];


export default function AuditDataPage() {
  const { currentCase } = useApp();
  const qc = useQueryClient();
  const t = useT();
  const years = useMemo(() => caseYearRange(currentCase), [currentCase]);
  // One-screen layout: all boxes visible at once; clicking one opens its
  // upload area below (per the auditor: no scrolling to find a data type).
  const [activeKind, setActiveKind] = useState<DatasetKind>('TRIAL_BALANCE');

  const { data: datasets = [] } = useQuery({
    queryKey: ['datasets', currentCase?.id],
    queryFn: () => api<Dataset[]>(`/datasets/audit-case/${currentCase!.id}`),
    enabled: !!currentCase,
    refetchInterval: 5000,
  });

  const { data: banks } = useQuery({
    queryKey: ['bank-accounts', currentCase?.id],
    queryFn: () => api<BankAccountsResponse>(`/audit-cases/${currentCase!.id}/bank-accounts`),
    enabled: !!currentCase,
    refetchInterval: 10000,
  });

  const upload = useMutation({
    mutationFn: async ({ file, kind, periodYear, bankCode }: {
      file: File; kind: DatasetKind; periodYear?: number; bankCode?: string;
    }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('audit_case_id', currentCase!.id);
      fd.append('kind', kind);
      if (periodYear != null) fd.append('period_year', String(periodYear));
      if (bankCode) fd.append('bank_account_code', bankCode);
      return apiUploadForm<Dataset>('/datasets', fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['datasets', currentCase?.id] });
      qc.invalidateQueries({ queryKey: ['bank-accounts', currentCase?.id] });
    },
  });

  if (!currentCase) {
    return (
      <Card>
        <CardContent>
          <div className="text-center py-12 text-slate-500">
            <Building2 className="w-12 h-12 mx-auto text-slate-300 mb-3" />
            <div className="text-lg font-semibold text-slate-700 mb-2">{t('data.noCaseTitle')}</div>
            <div className="text-sm">{t('data.noCaseBody')}</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Helper: find a dataset for (kind, year, optional bankCode)
  const findDs = (kind: DatasetKind, year: number, bankCode?: string) =>
    datasets.find((d) =>
      d.kind === kind
      && d.period_year === year
      && (bankCode ? d.bank_account_code === bankCode : true),
    );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Upload className="w-6 h-6 text-black" />
          {t('data.pageTitle')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          <strong>{currentCase.taxpayer?.raison_sociale ?? '—'}</strong> —
          <span className="font-mono ml-1">{currentCase.taxpayer?.niu ?? '—'}</span> ·
          <span className="ml-1">{currentCase.audit_type}</span> ·
          <span className="ml-1">{years.length} {t('data.exercises')} : {years.join(', ')}</span>
        </p>
      </div>

      {/* Upload failures used to be silent (no onError on the mutation): a
          rejected POST showed nothing and the user was left guessing. Surface
          the server's reason verbatim — it is now a clear, actionable message. */}
      {upload.isError && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />
          <div className="text-sm text-rose-800">
            <span className="font-semibold">Échec du téléversement.</span>{' '}
            {(upload.error as Error)?.message || 'Erreur inconnue.'}
          </div>
        </div>
      )}

      {/* ── One-screen selector: every data type as a compact box ────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {SECTIONS.map((sec) => {
          const Icon = sec.Icon;
          const active = activeKind === sec.kind;
          const kindDs = datasets.filter((d) => d.kind === sec.kind);
          return (
            <button
              key={sec.kind}
              type="button"
              onClick={() => setActiveKind(sec.kind)}
              className={cn(
                'rounded-lg border p-2.5 text-left transition',
                active
                  ? 'border-black bg-neutral-50 shadow-sm ring-1 ring-black'
                  : 'border-slate-200 bg-white hover:border-slate-400',
              )}
            >
              <div className="flex items-center gap-1.5">
                <Icon className="w-4 h-4 text-black flex-shrink-0" />
                <span className="text-[11px] font-semibold text-slate-800 leading-tight truncate">
                  {sec.kind === 'MONTHLY_RETURN' ? 'DMM' : t(sec.titleKey)}
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-1 flex-wrap">
                {!sec.perBankAccount && sec.kind !== 'MONTHLY_RETURN' && years.map((y) => {
                  const ds = findDs(sec.kind, y);
                  return (
                    <span
                      key={y}
                      title={`${y} — ${ds ? ds.status : 'aucun fichier'}`}
                      className={cn(
                        'inline-block w-2.5 h-2.5 rounded-full border',
                        !ds ? 'bg-white border-slate-300'
                        : ds.status === 'PARSED' ? 'bg-emerald-500 border-emerald-600'
                        : ds.status === 'PENDING_MAPPING' ? 'bg-indigo-500 border-indigo-600'
                        : ds.status === 'PARSE_ERROR' ? 'bg-rose-500 border-rose-600'
                        : 'bg-amber-400 border-amber-500',
                      )}
                    />
                  );
                })}
                <span className="text-[10px] text-slate-500 ml-auto font-mono">
                  {kindDs.length > 0 ? `${kindDs.length} fichier${kindDs.length > 1 ? 's' : ''}` : '—'}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* ── Active section: upload area for the selected box ─────────────── */}
      {SECTIONS.filter((sec) => sec.kind === activeKind).map((sec) => {
        const Icon = sec.Icon;

        // Special case: bank statements — one row per detected bank account × per year
        if (sec.perBankAccount) {
          return (
            <Card key={sec.kind}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="w-5 h-5 text-black" />
                  {t(sec.titleKey)}
                </CardTitle>
                <div className="text-xs text-slate-500 mt-1">{t(sec.hintKey)}</div>
              </CardHeader>
              <CardContent>
                {banks?.bank_accounts.length === 0 ? (
                  <div className="text-sm text-slate-500 bg-neutral-100 border border-neutral-300 rounded-lg p-3 flex gap-3">
                    <AlertCircle className="w-5 h-5 text-neutral-700 flex-shrink-0" />
                    <div>
                      <div className="font-medium text-black">{t('data.noBankDetected')}</div>
                      <div className="text-xs text-neutral-700 mt-0.5">
                        {banks?.note ?? t('data.noBankDetectedBody')}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="text-xs text-slate-500">
                      {banks?.bank_accounts.length} {t('data.banksDetectedFrom')}
                      <span className="ml-2 text-slate-400">({t('data.source')} : {banks?.source_filename})</span>
                    </div>
                    {banks?.bank_accounts.map((acct) => (
                      <div key={acct.account_code} className="border border-slate-200 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-2">
                          <div>
                            <div className="font-mono text-sm font-semibold text-black">{acct.account_code}</div>
                            <div className="text-xs text-slate-500">{acct.account_name}</div>
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono">
                            {t('data.balance')} D : {acct.closing_debit.toLocaleString('fr-FR')} ·
                            {t('data.balance')} C : {acct.closing_credit.toLocaleString('fr-FR')}
                          </div>
                        </div>
                        <YearGrid
                          years={years}
                          kind={sec.kind}
                          bankCode={acct.account_code}
                          findDs={findDs}
                          onUpload={(f, y) => upload.mutate({ file: f, kind: sec.kind, periodYear: y, bankCode: acct.account_code })}
                          uploading={upload.isPending}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        }

        // Special case: monthly returns — bulk DMM upload + grid viewer
        if (sec.kind === 'MONTHLY_RETURN') {
          return (
            <Card key={sec.kind}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="w-5 h-5 text-black" />
                  Déclarations mensuelles (DMM)
                </CardTitle>
                <div className="text-xs text-slate-500 mt-1">
                  Chargez vos DMM PDF en lot — l'application extrait automatiquement le mois,
                  l'exercice et chaque ligne d'impôt (Acompte IS L50, TVA L36, IRPP L76, IRCM L62,
                  précomptes…) puis les répartit dans le tableau mensuel.
                </div>
              </CardHeader>
              <CardContent>
                <DmmBulkSection caseId={currentCase.id} years={years} />
              </CardContent>
            </Card>
          );
        }

        // Standard: one upload slot per year
        return (
          <Card key={sec.kind}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Icon className="w-5 h-5 text-black" />
                {t(sec.titleKey)}
              </CardTitle>
              <div className="text-xs text-slate-500 mt-1">{t(sec.hintKey)}</div>
            </CardHeader>
            <CardContent>
              <YearGrid
                years={years}
                kind={sec.kind}
                findDs={findDs}
                onUpload={(f, y) => upload.mutate({ file: f, kind: sec.kind, periodYear: y })}
                uploading={upload.isPending}
              />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}


function YearGrid({
  years, kind, bankCode, findDs, onUpload, uploading,
}: {
  years: number[];
  kind: DatasetKind;
  bankCode?: string;
  findDs: (kind: DatasetKind, year: number, bankCode?: string) => Dataset | undefined;
  onUpload: (file: File, year: number) => void;
  uploading: boolean;
}) {
  const t = useT();
  // Ingest-v2 — the GL/TB awaiting the auditor's mapping confirmation.
  const [mapDs, setMapDs] = useState<Dataset | null>(null);
  if (years.length === 0) {
    return <div className="text-xs text-slate-400 italic">{t('data.setPeriodToActivate')}</div>;
  }
  return (
    <>
    {mapDs && (
      <MappingConfirmModal
        datasetId={mapDs.id}
        filename={mapDs.original_filename}
        open={!!mapDs}
        onClose={() => setMapDs(null)}
      />
    )}
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
      {years.map((year) => {
        const ds = findDs(kind, year, bankCode);
        const inputId = `up-${kind}-${year}-${bankCode ?? 'main'}`;
        return (
          <div key={year} className={cn(
            'border rounded-lg p-2.5 text-xs',
            ds?.status === 'PARSED' ? 'border-neutral-300 bg-white'
            : ds?.status === 'PENDING_MAPPING' ? 'border-2 border-indigo-400 bg-indigo-50/50'
            : ds?.status === 'PARSE_ERROR' ? 'border-2 border-black bg-white'
            : ds?.status === 'PARSING' ? 'border-black bg-neutral-100'
            : ds ? 'border-slate-200 bg-slate-50'
            : 'border-dashed border-slate-300 bg-white',
          )}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-slate-800">{t('app.year')} {year}</span>
              {ds?.status === 'PARSED' && <CheckCircle2 className="w-3.5 h-3.5 text-neutral-700" />}
              {ds?.status === 'PENDING_MAPPING' && <ScanLine className="w-3.5 h-3.5 text-indigo-600" />}
              {ds?.status === 'PARSE_ERROR' && <AlertCircle className="w-3.5 h-3.5 text-black" />}
              {ds?.status === 'PARSING' && <Loader2 className="w-3.5 h-3.5 text-black animate-spin" />}
            </div>
            {ds ? (
              <div className="space-y-1">
                <div className="truncate text-slate-700" title={ds.original_filename}>
                  {ds.original_filename}
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <Badge variant={
                    ds.status === 'PARSED' ? 'ok'
                    : ds.status === 'PARSE_ERROR' ? 'err'
                    : ds.status === 'PARSING' ? 'info'
                    : ds.status === 'PENDING_MAPPING' ? 'warn'
                    : 'neutral'
                  }>{ds.status === 'PENDING_MAPPING' ? 'À CONFIRMER' : ds.status}</Badge>
                  {ds.rows_count != null && (
                    <span className="text-[10px] text-slate-500">{ds.rows_count} {t('data.rows')}</span>
                  )}
                </div>
                <ControlTotalsBadge ct={ds.control_totals} />
                {ds.status === 'PENDING_MAPPING' && (
                  <button
                    type="button"
                    onClick={() => setMapDs(ds)}
                    className="mt-1 w-full inline-flex items-center justify-center gap-1 rounded-md bg-indigo-600 px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 transition"
                  >
                    <ScanLine className="w-3 h-3" />
                    Vérifiez le mapping
                  </button>
                )}
                <div className="text-[10px] text-slate-400">{formatDate(ds.uploaded_at)}</div>
                {ds.parse_error && (
                  <div className="text-[10px] text-black font-bold line-clamp-2">{ds.parse_error}</div>
                )}
                {ds.status === 'PARSED' && ds.column_mapping?.detected && (
                  <ColumnDetectionReport kind={ds.kind} detected={ds.column_mapping.detected as Record<string, boolean>} />
                )}
                <label htmlFor={inputId} className="inline-block mt-1 text-[10px] text-black underline cursor-pointer hover:no-underline">
                  {t('app.replace')}
                </label>
              </div>
            ) : (
              <label htmlFor={inputId} className="block w-full text-center py-3 cursor-pointer text-slate-500 hover:text-black hover:bg-slate-50 rounded transition">
                <Upload className="w-4 h-4 inline mr-1" />
                {t('app.upload')}
              </label>
            )}
            <input
              id={inputId}
              type="file"
              accept=".xlsx,.xls,.csv,.pdf,image/*"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onUpload(file, year);
                e.target.value = '';
              }}
            />
          </div>
        );
      })}
    </div>
    </>
  );
}


/**
 * Post-upload AI-detection report.
 *
 * Shows the auditor which canonical columns the SaaS recognised in the file.
 * Each field is rendered as a tiny green ✓ chip when detected, or a red ✗
 * chip when missing.
 *
 * Field sets:
 *  - TRIAL_BALANCE   : account_code / account_name / opening_d / opening_c /
 *                      period_d / period_c / closing_d / closing_c
 *  - GENERAL_LEDGER  : piece_number / entry_date / journal_code / account_code /
 *                      account_name / libelle / debit / credit / lettrage
 */
/** Control totals — « le fichier contient N lignes × M colonnes, l'outil en a
 *  lu N × M ». Green when every file row is accounted for (ingested, exclue
 *  avec motif, ou ligne de structure) ; red when the tool read less than the
 *  file contains. */
function ControlTotalsBadge({ ct }: { ct: Dataset['control_totals'] }) {
  if (!ct) return null;
  const pending = ct.read_rows == null;
  const ok = ct.complete === true;
  const bad = ct.complete === false;
  return (
    <div
      className={cn(
        'mt-1 rounded border px-1.5 py-1 text-[10px] leading-tight',
        pending ? 'border-slate-200 bg-white text-slate-600'
        : ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
        : bad ? 'border-rose-300 bg-rose-50 text-rose-800'
        : 'border-slate-200 bg-white text-slate-600',
      )}
      title="Totaux de contrôle : dimensions du fichier vs données lues par l'outil"
    >
      <span className="font-semibold">Fichier</span>{' '}
      <span className="font-mono">{ct.file_rows.toLocaleString('fr-FR')} L × {ct.file_cols} C</span>
      {ct.sheets != null && ct.sheets > 1 && <span> · {ct.sheets} feuilles</span>}
      {!pending && (
        <>
          {' · '}<span className="font-semibold">Lues</span>{' '}
          <span className="font-mono">
            {(ct.read_rows as number).toLocaleString('fr-FR')} L
            {ct.read_cols != null && <> × {ct.read_cols} C</>}
          </span>
          {ct.excluded_rows != null && ct.excluded_rows > 0 && (
            <span> · {ct.excluded_rows} exclue(s)</span>
          )}
          {ct.structural_rows != null && ct.structural_rows > 0 && (
            <span> · {ct.structural_rows} structure</span>
          )}
          <span className="ml-1 font-bold">{ok ? '✓' : bad ? '✗ incomplet' : ''}</span>
        </>
      )}
    </div>
  );
}

function ColumnDetectionReport({ kind, detected }: { kind: string; detected: Record<string, boolean> }) {
  const t = useT();
  const FIELDS_TB: { key: string; labelKey: MessageKey }[] = [
    { key: 'account_code',   labelKey: 'data.detect.accountCode' },
    { key: 'account_name',   labelKey: 'data.detect.accountName' },
    { key: 'opening_debit',  labelKey: 'data.detect.openingD' },
    { key: 'opening_credit', labelKey: 'data.detect.openingC' },
    { key: 'period_debit',   labelKey: 'data.detect.periodD' },
    { key: 'period_credit',  labelKey: 'data.detect.periodC' },
    { key: 'closing_debit',  labelKey: 'data.detect.closingD' },
    { key: 'closing_credit', labelKey: 'data.detect.closingC' },
  ];
  const FIELDS_GL: { key: string; labelKey: MessageKey }[] = [
    { key: 'piece_number',  labelKey: 'data.detect.pieceNumber' },
    { key: 'entry_date',    labelKey: 'data.detect.entryDate' },
    { key: 'journal_code',  labelKey: 'data.detect.journalCode' },
    { key: 'account_code',  labelKey: 'data.detect.accountCode' },
    { key: 'account_name',  labelKey: 'data.detect.accountName' },
    { key: 'libelle',       labelKey: 'data.detect.libelle' },
    { key: 'debit',         labelKey: 'data.detect.debit' },
    { key: 'credit',        labelKey: 'data.detect.credit' },
    { key: 'lettrage',      labelKey: 'data.detect.lettrage' },
  ];

  let fields: { key: string; labelKey: MessageKey }[];
  if (kind === 'TRIAL_BALANCE') fields = FIELDS_TB;
  else if (kind === 'GENERAL_LEDGER') fields = FIELDS_GL;
  else return null;

  const okCount = fields.filter((f) => detected[f.key]).length;
  return (
    <div className="mt-2 border-t border-slate-100 pt-2">
      <div className="text-[10px] font-semibold text-slate-600 mb-1">
        {t('data.detect.title')} ({okCount}/{fields.length})
      </div>
      <div className="flex flex-wrap gap-1">
        {fields.map((f) => {
          const ok = !!detected[f.key];
          return (
            <span
              key={f.key}
              className={cn(
                'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium',
                ok
                  ? 'bg-white text-neutral-700 border border-neutral-300'
                  : 'bg-white text-black font-bold border-2 border-black',
              )}
              title={ok ? t('data.detect.detected') : t('data.detect.missing')}
            >
              {ok ? '✓' : '✗'} {t(f.labelKey)}
            </span>
          );
        })}
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// DMM bulk upload + monthly grid viewer
// ─────────────────────────────────────────────────────────────────────────────

interface GridCell {
  id: string;
  declared_amount: number;
  base_amount: number | null;
  principal_amount: number | null;
  cac_amount: number | null;
  penalty_amount: number | null;
  line_code: string | null;
  filing_date: string | null;
  filing_deadline: string | null;
  status: string | null;
  source_dataset_id: string | null;
}

interface GridMonth {
  month: number;
  month_label: string;
  has_dmm: boolean;
  source_dataset_id: string | null;
  total_declared_xaf: number;
  by_tax_type: Record<string, GridCell>;
}

interface GridResp {
  year: number;
  tax_types: string[];
  months: GridMonth[];
  annual_totals_by_tax_type: Record<string, number>;
  annual_total: number;
  months_with_dmm: number;
}

const TAX_LABELS: Record<string, string> = {
  ACOMPTE_IS: 'Acompte IS',
  TVA: 'TVA',
  IRPP_SALAIRES: 'IRPP / RTS',
  IRCM: 'IRCM',
  PRECOMPTE_LOYERS: 'Préc. loyers',
  PRECOMPTE_ACHATS: 'Préc. achats',
  TSR: 'TSR',
  CFC: 'CFC',
  FNE: 'FNE',
};

interface UploadItem {
  filename: string;
  status: string;
  period_year?: number;
  period_month?: number;
  lines_created?: number;
  source?: string;
  dataset_id?: string;
  document_number?: string;
  taxpayer_niu?: string;
  error?: string;
}

function DmmBulkSection({ caseId, years }: { caseId: string; years: number[] }) {
  const qc = useQueryClient();
  const [selectedYear, setSelectedYear] = useState<number>(years[0] || new Date().getFullYear());
  const [files, setFiles] = useState<File[]>([]);
  const [lastResults, setLastResults] = useState<UploadItem[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number; current: string } | null>(null);

  const gridQ = useQuery({
    queryKey: ['dmm-grid', caseId, selectedYear],
    queryFn: () =>
      api<GridResp>(`/monthly-returns/audit-case/${caseId}/grid?year=${selectedYear}`),
  });

  const uploadMut = useMutation({
    mutationFn: async (toUpload: File[]) => {
      // Sequential, one file per request → real progress feedback
      const allItems: UploadItem[] = [];
      setProgress({ done: 0, total: toUpload.length, current: toUpload[0]?.name || '' });
      for (let i = 0; i < toUpload.length; i++) {
        setProgress({ done: i, total: toUpload.length, current: toUpload[i].name });
        const fd = new FormData();
        fd.append('audit_case_id', caseId);
        fd.append('files', toUpload[i]);
        const res = await apiUploadForm<{ processed: number; total_lines_created: number; items: UploadItem[] }>(
          '/monthly-returns/bulk-dmm', fd,
        );
        allItems.push(...(res.items || []));
        setProgress({ done: i + 1, total: toUpload.length, current: toUpload[i].name });
        void qc.invalidateQueries({ queryKey: ['dmm-grid', caseId] });
      }
      return { items: allItems };
    },
    onSuccess: (data) => {
      setFiles([]);
      setProgress(null);
      setLastResults(data.items || []);
      void qc.invalidateQueries({ queryKey: ['dmm-grid', caseId] });
      // If we uploaded a DMM from a year not currently displayed, switch to it
      const firstOK = (data.items || []).find(
        (it) => it.status === 'OK' && it.period_year && years.includes(it.period_year),
      );
      if (firstOK && firstOK.period_year && firstOK.period_year !== selectedYear) {
        setSelectedYear(firstOK.period_year);
      }
    },
    onError: (e: any) => { setProgress(null); alert(`Échec : ${e?.message || 'erreur'}`); },
  });

  const deleteDatasetMut = useMutation({
    mutationFn: async (datasetId: string) =>
      api(`/monthly-returns/dataset/${datasetId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dmm-grid', caseId] });
    },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  const grid = gridQ.data;

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        className="border-2 border-dashed border-slate-300 rounded-lg p-4 bg-slate-50/50"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const fs = Array.from(e.dataTransfer.files).filter((f) =>
            f.name.toLowerCase().endsWith('.pdf'),
          );
          if (fs.length) setFiles((prev) => [...prev, ...fs]);
        }}
      >
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm text-slate-700">
            <b>{files.length}</b> fichier(s) prêt(s). Glissez-déposez vos DMM PDF ici, ou utilisez le bouton.
          </div>
          <div className="flex items-center gap-2">
            <label className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-slate-300 bg-white hover:bg-slate-50 cursor-pointer">
              <Upload className="w-3.5 h-3.5" /> Sélectionner des PDF…
              <input
                type="file"
                multiple
                hidden
                accept=".pdf"
                onChange={(e) => {
                  const fs = Array.from(e.target.files || []);
                  if (fs.length) setFiles((prev) => [...prev, ...fs]);
                  e.target.value = '';
                }}
              />
            </label>
            <button
              type="button"
              onClick={() => uploadMut.mutate(files)}
              disabled={!files.length || uploadMut.isPending}
              className="px-3 py-1.5 text-xs rounded bg-black text-white hover:bg-neutral-900 disabled:opacity-40"
            >
              {uploadMut.isPending ? 'Extraction en cours…' : 'Charger & extraire'}
            </button>
            {files.length > 0 && !uploadMut.isPending && (
              <button
                type="button"
                onClick={() => setFiles([])}
                className="px-2 py-1.5 text-xs text-slate-500 hover:text-black"
              >
                vider
              </button>
            )}
          </div>
        </div>

        {/* Progress bar — sequential extraction */}
        {progress && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-[11px] text-slate-600 mb-1">
              <span>
                Traitement IA : <b>{progress.done}/{progress.total}</b> fichier(s)
                {progress.done < progress.total && progress.current && (
                  <span className="text-slate-400"> — en cours : {progress.current}</span>
                )}
              </span>
              <span className="font-mono font-semibold">
                {progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0}%
              </span>
            </div>
            <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-black transition-all duration-300 ease-out"
                style={{ width: `${progress.total > 0 ? (progress.done / progress.total) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}

        {files.length > 0 && !progress && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {files.map((f, i) => (
              <span key={i} className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[11px]">
                {f.name}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Per-upload results panel — shown after each batch */}
      {lastResults.length > 0 && (
        <div className="border border-slate-200 rounded-lg overflow-hidden">
          <div className="bg-slate-50 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-600 flex items-center justify-between">
            <span>Résultats de la dernière extraction ({lastResults.length} fichier(s))</span>
            <button
              type="button"
              onClick={() => setLastResults([])}
              className="text-slate-400 hover:text-slate-600 text-[10px] normal-case tracking-normal"
            >
              fermer
            </button>
          </div>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-slate-200 bg-white">
                <th className="px-3 py-1.5 text-left">Fichier</th>
                <th className="px-3 py-1.5 text-left">Période extraite</th>
                <th className="px-3 py-1.5 text-left">Statut</th>
                <th className="px-3 py-1.5 text-right">Lignes</th>
                <th className="px-3 py-1.5 text-left">Avertissement</th>
                <th className="px-3 py-1.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {lastResults.map((it, i) => {
                const yearOK = !it.period_year || years.includes(it.period_year);
                const monthLabel = it.period_month
                  ? ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'][it.period_month - 1]
                  : '—';
                return (
                  <tr
                    key={`${it.filename}-${i}`}
                    className={cn(
                      'border-b border-slate-100',
                      !yearOK && it.status === 'OK' && 'bg-neutral-100',
                      it.status !== 'OK' && 'bg-white border-2 border-black',
                    )}
                  >
                    <td className="px-3 py-1.5 truncate max-w-[280px]" title={it.filename}>
                      {it.filename}
                    </td>
                    <td className="px-3 py-1.5">
                      {it.period_year ? `${monthLabel} ${it.period_year}` : <span className="text-slate-400 italic">période inconnue</span>}
                    </td>
                    <td className="px-3 py-1.5">
                      {it.status === 'OK' ? (
                        <span className="text-neutral-700">✅ OK</span>
                      ) : (
                        <span className="text-black font-bold">⚠ {it.status}</span>
                      )}
                      {it.source && <span className="ml-1 text-[10px] text-slate-400">[{it.source}]</span>}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono">
                      {it.lines_created ?? 0}
                    </td>
                    <td className="px-3 py-1.5">
                      {!yearOK && it.status === 'OK' && (
                        <span className="text-neutral-700 text-[11px]">
                          ⚠ Exercice <b>{it.period_year}</b> hors scope du dossier (
                          {years.join(', ')}). La DMM a été conservée — vous pouvez la supprimer si
                          c&apos;est une erreur, ou la garder pour consultation.
                        </span>
                      )}
                      {it.error && (
                        <span className="text-black font-bold text-[11px]">{it.error}</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {it.dataset_id && (
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(`Supprimer cette DMM (${it.filename}) ?`)) {
                              deleteDatasetMut.mutate(it.dataset_id!);
                              setLastResults((prev) => prev.filter((_, j) => j !== i));
                            }
                          }}
                          className="text-black hover:bg-neutral-100 rounded px-1.5 py-0.5"
                          title="Supprimer cette DMM"
                        >
                          🗑 Supprimer
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Year selector + summary */}
      <div className="flex items-center gap-2 text-xs flex-wrap">
        <span className="text-slate-500">Exercice :</span>
        {years.map((y) => (
          <button
            key={y}
            onClick={() => setSelectedYear(y)}
            className={cn(
              'px-2 py-1 rounded border',
              y === selectedYear
                ? 'bg-black text-white border-black'
                : 'bg-white border-slate-300 hover:bg-slate-50',
            )}
          >
            {y}
          </button>
        ))}
        {grid && (
          <span className="ml-auto text-slate-500">
            <b>{grid.months_with_dmm}</b> / 12 DMM chargées · Σ déclaré annuel{' '}
            <b className="font-mono">{formatXAF(grid.annual_total)}</b>
          </span>
        )}
      </div>

      {/* Grid */}
      {grid && (
        <div className="overflow-x-auto border border-slate-200 rounded">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-2 py-2 text-left text-[10px] uppercase tracking-wider text-slate-500 sticky left-0 bg-slate-50">Mois</th>
                {grid.tax_types.map((tt) => (
                  <th key={tt} className="px-2 py-2 text-right text-[10px] uppercase tracking-wider text-slate-500">
                    {TAX_LABELS[tt] || tt}
                  </th>
                ))}
                <th className="px-2 py-2 text-right text-[10px] uppercase tracking-wider text-slate-700 bg-slate-100">Total mois</th>
                <th className="px-2 py-2 text-center text-[10px] uppercase tracking-wider text-slate-500 w-12">Suppr.</th>
              </tr>
            </thead>
            <tbody>
              {grid.months.map((m) => (
                <tr key={m.month} className={cn('border-b border-slate-100', !m.has_dmm && 'bg-neutral-100/30')}>
                  <td className="px-2 py-1.5 sticky left-0 bg-white">
                    <div className="font-medium">{m.month_label}</div>
                    {!m.has_dmm && <div className="text-[10px] text-black font-bold">DMM manquante</div>}
                  </td>
                  {grid.tax_types.map((tt) => {
                    const cell = m.by_tax_type[tt];
                    if (!cell) {
                      return (
                        <td key={tt} className="px-2 py-1.5 text-right text-slate-300">
                          —
                        </td>
                      );
                    }
                    return (
                      <td
                        key={tt}
                        className="px-2 py-1.5 text-right font-mono"
                        title={
                          `Principal: ${cell.principal_amount ?? '—'}  CAC: ${cell.cac_amount ?? '—'}` +
                          (cell.line_code ? `  Ligne: ${cell.line_code}` : '')
                        }
                      >
                        {formatXAF(cell.declared_amount)}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1.5 text-right font-mono font-semibold bg-slate-50">
                    {m.has_dmm ? formatXAF(m.total_declared_xaf) : '—'}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    {m.has_dmm && m.source_dataset_id ? (
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Supprimer la DMM de ${m.month_label} ${grid.year} ? Toutes les lignes d'impôt extraites seront supprimées.`)) {
                            deleteDatasetMut.mutate(m.source_dataset_id!);
                          }
                        }}
                        className="text-black hover:text-black hover:bg-neutral-100 rounded p-1"
                        title={`Supprimer la DMM de ${m.month_label}`}
                        disabled={deleteDatasetMut.isPending}
                      >
                        🗑
                      </button>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
              <tr className="bg-black text-white font-semibold">
                <td className="px-2 py-2 sticky left-0 bg-black">TOTAL ANNUEL</td>
                {grid.tax_types.map((tt) => (
                  <td key={tt} className="px-2 py-2 text-right font-mono">
                    {formatXAF(grid.annual_totals_by_tax_type[tt] || 0)}
                  </td>
                ))}
                <td className="px-2 py-2 text-right font-mono">{formatXAF(grid.annual_total)}</td>
                <td className="px-2 py-2"></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <div className="text-[10px] text-slate-500 italic">
        Survolez une cellule pour voir le détail Principal / CAC et la ligne du formulaire DGI.
        L&apos;écran « Acomptes mensuels IS » dans Vérifications › IS utilise ces données pour les contrôles de recoupement.
      </div>
    </div>
  );
}
