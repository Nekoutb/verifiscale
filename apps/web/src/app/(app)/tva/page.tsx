'use client';

import Link from 'next/link';
import { Receipt, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useT, type MessageKey } from '@/lib/i18n';

interface SubLink {
  href: string;
  titleKey: MessageKey;
  subtitleKey: MessageKey;
}

const LINKS: SubLink[] = [
  { href: '/tva/rapprochement', titleKey: 'vat.rapprochement.title', subtitleKey: 'vat.rapprochement.subtitle' },
  { href: '/tva/deductible',    titleKey: 'vat.deductible.title',    subtitleKey: 'vat.deductible.subtitle' },
  { href: '/tva/collectee',     titleKey: 'vat.collectee.title',     subtitleKey: 'vat.collectee.subtitle' },
  { href: '/tva/exonerations',  titleKey: 'vat.exonerations.title',  subtitleKey: 'vat.exonerations.subtitle' },
  { href: '/tva/synthese',      titleKey: 'vat.synthese.title',      subtitleKey: 'vat.synthese.subtitle' },
];

export default function VATPage() {
  const t = useT();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Receipt className="w-6 h-6 text-navy" />
          {t('nav.vat')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">{t('vat.subtitle')}</p>
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
