'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Building2, AlertTriangle, CheckCircle2, FileWarning } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';

interface AmortRow {
  reference: string;
  name: string;
  acquisition_date: string | null;
  disposal_date: string | null;
  gross_value_xaf: number;
  accumulated_depreciation_xaf: number | null;
  register_rate_pct: number | null;
  register_year_depreciation_xaf: number | null;
  fiscal_category_code: string;
  fiscal_category_label_fr: string;
  fiscal_category_label_en: string;
  prescribed_rate_pct: number;
  rate_match: boolean;
  rate_match_delta_pp: number;
  recomputed_year_depreciation_xaf: number;
  variance_xaf: number;
}

interface AmortResp {
  fiscal_year: number;
  source_dataset_id: string | null;
  source_filename: string | null;
  rows: AmortRow[];
  summary: {
    asset_count: number;
    rate_mismatch_count: number;
    total_register_year_depreciation_xaf: number;
    total_recomputed_year_depreciation_xaf: number;
    total_variance_xaf: number;
    total_variance_abs_xaf: number;
    fiscal_year: number;
  } | null;
  note?: string;
}

export default function AmortissementsPage() {
  const t = useT();
  const { currentCase, locale } = useApp();

  const { data, isLoading } = useQuery({
    queryKey: ['amortissements', currentCase?.id],
    queryFn: () => api<AmortResp>(`/audit-cases/${currentCase!.id}/amortissements`),
    enabled: !!currentCase,
  });

  return (
    <div className="space-y-6">
      <Link
        href="/impots-societes"
        className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        {t('nav.corporateTax')}
      </Link>

      <div>
        <h1 className="font-display text-2xl font-extrabold flex items-center gap-2 text-black tracking-tight">
          <Building2 className="w-6 h-6 text-black" />
          {t('is.amortissements.title')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">{t('is.amortissements.subtitle')}</p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-center py-10 text-slate-500">{t('data.noCaseTitle')}</div></CardContent></Card>
      )}

      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">{t('app.loading')}</div></CardContent></Card>
      )}

      {currentCase && data?.note && (
        <Card>
          <CardContent>
            <div className="flex items-start gap-3 py-2">
              <FileWarning className="w-5 h-5 text-black flex-shrink-0 mt-0.5" />
              <div className="text-sm text-slate-700">{data.note}</div>
            </div>
          </CardContent>
        </Card>
      )}

      {data?.summary && (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <KPI label={t('amort.kpiAssets')} value={data.summary.asset_count} />
            <KPI
              label={t('amort.kpiRateMismatch')}
              value={data.summary.rate_mismatch_count}
              tone={data.summary.rate_mismatch_count ? 'err' : 'ok'}
            />
            <KPI label={t('amort.kpiRegisterDep')} value={`${formatXAF(data.summary.total_register_year_depreciation_xaf)}`} />
            <KPI label={t('amort.kpiRecomputedDep')} value={`${formatXAF(data.summary.total_recomputed_year_depreciation_xaf)}`} />
            <KPI
              label={t('amort.kpiVariance')}
              value={formatXAF(data.summary.total_variance_xaf)}
              tone={Math.abs(data.summary.total_variance_xaf) > 1000 ? 'warn' : 'ok'}
            />
          </div>

          {/* Source dataset */}
          <div className="text-xs text-slate-500">
            {t('amort.source')} : <span className="font-mono">{data.source_filename}</span> · {t('app.year')} {data.fiscal_year}
          </div>

          {/* Main table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2.5">{t('amort.col.reference')}</th>
                    <th className="px-3 py-2.5">{t('amort.col.acqDate')}</th>
                    <th className="px-3 py-2.5">{t('amort.col.dispDate')}</th>
                    <th className="px-3 py-2.5">{t('amort.col.name')}</th>
                    <th className="px-3 py-2.5">{t('amort.col.category')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.grossValue')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.accumDep')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.nbv')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.regRate')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.prescribedRate')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.recomputed')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.register')}</th>
                    <th className="px-3 py-2.5 text-right">{t('amort.col.variance')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={`${r.reference}-${i}`} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-3 py-2 font-mono">{r.reference || '—'}</td>
                      <td className="px-3 py-2">{formatDate(r.acquisition_date) || '—'}</td>
                      <td className="px-3 py-2">{formatDate(r.disposal_date) || '—'}</td>
                      <td className="px-3 py-2 font-medium text-slate-800">{r.name}</td>
                      <td className="px-3 py-2">
                        <div className="text-[11px]">{locale === 'fr' ? r.fiscal_category_label_fr : r.fiscal_category_label_en}</div>
                        <div className="text-[9px] font-mono text-slate-400">{r.fiscal_category_code}</div>
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-semibold text-slate-800">
                        {formatXAF(r.gross_value_xaf)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-slate-600">
                        {r.accumulated_depreciation_xaf != null ? formatXAF(r.accumulated_depreciation_xaf) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {r.accumulated_depreciation_xaf != null
                          ? formatXAF(r.gross_value_xaf - r.accumulated_depreciation_xaf)
                          : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {r.register_rate_pct != null ? `${r.register_rate_pct.toFixed(2)} %` : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{r.prescribed_rate_pct.toFixed(2)} %</td>
                      <td className="px-3 py-2 text-right font-mono">{formatXAF(r.recomputed_year_depreciation_xaf)}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {r.register_year_depreciation_xaf != null ? formatXAF(r.register_year_depreciation_xaf) : '—'}
                      </td>
                      <td className={cn(
                        'px-3 py-2 text-right font-mono tabular-nums',
                        Math.abs(r.variance_xaf) < 100 ? 'text-neutral-700'
                        : r.variance_xaf > 0 ? 'text-black font-extrabold underline decoration-2 underline-offset-2'
                        : 'text-black font-semibold',
                      )}>
                        {formatXAF(r.variance_xaf)}
                      </td>
                    </tr>
                  ))}
                  {/* Totals row */}
                  {(() => {
                    const totalGross = data.rows.reduce((s, r) => s + r.gross_value_xaf, 0);
                    const totalAccum = data.rows.reduce((s, r) => s + (r.accumulated_depreciation_xaf || 0), 0);
                    const totalNbv   = totalGross - totalAccum;
                    return (
                      <tr className="bg-slate-50 border-t-2 border-slate-300 font-bold text-[11px]">
                        <td colSpan={5} className="px-3 py-3 text-right uppercase tracking-wider text-slate-700">
                          {t('rec.total')}
                        </td>
                        <td className="px-3 py-3 text-right font-mono">{formatXAF(totalGross)}</td>
                        <td className="px-3 py-3 text-right font-mono">{formatXAF(totalAccum)}</td>
                        <td className="px-3 py-3 text-right font-mono">{formatXAF(totalNbv)}</td>
                        <td colSpan={2} />
                        <td className="px-3 py-3 text-right font-mono">{formatXAF(data.summary.total_recomputed_year_depreciation_xaf)}</td>
                        <td className="px-3 py-3 text-right font-mono">{formatXAF(data.summary.total_register_year_depreciation_xaf)}</td>
                        <td className={cn(
                          'px-3 py-3 text-right font-mono tabular-nums',
                          Math.abs(data.summary.total_variance_xaf) < 1000 ? 'text-neutral-700' : 'text-black font-extrabold underline decoration-2 underline-offset-2',
                        )}>
                          {formatXAF(data.summary.total_variance_xaf)}
                        </td>
                      </tr>
                    );
                  })()}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="text-[11px] text-slate-500 leading-relaxed">
            {t('amort.legalNote')}
          </div>
        </>
      )}

      {data?.summary && data.rows.length === 0 && (
        <Card>
          <CardContent>
            <div className="text-center py-10 text-slate-500">{t('amort.empty')}</div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function KPI({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls =
    tone === 'err'  ? 'text-black font-extrabold border-b-[3px] border-black inline-block pb-0.5'
    : tone === 'warn' ? 'text-black font-semibold'
    : tone === 'ok'   ? 'text-neutral-700 font-medium'
    : 'text-black font-bold';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">{label}</div>
        <div className={`text-base mt-1 font-display tabular-nums ${cls}`}>{value}</div>
      </CardContent>
    </Card>
  );
}
