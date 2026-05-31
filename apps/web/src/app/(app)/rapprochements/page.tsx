'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  GitCompare, CheckCircle2, AlertTriangle, Circle, Building2, FileWarning,
  RefreshCw, ChevronDown, ChevronRight, FileText, Printer,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF } from '@/lib/utils';
import type {
  AccountBreakdownRow, RecItemsAnalysis, ReconciliationResult, ReconciliationsResponse,
} from '@/lib/types';


type ReportSummary = {
  case_reference?: string | null;
  fiscal_year?: number | null;
  taxpayer?: { raison_sociale?: string | null; niu?: string | null } | null;
  generated_at: string;
  generated_by: string;
  summary: {
    total_recs: number;
    by_status: { ALIGNED?: number; DISCREPANCY?: number; MISSING?: number };
    total_variance_abs_xaf: number;
  };
  verdict: 'FAVORABLE' | 'RÉSERVÉE' | 'À INSTRUIRE';
  conclusion: string;
  items: Array<{
    key: string; title: string;
    ref_label?: string | null; ref_amount?: number | null;
    counter_label?: string | null; counter_amount?: number | null;
    diff?: number | null; status: string;
  }>;
  legal_reference: string;
};

export default function RapprochementsPage() {
  const { currentCase } = useApp();
  const qc = useQueryClient();
  const t = useT();
  const [showReport, setShowReport] = useState(false);

  const { data, isLoading, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['reconciliations', currentCase?.id],
    queryFn: () => api<ReconciliationsResponse>(`/audit-cases/${currentCase!.id}/reconciliations`),
    enabled: !!currentCase,
    // Cached server-side now — invalidated only when a new dataset is uploaded.
    // Skip the 5 s auto-refetch so we don't pay Claude calls for nothing.
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,
  });

  const reportQ = useQuery({
    queryKey: ['reconciliations-report', currentCase?.id],
    queryFn: () => api<ReportSummary>(
      `/audit-cases/${currentCase!.id}/reconciliations/report`,
    ),
    enabled: !!currentCase && showReport,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,
  });

  const updateAmount = useMutation({
    mutationFn: ({ datasetId, amount }: { datasetId: string; amount: number }) =>
      api(`/datasets/${datasetId}`, {
        method: 'PATCH',
        body: { summary_amount: amount },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reconciliations', currentCase?.id] }),
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

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <GitCompare className="w-6 h-6 text-navy" />
            {t('rec.pageTitle')}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            <strong>{currentCase.taxpayer.raison_sociale}</strong> · {t('app.year')} {currentCase.fiscal_year}
            {data?.tb_filename && <span className="ml-1 text-slate-400">· {t('rec.tbSource')}&nbsp;: {data.tb_filename}</span>}
            {data?.tolerance_fcfa != null && <span className="ml-1 text-slate-400">· {t('rec.tolerance')}&nbsp;: ±{data.tolerance_fcfa} FCFA</span>}
          </p>
          {dataUpdatedAt > 0 && (
            <p className="text-[11px] text-slate-400 mt-1">
              {t('rec.lastUpdated')} : {new Date(dataUpdatedAt).toLocaleTimeString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setShowReport((s) => !s);
              if (!showReport) {
                qc.invalidateQueries({ queryKey: ['reconciliations-report', currentCase.id] });
              }
            }}
          >
            <FileText className="w-4 h-4" />
            {showReport ? 'Masquer le rapport' : 'Rapport synthèse'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              // Force server-side recompute (bypass the per-case cache)
              await api<ReconciliationsResponse>(
                `/audit-cases/${currentCase.id}/reconciliations?refresh=true`,
              );
              void refetch();
              qc.invalidateQueries({ queryKey: ['bank-accounts', currentCase.id] });
              qc.invalidateQueries({ queryKey: ['datasets', currentCase.id] });
              qc.invalidateQueries({ queryKey: ['reconciliations-report', currentCase.id] });
            }}
            disabled={isFetching}
            title={t('rec.refreshHint')}
          >
            <RefreshCw className={cn('w-4 h-4', isFetching && 'animate-spin')} />
            {isFetching ? t('rec.refreshing') : t('rec.refresh')}
          </Button>
        </div>
      </div>

      {showReport && (
        <ReportPanel report={reportQ.data} loading={reportQ.isLoading} />
      )}

      {isLoading && <Card><CardContent className="text-sm text-slate-500">{t('rec.computing')}</CardContent></Card>}

      {data?.note && (
        <Card>
          <CardContent>
            <div className="flex gap-3 items-start">
              <FileWarning className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">{data.note}</div>
            </div>
          </CardContent>
        </Card>
      )}

      {data?.reconciliations
        .slice()
        .sort((a, b) => {
          // Variances first, then missing, then aligned.
          const rank = { DISCREPANCY: 0, MISSING: 1, ALIGNED: 2 } as const;
          return rank[a.status] - rank[b.status];
        })
        .map((r) => (
          <ReconciliationCard
            key={r.key}
            rec={r}
            onSaveAmount={(datasetId, amount) => updateAmount.mutate({ datasetId, amount })}
            saving={updateAmount.isPending}
          />
        ))}
    </div>
  );
}


function ReportPanel({ report, loading }: { report?: ReportSummary; loading: boolean }) {
  if (loading) {
    return (
      <Card>
        <CardContent className="text-sm text-slate-500">
          Génération du rapport en cours…
        </CardContent>
      </Card>
    );
  }
  if (!report) return null;

  const verdictColor = report.verdict === 'FAVORABLE'
    ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
    : report.verdict === 'RÉSERVÉE'
      ? 'bg-rose-50 border-rose-300 text-rose-800'
      : 'bg-amber-50 border-amber-300 text-amber-800';

  return (
    <Card className="border-navy/30 shadow-md print:shadow-none print:border-slate-300">
      <CardHeader className="border-b border-slate-200 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-xl">
              <FileText className="w-6 h-6 text-navy" />
              Rapport de rapprochement — synthèse
            </CardTitle>
            <p className="text-sm text-slate-500 mt-1">
              {report.taxpayer?.raison_sociale} (NIU {report.taxpayer?.niu || '—'}) ·
              Exercice {report.fiscal_year} ·
              Réf. {report.case_reference || '—'}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Émis le {new Date(report.generated_at).toLocaleString('fr-FR')} par {report.generated_by}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            className="print:hidden"
          >
            <Printer className="w-4 h-4" />
            Imprimer
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {/* Verdict */}
        <div className={cn('rounded-md border px-4 py-3', verdictColor)}>
          <div className="text-xs font-semibold uppercase tracking-wider">Verdict global</div>
          <div className="text-lg font-bold mt-0.5">{report.verdict}</div>
          <p className="text-sm mt-1">{report.conclusion}</p>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-4 gap-3 text-center">
          <KPI label="Rapprochements" value={report.summary.total_recs} />
          <KPI label="Alignés" value={report.summary.by_status.ALIGNED ?? 0}
               cls="text-emerald-700" />
          <KPI label="Écarts" value={report.summary.by_status.DISCREPANCY ?? 0}
               cls="text-rose-700" />
          <KPI label="Σ écarts |FCFA|"
               value={formatXAF(report.summary.total_variance_abs_xaf)}
               cls="text-slate-900" />
        </div>

        {/* Contrôles effectués */}
        <div>
          <div className="text-sm font-semibold text-slate-700 mb-2">
            Contrôles effectués
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-600">
                  <th className="text-left p-2 border border-slate-200">Contrôle</th>
                  <th className="text-right p-2 border border-slate-200">Référence (FCFA)</th>
                  <th className="text-right p-2 border border-slate-200">Contrepartie (FCFA)</th>
                  <th className="text-right p-2 border border-slate-200">Écart</th>
                  <th className="text-center p-2 border border-slate-200">Statut</th>
                </tr>
              </thead>
              <tbody>
                {report.items.map((it) => (
                  <tr key={it.key} className="hover:bg-slate-50">
                    <td className="p-2 border border-slate-200 text-slate-800">
                      <div className="font-medium">{it.title}</div>
                      <div className="text-[10px] text-slate-500">
                        {it.ref_label} ↔ {it.counter_label}
                      </div>
                    </td>
                    <td className="p-2 border border-slate-200 text-right tabular-nums">
                      {it.ref_amount != null ? formatXAF(it.ref_amount) : '—'}
                    </td>
                    <td className="p-2 border border-slate-200 text-right tabular-nums">
                      {it.counter_amount != null ? formatXAF(it.counter_amount) : '—'}
                    </td>
                    <td className={cn(
                      'p-2 border border-slate-200 text-right tabular-nums font-medium',
                      it.diff != null && Math.abs(it.diff) > 1000
                        ? 'text-rose-700' : 'text-slate-700',
                    )}>
                      {it.diff != null ? formatXAF(it.diff) : '—'}
                    </td>
                    <td className="p-2 border border-slate-200 text-center">
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-[10px]',
                          it.status === 'ALIGNED' && 'border-emerald-300 text-emerald-700',
                          it.status === 'DISCREPANCY' && 'border-rose-300 text-rose-700',
                          it.status === 'MISSING' && 'border-slate-300 text-slate-500',
                        )}
                      >
                        {it.status === 'ALIGNED' ? 'Aligné'
                          : it.status === 'DISCREPANCY' ? 'Écart'
                            : 'Données manquantes'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pied — référence légale */}
        <div className="text-[10px] text-slate-400 border-t border-slate-200 pt-2">
          Référentiel : {report.legal_reference}
        </div>
      </CardContent>
    </Card>
  );
}

function KPI({ label, value, cls }: { label: string; value: number | string; cls?: string }) {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-md p-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={cn('text-lg font-bold tabular-nums', cls || 'text-slate-900')}>
        {typeof value === 'number' ? value : value}
      </div>
    </div>
  );
}


function statusIcon(status: 'ALIGNED' | 'DISCREPANCY' | 'MISSING') {
  if (status === 'ALIGNED') return <CheckCircle2 className="w-5 h-5 text-emerald-600" />;
  if (status === 'DISCREPANCY') return <AlertTriangle className="w-5 h-5 text-rose-600" />;
  return <Circle className="w-5 h-5 text-slate-300" />;
}

function StatusBadge({ status }: { status: 'ALIGNED' | 'DISCREPANCY' | 'MISSING' }) {
  const t = useT();
  if (status === 'ALIGNED') return <Badge variant="ok">{t('rec.statusAligned')}</Badge>;
  if (status === 'DISCREPANCY') return <Badge variant="err">{t('rec.statusDiscrepancy')}</Badge>;
  return <Badge variant="neutral">{t('rec.statusMissing')}</Badge>;
}

function ReconciliationCard({
  rec, onSaveAmount, saving,
}: {
  rec: ReconciliationResult;
  onSaveAmount: (datasetId: string, amount: number) => void;
  saving: boolean;
}) {
  const t = useT();

  // The TB↔GL rollforward has a translated title + dynamic subtitle.
  // Backend sends a French default; override with the i18n key here.
  const isTbGl = rec.key === 'TB_GL';
  const displayTitle = isTbGl ? t('rec.tbgl.title') : rec.title;
  const displaySubtitle = isTbGl
    ? (rec.rollforward_summary?.gl_loaded
        ? `${t('rec.tbgl.subWithGL')} ${rec.rollforward_summary.gl_filename ? `${t('rec.tbgl.glSource')}: ${rec.rollforward_summary.gl_filename}` : ''}`.trim()
        : t('rec.tbgl.subNoGL'))
    : rec.subtitle;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3 text-base">
          {statusIcon(rec.status)}
          <span className="flex-1">{displayTitle}</span>
          <StatusBadge status={rec.status} />
        </CardTitle>
        <div className="text-xs text-slate-500 mt-1 ml-8">{displaySubtitle}</div>
      </CardHeader>
      <CardContent>
        {/* Main row (or single comparison row) */}
        {!rec.sub_items && (
          <RecRow
            refLabel={rec.ref_label}
            refAmount={rec.ref_amount}
            counterLabel={rec.counter_label}
            counterAmount={rec.counter_amount}
            counterFilename={rec.counter_filename ?? undefined}
            diff={rec.diff}
            isCount={rec.is_count}
            status={rec.status}
          />
        )}

        {/* TB↔GL rollforward — per-account opening / movement / expected / actual / variance */}
        {rec.sub_items && isTbGl && (
          <TbGlRollforward rec={rec} />
        )}

        {/* AP / AR / Inventory — collapsible breakdown of contributing TB accounts */}
        {rec.account_breakdown && rec.account_breakdown.length > 0 && !isTbGl && (
          <AccountBreakdownDropdown
            breakdown={rec.account_breakdown}
            recStatus={rec.status}
            recDiff={rec.diff}
          />
        )}

        {/* Reconciling items — methodology categorization for DISCREPANCY recs */}
        {rec.rec_items && (
          <RecItemsPanel analysis={rec.rec_items} />
        )}

        {/* Bank reconciliation has one sub-row per bank account */}
        {rec.sub_items && !isTbGl && (
          <div className="space-y-2">
            <div className="grid grid-cols-12 gap-2 text-[11px] uppercase tracking-wider text-slate-500 px-3 py-1.5">
              <div className="col-span-3">{t('rec.bankAccount')}</div>
              <div className="col-span-3 text-right">{t('rec.tbClosing')}</div>
              <div className="col-span-3 text-right">{t('rec.statementClosing')}</div>
              <div className="col-span-2 text-right">{t('rec.diff')}</div>
              <div className="col-span-1 text-center">{t('rec.status')}</div>
            </div>
            {rec.sub_items.map((sub) => {
              const hasStatement = !!sub.counter_dataset_id;
              const hasVar = sub.diff != null && Math.abs(sub.diff) >= 100;
              return (
                <div key={sub.account_code} className="space-y-1">
                  <div className="grid grid-cols-12 gap-2 items-center px-3 py-2 border border-slate-100 rounded text-xs">
                    <div className="col-span-3">
                      <div className="font-mono font-semibold">{sub.account_code}</div>
                      <div className="text-[10px] text-slate-500">{sub.account_name}</div>
                    </div>
                    <div className="col-span-3 text-right font-mono">{formatXAF(sub.ref_amount)}</div>
                    <div className="col-span-3 text-right">
                      {hasStatement ? (
                        <>
                          <span className="font-mono font-semibold">
                            {sub.counter_amount != null ? formatXAF(sub.counter_amount) : '—'}
                          </span>
                          {sub.counter_filename && (
                            <div className="text-[9px] text-slate-400 truncate" title={sub.counter_filename}>
                              📎 {sub.counter_filename}
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-slate-400 italic text-[11px]">{t('rec.noStatement')}</span>
                      )}
                    </div>
                    <div className={cn(
                      'col-span-2 text-right font-mono',
                      sub.diff == null ? 'text-slate-300'
                      : Math.abs(sub.diff) < 100 ? 'text-emerald-600'
                      : 'text-rose-600',
                    )}>
                      {sub.diff == null ? '—' : formatXAF(sub.diff)}
                    </div>
                    <div className="col-span-1 flex justify-center">{statusIcon(sub.status)}</div>
                  </div>
                  {/* Red-flag callout when a variance exists */}
                  {hasStatement && hasVar && (
                    <div className="ml-3 px-3 py-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-700 flex items-start gap-2">
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                      <div>{t('rec.bankReqReconciliation')}</div>
                    </div>
                  )}
                </div>
              );
            })}

            {/* Bank totals row */}
            <div className="grid grid-cols-12 gap-2 items-center px-3 py-2 bg-slate-50 rounded text-xs font-semibold border-t-2 border-slate-200">
              <div className="col-span-3">{t('rec.total')}</div>
              <div className="col-span-3 text-right font-mono">{formatXAF(rec.ref_amount)}</div>
              <div className="col-span-3 text-right font-mono">
                {rec.counter_amount != null ? formatXAF(rec.counter_amount) : '—'}
              </div>
              <div className={cn(
                'col-span-2 text-right font-mono',
                rec.diff == null ? 'text-slate-400'
                : Math.abs(rec.diff) < 100 ? 'text-emerald-600'
                : 'text-rose-600',
              )}>
                {rec.diff == null ? '—' : formatXAF(rec.diff)}
              </div>
              <div className="col-span-1" />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function RecRow({
  refLabel, refAmount, counterLabel, counterAmount, counterFilename,
  diff, isCount, status,
}: {
  refLabel: string; refAmount: number; counterLabel: string; counterAmount: number | null;
  counterFilename?: string;
  diff: number | null; isCount?: boolean;
  status: 'ALIGNED' | 'DISCREPANCY' | 'MISSING';
}) {
  const t = useT();
  return (
    <div className="grid grid-cols-3 gap-4">
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">{refLabel}</div>
        <div className="text-xl font-bold font-display mt-1">
          {isCount ? refAmount : formatXAF(refAmount)}
        </div>
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">{counterLabel}</div>
        {counterAmount != null ? (
          <div className={cn(
            'text-xl font-bold font-display mt-1',
            isCount && counterAmount === 0 ? 'text-emerald-600' :
            isCount && counterAmount !== 0 ? 'text-rose-600' : '',
          )}>
            {isCount ? counterAmount : formatXAF(counterAmount)}
          </div>
        ) : (
          <div className="text-sm text-slate-400 italic mt-2">{t('rec.noFile')}</div>
        )}
        {counterFilename && (
          <div className="text-[10px] text-slate-400 mt-1 truncate">{counterFilename}</div>
        )}
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">{t('rec.diff')}</div>
        <div className={cn(
          'text-xl font-bold font-display mt-1',
          diff == null ? 'text-slate-300'
          : Math.abs(diff) < 100 ? 'text-emerald-600'
          : 'text-rose-600',
        )}>
          {diff == null ? '—' : (isCount ? diff : formatXAF(diff) + ' FCFA')}
        </div>
        {status === 'DISCREPANCY' && diff != null && !isCount && (
          <div className="text-[11px] text-rose-600 mt-1">
            {diff > 0 ? t('rec.over') : t('rec.under')}
          </div>
        )}
      </div>
    </div>
  );
}


/**
 * Collapsible "Show accounts" dropdown for AP / AR / Inventory rec cards.
 * Surfaces every TB account that contributes to the aggregate, sorted by
 * absolute amount descending. If the parent rec has a non-zero variance,
 * the card glows red to signal that the variance is unresolved at the total
 * level (we don't have per-account variance here since the counter is a single
 * uploaded total).
 */
function AccountBreakdownDropdown({
  breakdown, recStatus, recDiff,
}: {
  breakdown: AccountBreakdownRow[];
  recStatus: 'ALIGNED' | 'DISCREPANCY' | 'MISSING';
  recDiff: number | null;
}) {
  const t = useT();
  const [open, setOpen] = useState(recStatus === 'DISCREPANCY');
  const hasVariance = recStatus === 'DISCREPANCY' && recDiff != null;

  return (
    <div className={cn('mt-4 border-t pt-3', hasVariance ? 'border-rose-200' : 'border-slate-200')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-navy hover:underline"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {open ? t('rec.hideAccounts') : t('rec.showAccounts')}
        <span className="text-slate-500 font-normal">
          ({breakdown.length} {t('rec.accountsContributing')})
        </span>
      </button>

      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-500">
                <th className="text-left px-3 py-2 w-32">{t('rec.tbgl.account')}</th>
                <th className="text-left px-3 py-2">{/* libellé */}</th>
                <th className="text-right px-3 py-2 w-40">{t('rec.amount')}</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.map((b) => (
                <tr key={b.account_code} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono font-semibold">{b.account_code}</td>
                  <td className="px-3 py-1.5 text-slate-600">{b.account_name}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{formatXAF(b.amount)}</td>
                </tr>
              ))}
              <tr className="bg-slate-50 border-t-2 border-slate-300 font-semibold">
                <td colSpan={2} className="px-3 py-2 text-xs">{t('rec.total')}</td>
                <td className="px-3 py-2 text-right font-mono">
                  {formatXAF(breakdown.reduce((s, b) => s + b.amount, 0))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


function TbGlRollforward({ rec }: { rec: ReconciliationResult }) {
  const t = useT();
  const subs = rec.sub_items ?? [];
  const summary = rec.rollforward_summary;
  const variances = subs.filter((s) => s.status === 'DISCREPANCY');
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? subs : variances.length ? variances : subs.slice(0, 5);

  return (
    <div className="space-y-3">
      {/* Headline summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-2">
        <SummaryStat label={t('rec.tbgl.accountsExamined')} value={summary?.accounts_examined ?? subs.length} />
        <SummaryStat
          label={t('rec.tbgl.accountsInVariance')}
          value={summary?.accounts_in_variance ?? variances.length}
          tone={variances.length ? 'err' : 'ok'}
        />
        <SummaryStat
          label={t('rec.tbgl.expectedClose')}
          value={formatXAF(rec.ref_amount)}
          mono
        />
        <SummaryStat
          label={t('rec.tbgl.actualClose')}
          value={formatXAF(rec.counter_amount ?? 0)}
          mono
        />
      </div>

      {/* Per-account table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-500">
              <th className="text-left px-3 py-2 w-32">{t('rec.tbgl.account')}</th>
              <th className="text-left px-3 py-2">{/* name */}</th>
              <th className="text-right px-3 py-2">{t('rec.tbgl.opening')}</th>
              <th className="text-right px-3 py-2">{t('rec.tbgl.movements')}</th>
              <th className="text-right px-3 py-2">{t('rec.tbgl.expectedClose')}</th>
              <th className="text-right px-3 py-2">{t('rec.tbgl.actualClose')}</th>
              <th className="text-right px-3 py-2">{t('rec.tbgl.variance')}</th>
              <th className="text-center px-3 py-2">{t('rec.status')}</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((s) => (
              <tr
                key={s.account_code}
                className={cn(
                  'border-b border-slate-100',
                  s.status === 'DISCREPANCY' ? 'bg-rose-50/40' : 'hover:bg-slate-50',
                )}
              >
                <td className="px-3 py-1.5 font-mono font-semibold">{s.account_code}</td>
                <td className="px-3 py-1.5 text-slate-600">{s.account_name}</td>
                <td className="px-3 py-1.5 text-right font-mono">{formatXAF(s.opening_amount ?? 0)}</td>
                <td className="px-3 py-1.5 text-right font-mono">{formatXAF(s.movement_amount ?? 0)}</td>
                <td className="px-3 py-1.5 text-right font-mono">{formatXAF(s.expected_close ?? 0)}</td>
                <td className="px-3 py-1.5 text-right font-mono">{formatXAF(s.actual_close ?? 0)}</td>
                <td className={cn(
                  'px-3 py-1.5 text-right font-mono font-semibold',
                  s.diff == null ? 'text-slate-300'
                  : Math.abs(s.diff) < 1 ? 'text-emerald-600'
                  : 'text-rose-600',
                )}>
                  {s.diff == null ? '—' : formatXAF(s.diff)}
                </td>
                <td className="px-3 py-1.5 text-center">{statusIcon(s.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* If everything balances OR there are >5 rows, allow toggling full view */}
      {(variances.length === 0 && subs.length > 5) || (variances.length > 0 && subs.length > variances.length) ? (
        <div className="text-center">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="text-[11px] text-navy underline hover:no-underline"
          >
            {showAll
              ? `Voir uniquement les écarts (${variances.length})`
              : `Voir tous les comptes (${subs.length})`}
          </button>
        </div>
      ) : null}

      {variances.length === 0 && (
        <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded p-2 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          {t('rec.tbgl.allAligned')}
        </div>
      )}
    </div>
  );
}

function SummaryStat({
  label, value, tone = 'neutral', mono = false,
}: {
  label: string;
  value: string | number;
  tone?: 'ok' | 'warn' | 'err' | 'neutral';
  mono?: boolean;
}) {
  const cls =
    tone === 'err' ? 'text-rose-600'
    : tone === 'warn' ? 'text-amber-600'
    : tone === 'ok' ? 'text-emerald-600'
    : 'text-slate-900';
  return (
    <div className="border border-slate-200 rounded p-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={cn('font-bold text-base mt-0.5', cls, mono && 'font-mono text-sm')}>{value}</div>
    </div>
  );
}


function CounterAmountInput({
  datasetId, initial, onSave, saving,
}: {
  datasetId: string;
  initial: number | null;
  onSave: (id: string, amount: number) => void;
  saving: boolean;
}) {
  const [value, setValue] = useState(initial?.toString() ?? '');
  const [dirty, setDirty] = useState(false);

  return (
    <div className="flex items-center gap-1 mt-1">
      <input
        type="number"
        value={value}
        onChange={(e) => { setValue(e.target.value); setDirty(true); }}
        placeholder="0"
        className="w-32 text-right text-sm font-mono border border-slate-200 rounded px-2 py-1 focus:outline-none focus:border-navy"
      />
      <span className="text-[10px] text-slate-400">FCFA</span>
      {dirty && (
        <Button
          size="sm" variant="outline"
          disabled={saving}
          onClick={() => {
            const v = parseFloat(value || '0');
            if (!isNaN(v)) {
              onSave(datasetId, v);
              setDirty(false);
            }
          }}
        >
          OK
        </Button>
      )}
    </div>
  );
}


/**
 * Reconciling-items panel — surfaces Claude's categorization of variances
 * per standard reconciliation methodology (TIMING / POSTING_ERROR / OMISSION /
 * FX_GAIN_LOSS / INTERCOMPANY_UNMATCHED / OTHER) with aging + escalation.
 */
function RecItemsPanel({ analysis }: { analysis: RecItemsAnalysis }) {
  const t = useT();
  const [open, setOpen] = useState(true);

  const catLabel: Record<RecItemsAnalysis['items'][number]['category'], { fr: string; en: string; color: string }> = {
    TIMING:                  { fr: 'Décalage temporel',        en: 'Timing difference',        color: 'bg-sky-100 text-sky-800 border-sky-200' },
    POSTING_ERROR:           { fr: "Erreur d'imputation",      en: 'Posting error',            color: 'bg-rose-100 text-rose-800 border-rose-200' },
    OMISSION:                { fr: 'Omission',                  en: 'Omission',                 color: 'bg-amber-100 text-amber-800 border-amber-200' },
    FX_GAIN_LOSS:            { fr: 'Différence de change',     en: 'FX gain/loss',             color: 'bg-purple-100 text-purple-800 border-purple-200' },
    INTERCOMPANY_UNMATCHED:  { fr: 'Intercompagnie non lettré', en: 'Intercompany unmatched',  color: 'bg-indigo-100 text-indigo-800 border-indigo-200' },
    OTHER:                   { fr: 'Autre',                     en: 'Other',                    color: 'bg-slate-100 text-slate-700 border-slate-200' },
  };

  const ageLabel: Record<RecItemsAnalysis['items'][number]['aging_bucket'], string> = {
    ZERO_TO_30:        '0–30 j',
    THIRTY_ONE_TO_60:  '31–60 j',
    SIXTY_ONE_TO_90:   '61–90 j',
    OVER_90:           '> 90 j',
    UNKNOWN:           '—',
  };

  // No items + clean summary = trivial, hide the whole panel.
  if (analysis.source === 'trivial' && analysis.items.length === 0) return null;

  return (
    <div className={cn(
      'mt-4 border rounded-lg overflow-hidden',
      analysis.escalation ? 'border-rose-300 bg-rose-50/30' : 'border-slate-200 bg-slate-50/30',
    )}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-slate-50 transition"
      >
        {open ? <ChevronDown className="w-4 h-4 text-navy" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
        <div className="flex-1">
          <div className="text-xs font-semibold text-slate-900 flex items-center gap-2">
            {t('rec.items.title')}
            {analysis.escalation && (
              <Badge variant="err" className="text-[10px]">{t('rec.items.escalation')}</Badge>
            )}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">{analysis.summary}</div>
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          {analysis.items.length} {t('rec.items.itemsLabel')}
        </span>
      </button>
      {open && analysis.items.length > 0 && (
        <div className="border-t border-slate-200 divide-y divide-slate-100 bg-white">
          {analysis.items.map((it, i) => {
            const cat = catLabel[it.category] || catLabel.OTHER;
            return (
              <div key={i} className="px-4 py-3 text-xs">
                <div className="flex items-start gap-2 flex-wrap">
                  <span className={cn('px-2 py-0.5 rounded text-[10px] font-semibold border', cat.color)}>
                    {cat.fr}
                  </span>
                  <span className={cn(
                    'px-1.5 py-0.5 rounded text-[10px] font-mono border',
                    it.likelihood === 'HIGH'   ? 'border-rose-300 text-rose-700'
                    : it.likelihood === 'LOW'  ? 'border-slate-300 text-slate-500'
                    : 'border-amber-300 text-amber-700',
                  )}>
                    {it.likelihood}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600">
                    {ageLabel[it.aging_bucket]}
                  </span>
                  <span className="ml-auto font-mono font-semibold">
                    {formatXAF(it.estimated_amount_xaf)}
                  </span>
                </div>
                <div className="mt-1.5 text-slate-700">{it.description}</div>
                <div className="mt-1 text-[11px] text-slate-500 italic">
                  ➜ {it.action}
                </div>
              </div>
            );
          })}
          <div className="px-4 py-2 bg-slate-50 text-[10px] text-slate-400 font-mono flex items-center justify-between">
            <span>{t('rec.items.materiality')} : {formatXAF(analysis.materiality_xaf)} FCFA</span>
            <span>{t('rec.items.source')}: {analysis.source}</span>
          </div>
        </div>
      )}
    </div>
  );
}
