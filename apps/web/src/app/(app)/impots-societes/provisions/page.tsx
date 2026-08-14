'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Layers, ChevronDown, ChevronRight, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ControlHeader } from '@/components/control-header';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF } from '@/lib/utils';

type Entry = {
  piece_number: string; entry_date: string | null; libelle: string;
  debit_xaf: number; credit_xaf: number; kind: 'DOTATION' | 'REPRISE' | 'NON_CLASSE';
};
type Row = {
  account_code: string; account_name: string; group_key: string; group_label: string;
  opening_xaf: number; additions_xaf: number; reversals_xaf: number;
  unclassified_xaf: number; expected_closing_xaf: number; actual_closing_xaf: number;
  variance_xaf: number; status: 'ALIGNED' | 'DISCREPANCY'; entries: Entry[];
};
type Resp = {
  data_loaded: boolean;
  summary: {
    opening_xaf: number; additions_xaf: number; reversals_xaf: number;
    unclassified_xaf: number; expected_closing_xaf: number; actual_closing_xaf: number;
    variance_xaf: number; account_count: number; discrepancy_count: number;
    tb_filename: string | null; gl_filename: string | null; gl_loaded: boolean;
  } | null;
  groups: { key: string; label: string }[];
  rows: Row[];
  note?: string;
};

export default function ProvisionsPage() {
  const t = useT();
  const { currentCase } = useApp();
  const [open, setOpen] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['provisions', currentCase?.id],
    queryFn: () => api<Resp>(`/audit-cases/${currentCase!.id}/provisions`),
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
          <Layers className="w-6 h-6 text-black" />
          Provisions — rollforward
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Ouverture (balance) + Dotations (contrepartie 69XX du grand-livre) − Reprises
          (contrepartie 79XX) = clôture attendue, comparée à la clôture réelle.
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
      {currentCase && data && !data.data_loaded && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center italic">
          {data.note ?? 'Chargez la balance générale dans « Données ».'}
        </div></CardContent></Card>
      )}

      {currentCase && data?.data_loaded && data.summary && (
        <>
          <ControlHeader
            expected={data.summary.expected_closing_xaf}
            actual={data.summary.actual_closing_xaf}
            variance={data.summary.variance_xaf}
            exposure={Math.abs(data.summary.variance_xaf)}
            sublabels={{
              expected: 'Clôture attendue (rollforward)',
              actual: 'Clôture réelle (balance)',
              variance: 'Écart à justifier',
              exposure: 'Provisions à instruire',
            }}
            stats={[
              { label: 'Ouverture', value: formatXAF(data.summary.opening_xaf) },
              { label: 'Dotations (69XX)', value: formatXAF(data.summary.additions_xaf) },
              { label: 'Reprises (79XX)', value: formatXAF(data.summary.reversals_xaf) },
              { label: 'Mouvements non classés', value: formatXAF(data.summary.unclassified_xaf),
                tone: data.summary.unclassified_xaf !== 0 ? 'warn' : 'ok' },
              { label: 'Comptes en écart', value: data.summary.discrepancy_count,
                tone: data.summary.discrepancy_count > 0 ? 'err' : 'ok' },
            ]}
          />

          {!data.summary.gl_loaded && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900 flex items-start gap-2">
              <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>Grand-livre absent — dotations et reprises ne peuvent pas être ventilées.</span>
            </div>
          )}

          {data.groups.map((g) => {
            const rows = data.rows.filter((r) => r.group_key === g.key);
            if (rows.length === 0) return null;
            return (
              <Card key={g.key}>
                <CardHeader>
                  <CardTitle className="text-base">{g.label}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
                        <tr className="border-b border-neutral-200">
                          <th className="text-left px-2 py-1.5">Compte</th>
                          <th className="text-right px-2 py-1.5">Ouverture</th>
                          <th className="text-right px-2 py-1.5">+ Dotations</th>
                          <th className="text-right px-2 py-1.5">− Reprises</th>
                          <th className="text-right px-2 py-1.5">Non classés</th>
                          <th className="text-right px-2 py-1.5">Clôture attendue</th>
                          <th className="text-right px-2 py-1.5">Clôture réelle</th>
                          <th className="text-right px-2 py-1.5">Écart</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => {
                          const isOpen = open === r.account_code;
                          return (
                            <>
                              <tr key={r.account_code}
                                  onClick={() => setOpen(isOpen ? null : r.account_code)}
                                  className={cn('border-b border-neutral-100 cursor-pointer hover:bg-neutral-50',
                                    r.status === 'DISCREPANCY' && 'bg-rose-50/60')}>
                                <td className="px-2 py-1.5">
                                  <span className="inline-flex items-center gap-1">
                                    {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                    <span className="font-mono font-semibold">{r.account_code}</span>
                                  </span>
                                  <div className="text-[10px] text-neutral-500 ml-4">{r.account_name}</div>
                                </td>
                                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{formatXAF(r.opening_xaf)}</td>
                                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-emerald-700">{formatXAF(r.additions_xaf)}</td>
                                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-amber-700">{formatXAF(r.reversals_xaf)}</td>
                                <td className={cn('px-2 py-1.5 text-right font-mono tabular-nums',
                                  r.unclassified_xaf !== 0 ? 'text-amber-800 font-semibold' : 'text-neutral-400')}>
                                  {r.unclassified_xaf !== 0 ? formatXAF(r.unclassified_xaf) : '—'}
                                </td>
                                <td className="px-2 py-1.5 text-right font-mono tabular-nums font-semibold">{formatXAF(r.expected_closing_xaf)}</td>
                                <td className="px-2 py-1.5 text-right font-mono tabular-nums font-semibold">{formatXAF(r.actual_closing_xaf)}</td>
                                <td className={cn('px-2 py-1.5 text-right font-mono tabular-nums font-bold',
                                  r.status === 'DISCREPANCY' ? 'text-rose-700' : 'text-emerald-700')}>
                                  {formatXAF(r.variance_xaf)}
                                </td>
                              </tr>
                              {isOpen && (
                                <tr key={`${r.account_code}-d`}>
                                  <td colSpan={8} className="px-3 py-2 bg-neutral-50">
                                    <div className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1">
                                      Mouvements du compte (classés par N° d&apos;écriture)
                                    </div>
                                    <table className="w-full text-[11px] bg-white">
                                      <thead className="text-[10px] text-neutral-500">
                                        <tr className="border-b border-neutral-200">
                                          <th className="text-left px-2 py-1">Date</th>
                                          <th className="text-left px-2 py-1">N° écriture</th>
                                          <th className="text-left px-2 py-1">Libellé</th>
                                          <th className="text-right px-2 py-1">Débit</th>
                                          <th className="text-right px-2 py-1">Crédit</th>
                                          <th className="text-left px-2 py-1">Nature</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {r.entries.map((e, i) => (
                                          <tr key={i} className="border-b border-neutral-100">
                                            <td className="px-2 py-1 font-mono">{e.entry_date?.slice(0, 10) ?? '—'}</td>
                                            <td className="px-2 py-1 font-mono">{e.piece_number}</td>
                                            <td className="px-2 py-1 max-w-[260px] truncate" title={e.libelle}>{e.libelle}</td>
                                            <td className="px-2 py-1 text-right font-mono">{e.debit_xaf ? formatXAF(e.debit_xaf) : '—'}</td>
                                            <td className="px-2 py-1 text-right font-mono">{e.credit_xaf ? formatXAF(e.credit_xaf) : '—'}</td>
                                            <td className="px-2 py-1">
                                              <span className={cn('text-[9px] font-bold px-1 py-0.5 rounded border',
                                                e.kind === 'DOTATION' ? 'border-emerald-300 text-emerald-700 bg-emerald-50'
                                                : e.kind === 'REPRISE' ? 'border-amber-300 text-amber-800 bg-amber-50'
                                                : 'border-neutral-300 text-neutral-600 bg-neutral-50')}>
                                                {e.kind === 'NON_CLASSE' ? 'non classé' : e.kind.toLowerCase()}
                                              </span>
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </td>
                                </tr>
                              )}
                            </>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </>
      )}
    </div>
  );
}
