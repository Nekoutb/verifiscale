'use client';

/**
 * ReintegrationTable — one consistent presentation for the "réintégrations"
 * shown by every charge-deductibility module (amortissements, charges espèces,
 * primes, charges financières, petit-matériel, dons, personnel…).
 *
 * Audit-v2 #1 — "Les tableaux qui présentent les réintégrations sur chaque
 * élément de charge devraient pouvoir être similaires partout."
 *
 * Callers pass a column spec + rows; the component owns the styling, number
 * formatting (tabular FCFA / %), the emphasised réintégration column, the
 * totals row, and the empty state — so they never drift apart again.
 */
import * as React from 'react';
import { cn, formatXAF } from '@/lib/utils';

export type ReintegrationColumnKind = 'text' | 'xaf' | 'pct' | 'node';

export interface ReintegrationColumn {
  /** Key looked up on each row object (and on the optional totals object). */
  key: string;
  /** Header label (already translated by the caller). */
  label: string;
  align?: 'left' | 'right' | 'center';
  kind?: ReintegrationColumnKind;
  /** Render the cell bold (e.g. the réintégration amount). */
  bold?: boolean;
  /** Mark this as THE réintégration column — it gets the emphasis treatment. */
  reinteg?: boolean;
  /** Optional custom cell renderer (used when kind === 'node'). */
  render?: (row: Record<string, unknown>) => React.ReactNode;
  /** Optional per-column width hint (Tailwind class, e.g. 'w-40'). */
  className?: string;
}

export interface ReintegrationTableProps {
  columns: ReintegrationColumn[];
  rows: Array<Record<string, unknown>>;
  /** Optional totals row rendered bold with a top rule. */
  totals?: Record<string, unknown>;
  totalsLabel?: string;
  /** Which column the totals label sits under (defaults to first column). */
  caption?: string;
  emptyLabel?: string;
  className?: string;
}

function fmt(kind: ReintegrationColumnKind | undefined, value: unknown): string {
  if (value == null || value === '') return '—';
  if (kind === 'xaf') return `${formatXAF(Number(value))} FCFA`;
  if (kind === 'pct') return `${Number(value).toFixed(2)} %`;
  return String(value);
}

function alignClass(a?: 'left' | 'right' | 'center'): string {
  return a === 'right' ? 'text-right' : a === 'center' ? 'text-center' : 'text-left';
}

export function ReintegrationTable({
  columns,
  rows,
  totals,
  totalsLabel = 'Total',
  caption,
  emptyLabel = 'Aucune réintégration.',
  className,
}: ReintegrationTableProps) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      {caption && (
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500 mb-2">
          {caption}
        </div>
      )}
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-neutral-200 text-neutral-500">
            {columns.map((c) => (
              <th
                key={c.key}
                className={cn(
                  'px-3 py-2.5 font-semibold uppercase tracking-wider text-[10px]',
                  alignClass(c.align),
                  c.className,
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-neutral-400 italic">
                {emptyLabel}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className="border-b border-neutral-100 hover:bg-neutral-50">
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={cn(
                      'px-3 py-2',
                      alignClass(c.align),
                      (c.kind === 'xaf' || c.kind === 'pct') && 'font-mono tabular-nums',
                      c.bold && 'font-semibold',
                      c.reinteg && Number(row[c.key]) > 0 && 'text-black font-bold',
                    )}
                    style={c.kind === 'xaf' || c.kind === 'pct' ? { fontFeatureSettings: '"tnum"' } : undefined}
                  >
                    {c.kind === 'node' && c.render ? c.render(row) : fmt(c.kind, row[c.key])}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
        {totals && rows.length > 0 && (
          <tfoot>
            <tr className="border-t-2 border-neutral-300 bg-neutral-50 font-bold">
              {columns.map((c, idx) => (
                <td
                  key={c.key}
                  className={cn(
                    'px-3 py-3',
                    alignClass(c.align),
                    (c.kind === 'xaf' || c.kind === 'pct') && 'font-mono tabular-nums',
                    c.reinteg && 'text-black underline decoration-2 underline-offset-2',
                  )}
                  style={c.kind === 'xaf' || c.kind === 'pct' ? { fontFeatureSettings: '"tnum"' } : undefined}
                >
                  {idx === 0
                    ? (totals[c.key] != null ? fmt(c.kind, totals[c.key]) : totalsLabel)
                    : totals[c.key] != null
                      ? fmt(c.kind, totals[c.key])
                      : ''}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
