'use client';

import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, BarChart3, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge, severityToVariant, severityLabel } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF } from '@/lib/utils';
import { CATEGORY_LABELS, type ControlRun, type ControlFinding } from '@/lib/types';

export default function ReportsPage() {
  const t = useT();
  const { currentCase } = useApp();

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['runs', currentCase?.id],
    queryFn: () => api<ControlRun[]>(`/control-runs/audit-case/${currentCase!.id}`),
    enabled: !!currentCase,
  });

  // Group most recent run per category
  const runByCategory: Record<string, ControlRun | undefined> = {};
  for (const r of runs) {
    if (!runByCategory[r.category]) runByCategory[r.category] = r;
  }

  const allFindings: ControlFinding[] = runs.flatMap((r) => r.findings);
  const totalImpact = runs.reduce((s, r) => s + (r.summary?.estimated_total_impact_xaf ?? 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-navy" />
          {t('nav.rapports')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          {currentCase
            ? `${currentCase.taxpayer.raison_sociale} · ${t('app.year')} ${currentCase.fiscal_year}`
            : t('data.noCaseTitle')}
        </p>
      </div>

      {!currentCase ? (
        <Card><CardContent><div className="text-center py-12 text-slate-500">{t('data.noCaseBody')}</div></CardContent></Card>
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPI label={t('dossier.totalFindings')} value={allFindings.length} tone={allFindings.length ? 'err' : 'ok'} />
            <KPI label={t('dossier.categoriesRun')} value={Object.keys(runByCategory).length} />
            <KPI label={t('dossier.estimatedImpact')} value={`${formatXAF(totalImpact)} FCFA`} tone={totalImpact ? 'warn' : 'ok'} />
            <KPI
              label={t('reports.blocking')}
              value={runs.reduce((s, r) => s + (r.summary?.blocking ?? 0), 0)}
              tone="err"
            />
          </div>

          {/* Consolidated findings */}
          <Card>
            <CardHeader>
              <CardTitle>{t('reports.consolidatedFindings')}</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="text-sm text-slate-500 py-6 text-center">{t('app.loading')}</div>
              ) : allFindings.length === 0 ? (
                <div className="text-center py-12 text-slate-500">{t('dossier.findings.empty')}</div>
              ) : (
                <div className="space-y-4">
                  {Object.entries(runByCategory).map(([cat, run]) => {
                    if (!run || run.findings.length === 0) return null;
                    const meta = CATEGORY_LABELS[cat] || { short: cat, full: cat, color: 'bg-slate-200' };
                    return (
                      <div key={cat} className="border border-slate-200 rounded-lg overflow-hidden">
                        <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                          <div className="flex items-center gap-2 text-sm">
                            <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold', meta.color)}>{meta.short}</span>
                            <span className="font-semibold">{meta.full}</span>
                          </div>
                          <Badge variant="info">{run.findings.length} {t('dossier.findings.anomalies')}</Badge>
                        </div>
                        <div className="divide-y divide-slate-100">
                          {run.findings.map((f) => <FindingRow key={f.id} f={f} />)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function FindingRow({ f }: { f: ControlFinding }) {
  const isInfo = f.severity === 'INFO';
  return (
    <div className="p-4">
      <div className="flex items-start gap-3">
        {isInfo ? (
          <Info className="w-5 h-5 flex-shrink-0 mt-0.5 text-sky-600" />
        ) : (
          <AlertTriangle className={cn('w-5 h-5 flex-shrink-0 mt-0.5',
            f.severity === 'BLOCKING' || f.severity === 'HIGH' ? 'text-rose-600'
            : f.severity === 'MEDIUM' ? 'text-amber-600' : 'text-slate-400'
          )} />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-slate-900 text-sm">{f.title}</div>
          <div className="text-xs text-slate-600 mt-1 leading-relaxed">{f.description}</div>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <Badge variant={severityToVariant(f.severity)}>{severityLabel(f.severity)}</Badge>
            <span className="text-[11px] font-mono text-slate-500">
              {f.control_code}{f.legal_reference ? ` · ${f.legal_reference}` : ''}
            </span>
          </div>
        </div>
        {f.estimated_impact_xaf ? (
          <div className="text-right text-sm flex-shrink-0">
            <div className="text-[10px] text-slate-500 uppercase">Impact</div>
            <div className="font-bold text-rose-600">{formatXAF(f.estimated_impact_xaf)} FCFA</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function KPI({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls = tone === 'err' ? 'text-rose-600' : tone === 'warn' ? 'text-amber-600' : tone === 'ok' ? 'text-emerald-600' : 'text-slate-900';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
        <div className={`text-2xl font-bold mt-1 font-display ${cls}`}>{value}</div>
      </CardContent>
    </Card>
  );
}
