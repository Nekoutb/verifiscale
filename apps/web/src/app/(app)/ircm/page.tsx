'use client';

import { Coins } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useT } from '@/lib/i18n';

export default function IRCMPage() {
  const t = useT();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Coins className="w-6 h-6 text-black" />
          {t('nav.ircm')}
        </h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-slate-500">{t('common.optional')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-slate-500 py-6 text-center italic">
            {/* TODO: IRCM — dividendes, intérêts, plus-values, retenue à la source 16,5% / 18% */}
            —
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
