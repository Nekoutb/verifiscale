'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft, Building2, Info, FileWarning, CheckCircle2, AlertTriangle,
  XCircle, Clock,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';

interface MonthLine {
  month: number;
  period_label: string;
  ca_gl_xaf: number;
  expected_acompte_xaf: number;
  dmm_present: boolean;
  dmm_filing_date: string | null;
  filing_deadline: string;
  declared_acompte_xaf: number;
  ca_dmm_xaf: number | null;
  variance_xaf: number;
  variance_pct: number | null;
  deadline_status: 'ON_TIME' | 'LATE' | 'MISSING' | 'NO_FILING_DATE';
  status: 'OK' | 'VARIANCE_MINOR' | 'VARIANCE_MAJOR' | 'MISSING_DMM' | 'NO_CA';
}

interface AcompteResp {
  fiscal_year: number;
  regime: 'REEL' | 'SIMPLIFIE';
  rate_pct: number;
  revenue_account_prefix: string;
  source_dataset_id: string | null;
  source_filename: string | null;
  months: MonthLine[];
  annual: {
    ca_gl_xaf: number;
    ca_dmm_xaf: number;
    ca_variance_xaf: number;
    ca_variance_pct: number | null;
    expected_total_acompte_xaf: number;
    declared_total_acompte_xaf: number;
    acompte_variance_xaf: number;
    acompte_variance_pct: number | null;
    dmm_present_months: number[];
    dmm_missing_months: number[];
    dmm_count: number;
    tolerance_pct: number;
  };
  summary_status: 'GREEN' | 'AMBER' | 'RED' | 'GREY';
  note?: string;
  legal_reference: string;
}

export default function AcompteIsPage() {
  const t = useT();
  const { currentCase } = useApp();

  const { data, isLoading } = useQuery({
    queryKey: ['acompte-is', currentCase?.id],
    queryFn: () => api<AcompteResp>(`/audit-cases/${currentCase!.id}/acompte-is`),
    enabled: !!currentCase,
  });

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" />
        {t('nav.corporateTax')}
      </Link>

      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Building2 className="w-6 h-6 text-black" />
          Acomptes mensuels IS
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          CGI Cameroun, Art. 21 — 2,2 % (régime du réel) / 5,5 % (régime simplifié) du CA HT mensuel,
          payable au 15 du mois suivant.
        </p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-center py-10 text-slate-500">
          {t('data.noCaseTitle')}
        </div></CardContent></Card>
      )}

      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">
          {t('app.loading')}
        </div></CardContent></Card>
      )}

      {data?.note && (
        <Card><CardContent>
          <div className="flex items-start gap-3 py-2">
            <FileWarning className="w-5 h-5 text-neutral-700 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-700">{data.note}</div>
          </div>
        </CardContent></Card>
      )}

      {data && data.months && (
        <>
          {/* ── KPIs ───────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <KPI label="Régime"
                 value={data.regime === 'REEL' ? 'Réel' : 'Simplifié'}
                 sublabel={`taux ${data.rate_pct.toFixed(1)} %`} />
            <KPI label="Exercice"
                 value={String(data.fiscal_year)} />
            <KPI label="DMM chargées"
                 value={`${data.annual.dmm_count} / 12`}
                 tone={data.annual.dmm_count === 12 ? 'ok' : data.annual.dmm_count >= 9 ? 'warn' : 'err'} />
            <KPI label="CA HT GL annuel"
                 value={formatXAF(data.annual.ca_gl_xaf)} />
            <KPI label="Statut global"
                 value={statusLabel(data.summary_status)}
                 tone={statusTone(data.summary_status)} />
          </div>

          {/* ── Contrôle (c) — recoupement annuel CA GL vs CA DMM ──── */}
          <Card>
            <CardHeader>
              <CardTitle>
                Contrôle (c) — Recoupement annuel : Σ CA comptes 70XX (GL) vs Σ CA déclarés (12 DMM)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 text-sm">
                <Field label="CA GL (Σ crédits 70XX)" value={formatXAF(data.annual.ca_gl_xaf)} />
                <Field label="CA déclaré (Σ 12 DMM)"   value={formatXAF(data.annual.ca_dmm_xaf)} />
                <Field
                  label="Écart"
                  value={formatXAF(data.annual.ca_variance_xaf)}
                  tone={Math.abs(data.annual.ca_variance_pct ?? 0) > data.annual.tolerance_pct ? 'err' : 'ok'}
                />
                <Field
                  label="Écart %"
                  value={data.annual.ca_variance_pct !== null ? `${data.annual.ca_variance_pct.toFixed(2)} %` : '—'}
                  tone={Math.abs(data.annual.ca_variance_pct ?? 0) > data.annual.tolerance_pct ? 'err' : 'ok'}
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-3">
                {Math.abs(data.annual.ca_variance_pct ?? 0) <= data.annual.tolerance_pct ? (
                  <>✅ Recoupement satisfaisant (tolérance ±{data.annual.tolerance_pct} %).</>
                ) : (data.annual.ca_variance_xaf > 0 ? (
                  <>⚠️ CA GL &gt; CA DMM — <b>sous-déclaration au fisc</b> à investiguer ({formatXAF(Math.abs(data.annual.ca_variance_xaf))} non déclaré).</>
                ) : (
                  <>⚠️ CA DMM &gt; CA GL — CA déclaré au fisc <b>non comptabilisé</b> ({formatXAF(Math.abs(data.annual.ca_variance_xaf))} d'écart).</>
                ))}
              </p>
            </CardContent>
          </Card>

          {/* ── Annuel acomptes — projection vs déclarés ───────────── */}
          <Card>
            <CardHeader>
              <CardTitle>
                Acomptes annuels — attendus ({data.rate_pct.toFixed(1)} % × CA GL) vs déclarés
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 text-sm">
                <Field label="Attendu (taux × CA GL)" value={formatXAF(data.annual.expected_total_acompte_xaf)} />
                <Field label="Σ Acomptes DMM"        value={formatXAF(data.annual.declared_total_acompte_xaf)} />
                <Field
                  label="Écart"
                  value={formatXAF(data.annual.acompte_variance_xaf)}
                  tone={data.annual.acompte_variance_xaf < 0 ? 'err' : 'ok'}
                />
                <Field
                  label="Écart %"
                  value={data.annual.acompte_variance_pct !== null ? `${data.annual.acompte_variance_pct.toFixed(2)} %` : '—'}
                  tone={data.annual.acompte_variance_pct !== null && data.annual.acompte_variance_pct < -1 ? 'err' : 'ok'}
                />
              </div>
            </CardContent>
          </Card>

          {/* ── Tableau mensuel — contrôles (a) + (b) ──────────────── */}
          <Card>
            <CardHeader>
              <CardTitle>
                Contrôle mensuel (a) présence DMM · (b) acompte ≈ {data.rate_pct.toFixed(1)} % × Σ 70XX
              </CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2.5">Mois</th>
                    <th className="px-3 py-2.5 text-right">CA GL (70XX)</th>
                    <th className="px-3 py-2.5 text-right">CA DMM (base)</th>
                    <th className="px-3 py-2.5 text-right">Acompte attendu</th>
                    <th className="px-3 py-2.5 text-right">Acompte déclaré</th>
                    <th className="px-3 py-2.5 text-right">Écart</th>
                    <th className="px-3 py-2.5 text-right">Écart %</th>
                    <th className="px-3 py-2.5">DMM</th>
                    <th className="px-3 py-2.5">Délai</th>
                    <th className="px-3 py-2.5">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {data.months.map((m) => (
                    <tr key={m.month} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-3 py-2">{m.period_label}</td>
                      <td className="px-3 py-2 text-right font-mono">{formatXAF(m.ca_gl_xaf)}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {m.ca_dmm_xaf !== null ? formatXAF(m.ca_dmm_xaf) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{formatXAF(m.expected_acompte_xaf)}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {m.dmm_present ? formatXAF(m.declared_acompte_xaf) : '—'}
                      </td>
                      <td className={cn(
                        'px-3 py-2 text-right font-mono',
                        m.dmm_present && Math.abs(m.variance_pct ?? 0) > 1 ? 'text-black font-bold underline decoration-2' : 'text-slate-500',
                      )}>
                        {m.dmm_present ? formatXAF(m.variance_xaf) : '—'}
                      </td>
                      <td className={cn(
                        'px-3 py-2 text-right font-mono',
                        m.dmm_present && Math.abs(m.variance_pct ?? 0) > 1 ? 'text-black font-bold underline decoration-2' : 'text-slate-500',
                      )}>
                        {m.variance_pct !== null ? `${m.variance_pct.toFixed(2)} %` : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {m.dmm_present ? (
                          <span className="inline-flex items-center gap-1 text-neutral-700 text-[11px]">
                            <CheckCircle2 className="w-3 h-3" />
                            {formatDate(m.dmm_filing_date) || 'déposée'}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-black font-bold underline decoration-2 text-[11px]">
                            <XCircle className="w-3 h-3" />
                            manquante
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2"><DeadlineBadge s={m.deadline_status} /></td>
                      <td className="px-3 py-2"><StatusPill s={m.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* ── Mois manquants ─────────────────────────────────────── */}
          {data.annual.dmm_missing_months.length > 0 && (
            <Card>
              <CardContent>
                <div className="flex items-start gap-3 py-2">
                  <AlertTriangle className="w-5 h-5 text-neutral-700 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-slate-700">
                    <b>Contrôle (a) — DMM manquantes :</b>{' '}
                    {data.annual.dmm_missing_months.map((m) => (
                      <span key={m} className="inline-block px-1.5 py-0.5 mx-0.5 bg-white border-2 border-black text-black font-bold underline decoration-2 rounded text-xs">
                        {monthLabel(m)} {data.fiscal_year}
                      </span>
                    ))}
                    . Chargez les DMM correspondantes dans Données › Déclarations mensuelles
                    pour activer le contrôle complet.
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              Source légale : <i>{data.legal_reference}</i>. Cette page implémente les contrôles
              (a) présence des 12 DMM, (b) recoupement mensuel acompte ≈ taux × Σ comptes 70XX,
              et (c) recoupement annuel CA GL vs CA DMM.
              Pénalités (Art. L106 LPF) et imputation DAR-IS : à venir en partie 2.
            </span>
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function KPI({ label, value, sublabel, tone = 'neutral' }: { label: string; value: number | string; sublabel?: string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls = tone === 'err' ? 'text-black font-bold underline decoration-2' : tone === 'warn' ? 'text-neutral-700' : tone === 'ok' ? 'text-neutral-700' : 'text-slate-900';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
        <div className={`text-base font-bold mt-1 font-display ${cls}`}>{value}</div>
        {sublabel && <div className="text-[10px] text-slate-500 mt-0.5">{sublabel}</div>}
      </CardContent>
    </Card>
  );
}

function Field({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls = tone === 'err' ? 'text-black font-extrabold underline decoration-2 underline-offset-4' : tone === 'warn' ? 'text-neutral-700 font-semibold' : tone === 'ok' ? 'text-neutral-600' : 'text-slate-900';
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`font-mono text-base font-semibold ${cls}`}>{value}</div>
    </div>
  );
}

function DeadlineBadge({ s }: { s: 'ON_TIME' | 'LATE' | 'MISSING' | 'NO_FILING_DATE' }) {
  if (s === 'ON_TIME') return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-white text-neutral-700 border border-neutral-300"><Clock className="w-3 h-3" />Dans les délais</span>;
  if (s === 'LATE')    return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-white text-black border-2 border-black font-semibold"><Clock className="w-3 h-3" />En retard</span>;
  if (s === 'MISSING') return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">—</span>;
  return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-neutral-100 text-black border border-neutral-400">Date manquante</span>;
}

function StatusPill({ s }: { s: 'OK' | 'VARIANCE_MINOR' | 'VARIANCE_MAJOR' | 'MISSING_DMM' | 'NO_CA' }) {
  if (s === 'OK')              return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-white text-neutral-700 border border-neutral-300 font-semibold">OK</span>;
  if (s === 'VARIANCE_MINOR')  return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-neutral-100 text-black border border-neutral-400 font-semibold">Écart mineur</span>;
  if (s === 'VARIANCE_MAJOR')  return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-white text-black border-2 border-black font-bold">Écart majeur</span>;
  if (s === 'MISSING_DMM')     return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-white text-black border-2 border-black font-semibold">DMM manquante</span>;
  return <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">Pas de CA</span>;
}

function statusLabel(s: 'GREEN' | 'AMBER' | 'RED' | 'GREY') {
  if (s === 'GREEN') return '🟢 Conforme';
  if (s === 'AMBER') return '🟠 Vigilance';
  if (s === 'RED')   return '🔴 À redresser';
  return '⚪ N/A';
}
function statusTone(s: 'GREEN' | 'AMBER' | 'RED' | 'GREY'): 'ok' | 'warn' | 'err' | 'neutral' {
  if (s === 'GREEN') return 'ok';
  if (s === 'AMBER') return 'warn';
  if (s === 'RED')   return 'err';
  return 'neutral';
}
function monthLabel(m: number): string {
  return ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'][m - 1];
}
