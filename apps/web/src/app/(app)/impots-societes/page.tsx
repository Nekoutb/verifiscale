'use client';

import Link from 'next/link';
import { Building2, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useT, type MessageKey } from '@/lib/i18n';

interface SubLink {
  href: string;
  titleKey: MessageKey;
  subtitleKey: MessageKey;
}

const LINKS: SubLink[] = [
  { href: '/impots-societes/amortissements',            titleKey: 'is.amortissements.title',           subtitleKey: 'is.amortissements.subtitle' },
  { href: '/impots-societes/reglements-especes',        titleKey: 'is.cash.title',                     subtitleKey: 'is.cash.subtitle' },
  { href: '/impots-societes/dons',                      titleKey: 'is.dons.title',                     subtitleKey: 'is.dons.subtitle' },
  { href: '/impots-societes/acomptes',                  titleKey: 'is.acomptes.title',                 subtitleKey: 'is.acomptes.subtitle' },
  { href: '/impots-societes/primes-assurance',          titleKey: 'is.assurance.title',                subtitleKey: 'is.assurance.subtitle' },
  { href: '/impots-societes/charges-financieres',       titleKey: 'is.financieres.title',              subtitleKey: 'is.financieres.subtitle' },
  { href: '/impots-societes/petit-materiel',            titleKey: 'is.petitMateriel.title',            subtitleKey: 'is.petitMateriel.subtitle' },
  { href: '/impots-societes/non-deductibles',           titleKey: 'is.nonDeductible.title',            subtitleKey: 'is.nonDeductible.subtitle' },
  { href: '/impots-societes/partiellement-deductibles', titleKey: 'is.partiellementDeductible.title',  subtitleKey: 'is.partiellementDeductible.subtitle' },
  { href: '/impots-societes/synthese',                  titleKey: 'is.synthese.title',                 subtitleKey: 'is.synthese.subtitle' },
];

export default function CorporateIncomeTaxPage() {
  const t = useT();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Building2 className="w-6 h-6 text-navy" />
          {t('nav.corporateTax')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">{t('is.subtitle')}</p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm text-slate-500 uppercase tracking-wider">{t('is.pickControl')}</CardTitle></CardHeader>
        <div className="divide-y divide-slate-100">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 transition group"
            >
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-900 text-sm">{t(l.titleKey)}</div>
                <div className="text-xs text-slate-500 mt-0.5">{t(l.subtitleKey)}</div>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-navy" />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
