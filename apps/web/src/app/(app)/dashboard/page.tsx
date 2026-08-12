'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight, Briefcase, Folder, CheckCircle2, Plus,
  Layers, Activity, AlertTriangle, Clock,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import type { AuditCase } from '@/lib/types';
import { useApp } from '@/lib/store';
import { cn } from '@/lib/utils';
import { useT, type MessageKey } from '@/lib/i18n';
import { AuditeePicker } from '@/components/auditee-picker';
import { NewCaseModal } from '@/components/new-case-modal';

export default function DashboardPage() {
  const t = useT();
  const user = useApp((s) => s.user);
  const currentCase = useApp((s) => s.currentCase);
  const setCurrentCase = useApp((s) => s.setCurrentCase);
  const [newOpen, setNewOpen] = useState(false);

  const { data: cases = [] } = useQuery({
    queryKey: ['audit-cases'],
    queryFn: () => api<AuditCase[]>('/audit-cases'),
  });

  const active = cases.filter((c) => c.status !== 'CLOS').length;
  const highRisk = cases.filter((c) => c.risk_level === 'ELEVE').length;
  const activeCases = cases.filter((c) => c.status !== 'CLOS');

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="font-display text-2xl font-extrabold text-black tracking-tight">
            {t('dashboard.greeting')} {user?.full_name?.split(' ')[0] || ''}
          </h1>
          <p className="text-sm text-neutral-700 mt-1">
            {t('dashboard.subtitle')}
          </p>
        </div>
        <Button onClick={() => setNewOpen(true)}>
          <Plus className="w-4 h-4" />
          {t('dashboard.newCase')}
        </Button>
      </div>

      <NewCaseModal open={newOpen} onClose={() => setNewOpen(false)} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: t('dashboard.kpiTotal'),    value: cases.length, emphasize: false, Icon: Layers,         tint: 'bg-indigo-50 text-indigo-600' },
          { label: t('dashboard.kpiActive'),   value: active,       emphasize: false, Icon: Activity,       tint: 'bg-blue-50 text-blue-600' },
          { label: t('dashboard.kpiHighRisk'), value: highRisk,     emphasize: true,  Icon: AlertTriangle,  tint: 'bg-rose-50 text-rose-600' },
          { label: t('dashboard.kpiNotify'),   value: 0,            emphasize: false, Icon: Clock,          tint: 'bg-amber-50 text-amber-700' },
        ].map((k) => (
          <Card key={k.label}>
            <CardContent>
              <div className="flex items-start justify-between gap-2">
                <div className="text-[11px] font-semibold text-neutral-700 uppercase tracking-[0.12em]">
                  {k.label}
                </div>
                <span className={cn('w-8 h-8 rounded-lg grid place-items-center flex-shrink-0', k.tint)}>
                  <k.Icon className="w-[18px] h-[18px]" />
                </span>
              </div>
              <div
                className={cn(
                  'mt-2 font-display tabular-nums text-3xl leading-none',
                  k.emphasize ? 'font-extrabold text-rose-600' : 'font-bold text-black',
                )}
                style={{ fontFeatureSettings: '"tnum"' }}
              >
                {k.value}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Master filter — drives every other page */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-black" />
              {t('dashboard.pickerTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-neutral-700 mb-4 leading-snug">
              Paramètres du dossier actif — la sélection de l&apos;engagement se fait
              dans la liste « Dossiers en cours » ci-contre.
            </p>
            <AuditeePicker variant="light" showSelector={false} />
          </CardContent>
        </Card>

        {/* Active files panel — replaces the old "Dossiers d'audit" page */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Folder className="w-4 h-4 text-black" />
              {t('dashboard.activeFilesTitle')}
            </CardTitle>
            <span className="text-xs text-neutral-500">{t('dashboard.activeFilesHint')}</span>
          </CardHeader>
          {activeCases.length === 0 ? (
            <CardContent>
              <div className="py-8 text-center space-y-3">
                <div className="text-sm text-neutral-500 italic">{t('dossiers.empty')}</div>
                <Button onClick={() => setNewOpen(true)} variant="outline" size="sm">
                  <Plus className="w-4 h-4" />
                  {t('dashboard.newCase')}
                </Button>
              </div>
            </CardContent>
          ) : (
            <div>
              {activeCases.map((c) => {
                const isActive = currentCase?.id === c.id;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setCurrentCase(c)}
                    className={cn(
                      'w-full text-left flex items-center gap-3 px-5 py-3 border-t border-neutral-100 first:border-t-0 hover:bg-neutral-50 transition group',
                      isActive && 'bg-neutral-50 ring-1 ring-inset ring-black',
                    )}
                  >
                    <div className={cn(
                      'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 border',
                      c.risk_level === 'ELEVE' ? 'bg-rose-50 text-rose-600 border-rose-200'
                        : c.risk_level === 'MOYEN' ? 'bg-amber-50 text-amber-700 border-amber-200'
                        : 'bg-emerald-50 text-emerald-600 border-emerald-200',
                    )}>
                      <Folder className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="font-semibold text-black text-sm truncate">
                          {c.taxpayer.raison_sociale}
                        </div>
                        {isActive && (
                          <span className="text-[9px] flex items-center gap-1 px-1.5 py-0.5 border border-black text-black uppercase tracking-wider font-semibold">
                            <CheckCircle2 className="w-3 h-3" />
                            {t('dashboard.activeCaseBadge')}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-neutral-700 mt-0.5 font-mono flex items-center gap-2 tabular-nums" style={{ fontFeatureSettings: '"tnum"' }}>
                        <span>{c.reference}</span>
                        <span>·</span>
                        <span>NIU {c.taxpayer.niu}</span>
                        <span>·</span>
                        <span>{t('dossiers.fiscalYear')} {c.fiscal_year}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Badge variant={statusVariant(c.status)}>{t(statusLabelKey(c.status))}</Badge>
                      <Badge variant={riskVariant(c.risk_level)}>{t(riskLabelKey(c.risk_level))}</Badge>
                      <Link
                        href={`/dossiers/${c.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-neutral-500 hover:text-black opacity-0 group-hover:opacity-100 transition"
                        title="Ouvrir le détail du dossier"
                      >
                        <ArrowRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      </div>

    </div>
  );
}

function statusVariant(s: AuditCase['status']) {
  switch (s) {
    case 'EN_COURS': return 'info' as const;
    case 'RAPPORT': case 'NOTIFIE': return 'warn' as const;
    case 'CLOS': return 'neutral' as const;
    default: return 'neutral' as const;
  }
}
function statusLabelKey(s: AuditCase['status']): MessageKey {
  return ({
    PLANIFICATION: 'dossiers.statusPlanification',
    EN_COURS: 'dossiers.statusEnCours',
    CONTRADICTOIRE: 'dossiers.statusContradictoire',
    RAPPORT: 'dossiers.statusRapport',
    NOTIFIE: 'dossiers.statusNotifie',
    CLOS: 'dossiers.statusClos',
  } as const)[s];
}
function riskVariant(r: AuditCase['risk_level']) {
  return ({ FAIBLE: 'ok', MOYEN: 'warn', ELEVE: 'err' } as const)[r];
}
function riskLabelKey(r: AuditCase['risk_level']): MessageKey {
  return ({
    FAIBLE: 'dossiers.riskFaible',
    MOYEN: 'dossiers.riskMoyen',
    ELEVE: 'dossiers.riskEleve',
  } as const)[r];
}
