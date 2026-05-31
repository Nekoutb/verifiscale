'use client';

import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Building2, Info, FileWarning } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';

interface PMLine {
  piece_number: string;
  entry_date: string | null;
  line_number: number;
  account_code: string;
  account_name: string | null;
  libelle: string | null;
  amount_xaf: number;
  supplier_guess: string | null;
  qualification: string;
  qualification_source: string;
  depreciation_rate_pct: number;
  reint_differential_xaf: number;
  reint_total_xaf: number;
  reint_third_xaf: number;
  basis: string;
  reintegration_xaf: number;
  excluded: boolean;
  verdict_reason: string | null;
}

interface PMResp {
  threshold_xaf: number;
  target_accounts: string[];
  grey_zone_accounts?: string[];
  source_filename?: string;
  lines: PMLine[];
  summary: {
    threshold_xaf: number;
    line_count: number;
    hand_tool_count: number;
    other_count: number;
    excluded_count: number;
    total_amount_xaf: number;
    total_reint_differential_xaf: number;
    total_reint_total_xaf: number;
    total_reint_third_xaf: number;
    total_reintegration_selected_xaf: number;
  } | null;
  note?: string;
  legal_reference: string;
}

const QUALIFS = [
  { value: 'HAND_TOOL', label: 'Outillage à main (100%)' },
  { value: 'IT', label: 'Informatique (25%)' },
  { value: 'REPRO', label: 'Reprographie (33,33%)' },
  { value: 'FURNITURE', label: 'Mobilier (10%)' },
  { value: 'EQUIPMENT', label: 'Matériel/Machine (20%)' },
  { value: 'OTHER', label: 'Autre (20%)' },
  { value: 'EXCLUDED', label: 'Exclure (consommable réel)' },
];

export default function PetitMaterielPage() {
  const t = useT();
  const { currentCase } = useApp();
  const qc = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['petit-materiel', currentCase?.id],
    queryFn: () => api<PMResp>(`/audit-cases/${currentCase!.id}/petit-materiel`),
    enabled: !!currentCase,
  });

  const patchMut = useMutation({
    mutationFn: async (body: any) => api(`/audit-cases/${currentCase!.id}/petit-materiel/line`,
      { method: 'PATCH', body }),
    onSuccess: () => { void refetch(); void qc.invalidateQueries({ queryKey: ['petit-materiel'] }); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  // Global basis applier — flips ALL non-excluded lines to the chosen basis at once
  const applyBasisAllMut = useMutation({
    mutationFn: async (basis: 'DIFFERENTIAL' | 'TOTAL' | 'THIRD') => {
      const lines = (data?.lines || []).filter((l) => !l.excluded);
      for (const l of lines) {
        await api(`/audit-cases/${currentCase!.id}/petit-materiel/line`, {
          method: 'PATCH',
          body: { piece_number: l.piece_number, line_number: l.line_number, reintegration_basis: basis },
        });
      }
    },
    onSuccess: () => { void refetch(); void qc.invalidateQueries({ queryKey: ['petit-materiel'] }); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-navy">
        <ArrowLeft className="w-3.5 h-3.5" /> Impôts sur les sociétés
      </Link>
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Building2 className="w-6 h-6 text-navy" /> Petit matériel et outillage
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Seuil d'immobilisation obligatoire 500 000 FCFA. Au-delà, le bien doit être immobilisé
          puis amorti — l'outillage à main s'amortit toutefois à 100 %.
        </p>
      </div>

      {!currentCase && <Card><CardContent><div className="text-center py-10 text-slate-500">{t('data.noCaseTitle')}</div></CardContent></Card>}
      {currentCase && isLoading && <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">Chargement…</div></CardContent></Card>}

      {data?.note && (
        <Card><CardContent>
          <div className="flex items-start gap-3 py-2">
            <FileWarning className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-700">{data.note}</div>
          </div>
        </CardContent></Card>
      )}

      {data?.summary && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <KPI label="Lignes > 500K" value={data.summary.line_count} />
            <KPI label="Outillage main (100%)" value={data.summary.hand_tool_count}
                 tone={data.summary.hand_tool_count ? 'warn' : 'neutral'} />
            <KPI label="Autre matériel" value={data.summary.other_count}
                 tone={data.summary.other_count ? 'err' : 'ok'} />
            <KPI label="Réint. différentiel" value={formatXAF(data.summary.total_reint_differential_xaf)} tone="warn" />
            <KPI label="Réint. retenue" value={formatXAF(data.summary.total_reintegration_selected_xaf)}
                 tone={data.summary.total_reintegration_selected_xaf > 0 ? 'err' : 'ok'} />
          </div>

          <div className="text-[11px] text-slate-500">
            Source : <span className="font-mono">{data.source_filename}</span> ·
            Comptes balayés : <span className="font-mono">{[...data.target_accounts, ...(data.grey_zone_accounts || [])].join(' · ')}</span> ·
            Différentiel total {formatXAF(data.summary.total_reint_differential_xaf)} /
            Coût total {formatXAF(data.summary.total_reint_total_xaf)}
          </div>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle>Acquisitions ≥ 500 000 FCFA passées en charge</CardTitle>
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="text-slate-500">Base de réintégration (toutes lignes) :</span>
                  <button onClick={() => applyBasisAllMut.mutate('DIFFERENTIAL')}
                    disabled={applyBasisAllMut.isPending}
                    className="px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-50">
                    Tout en différentiel
                  </button>
                  <button onClick={() => applyBasisAllMut.mutate('THIRD')}
                    disabled={applyBasisAllMut.isPending}
                    className="px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-50">
                    Tout en 1/3–2/3
                  </button>
                  <button onClick={() => applyBasisAllMut.mutate('TOTAL')}
                    disabled={applyBasisAllMut.isPending}
                    className="px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-50">
                    Tout en coût total
                  </button>
                  {applyBasisAllMut.isPending && <span className="text-slate-400">application…</span>}
                </div>
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                Astuce : vous pouvez aussi choisir la base ligne par ligne (colonne « Base retenue »).
              </div>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2.5">Pièce</th>
                    <th className="px-3 py-2.5">Date</th>
                    <th className="px-3 py-2.5">Compte</th>
                    <th className="px-3 py-2.5">Libellé</th>
                    <th className="px-3 py-2.5 text-right">Montant</th>
                    <th className="px-3 py-2.5">Qualification</th>
                    <th className="px-3 py-2.5 text-right">Taux</th>
                    <th className="px-3 py-2.5 text-right">Réint. diff.</th>
                    <th className="px-3 py-2.5 text-right">Réint. 1/3–2/3</th>
                    <th className="px-3 py-2.5 text-right">Réint. total</th>
                    <th className="px-3 py-2.5">Base retenue</th>
                  </tr>
                </thead>
                <tbody>
                  {data.lines.map((l) => (
                    <tr key={`${l.piece_number}-${l.line_number}`}
                        className={cn('border-b border-slate-100 hover:bg-slate-50',
                          l.excluded && 'opacity-50',
                          !l.excluded && l.qualification === 'HAND_TOOL' && 'bg-amber-50/30',
                          !l.excluded && l.qualification !== 'HAND_TOOL' && 'bg-rose-50/30')}>
                      <td className="px-3 py-2 font-mono">{l.piece_number}</td>
                      <td className="px-3 py-2">{formatDate(l.entry_date) || '—'}</td>
                      <td className="px-3 py-2">
                        <div className="font-mono">{l.account_code}</div>
                        <div className="text-[10px] text-slate-500">{l.account_name || ''}</div>
                      </td>
                      <td className="px-3 py-2 max-w-[220px] truncate" title={l.libelle || ''}>{l.libelle || '—'}</td>
                      <td className="px-3 py-2 text-right font-mono font-semibold">{formatXAF(l.amount_xaf)}</td>
                      <td className="px-3 py-2">
                        <select
                          value={l.qualification}
                          onChange={(e) => patchMut.mutate({
                            piece_number: l.piece_number, line_number: l.line_number,
                            qualification: e.target.value,
                            excluded: e.target.value === 'EXCLUDED',
                          })}
                          className={cn('text-[11px] px-1.5 py-1 rounded border border-slate-300',
                            l.qualification_source === 'AUTO' && 'text-slate-600')}
                        >
                          {QUALIFS.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
                        </select>
                        {l.qualification_source === 'AUTO' && <span className="ml-1 text-[9px] text-slate-400">auto</span>}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{l.depreciation_rate_pct}%</td>
                      <td className="px-3 py-2 text-right font-mono text-amber-700">{l.excluded ? '—' : formatXAF(l.reint_differential_xaf)}</td>
                      <td className="px-3 py-2 text-right font-mono text-orange-700">{l.excluded ? '—' : formatXAF(l.reint_third_xaf)}</td>
                      <td className="px-3 py-2 text-right font-mono text-rose-700">{l.excluded ? '—' : formatXAF(l.reint_total_xaf)}</td>
                      <td className="px-3 py-2">
                        {l.excluded ? <span className="text-[10px] text-slate-400 italic">exclu</span> : (
                          <div className="flex gap-0.5">
                            {(['DIFFERENTIAL', 'THIRD', 'TOTAL'] as const).map((b) => (
                              <button key={b}
                                onClick={() => patchMut.mutate({ piece_number: l.piece_number, line_number: l.line_number, reintegration_basis: b })}
                                className={cn('px-1.5 py-0.5 rounded text-[10px] border',
                                  l.basis === b ? 'bg-navy text-white border-navy' : 'bg-white border-slate-300 hover:bg-slate-50')}>
                                {b === 'DIFFERENTIAL' ? 'Diff.' : b === 'THIRD' ? '⅓–⅔' : 'Total'}
                              </button>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                  {data.lines.length === 0 && (
                    <tr><td colSpan={11} className="px-3 py-8 text-center text-slate-500 italic">
                      Aucune acquisition ≥ 500 000 FCFA passée en charge sur les comptes 6056 / 6044 / 6047 / 624X.
                    </td></tr>
                  )}
                  {data.lines.length > 0 && (
                    <tr className="bg-navy text-white font-semibold">
                      <td colSpan={6} className="px-3 py-2.5 text-right uppercase tracking-wider text-[10px]">Réintégration retenue</td>
                      <td className="px-3 py-2.5"></td>
                      <td className="px-3 py-2.5 text-right font-mono">{formatXAF(data.summary.total_reint_differential_xaf)}</td>
                      <td className="px-3 py-2.5 text-right font-mono">{formatXAF(data.summary.total_reint_third_xaf)}</td>
                      <td className="px-3 py-2.5 text-right font-mono">{formatXAF(data.summary.total_reint_total_xaf)}</td>
                      <td className="px-3 py-2.5 text-right font-mono">{formatXAF(data.summary.total_reintegration_selected_xaf)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              <b>Méthode :</b> seul l'excédent de déduction est réintégrable. Pour l'<b>outillage à main</b>
              (taux 100 %) le différentiel est nul — c'est un simple vice de forme. Pour le <b>matériel à
              durée d'amortissement</b> (informatique 25 %, mobilier 10 %, machines 20 %…), la réintégration
              différentielle = coût − amortissement de 1ère année. Vous pouvez basculer chaque ligne sur
              « Total » si vous retenez la position stricte. CGI Cameroun — seuil 500 000 FCFA.
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function KPI({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls = tone === 'err' ? 'text-rose-600' : tone === 'warn' ? 'text-amber-600' : tone === 'ok' ? 'text-emerald-600' : 'text-slate-900';
  return (
    <Card><CardContent>
      <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`text-base font-bold mt-1 font-display ${cls}`}>{value}</div>
    </CardContent></Card>
  );
}
