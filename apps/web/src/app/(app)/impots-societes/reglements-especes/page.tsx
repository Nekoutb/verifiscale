'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Building2, Info, FileWarning, ShieldCheck, ShieldX, ShieldAlert,
  ChevronDown, ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';

interface SimilarEntry {
  piece_number: string;
  line_number: number;
  account_code: string;
  account_name: string | null;
  libelle: string | null;
  amount_xaf: number;
  year: number | null;
  date: string | null;
  match_score: number;
  match_reasons: string[];
}

interface CashLine {
  pi_number: string;
  pi_date: string | null;
  line_number: number;
  account_code: string;
  account_name: string | null;
  libelle: string | null;
  amount_xaf: number;
  counter_supplier_niu: string | null;
  counter_supplier_name: string | null;
  tag: 'CONFIRMED' | 'LIKELY' | 'REVIEW';
  per_piece_total_xaf: number;
  per_piece_breach: boolean;
  cash_credit_total_xaf: number;
  cash_credit_breach: boolean;
  account_class_code: string;
  account_class_label: string;
  estimated_reintegration_xaf: number;
  // Lettre DGI 2011
  excluded: boolean;
  exclusion_kind: string | null;
  current_year: 'YES' | 'NO' | 'UNKNOWN';
  current_year_source: 'AUTO' | 'MANUAL';
  current_year_confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  current_year_reason: string;
  similar_entries: SimilarEntry[];
  is_supplement_xaf: number;
  ircm_xaf: number;
  total_penalty_xaf: number;
}

interface SupplierAgg {
  key: string;
  counter_supplier_niu: string | null;
  counter_supplier_name: string;
  line_count: number;
  piece_count: number;
  total_amount_xaf: number;
  estimated_reintegration_xaf: number;
}

interface ByClassAgg {
  class_code: string;
  class_label: string;
  line_count: number;
  total_amount_xaf: number;
}

interface CashResp {
  threshold_xaf: number;
  debit_classes_tested: string[];
  source_dataset_id: string | null;
  source_filename: string | null;
  fiscal_year?: number | null;
  lines: CashLine[];
  by_supplier: SupplierAgg[];
  by_class: ByClassAgg[];
  summary: {
    threshold_xaf: number;
    debit_classes_tested: string[];
    lines_tested_count: number;
    confirmed_count: number;
    likely_count: number;
    review_count: number;
    supplier_count: number;
    cash_credit_breach_piece_count: number;
    total_amount_xaf: number;
    estimated_reintegration_xaf: number;
    excluded_count: number;
    excluded_by_kind: { SALARY: number; MISSION: number; ADMIN_FEE: number; OTHER: number };
    current_year_yes_count: number;
    current_year_no_count: number;
    current_year_unknown_count: number;
    reintegration_xaf: number;
    is_supplement_xaf: number;
    ircm_xaf: number;
    total_penalty_xaf: number;
    is_rate_pct: number;
    ircm_rate_pct: number;
  } | null;
  note?: string;
  legal_reference?: string;
}

export default function CashPaymentsPage() {
  const t = useT();
  const { currentCase } = useApp();
  const qc = useQueryClient();
  const [openLine, setOpenLine] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['cash-payments', currentCase?.id],
    queryFn: () => api<CashResp>(`/audit-cases/${currentCase!.id}/cash-payments`),
    enabled: !!currentCase,
  });

  const overrideMut = useMutation({
    mutationFn: async (body: any) => api(`/audit-cases/${currentCase!.id}/cash-payments/line`,
      { method: 'PATCH', body }),
    onSuccess: () => { void refetch(); void qc.invalidateQueries({ queryKey: ['cash-payments'] }); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" />
        {t('nav.corporateTax')}
      </Link>

      <div>
        <h1 className="font-display text-2xl font-extrabold flex items-center gap-2 text-black tracking-tight">
          <Building2 className="w-6 h-6 text-black" />
          {t('cash.title')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">{t('cash.subtitle')}</p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-center py-10 text-slate-500">{t('data.noCaseTitle')}</div></CardContent></Card>
      )}

      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">{t('app.loading')}</div></CardContent></Card>
      )}

      {data?.note && (
        <Card><CardContent>
          <div className="flex items-start gap-3 py-2">
            <FileWarning className="w-5 h-5 text-black flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-700">{data.note}</div>
          </div>
        </CardContent></Card>
      )}

      {data?.summary && (
        <>
          {/* KPIs : 2 lignes — la 1ʳᵉ classique, la 2ᵈ avec la bifurcation Lettre 2011 */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <KPI label={t('cash.kpi.linesTested')}     value={data.summary.lines_tested_count} />
            <KPI label="Exclues (lettre 2011)"          value={data.summary.excluded_count}
                 tone={data.summary.excluded_count ? 'warn' : 'neutral'} />
            <KPI label="Rattachées exercice (oui)"      value={data.summary.current_year_yes_count}
                 tone={data.summary.current_year_yes_count ? 'err' : 'ok'} />
            <KPI label="Non rattachées"                 value={data.summary.current_year_no_count}
                 tone={data.summary.current_year_no_count ? 'warn' : 'ok'} />
            <KPI label="Σ rattachées (réintég.)"        value={formatXAF(data.summary.reintegration_xaf)}
                 tone={data.summary.reintegration_xaf > 0 ? 'err' : 'ok'} />
            <KPI label="Σ pénalité totale"               value={formatXAF(data.summary.total_penalty_xaf)}
                 tone={data.summary.total_penalty_xaf > 0 ? 'err' : 'ok'} />
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPI label={`IS additionnel (${data.summary.is_rate_pct}%)`}
                 value={formatXAF(data.summary.is_supplement_xaf)} tone="warn" />
            <KPI label={`IRCM (${data.summary.ircm_rate_pct}%)`}
                 value={formatXAF(data.summary.ircm_xaf)} tone="warn" />
            <KPI label="Pièces avec crédit-caisse > 100K"
                 value={data.summary.cash_credit_breach_piece_count}
                 tone={data.summary.cash_credit_breach_piece_count ? 'warn' : 'ok'} />
            <KPI label="Σ montant brut testé"           value={formatXAF(data.summary.total_amount_xaf)} />
          </div>

          {/* Bandeau exceptions Lettre DGI 2011 */}
          {data.summary.excluded_count > 0 && (
            <Card>
              <CardContent>
                <div className="text-xs text-slate-700">
                  <b>Lettre DGI N° 5333/MINFI/DGI/LC/L du 04/08/2011</b> — {data.summary.excluded_count} ligne(s) automatiquement
                  exclue(s) du contrôle Art. 7 bis :
                  <span className="ml-2">
                    {data.summary.excluded_by_kind.SALARY > 0 && <span className="mr-2"><b>{data.summary.excluded_by_kind.SALARY}</b> salaires (661-668)</span>}
                    {data.summary.excluded_by_kind.MISSION > 0 && <span className="mr-2"><b>{data.summary.excluded_by_kind.MISSION}</b> missions (6384)</span>}
                    {data.summary.excluded_by_kind.ADMIN_FEE > 0 && <span className="mr-2"><b>{data.summary.excluded_by_kind.ADMIN_FEE}</b> jetons CA (6581)</span>}
                    {data.summary.excluded_by_kind.OTHER > 0 && <span className="mr-2"><b>{data.summary.excluded_by_kind.OTHER}</b> autres (manuel)</span>}
                  </span>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="text-xs text-slate-500">
            {t('cash.source')} : <span className="font-mono">{data.source_filename}</span>
            {' · '}
            {t('cash.threshold')} : <span className="font-mono">{formatXAF(data.threshold_xaf)} FCFA</span>
            {data.fiscal_year && (<>{' · '}Exercice contrôlé : <span className="font-mono">{data.fiscal_year}</span></>)}
            {' · '}
            <span className="italic">{data.legal_reference || 'CGI Cameroun, Art. 7 bis'}</span>
          </div>

          {/* Per-class breakdown */}
          {data.by_class.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t('cash.byClass.title')}</CardTitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                      <th className="px-3 py-2.5">{t('cash.byClass.classCode')}</th>
                      <th className="px-3 py-2.5">{t('cash.byClass.classLabel')}</th>
                      <th className="px-3 py-2.5 text-right">{t('cash.bySupplier.lines')}</th>
                      <th className="px-3 py-2.5 text-right">{t('cash.byClass.total')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_class.map((c) => (
                      <tr key={c.class_code} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-3 py-2 font-mono font-bold">{c.class_code}XXX</td>
                        <td className="px-3 py-2 text-slate-800">{c.class_label}</td>
                        <td className="px-3 py-2 text-right font-mono">{c.line_count}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums font-bold text-black">
                          {formatXAF(c.total_amount_xaf)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {data.by_supplier.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t('cash.bySupplier.title')}</CardTitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                      <th className="px-3 py-2.5">{t('cash.bySupplier.supplier')}</th>
                      <th className="px-3 py-2.5">{t('cash.bySupplier.niu')}</th>
                      <th className="px-3 py-2.5 text-right">{t('cash.bySupplier.pieces')}</th>
                      <th className="px-3 py-2.5 text-right">{t('cash.bySupplier.lines')}</th>
                      <th className="px-3 py-2.5 text-right">{t('cash.bySupplier.totalHT')}</th>
                      <th className="px-3 py-2.5 text-right">{t('cash.bySupplier.reintegration')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_supplier.map((s) => (
                      <tr key={s.key} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-3 py-2 font-medium text-slate-800">{s.counter_supplier_name}</td>
                        <td className="px-3 py-2 font-mono text-[11px]">{s.counter_supplier_niu || '—'}</td>
                        <td className="px-3 py-2 text-right font-mono">{s.piece_count}</td>
                        <td className="px-3 py-2 text-right font-mono">{s.line_count}</td>
                        <td className="px-3 py-2 text-right font-mono">{formatXAF(s.total_amount_xaf)}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums font-bold text-black">
                          {formatXAF(s.estimated_reintegration_xaf)}
                        </td>
                      </tr>
                    ))}
                    <tr className="bg-neutral-50 border-t-2 border-black font-bold">
                      <td colSpan={4} className="px-3 py-3 text-right uppercase tracking-wider text-black">
                        {t('rec.total')}
                      </td>
                      <td className="px-3 py-3 text-right font-mono tabular-nums text-black">
                        {formatXAF(data.by_supplier.reduce((s, r) => s + r.total_amount_xaf, 0))}
                      </td>
                      <td className="px-3 py-3 text-right font-mono tabular-nums text-black font-extrabold underline decoration-2 underline-offset-2">
                        {formatXAF(data.summary.estimated_reintegration_xaf)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>{t('cash.lines.title')}</CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2.5">{t('cash.col.tag')}</th>
                    <th className="px-3 py-2.5">{t('cash.col.piece')}</th>
                    <th className="px-3 py-2.5">{t('cash.col.date')}</th>
                    <th className="px-3 py-2.5">{t('cash.col.class')}</th>
                    <th className="px-3 py-2.5">{t('cash.col.account')}</th>
                    <th className="px-3 py-2.5">{t('cash.col.libelle')}</th>
                    <th className="px-3 py-2.5">{t('cash.col.niu')}</th>
                    <th className="px-3 py-2.5 text-right">{t('cash.col.amount')}</th>
                    <th className="px-3 py-2.5 text-right">{t('cash.col.amount')}</th>
                    <th className="px-3 py-2.5">Rattachement exercice</th>
                    <th className="px-3 py-2.5 text-right">IS suppl. (33 %)</th>
                    <th className="px-3 py-2.5 text-right">IRCM (16,5 %)</th>
                    <th className="px-3 py-2.5 text-right">Pénalité totale</th>
                    <th className="px-3 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {data.lines.map((l, i) => {
                    const lineKey = `${l.pi_number}::${l.line_number}::${i}`;
                    const isOpen = openLine === lineKey;
                    return (
                    <>
                    <tr key={lineKey} className={cn('border-b border-neutral-100 hover:bg-neutral-50',
                      l.excluded && 'bg-neutral-50 opacity-70',
                      !l.excluded && l.current_year === 'YES' && 'bg-neutral-100/50',
                      !l.excluded && l.current_year === 'NO' && 'bg-neutral-50/60')}>
                      <td className="px-3 py-2">
                        {l.excluded ? <Badge variant="neutral">Exclue ({l.exclusion_kind})</Badge> : <TagBadge tag={l.tag} />}
                      </td>
                      <td className="px-3 py-2 font-mono">{l.pi_number}</td>
                      <td className="px-3 py-2">{formatDate(l.pi_date) || '—'}</td>
                      <td className="px-3 py-2">
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[10px]">
                          {l.account_class_code}XXX
                        </span>
                        <div className="text-[10px] text-slate-500 mt-0.5">{l.account_class_label}</div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-mono">{l.account_code}</div>
                        <div className="text-[10px] text-slate-500">{l.account_name || ''}</div>
                      </td>
                      <td className="px-3 py-2 text-slate-700 max-w-[220px] truncate" title={l.libelle || ''}>
                        {l.libelle || '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px]">{l.counter_supplier_niu || '—'}</td>
                      <td className="px-3 py-2 text-right font-mono font-semibold">
                        {formatXAF(l.amount_xaf)}
                      </td>
                      <td className="px-3 py-2">
                        {l.excluded ? (
                          <span className="text-[10px] text-slate-400 italic">hors périmètre</span>
                        ) : (
                          <CurrentYearBadge cy={l.current_year} confidence={l.current_year_confidence}
                                            source={l.current_year_source} reason={l.current_year_reason} />
                        )}
                      </td>
                      <td className={cn('px-3 py-2 text-right font-mono tabular-nums',
                          l.is_supplement_xaf > 0 ? 'text-black font-bold' : 'text-neutral-400')}>
                        {l.is_supplement_xaf > 0 ? formatXAF(l.is_supplement_xaf) : '—'}
                      </td>
                      <td className={cn('px-3 py-2 text-right font-mono tabular-nums',
                          l.ircm_xaf > 0 ? 'text-neutral-800' : 'text-neutral-400')}>
                        {l.ircm_xaf > 0 ? formatXAF(l.ircm_xaf) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums font-extrabold text-black">
                        {l.total_penalty_xaf > 0 ? formatXAF(l.total_penalty_xaf) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => setOpenLine(isOpen ? null : lineKey)}
                          className="text-black text-[10px] hover:underline inline-flex items-center gap-0.5">
                          {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          {isOpen ? 'fermer' : 'détail'}
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr key={`${lineKey}-detail`} className="bg-slate-50 border-b border-slate-200">
                        <td colSpan={13} className="px-4 py-3">
                          <CashLineDetail line={l} onOverride={(body) => overrideMut.mutate({
                            piece_number: l.pi_number, line_number: l.line_number, ...body,
                          })} />
                        </td>
                      </tr>
                    )}
                    </>
                  );})}
                  {data.lines.length === 0 && (
                    <tr><td colSpan={13} className="px-3 py-8 text-center text-slate-500 italic">{t('cash.empty')}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>{t('cash.legalNote')}</span>
          </div>
        </>
      )}
    </div>
  );
}

function TagBadge({ tag }: { tag: 'CONFIRMED' | 'LIKELY' | 'REVIEW' }) {
  const t = useT();
  if (tag === 'CONFIRMED') return <Badge variant="err">{t('cash.tag.confirmed')}</Badge>;
  if (tag === 'LIKELY')    return <Badge variant="warn">{t('cash.tag.likely')}</Badge>;
  return <Badge variant="neutral">{t('cash.tag.review')}</Badge>;
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

function CurrentYearBadge({ cy, confidence, source, reason }: {
  cy: 'YES' | 'NO' | 'UNKNOWN'; confidence: string; source: string; reason: string;
}) {
  const pip = confidence === 'HIGH' ? '●●●' : confidence === 'MEDIUM' ? '●●○' : '●○○';
  if (cy === 'YES') return (
    <span title={reason} className="inline-flex flex-col items-start">
      <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-black bg-transparent text-black font-extrabold">
        <ShieldX className="w-3 h-3" /> Exercice : OUI
      </span>
      <span className="text-[9px] text-neutral-500 mt-0.5 tracking-widest">{pip} {confidence}{source === 'MANUAL' && ' · override'}</span>
    </span>
  );
  if (cy === 'NO') return (
    <span title={reason} className="inline-flex flex-col items-start">
      <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 bg-transparent text-neutral-700 font-medium">
        <ShieldCheck className="w-3 h-3" /> Exercice : NON
      </span>
      <span className="text-[9px] text-neutral-500 mt-0.5 tracking-widest">{pip} {confidence}{source === 'MANUAL' && ' · override'}</span>
    </span>
  );
  return (
    <span title={reason} className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 bg-transparent text-neutral-600 font-medium">
      <ShieldAlert className="w-3 h-3" /> ?
    </span>
  );
}

function CashLineDetail({ line, onOverride }: {
  line: CashLine;
  onOverride: (body: any) => void;
}) {
  const [reason, setReason] = useState('');
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Diagnostic + similar entries */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
          Diagnostic automatique
        </div>
        <div className="bg-white border border-slate-200 rounded p-2 text-xs mb-2">
          {line.current_year_reason}
        </div>
        {line.similar_entries && line.similar_entries.length > 0 && (
          <>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
              Écritures GL similaires trouvées ({line.similar_entries.length})
            </div>
            <div className="bg-white border border-slate-200 rounded text-[11px] divide-y divide-slate-100">
              {line.similar_entries.map((s, i) => (
                <div key={i} className="px-2 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-600">{s.piece_number}/L{s.line_number}</span>
                    <span className="text-[9px] px-1 rounded bg-slate-100">{s.account_code}</span>
                    <span className="font-mono">{formatXAF(s.amount_xaf)}</span>
                    <span className="text-slate-500">{s.year}</span>
                    <span className="text-[9px] text-slate-400">score {s.match_score}</span>
                  </div>
                  <div className="text-[10px] text-slate-500 truncate" title={s.libelle || ''}>{s.libelle}</div>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {s.match_reasons.map((r, j) => (
                      <span key={j} className="text-[9px] px-1 py-0 rounded border border-neutral-300 text-neutral-700">{r}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      {/* Actions auditeur */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
          Décision auditeur
        </div>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="Motivation (recommandé pour tout override)…"
          className="w-full text-xs p-2 border border-slate-300 rounded h-14 mb-2" />
        <div className="flex flex-wrap gap-1.5">
          <button onClick={() => onOverride({ current_year_decision: 'YES', decision_reason: reason })}
            className="px-2 py-1 text-[11px] rounded bg-black text-white border border-black hover:bg-neutral-800">
            Forcer : OUI exercice
          </button>
          <button onClick={() => onOverride({ current_year_decision: 'NO', decision_reason: reason })}
            className="px-2 py-1 text-[11px] rounded border border-black text-black bg-transparent hover:bg-neutral-50">
            Forcer : NON exercice
          </button>
          <button onClick={() => onOverride({ excluded: true, exclusion_kind: 'OTHER', decision_reason: reason })}
            className="px-2 py-1 text-[11px] rounded bg-neutral-200 text-neutral-700 hover:bg-neutral-300">
            Exclure du contrôle
          </button>
          <button onClick={() => onOverride({ excluded: false, current_year_decision: null, decision_reason: '' })}
            className="px-2 py-1 text-[11px] rounded border border-neutral-300 text-neutral-700 hover:border-black">
            Réinitialiser (auto)
          </button>
        </div>
        <div className="mt-2 text-[10px] text-slate-500">
          {line.current_year === 'YES' && <>Si <b>OUI</b> : IS 33 % + IRCM 16,5 % sur {formatXAF(line.amount_xaf)} = {formatXAF(line.amount_xaf * 0.495)}</>}
          {line.current_year === 'NO' && <>Si <b>NON</b> : IRCM 16,5 % seul sur {formatXAF(line.amount_xaf)} = {formatXAF(line.amount_xaf * 0.165)}</>}
        </div>
      </div>
    </div>
  );
}
