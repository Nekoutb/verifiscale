'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight, Briefcase, Folder, CheckCircle2, Plus,
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
          <h1 className="font-display text-2xl font-bold text-slate-900">
            {t('dashboard.greeting')} {user?.full_name?.split(' ')[0] || ''} 👋
          </h1>
          <p className="text-sm text-slate-500 mt-1">
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
          { label: t('dashboard.kpiTotal'),    value: cases.length },
          { label: t('dashboard.kpiActive'),   value: active, cls: 'text-navy' },
          { label: t('dashboard.kpiHighRisk'), value: highRisk, cls: 'text-rose-600' },
          { label: t('dashboard.kpiNotify'),   value: 0, cls: 'text-amber-600' },
        ].map((k) => (
          <Card key={k.label}>
            <CardContent>
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                {k.label}
              </div>
              <div className={`text-2xl font-bold mt-2 font-display ${k.cls || 'text-slate-900'}`}>
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
              <Briefcase className="w-4 h-4 text-navy" />
              {t('dashboard.pickerTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500 mb-4 leading-snug">{t('dashboard.pickerHint')}</p>
            <AuditeePicker variant="light" />
          </CardContent>
        </Card>

        {/* Active files panel — replaces the old "Dossiers d'audit" page */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Folder className="w-4 h-4 text-navy" />
              {t('dashboard.activeFilesTitle')}
            </CardTitle>
            <span className="text-xs text-slate-400">{t('dashboard.activeFilesHint')}</span>
          </CardHeader>
          {activeCases.length === 0 ? (
            <CardContent>
              <div className="py-8 text-center space-y-3">
                <div className="text-sm text-slate-500 italic">{t('dossiers.empty')}</div>
                <Button onClick={() => setNewOpen(true)} variant="outline" size="sm">
                  <Plus className="w-4 h-4" />
                  {t('dashboard.newCase')}
                </Button>
              </div>
            </CardContent>
          ) : (
            <div className="divide-y divide-slate-100">
              {activeCases.map((c) => {
                const isActive = currentCase?.id === c.id;
                return (
                  <Link
                    key={c.id}
                    href={`/dossiers/${c.id}`}
                    className={cn(
                      'flex items-center gap-3 px-5 py-3 hover:bg-slate-50 transition group',
                      isActive && 'bg-gold/5',
                    )}
                  >
                    <div className={cn(
                      'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
                      isActive ? 'bg-gold/15 text-amber-700' : 'bg-slate-100 text-slate-500',
                    )}>
                      <Folder className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="font-semibold text-slate-900 text-sm truncate">
                          {c.taxpayer.raison_sociale}
                        </div>
                        {isActive && (
                          <Badge variant="warn" className="text-[9px] flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            {t('dashboard.activeCaseBadge')}
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 font-mono flex items-center gap-2">
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
                      <ArrowRight className="w-4 h-4 text-slate-400 opacity-0 group-hover:opacity-100 transition" />
                    </div>
                  </Link>
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
