'use client';

/**
 * Harmonized control header — the SAME four boxes, in the SAME order, on every
 * audited-aspect page (amortissements, règlements espèces, dons, charges
 * financières, primes d'assurance, petit matériel, acomptes, …):
 *
 *   1. Attendu             — amount expected per the CGI rule (recalcul, plafond, dû)
 *   2. Réel                — amount actually observed in the audited data
 *   3. Écart               — variance (actual − expected unless module-specific)
 *   4. Exposition au risque — réintégration + rappels + pénalités
 *
 * Module-specific figures (lines tested, mismatch counts, …) are NOT boxes:
 * they render as compact inline chips underneath, so page-to-page the header
 * always reads identically.
 */

import { Card, CardContent } from '@/components/ui/card';
import { useT } from '@/lib/i18n';
import { cn, formatXAF } from '@/lib/utils';

export type ControlTone = 'ok' | 'warn' | 'err' | 'neutral';

export interface ControlStat {
  label: string;
  value: string | number;
  tone?: ControlTone;
}

export interface ControlHeaderProps {
  /** Attendu — per the tax code. */
  expected: number;
  /** Réel — per the books / uploaded data. */
  actual: number;
  /** Écart — defaults to actual − expected when omitted. */
  variance?: number;
  /** Exposition au risque — réintégrations + impôts additionnels + pénalités. */
  exposure: number;
  /** Optional per-slot sublabels making module semantics explicit. */
  sublabels?: Partial<Record<'expected' | 'actual' | 'variance' | 'exposure', string>>;
  /** Compact module-specific stats (counts…) shown as chips under the strip. */
  stats?: ControlStat[];
}

const VALUE_CLS: Record<ControlTone, string> = {
  ok: 'text-emerald-700',
  warn: 'text-amber-700',
  err: 'text-rose-700',
  neutral: 'text-black',
};

const CHIP_CLS: Record<ControlTone, string> = {
  ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warn: 'bg-amber-50 text-amber-700 border-amber-200',
  err: 'bg-rose-50 text-rose-700 border-rose-200',
  neutral: 'bg-slate-50 text-slate-600 border-slate-200',
};

function Box({
  label,
  sublabel,
  value,
  tone,
}: {
  label: string;
  sublabel?: string;
  value: number;
  tone: ControlTone;
}) {
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">{label}</div>
        {sublabel && <div className="text-[10px] text-neutral-400 truncate" title={sublabel}>{sublabel}</div>}
        <div className={cn('text-base mt-1 font-display font-bold tabular-nums', VALUE_CLS[tone])}>
          {formatXAF(value)}
        </div>
      </CardContent>
    </Card>
  );
}

export function ControlHeader({ expected, actual, variance, exposure, sublabels, stats }: ControlHeaderProps) {
  const t = useT();
  const v = variance !== undefined ? variance : actual - expected;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Box label={t('ctl.expected')} sublabel={sublabels?.expected} value={expected} tone="neutral" />
        <Box label={t('ctl.actual')} sublabel={sublabels?.actual} value={actual} tone="neutral" />
        <Box
          label={t('ctl.variance')}
          sublabel={sublabels?.variance}
          value={v}
          tone={Math.abs(v) < 1 ? 'ok' : 'warn'}
        />
        <Box
          label={t('ctl.exposure')}
          sublabel={sublabels?.exposure}
          value={exposure}
          tone={exposure > 0 ? 'err' : 'ok'}
        />
      </div>

      {stats && stats.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {stats.map((s, i) => (
            <span
              key={i}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
                CHIP_CLS[s.tone ?? 'neutral'],
              )}
            >
              <span className="text-[10px] uppercase tracking-wide opacity-70">{s.label}</span>
              <span className="font-mono tabular-nums">{s.value}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
