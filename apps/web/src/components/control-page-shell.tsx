'use client';

import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useT, type MessageKey } from '@/lib/i18n';

/**
 * Standard right-pane shell for a single audit-control subcategory.
 * Shows the control title, subtitle (CGI/LPF anchor), a back link to the
 * parent module, and a placeholder body until the real control logic ships.
 */
export function ControlPageShell({
  parentHref,
  parentLabelKey,
  titleKey,
  subtitleKey,
  Icon,
}: {
  parentHref: string;
  parentLabelKey: MessageKey;
  titleKey: MessageKey;
  subtitleKey: MessageKey;
  Icon: React.ComponentType<{ className?: string }>;
}) {
  const t = useT();
  return (
    <div className="space-y-6">
      <Link
        href={parentHref}
        className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        {t(parentLabelKey)}
      </Link>

      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Icon className="w-6 h-6 text-black" />
          {t(titleKey)}
        </h1>
        <p className="text-sm text-slate-500 mt-1">{t(subtitleKey)}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-slate-500">{t('common.optional')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-slate-500 py-12 text-center italic">
            {t('common.comingSoon')}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
