'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import type { AuditCase } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import { Plus } from 'lucide-react';
import { useT, type MessageKey } from '@/lib/i18n';

export default function DossiersPage() {
  const t = useT();
  const { data: cases = [], isLoading } = useQuery({
    queryKey: ['audit-cases'],
    queryFn: () => api<AuditCase[]>('/audit-cases'),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">{t('dossiers.heading')}</h1>
          <p className="text-sm text-slate-500 mt-1">
            {t('dossiers.subheading')}
          </p>
        </div>
        <Button>
          <Plus className="w-4 h-4" />
          {t('dossiers.newCase')}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{isLoading ? t('app.loading') : `${cases.length} ${t('dossiers.countSuffix')}`}</CardTitle>
        </CardHeader>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
              <th className="px-5 py-2.5">{t('dossiers.reference')}</th>
              <th className="px-5 py-2.5">{t('dossiers.taxpayer')}</th>
              <th className="px-5 py-2.5">{t('dossiers.niu')}</th>
              <th className="px-5 py-2.5">{t('dossiers.sector')}</th>
              <th className="px-5 py-2.5">{t('dossiers.fiscalYear')}</th>
              <th className="px-5 py-2.5">{t('dossiers.status')}</th>
              <th className="px-5 py-2.5">{t('dossiers.risk')}</th>
              <th className="px-5 py-2.5">{t('dossiers.createdAt')}</th>
              <th className="px-5 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-5 py-3 font-mono text-xs">{c.reference}</td>
                <td className="px-5 py-3 font-medium text-slate-900">{c.taxpayer.raison_sociale}</td>
                <td className="px-5 py-3 font-mono text-xs">{c.taxpayer.niu}</td>
                <td className="px-5 py-3 text-slate-600">{c.taxpayer.sector || '—'}</td>
                <td className="px-5 py-3">{c.fiscal_year}</td>
                <td className="px-5 py-3"><Badge variant={statusVariant(c.status)}>{t(statusLabelKey(c.status))}</Badge></td>
                <td className="px-5 py-3"><Badge variant={riskVariant(c.risk_level)}>{t(riskLabelKey(c.risk_level))}</Badge></td>
                <td className="px-5 py-3 text-slate-500">{formatDate(c.created_at)}</td>
                <td className="px-5 py-3">
                  <Link href={`/dossiers/${c.id}`}>
                    <Button variant="outline" size="sm">{t('dossiers.open')}</Button>
                  </Link>
                </td>
              </tr>
            ))}
            {cases.length === 0 && !isLoading && (
              <tr><td colSpan={9} className="px-5 py-8 text-center text-slate-500">{t('dossiers.noCases')}</td></tr>
            )}
          </tbody>
        </table>
      </Card>
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
