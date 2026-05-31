'use client';

import { use, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Play, AlertTriangle, ShieldCheck, Info,
  TrendingUp, Receipt, BookCheck, Clock, CalendarDays,
  AlertCircle, CheckCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge, severityToVariant, severityLabel } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropZone } from '@/components/dropzone';
import { api, apiUploadForm } from '@/lib/api';
import { formatXAF, formatSigned, formatDate, cn } from '@/lib/utils';
import {
  CATEGORY_LABELS, TAX_TYPE_LABELS,
  type AuditCase, type ControlFinding, type ControlRun,
  type Dataset, type TrialBalanceLine, type MonthlyReturn, type TaxType,
} from '@/lib/types';
import { useT } from '@/lib/i18n';

// ── LPF helpers ──────────────────────────────────────────────────────────────
function daysBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);
}

function daysFromNow(d: string | null): number | null {
  if (!d) return null;
  return Math.round((new Date(d).getTime() - Date.now()) / 86_400_000);
}

function addDays(d: string | null, n: number): string | null {
  if (!d) return null;
  const dt = new Date(d);
  dt.setDate(dt.getDate() + n);
  return dt.toISOString().slice(0, 10);
}

interface LPFStep {
  label: string;
  date: string | null;
  deadline?: string | null;
  deadlineDays?: number;
  check?: boolean | null;
  /** DatasetKind to upload as the supporting PDF for this milestone, if any. */
  uploadKind?: 'AVIS_VERIFICATION' | 'DEBUT_INTERVENTION_PV' | 'FIN_INTERVENTION_PV' | 'NOTIFICATION_REDRESSEMENT' | 'REPONSE_CONTRIBUABLE';
}

function LPFTimeline({ dossier }: { dossier: AuditCase }) {
  const t = useT();
  const qc = useQueryClient();
  const avis = dossier.avis_verification_date;
  const debut = dossier.debut_intervention_date;
  const fin = dossier.fin_intervention_date;
  const notif = dossier.notification_date;
  const reponse = dossier.reponse_contribuable_date;

  const uploadLpf = useMutation({
    mutationFn: async ({ file, kind }: { file: File; kind: NonNullable<LPFStep['uploadKind']> }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('kind', kind);
      return apiUploadForm(`/audit-cases/${dossier.id}/lpf-documents`, fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['audit-case', dossier.id] });
      qc.invalidateQueries({ queryKey: ['lpf-docs', dossier.id] });
    },
  });

  const { data: lpfDocs = [] } = useQuery({
    queryKey: ['lpf-docs', dossier.id],
    queryFn: () => api<Array<{ id: string; kind: string; original_filename: string }>>(`/audit-cases/${dossier.id}/lpf-documents`),
  });
  const docByKind: Record<string, { id: string; original_filename: string } | undefined> = {};
  for (const d of lpfDocs) docByKind[d.kind] = d;

  const avisToDebut = daysBetween(avis, debut);
  const debutToFin = daysBetween(debut, fin);
  const finToNotif = daysBetween(fin, notif);
  const notifToReponse = daysBetween(notif, reponse);

  // Deadlines
  const deadlineDebut = addDays(avis, 15);
  const deadlineNotif = addDays(fin, 60);
  const deadlineReponse = addDays(notif, 30);
  const deadlineReponseMax = addDays(notif, 60);
  const deadlineAdminReponse = addDays(reponse, 60);

  const prescriptionExpiry = dossier.fiscal_year
    ? `${dossier.fiscal_year + 5}-01-01` // Jan 1 of N+5 = last day Dec 31 N+4
    : null;
  const prescJours = daysFromNow(prescriptionExpiry);

  const steps: LPFStep[] = [
    {
      label: t('dossier.lpf.avisVerification'),
      date: avis,
      check: avis != null,
      uploadKind: 'AVIS_VERIFICATION',
    },
    {
      label: t('dossier.lpf.debutIntervention'),
      date: debut,
      deadline: deadlineDebut,
      deadlineDays: 15,
      check: avisToDebut == null ? null : avisToDebut >= 15,
      uploadKind: 'DEBUT_INTERVENTION_PV',
    },
    {
      label: t('dossier.lpf.finIntervention'),
      date: fin,
      check: debutToFin == null ? null : debutToFin <= 90,
      uploadKind: 'FIN_INTERVENTION_PV',
    },
    {
      label: t('dossier.lpf.notification'),
      date: notif,
      deadline: deadlineNotif,
      deadlineDays: 60,
      check: finToNotif == null ? null : finToNotif <= 60,
      uploadKind: 'NOTIFICATION_REDRESSEMENT',
    },
    {
      label: t('dossier.lpf.reponseContribuable'),
      date: reponse,
      deadline: deadlineReponse,
      deadlineDays: 30,
      check: notifToReponse == null ? null : notifToReponse <= 60,
      uploadKind: 'REPONSE_CONTRIBUABLE',
    },
    {
      label: t('dossier.lpf.reponseAdmin'),
      date: null,
      deadline: deadlineAdminReponse,
      deadlineDays: 60,
      check: reponse == null ? null : true,
    },
  ];

  return (
    <div className="space-y-1">
      {steps.map((step, i) => {
        const deadlineJours = step.deadline ? daysFromNow(step.deadline) : null;
        const isOverdue = deadlineJours != null && deadlineJours < 0 && !step.date;
        const isUrgent = deadlineJours != null && deadlineJours >= 0 && deadlineJours <= 14 && !step.date;

        return (
          <div key={i} className="flex items-start gap-3 py-2 border-b border-slate-100 last:border-0">
            <div className="mt-0.5 flex-shrink-0">
              {step.check === true ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : step.check === false ? (
                <AlertCircle className="w-4 h-4 text-rose-500" />
              ) : isOverdue ? (
                <AlertCircle className="w-4 h-4 text-rose-500" />
              ) : (
                <Clock className="w-4 h-4 text-slate-300" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-slate-700">{step.label}</div>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                {step.date ? (
                  <span className="text-[11px] text-slate-500">{formatDate(step.date)}</span>
                ) : step.deadline ? (
                  <span className={cn(
                    'text-[11px] font-medium',
                    isOverdue ? 'text-rose-600' : isUrgent ? 'text-amber-600' : 'text-slate-400'
                  )}>
                    {isOverdue
                      ? `${t('dossier.lpf.deadlineOver')} (${formatDate(step.deadline)})`
                      : `${t('dossier.lpf.deadlineDue')} : ${formatDate(step.deadline)} (${deadlineJours} j)`}
                  </span>
                ) : (
                  <span className="text-[11px] text-slate-400">{t('dossier.lpf.pending')}</span>
                )}
                {step.date && step.deadline && finToNotif != null && (
                  step.check === false
                    ? <Badge variant="err" className="text-[10px]">{t('dossier.lpf.outOfTime')}</Badge>
                    : <Badge variant="ok" className="text-[10px]">{t('dossier.lpf.ok')}</Badge>
                )}
                {step.uploadKind && (
                  (() => {
                    const existing = docByKind[step.uploadKind!];
                    const inputId = `lpf-${step.uploadKind}`;
                    return (
                      <>
                        <label
                          htmlFor={inputId}
                          className="text-[10px] underline text-navy cursor-pointer hover:text-navy-deep"
                          title={existing ? existing.original_filename : ''}
                        >
                          {existing ? `📎 ${t('lpf.viewDoc')}` : `+ ${t('lpf.uploadDoc')}`}
                        </label>
                        <input
                          id={inputId}
                          type="file"
                          accept="application/pdf,image/*"
                          className="hidden"
                          disabled={uploadLpf.isPending}
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f) void uploadLpf.mutateAsync({ file: f, kind: step.uploadKind! });
                            e.target.value = '';
                          }}
                        />
                      </>
                    );
                  })()
                )}
              </div>
            </div>
          </div>
        );
      })}

      {prescriptionExpiry && (
        <div className={cn(
          'mt-3 pt-3 border-t border-dashed border-slate-200 flex items-center justify-between text-xs',
          prescJours != null && prescJours < 180 ? 'text-amber-700' : 'text-slate-500'
        )}>
          <span className="font-medium">{t('dossier.lpf.prescription')}</span>
          <span className="font-semibold">
            {prescJours != null && prescJours < 0
              ? `${t('dossier.lpf.prescribed')} ${formatDate(prescriptionExpiry)}`
              : `${t('dossier.lpf.expires')} ${formatDate(`${dossier.fiscal_year + 4}-12-31`)}${prescJours != null ? ` (${prescJours} j)` : ''}`
            }
          </span>
        </div>
      )}
    </div>
  );
}

export default function DossierPage({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<'overview'>('overview');

  const { data: dossier } = useQuery({
    queryKey: ['audit-case', id],
    queryFn: () => api<AuditCase>(`/audit-cases/${id}`),
  });

  const { data: datasets = [] } = useQuery({
    queryKey: ['datasets', id],
    queryFn: () => api<Dataset[]>(`/datasets/audit-case/${id}`),
    refetchInterval: 3000,
  });

  const { data: runs = [] } = useQuery({
    queryKey: ['runs', id],
    queryFn: () => api<ControlRun[]>(`/control-runs/audit-case/${id}`),
  });

  const { data: monthlyReturns = [] } = useQuery({
    queryKey: ['monthly-returns', id],
    queryFn: () => api<MonthlyReturn[]>(`/monthly-returns/audit-case/${id}`),
    refetchInterval: 5000,
  });

  // Upload + parse a monthly return PDF in one shot
  const parseReturn = useMutation({
    mutationFn: async ({ file, taxType }: { file: File; taxType: TaxType }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('audit_case_id', id);
      fd.append('kind', 'MONTHLY_RETURN');
      const dataset = await apiUploadForm<Dataset>('/datasets', fd);
      return api<MonthlyReturn>('/monthly-returns/parse', {
        method: 'POST',
        body: { dataset_id: dataset.id, tax_type_hint: taxType },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['monthly-returns', id] });
      qc.invalidateQueries({ queryKey: ['datasets', id] });
    },
  });

  // Upload + parse a payment receipt and attach to a monthly return
  const parsePayment = useMutation({
    mutationFn: async ({ file, returnId }: { file: File; returnId: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('audit_case_id', id);
      fd.append('kind', 'PAYMENT_PROOF');
      const dataset = await apiUploadForm<Dataset>('/datasets', fd);
      return api<unknown>('/monthly-returns/payment-proofs/parse', {
        method: 'POST',
        body: { monthly_return_id: returnId, dataset_id: dataset.id },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['monthly-returns', id] });
      qc.invalidateQueries({ queryKey: ['datasets', id] });
    },
  });

  // Update fiscal_year (year picker)
  const updateCase = useMutation({
    mutationFn: (patch: Partial<AuditCase>) =>
      api<AuditCase>(`/audit-cases/${id}`, { method: 'PATCH', body: patch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['audit-case', id] });
      qc.invalidateQueries({ queryKey: ['monthly-returns', id] });
    },
  });

  // Pick the LATEST parsed TB / GL — when a new file is uploaded it becomes
  // a new dataset row, and we want to show that instead of the previous one.
  const pickLatest = (kind: Dataset['kind']) =>
    [...datasets]
      .filter((d) => d.kind === kind && d.status === 'PARSED')
      .sort((a, b) => (a.uploaded_at < b.uploaded_at ? 1 : -1))[0];
  const tbDataset = pickLatest('TRIAL_BALANCE');
  const glDataset = pickLatest('GENERAL_LEDGER');

  const { data: tbLines = [] } = useQuery({
    queryKey: ['tb-lines', tbDataset?.id],
    queryFn: () => api<TrialBalanceLine[]>(`/datasets/${tbDataset!.id}/trial-balance`),
    enabled: !!tbDataset,
  });

  const upload = useMutation({
    mutationFn: async ({ file, kind }: { file: File; kind: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('audit_case_id', id);
      fd.append('kind', kind);
      return apiUploadForm<Dataset>('/datasets', fd);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['datasets', id] }),
  });

  const runControls = useMutation({
    mutationFn: (category: string) =>
      api<ControlRun>('/control-runs', {
        method: 'POST',
        body: { audit_case_id: id, category },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs', id] }),
  });

  // Group most recent run per category
  const runByCategory: Record<string, ControlRun | undefined> = {};
  for (const r of runs) {
    if (!runByCategory[r.category]) runByCategory[r.category] = r;
  }

  const tbDebitSum = tbLines.reduce((s, l) => s + Number(l.closing_debit), 0);
  const tbCreditSum = tbLines.reduce((s, l) => s + Number(l.closing_credit), 0);

  // Consolidated findings (across categories) for the Findings tab
  const allFindings: { run: ControlRun; finding: ControlFinding }[] = runs.flatMap((r) =>
    r.findings.map((f) => ({ run: r, finding: f })),
  );
  const totalImpact = runs.reduce((s, r) => s + (r.summary?.estimated_total_impact_xaf ?? 0), 0);

  if (!dossier) return <div>{t('dossier.loading')}</div>;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
          <span className="font-mono">{dossier.reference}</span>
          <span>·</span>
          <Badge variant={dossier.risk_level === 'ELEVE' ? 'err' : dossier.risk_level === 'MOYEN' ? 'warn' : 'ok'}>
            {t('dossier.risk')} {dossier.risk_level}
          </Badge>
          <span>·</span>
          <span>{t('dossier.fiscalYear')} {dossier.fiscal_year}</span>
        </div>
        <h1 className="font-display text-2xl font-bold text-slate-900">{dossier.taxpayer.raison_sociale}</h1>
        <p className="text-sm text-slate-500 mt-1 font-mono">{t('dossier.tin')} {dossier.taxpayer.niu}</p>
      </div>

      <div className="border-b border-slate-200 flex gap-6">
        {[
          ['overview', t('dossier.tabOverview')],
        ].map(([k, label]) => (
          <button
            key={k}
            onClick={() => setActiveTab(k as typeof activeTab)}
            className={`pb-2 -mb-px text-sm font-medium border-b-2 ${
              activeTab === k ? 'border-navy text-navy' : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-4">
          <div className="grid lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader><CardTitle>{t('dossier.taxpayerInfo')}</CardTitle></CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-y-3 text-sm">
                  <dt className="text-slate-500">{t('dossier.companyName')}</dt><dd className="font-medium">{dossier.taxpayer.raison_sociale}</dd>
                  <dt className="text-slate-500">{t('dossier.tin')}</dt><dd className="font-mono">{dossier.taxpayer.niu}</dd>
                  <dt className="text-slate-500">{t('dossier.address')}</dt><dd>{dossier.taxpayer.address || '—'}</dd>
                  <dt className="text-slate-500">{t('dossier.sector')}</dt><dd>{dossier.taxpayer.sector || '—'}</dd>
                  <dt className="text-slate-500">{t('dossier.taxRegime')}</dt><dd>{dossier.taxpayer.regime}</dd>
                  <dt className="text-slate-500">{t('dossier.controlledPeriod')}</dt><dd>{formatDate(dossier.period_start)} → {formatDate(dossier.period_end)}</dd>
                </dl>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CalendarDays className="w-4 h-4 text-rose-700" />
                  {t('dossier.lpfProcedure')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <LPFTimeline dossier={dossier} />
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPI label={t('dossier.totalFindings')} value={allFindings.length}
                 tone={allFindings.length ? 'err' : 'ok'} />
            <KPI label={t('dossier.categoriesRun')} value={Object.keys(runByCategory).length}
                 tone="neutral" />
            <KPI label={t('dossier.estimatedImpact')} value={`${formatXAF(totalImpact)} FCFA`}
                 tone={totalImpact ? 'warn' : 'ok'} />
            <KPI label={t('dossier.datasetsLoaded')} value={datasets.filter(d => d.status === 'PARSED').length}
                 tone="neutral" />
          </div>
        </div>
      )}

    </div>
  );
}

// ── Déclarations mensuelles grid (13 periods) ───────────────────────────────
const MONTHLY_TAX_TYPES: TaxType[] = [
  'TVA', 'IRPP_SALAIRES', 'CNPS', 'TSR', 'ACOMPTE_IS',
  'CFC', 'FNE', 'PRECOMPTE_LOYERS',
];
// 12 months of the fiscal year + January of the following year (for YE VAT reconciliation)
const MONTH_LABELS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'];
const PERIOD_COUNT = 13;

interface DeclarationsGridProps {
  fiscalYear: number;
  returns: MonthlyReturn[];
  onUploadDeclaration: (file: File, taxType: TaxType) => Promise<unknown>;
  onUploadPayment: (file: File, returnId: string) => Promise<unknown>;
  onChangeYear: (year: number) => void;
  uploading: boolean;
  yearUpdating: boolean;
}

// Compute the (year, month) for a given column index. cols 0-11 = Jan-Dec N; col 12 = Jan N+1.
function colToPeriod(fiscalYear: number, col: number): { year: number; month: number } {
  if (col < 12) return { year: fiscalYear, month: col + 1 };
  return { year: fiscalYear + 1, month: 1 };
}

function DeclarationsGrid({
  fiscalYear, returns, onUploadDeclaration, onUploadPayment, onChangeYear,
  uploading, yearUpdating,
}: DeclarationsGridProps) {
  // Index returns by (tax_type, year, month)
  const grid: Record<string, MonthlyReturn | undefined> = {};
  for (const r of returns) {
    if (r.period_month) grid[`${r.tax_type}_${r.period_year}_${r.period_month}`] = r;
  }

  // Totals
  const totalDeclared = returns.reduce((s, r) => s + Number(r.declared_amount), 0);
  const totalPaid = returns.reduce(
    (s, r) => s + r.payment_proofs.reduce((sp, p) => sp + Number(p.amount_paid), 0),
    0,
  );
  const tvaReturns = returns.filter(r => r.tax_type === 'TVA' && r.period_year === fiscalYear);
  const lateFilings = returns.filter(r => r.filing_date && r.filing_date > r.filing_deadline).length;

  return (
    <div className="space-y-6">
      {/* Year selector + KPIs */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card>
          <CardContent>
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Exercice fiscal</div>
            <div className="flex items-center gap-2 mt-1">
              <button
                onClick={() => onChangeYear(fiscalYear - 1)}
                disabled={yearUpdating}
                className="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold disabled:opacity-50"
                title="Année précédente"
              >−</button>
              <input
                type="number"
                value={fiscalYear}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v) && v >= 2000 && v <= 2099) onChangeYear(v);
                }}
                disabled={yearUpdating}
                className="w-20 text-center text-xl font-bold font-display border border-slate-200 rounded px-1 py-0.5 disabled:opacity-50"
              />
              <button
                onClick={() => onChangeYear(fiscalYear + 1)}
                disabled={yearUpdating}
                className="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold disabled:opacity-50"
                title="Année suivante"
              >+</button>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">{yearUpdating ? 'Mise à jour…' : 'Sélectionnable'}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Déclarations chargées</div>
            <div className="text-2xl font-bold mt-1 font-display">{returns.length}</div>
            <div className="text-xs text-slate-500 mt-0.5">sur {MONTHLY_TAX_TYPES.length * PERIOD_COUNT} possibles</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">TVA — Exercice {fiscalYear}</div>
            <div className={cn('text-2xl font-bold mt-1 font-display', tvaReturns.length === 12 ? 'text-emerald-600' : 'text-amber-600')}>
              {tvaReturns.length}/12
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Σ déclaré · Σ payé</div>
            <div className="text-base font-bold mt-1 font-display">{formatXAF(totalDeclared)}</div>
            <div className={cn('text-xs mt-0.5', totalPaid >= totalDeclared ? 'text-emerald-600' : 'text-amber-600')}>
              payé : {formatXAF(totalPaid)} FCFA
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Dépôts tardifs</div>
            <div className={cn('text-2xl font-bold mt-1 font-display', lateFilings ? 'text-rose-600' : 'text-emerald-600')}>
              {lateFilings}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Calendrier — 13 périodes (Jan {fiscalYear} → Jan {fiscalYear + 1})</CardTitle>
          <div className="text-xs text-slate-500 mt-1">
            La 13<sup>e</sup> colonne (Janvier {fiscalYear + 1}) sert au recoupement de fin d&apos;exercice
            (TVA solde TB clôture vs déclaration Jan {fiscalYear + 1}).
            <br />
            <span className="text-slate-400">
              Cliquez sur une cellule pour téléverser la déclaration (PDF) · le bouton 💳 sous la cellule
              ajoute la quittance de paiement.
            </span>
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th rowSpan={2} className="text-left px-4 py-3 text-[11px] uppercase tracking-wider text-slate-500">Impôt</th>
                <th colSpan={12} className="text-center px-2 py-2 text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                  Exercice {fiscalYear}
                </th>
                <th className="text-center px-2 py-2 text-[11px] uppercase tracking-wider text-slate-500 bg-amber-50 border-l border-slate-200">
                  YE&nbsp;Recon
                </th>
                <th rowSpan={2} className="text-right px-4 py-3 text-[11px] uppercase tracking-wider text-slate-500 min-w-[110px]">Σ déclaré</th>
                <th rowSpan={2} className="text-right px-4 py-3 text-[11px] uppercase tracking-wider text-slate-500 min-w-[110px]">Σ payé</th>
              </tr>
              <tr className="bg-slate-50 border-b border-slate-200">
                {MONTH_LABELS.map((m, i) => (
                  <th key={i} className="text-center px-1 py-2 text-[10px] uppercase tracking-wider text-slate-500 min-w-[48px]">
                    {m}
                  </th>
                ))}
                <th className="text-center px-1 py-2 text-[10px] uppercase tracking-wider text-slate-500 bg-amber-50 border-l border-slate-200 min-w-[48px]">
                  Jan&nbsp;{(fiscalYear + 1).toString().slice(-2)}
                </th>
              </tr>
            </thead>
            <tbody>
              {MONTHLY_TAX_TYPES.map((tax) => {
                const meta = TAX_TYPE_LABELS[tax];
                const taxReturns = returns.filter(r => r.tax_type === tax && r.period_year === fiscalYear);
                const sumDeclared = taxReturns.reduce((s, r) => s + Number(r.declared_amount), 0);
                const sumPaid = taxReturns.reduce(
                  (s, r) => s + r.payment_proofs.reduce((sp, p) => sp + Number(p.amount_paid), 0),
                  0,
                );
                return (
                  <tr key={tax} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-2">
                      <div className="font-medium text-slate-800 text-xs">{meta.short}</div>
                      <div className="text-[10px] text-slate-500">{meta.full}</div>
                    </td>
                    {Array.from({ length: PERIOD_COUNT }, (_, i) => i).map((col) => {
                      const { year, month } = colToPeriod(fiscalYear, col);
                      const r = grid[`${tax}_${year}_${month}`];
                      const isYeRecon = col === 12;
                      return (
                        <td
                          key={col}
                          className={cn('text-center px-1 py-1', isYeRecon && 'bg-amber-50/40 border-l border-slate-200')}
                        >
                          <DeclarationCell
                            tax={tax}
                            year={year}
                            month={month}
                            return_={r}
                            onUploadDeclaration={onUploadDeclaration}
                            onUploadPayment={onUploadPayment}
                            disabled={uploading}
                          />
                        </td>
                      );
                    })}
                    <td className="px-4 py-2 text-right font-mono text-xs">
                      {sumDeclared > 0 ? formatXAF(sumDeclared) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className={cn('px-4 py-2 text-right font-mono text-xs',
                      sumDeclared > 0 && sumPaid < sumDeclared ? 'text-rose-600' : 'text-slate-700'
                    )}>
                      {sumPaid > 0 ? formatXAF(sumPaid) : <span className="text-slate-300">—</span>}
                    </td>
                  </tr>
                );
              })}
              {/* Totals row */}
              <tr className="bg-slate-50 border-t-2 border-slate-300 font-semibold">
                <td className="px-4 py-3 text-xs text-slate-700">TOTAL</td>
                <td colSpan={13} className="px-4 py-3 text-xs text-slate-500">
                  {returns.length} déclaration(s) · {lateFilings} tardive(s) · {returns.reduce((s, r) => s + r.payment_proofs.length, 0)} quittance(s)
                </td>
                <td className="px-4 py-3 text-right font-mono text-xs">{formatXAF(totalDeclared)}</td>
                <td className="px-4 py-3 text-right font-mono text-xs">{formatXAF(totalPaid)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <CardContent>
          <div className="flex items-center gap-4 text-[11px] text-slate-500 flex-wrap">
            <LegendDot color="bg-emerald-500" label="Déclarée + payée" />
            <LegendDot color="bg-sky-500" label="Déclarée (paiement en attente)" />
            <LegendDot color="bg-amber-500" label="Déposée hors délai" />
            <LegendDot color="bg-rose-500" label="Manquante (échéance passée)" />
            <LegendDot color="bg-slate-200" label="Non encore due" />
          </div>
        </CardContent>
      </Card>

      {returns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Détail des déclarations chargées</CardTitle>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="text-left px-4 py-2">Impôt</th>
                  <th className="text-left px-4 py-2">Période</th>
                  <th className="text-left px-4 py-2">Dépôt</th>
                  <th className="text-left px-4 py-2">Échéance</th>
                  <th className="text-right px-4 py-2">Déclaré</th>
                  <th className="text-right px-4 py-2">Base</th>
                  <th className="text-left px-4 py-2">Statut</th>
                </tr>
              </thead>
              <tbody>
                {returns.map((r) => {
                  const late = r.filing_date && r.filing_date > r.filing_deadline;
                  return (
                    <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-2 font-medium">{TAX_TYPE_LABELS[r.tax_type]?.short ?? r.tax_type}</td>
                      <td className="px-4 py-2 text-xs">
                        {r.period_year}-{String(r.period_month ?? '?').padStart(2, '0')}
                      </td>
                      <td className="px-4 py-2 text-xs">{formatDate(r.filing_date)}</td>
                      <td className="px-4 py-2 text-xs">{formatDate(r.filing_deadline)}</td>
                      <td className="px-4 py-2 text-right font-mono">{formatXAF(r.declared_amount)}</td>
                      <td className="px-4 py-2 text-right font-mono">{r.base_amount ? formatXAF(r.base_amount) : '—'}</td>
                      <td className="px-4 py-2">
                        {late ? (
                          <Badge variant="warn">Hors délai</Badge>
                        ) : (
                          <Badge variant="ok">{r.status}</Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function DeclarationCell({
  tax, year, month, return_, onUploadDeclaration, onUploadPayment, disabled,
}: {
  tax: TaxType; year: number; month: number; return_?: MonthlyReturn;
  onUploadDeclaration: (file: File, taxType: TaxType) => Promise<unknown>;
  onUploadPayment: (file: File, returnId: string) => Promise<unknown>;
  disabled: boolean;
}) {
  const declInputId = `decl-${tax}-${year}-${month}`;
  const payInputId = `pay-${tax}-${year}-${month}`;
  const isFiled = !!return_;
  const isLate = !!(return_ && return_.filing_date && return_.filing_date > return_.filing_deadline);
  const hasPayment = !!(return_ && return_.payment_proofs.length > 0);

  // Has the deadline passed? (15 of N+1)
  const deadlineDate = month === 12
    ? new Date(year + 1, 0, 15)   // Dec → 15 Jan N+1
    : new Date(year, month, 15);  // month → 15 of month+1
  const isPastDue = new Date() > deadlineDate;

  let status: 'paid' | 'filed' | 'late' | 'missing' | 'pending';
  if (isFiled && hasPayment) status = 'paid';
  else if (isFiled && isLate) status = 'late';
  else if (isFiled) status = 'filed';
  else if (isPastDue) status = 'missing';
  else status = 'pending';

  const colors: Record<typeof status, string> = {
    paid:    'bg-emerald-500 hover:bg-emerald-600 text-white',
    filed:   'bg-sky-500 hover:bg-sky-600 text-white',
    late:    'bg-amber-500 hover:bg-amber-600 text-white',
    missing: 'bg-rose-500 hover:bg-rose-600 text-white',
    pending: 'bg-slate-200 hover:bg-slate-300 text-slate-500',
  };
  const icons: Record<typeof status, string> = {
    paid: '✓', filed: '✓', late: '!', missing: '✗', pending: '·',
  };

  const period = `${year}-${String(month).padStart(2, '0')}`;
  const tooltip = isFiled
    ? `${tax} ${period} — ${formatXAF(return_!.declared_amount)} FCFA${hasPayment ? ' · payée' : ' · en attente paiement'}${isLate ? ' · HORS DÉLAI' : ''}`
    : isPastDue
      ? `Déclaration ${tax} ${period} manquante — cliquer pour téléverser le PDF`
      : `Téléverser le PDF de la déclaration ${tax} ${period}`;

  return (
    <div className="inline-flex flex-col items-center gap-0.5">
      <label
        htmlFor={declInputId}
        title={tooltip}
        className={cn(
          'inline-flex items-center justify-center w-9 h-7 rounded text-[10px] font-bold cursor-pointer transition',
          colors[status],
          disabled && 'opacity-50 cursor-wait',
        )}
      >
        {icons[status]}
      </label>
      <input
        id={declInputId}
        type="file"
        accept="application/pdf,image/*"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onUploadDeclaration(file, tax);
          e.target.value = '';
        }}
      />
      {/* Payment receipt upload button — only enabled when declaration exists */}
      {isFiled && (
        <>
          <label
            htmlFor={payInputId}
            title={hasPayment ? `Quittance reçue le ${formatDate(return_!.payment_proofs[0]?.payment_date)}` : 'Téléverser la quittance de paiement'}
            className={cn(
              'inline-flex items-center justify-center w-9 h-5 rounded text-[9px] font-medium cursor-pointer transition',
              hasPayment
                ? 'bg-emerald-100 hover:bg-emerald-200 text-emerald-700'
                : 'bg-slate-100 hover:bg-slate-200 text-slate-500 border border-dashed border-slate-300',
              disabled && 'opacity-50 cursor-wait',
            )}
          >
            {hasPayment ? '€' : '€?'}
          </label>
          <input
            id={payInputId}
            type="file"
            accept="application/pdf,image/*"
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file && return_) void onUploadPayment(file, return_.id);
              e.target.value = '';
            }}
          />
        </>
      )}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn('inline-block w-3 h-3 rounded', color)} />
      <span>{label}</span>
    </div>
  );
}

function FindingRow({ f }: { f: ControlFinding }) {
  const isInfo = f.severity === 'INFO';
  return (
    <div className="p-4">
      <div className="flex items-start gap-3">
        {isInfo ? (
          <Info className="w-5 h-5 flex-shrink-0 mt-0.5 text-sky-600" />
        ) : (
          <AlertTriangle className={cn('w-5 h-5 flex-shrink-0 mt-0.5',
            f.severity === 'BLOCKING' || f.severity === 'HIGH' ? 'text-rose-600'
            : f.severity === 'MEDIUM' ? 'text-amber-600' : 'text-slate-400'
          )} />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-slate-900 text-sm">{f.title}</div>
          <div className="text-xs text-slate-600 mt-1 leading-relaxed">{f.description}</div>
          <div className="flex items-center gap-3 mt-2">
            <Badge variant={severityToVariant(f.severity)}>{severityLabel(f.severity)}</Badge>
            <span className="text-[11px] font-mono text-slate-500">
              {f.control_code} · {f.legal_reference}
            </span>
          </div>
        </div>
        {f.estimated_impact_xaf ? (
          <div className="text-right text-sm">
            <div className="text-[10px] text-slate-500 uppercase">Impact</div>
            <div className="font-bold text-rose-600">{formatXAF(f.estimated_impact_xaf)} FCFA</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function KPI({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls = tone === 'err' ? 'text-rose-600' : tone === 'warn' ? 'text-amber-600' : tone === 'ok' ? 'text-emerald-600' : 'text-slate-900';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
        <div className={`text-2xl font-bold mt-1 ${cls}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function MiniKPI({ label, value, tone }: { label: string; value: number; tone?: 'err' | 'warn' }) {
  const cls = tone === 'err' ? 'text-rose-600' : tone === 'warn' ? 'text-amber-600' : 'text-slate-700';
  return (
    <div>
      <div className={`text-xl font-bold ${cls}`}>{value}</div>
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
    </div>
  );
}
