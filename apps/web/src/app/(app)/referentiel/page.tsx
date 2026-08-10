'use client';

import { useMemo, useState } from 'react';
import catalog from '@/lib/controls-catalog.json';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge, severityToVariant, severityLabel } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ShieldCheck, Calculator, Receipt, Calendar, FileText, GitMerge, BookOpen, BookCheck, Search } from 'lucide-react';
import { useT } from '@/lib/i18n';

type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'BLOCKING';

interface Control {
  code: string;
  title: string;
  legal_ref: string;
  severity: Severity;
  automated: boolean;
  data?: string[];
}

interface Category {
  code: string;
  name: string;
  description?: string;
  controls: Control[];
}

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  A: ShieldCheck,
  B: Calculator,
  C: Receipt,
  D: BookOpen,
  E: Receipt,
  F: FileText,
  G: GitMerge,
  H: BookCheck,
};

// Implemented control codes — keep in sync with backend registry
const IMPLEMENTED = new Set([
  // Category A — 100% complete (16/16)
  'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9',
  'A10', 'A11', 'A12', 'A13', 'A13b', 'A13c', 'A14',
  // Category B — 100% complete (14/14)
  'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9',
  'B10', 'B11', 'B12', 'B13', 'B14',
  // Category C
  'C0', 'C1', 'C3', 'C9', 'C11', 'C14', 'C17', 'C19', 'C20',
  // Category D
  'D17', 'D18', 'D22', 'D23', 'D24', 'D26', 'D27', 'D28',
  // Category H — 100% complete (9/9)
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9',
]);

export default function ReferentielPage() {
  const t = useT();
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'implemented' | 'pending' | 'automated' | 'manual'>('all');

  const categories: Category[] = catalog.categories as unknown as Category[];

  const stats = useMemo(() => {
    const all = categories.flatMap((c) => c.controls);
    return {
      total: all.length,
      implemented: all.filter((c) => IMPLEMENTED.has(c.code)).length,
      automated: all.filter((c) => c.automated).length,
      blocking: all.filter((c) => c.severity === 'BLOCKING').length,
    };
  }, [categories]);

  const filteredCategories = useMemo(() => {
    const q = search.toLowerCase();
    return categories
      .map((cat) => ({
        ...cat,
        controls: cat.controls.filter((c) => {
          if (q && !`${c.code} ${c.title} ${c.legal_ref}`.toLowerCase().includes(q)) return false;
          if (filterStatus === 'implemented' && !IMPLEMENTED.has(c.code)) return false;
          if (filterStatus === 'pending' && IMPLEMENTED.has(c.code)) return false;
          if (filterStatus === 'automated' && !c.automated) return false;
          if (filterStatus === 'manual' && c.automated) return false;
          return true;
        }),
      }))
      .filter((c) => c.controls.length > 0);
  }, [categories, search, filterStatus]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold">{t('ref.title')}</h1>
        <p className="text-sm text-slate-500 mt-1">
          {t('ref.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label={t('ref.kpiTotal')}       value={stats.total} />
        <Stat label={t('ref.kpiImplemented')}  value={stats.implemented} tone="ok" sub={`${Math.round((stats.implemented / stats.total) * 100)}%`} />
        <Stat label={t('ref.kpiAutomated')}    value={stats.automated} />
        <Stat label={t('ref.kpiBlocking')}     value={stats.blocking} tone="err" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('ref.filters')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder={t('ref.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)}
            className="h-9 px-3 text-sm border border-slate-300 rounded-lg bg-white"
          >
            <option value="all">{t('ref.allStatuses')}</option>
            <option value="implemented">{t('ref.implemented')}</option>
            <option value="pending">{t('ref.pending')}</option>
            <option value="automated">{t('ref.automated')}</option>
            <option value="manual">{t('ref.manual')}</option>
          </select>
        </CardContent>
      </Card>

      {filteredCategories.map((cat) => {
        const Icon = CATEGORY_ICONS[cat.code] || ShieldCheck;
        return (
          <Card key={cat.code}>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-black text-white flex items-center justify-center">
                  <Icon className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-sm font-semibold">{t('ref.category')} {cat.code} — {cat.name}</div>
                  {cat.description && <div className="text-xs text-slate-500 font-normal mt-0.5">{cat.description}</div>}
                </div>
              </CardTitle>
              <Badge variant="neutral">{cat.controls.length} {t('ref.controlsCount')}</Badge>
            </CardHeader>
            <div className="divide-y divide-slate-100">
              {cat.controls.map((c) => {
                const implemented = IMPLEMENTED.has(c.code);
                return (
                  <div key={c.code} className="p-4 hover:bg-slate-50 transition">
                    <div className="flex items-start gap-3">
                      <code className="font-mono text-xs bg-slate-100 text-slate-700 px-2 py-1 rounded font-semibold flex-shrink-0">
                        {c.code}
                      </code>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-900">{c.title}</div>
                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                          <Badge variant={severityToVariant(c.severity)}>{severityLabel(c.severity)}</Badge>
                          <span className="text-[11px] font-mono text-slate-500">{c.legal_ref}</span>
                          {implemented ? (
                            <Badge variant="ok">{t('ref.tagImplemented')}</Badge>
                          ) : (
                            <Badge variant="neutral">{t('ref.tagPending')}</Badge>
                          )}
                          {c.automated ? (
                            <Badge variant="info">{t('ref.tagAutomatable')}</Badge>
                          ) : (
                            <Badge variant="warn">{t('ref.tagManual')}</Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        );
      })}

      {filteredCategories.length === 0 && (
        <Card>
          <CardContent>
            <div className="text-center text-slate-500 py-8">{t('ref.noMatch')}</div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, tone = 'neutral', sub }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral'; sub?: string }) {
  const cls = tone === 'err' ? 'text-rose-700 font-extrabold' : tone === 'warn' ? 'text-neutral-700 font-semibold' : tone === 'ok' ? 'text-neutral-600' : 'text-slate-900';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
        <div className={`text-2xl font-bold mt-1 font-display ${cls}`}>{value}</div>
        {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  );
}
