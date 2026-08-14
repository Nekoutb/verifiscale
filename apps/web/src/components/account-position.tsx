'use client';

/**
 * Monthly running-balance table + transaction drill-down.
 *
 * Shared by « Comptes d'associés » (46XX) and « Comptes divers » (4711/4712):
 *   - one row per account, 12 month-end balances, wrong-side months highlighted
 *   - click a flagged month -> transactions revealed, the entry that DRIVES the
 *     position first
 *   - offsetting pairs (same amount, opposite direction) can be hidden with one tick
 *   - optional « justification reçue » tick per transaction (persisted)
 */

import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, AlertTriangle, Link2 } from 'lucide-react';
import { api } from '@/lib/api';
import { cn, formatXAF } from '@/lib/utils';

export type PositionTx = {
  piece_number: string; line_number: number; entry_date: string | null;
  month: number | null; libelle: string;
  debit_xaf: number; credit_xaf: number; running_after_xaf: number;
  drives_position: boolean; offset_group: number | null;
  justified: boolean; hidden_offset: boolean;
};
export type PositionMonth = {
  month: number; label: string; debit_xaf: number; credit_xaf: number;
  balance_xaf: number; flagged: boolean; nature: 'DEBIT' | 'CREDIT' | null;
};
export type PositionAccount = {
  account_code: string; account_name: string;
  opening_balance_xaf: number; closing_balance_xaf: number;
  flagged_months: number; max_wrong_side_xaf: number;
  months: PositionMonth[]; transactions: PositionTx[];
};

export function AccountPositionTable({
  accounts, caseId, module, requireJustification, flagLabel,
}: {
  accounts: PositionAccount[];
  caseId: string;
  module: 'SHAREHOLDER' | 'SUNDRY';
  /** show the « justification reçue » column (comptes d'associés) */
  requireJustification?: boolean;
  flagLabel: (nature: 'DEBIT' | 'CREDIT' | null) => string;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [hideOffsets, setHideOffsets] = useState(true);
  const qc = useQueryClient();

  const review = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api(`/audit-cases/${caseId}/ledger-review`, { method: 'POST', body: { module, ...body } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['comptes-associes', caseId] });
      qc.invalidateQueries({ queryKey: ['comptes-divers', caseId] });
    },
  });

  if (accounts.length === 0) {
    return <div className="text-xs text-slate-500 italic py-3">Aucun compte dans le périmètre.</div>;
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-1.5 text-[11px] text-slate-600 cursor-pointer">
        <input type="checkbox" checked={hideOffsets} onChange={(e) => setHideOffsets(e.target.checked)} />
        <Link2 className="w-3 h-3" />
        Masquer les transactions qui s&apos;annulent (même montant, sens opposé)
      </label>

      {accounts.map((a) => {
        const isOpen = open === a.account_code;
        return (
          <div key={a.account_code} className="border border-neutral-200 rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : a.account_code)}
              className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-neutral-50 transition"
            >
              {isOpen ? <ChevronDown className="w-4 h-4 text-neutral-500" />
                      : <ChevronRight className="w-4 h-4 text-neutral-500" />}
              <span className="font-mono font-semibold text-sm">{a.account_code}</span>
              <span className="text-xs text-neutral-600 flex-1 truncate">{a.account_name}</span>
              {a.flagged_months > 0 ? (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-rose-300 bg-rose-50 text-rose-700 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  {a.flagged_months} mois · pointe {formatXAF(a.max_wrong_side_xaf)}
                </span>
              ) : (
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-emerald-300 bg-emerald-50 text-emerald-700">
                  conforme
                </span>
              )}
            </button>

            {/* 12 month-end balances */}
            <div className="overflow-x-auto border-t border-neutral-100">
              <table className="w-full text-[11px]">
                <thead className="bg-neutral-50 text-neutral-600">
                  <tr>
                    <th className="text-left px-2 py-1 font-semibold">Solde à fin de mois</th>
                    {a.months.map((m) => (
                      <th key={m.month} className="px-2 py-1 text-right font-semibold">{m.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="px-2 py-1.5 text-neutral-500">
                      ouverture {formatXAF(a.opening_balance_xaf)}
                    </td>
                    {a.months.map((m) => (
                      <td
                        key={m.month}
                        title={m.flagged ? flagLabel(m.nature) : undefined}
                        onClick={() => m.flagged && setOpen(a.account_code)}
                        className={cn(
                          'px-2 py-1.5 text-right font-mono tabular-nums whitespace-nowrap',
                          m.flagged
                            ? m.nature === 'DEBIT'
                              ? 'bg-rose-100 text-rose-800 font-bold cursor-pointer'
                              : 'bg-amber-100 text-amber-900 font-bold cursor-pointer'
                            : 'text-neutral-700',
                        )}
                        style={{ fontFeatureSettings: '"tnum"' }}
                      >
                        {formatXAF(m.balance_xaf)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>

            {isOpen && (
              <div className="border-t border-neutral-200 p-3 bg-neutral-50/60">
                <div className="text-[11px] text-neutral-600 mb-2">
                  Transactions du compte — la transaction qui provoque la position est en tête.
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px] bg-white">
                    <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
                      <tr className="border-b border-neutral-200">
                        <th className="text-left px-2 py-1">Date</th>
                        <th className="text-left px-2 py-1">N° écriture</th>
                        <th className="text-left px-2 py-1">Libellé</th>
                        <th className="text-right px-2 py-1">Débit</th>
                        <th className="text-right px-2 py-1">Crédit</th>
                        <th className="text-right px-2 py-1">Solde après</th>
                        <th className="text-center px-2 py-1">Contrepassée</th>
                        {requireJustification && <th className="text-center px-2 py-1">Justif. reçue</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {a.transactions
                        .filter((t) => !(hideOffsets && t.offset_group != null))
                        .map((t) => (
                          <tr key={`${t.piece_number}-${t.line_number}`}
                              className={cn('border-b border-neutral-100',
                                t.drives_position && 'bg-rose-50',
                                t.hidden_offset && 'opacity-50')}>
                            <td className="px-2 py-1 font-mono">{t.entry_date?.slice(0, 10) ?? '—'}</td>
                            <td className="px-2 py-1 font-mono">{t.piece_number}</td>
                            <td className="px-2 py-1 max-w-[280px] truncate" title={t.libelle}>
                              {t.drives_position && (
                                <span className="text-[9px] font-bold text-rose-700 mr-1">▶ À L&apos;ORIGINE</span>
                              )}
                              {t.libelle}
                            </td>
                            <td className="px-2 py-1 text-right font-mono tabular-nums font-semibold">
                              {t.debit_xaf ? formatXAF(t.debit_xaf) : '—'}
                            </td>
                            <td className="px-2 py-1 text-right font-mono tabular-nums">
                              {t.credit_xaf ? formatXAF(t.credit_xaf) : '—'}
                            </td>
                            <td className={cn('px-2 py-1 text-right font-mono tabular-nums',
                              t.running_after_xaf > 0 ? 'text-rose-700 font-bold' : 'text-neutral-600')}>
                              {formatXAF(t.running_after_xaf)}
                            </td>
                            <td className="px-2 py-1 text-center">
                              {t.offset_group != null ? (
                                <span className="text-[9px] text-indigo-700" title="Paire détectée (même montant, sens opposé)">
                                  ↔ paire {t.offset_group}
                                </span>
                              ) : '—'}
                            </td>
                            {requireJustification && (
                              <td className="px-2 py-1 text-center">
                                <input
                                  type="checkbox"
                                  checked={t.justified}
                                  onChange={(e) => review.mutate({
                                    piece_number: t.piece_number, line_number: t.line_number,
                                    account_code: a.account_code, justified: e.target.checked,
                                  })}
                                  className="accent-emerald-600"
                                  title="Justification reçue de l'entreprise"
                                />
                              </td>
                            )}
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
