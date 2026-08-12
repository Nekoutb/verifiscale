'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Users, ChevronDown, ChevronRight, Sparkles } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ControlHeader } from '@/components/control-header';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF } from '@/lib/utils';

type Row = {
  account_code: string; account_name: string; libelle: string;
  montant_xaf: number; entry_count: number;
  verdict: 'DEDUCTIBLE' | 'A_INSTRUIRE' | 'NON_DEDUCTIBLE';
  motif: string; article: string; source: 'regle' | 'ia';
};
type Resp = {
  gl_loaded: boolean; gl_filename?: string; article: string;
  summary: {
    total_xaf: number; non_deductible_xaf: number; a_instruire_xaf: number;
    deductible_xaf: number; row_count: number;
    non_deductible_count: number; a_instruire_count: number; ai_used: boolean;
  } | null;
  rows: Row[];
};

export default function ChargesPersonnelPage() {
  const t = useT();
  const { currentCase } = useApp();
  const [showArticle, setShowArticle] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['charges-personnel', currentCase?.id],
    queryFn: () => api<Resp>(`/audit-cases/${currentCase!.id}/charges-personnel`),
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
          <Users className="w-6 h-6 text-black" />
          Charges de personnel — Art. 7 A 1
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Travail effectif et rémunérations non excessives (a) · jetons de présence (b) ·
          allocations forfaitaires et dépenses somptuaires (c).
        </p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center italic">
          Sélectionnez un dossier dans la liste « Dossiers en cours ».
        </div></CardContent></Card>
      )}

      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">Analyse…</div></CardContent></Card>
      )}

      {currentCase && data && !data.gl_loaded && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center italic">
          Aucun grand-livre importé — chargez-le dans « Données » puis confirmez son mapping.
        </div></CardContent></Card>
      )}

      {currentCase && data?.gl_loaded && data.summary && (
        <>
          <ControlHeader
            expected={data.summary.deductible_xaf}
            actual={data.summary.total_xaf}
            variance={data.summary.non_deductible_xaf + data.summary.a_instruire_xaf}
            exposure={data.summary.non_deductible_xaf}
            sublabels={{
              expected: 'Charges de personnel déductibles',
              actual: 'Charges de personnel comptabilisées (cl. 66)',
              variance: 'Non déductibles + à instruire',
              exposure: 'Réintégration (non déductibles)',
            }}
            stats={[
              { label: 'Lignes analysées', value: data.summary.row_count },
              { label: 'Non déductibles', value: data.summary.non_deductible_count,
                tone: data.summary.non_deductible_count > 0 ? 'err' : 'ok' },
              { label: 'À instruire', value: data.summary.a_instruire_count,
                tone: data.summary.a_instruire_count > 0 ? 'warn' : 'ok' },
              { label: 'Vérification IA', value: data.summary.ai_used ? 'Art. 7 A 1 appliqué' : 'règles seules' },
            ]}
          />

          <button
            type="button"
            onClick={() => setShowArticle(!showArticle)}
            className="flex items-center gap-1.5 text-xs font-semibold text-black underline"
          >
            {showArticle ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            Texte appliqué — Article 7 A 1 a) b) c)
          </button>
          {showArticle && (
            <pre className="text-[11px] leading-relaxed whitespace-pre-wrap bg-neutral-50 border border-neutral-200 rounded-lg p-4 text-neutral-800">
              {data.article}
            </pre>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Lignes de charges (GL : <span className="font-mono text-xs">{data.gl_filename}</span>)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
                    <tr className="border-b border-neutral-200">
                      <th className="text-left px-2 py-1.5">Compte</th>
                      <th className="text-left px-2 py-1.5">Libellé</th>
                      <th className="text-right px-2 py-1.5">Montant</th>
                      <th className="text-left px-2 py-1.5">Verdict</th>
                      <th className="text-left px-2 py-1.5">Motif (Art. 7 A 1)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r, i) => (
                      <tr key={i} className={cn('border-b border-neutral-100 align-top',
                        r.verdict === 'NON_DEDUCTIBLE' && 'bg-rose-50/60',
                        r.verdict === 'A_INSTRUIRE' && 'bg-amber-50/50')}>
                        <td className="px-2 py-1.5">
                          <div className="font-mono font-semibold">{r.account_code}</div>
                          <div className="text-[10px] text-neutral-500">{r.account_name}</div>
                        </td>
                        <td className="px-2 py-1.5 max-w-[280px]">
                          <div className="truncate" title={r.libelle}>{r.libelle}</div>
                          <div className="text-[10px] text-neutral-400">{r.entry_count} écriture(s)</div>
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums font-semibold">
                          {formatXAF(r.montant_xaf)}
                        </td>
                        <td className="px-2 py-1.5">
                          <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded border whitespace-nowrap',
                            r.verdict === 'NON_DEDUCTIBLE' ? 'border-rose-300 text-rose-700 bg-rose-50'
                            : r.verdict === 'A_INSTRUIRE' ? 'border-amber-300 text-amber-800 bg-amber-50'
                            : 'border-emerald-300 text-emerald-700 bg-emerald-50')}>
                            {r.verdict === 'NON_DEDUCTIBLE' ? 'Non déductible'
                              : r.verdict === 'A_INSTRUIRE' ? 'À instruire' : 'Déductible'}
                          </span>
                          {r.source === 'ia' && (
                            <span className="ml-1 inline-flex items-center gap-0.5 text-[9px] text-indigo-700">
                              <Sparkles className="w-2.5 h-2.5" /> IA
                            </span>
                          )}
                        </td>
                        <td className="px-2 py-1.5 max-w-[340px] text-neutral-700">
                          {r.motif}
                          <div className="text-[10px] text-neutral-400 mt-0.5">{r.article}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
