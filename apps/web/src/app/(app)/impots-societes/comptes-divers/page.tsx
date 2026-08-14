'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Shuffle, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ControlHeader } from '@/components/control-header';
import { AccountPositionTable, type PositionAccount } from '@/components/account-position';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';

type Resp = {
  data_loaded: boolean;
  summary: {
    debtor_account_count: number; creditor_account_count: number;
    debtor_flagged_months: number; creditor_flagged_months: number;
    max_debit_xaf: number; max_credit_xaf: number;
    tb_filename: string | null; gl_filename: string | null;
  } | null;
  debtors: PositionAccount[];
  creditors: PositionAccount[];
};

export default function ComptesDiversPage() {
  const t = useT();
  const { currentCase } = useApp();

  const { data, isLoading } = useQuery({
    queryKey: ['comptes-divers', currentCase?.id],
    queryFn: () => api<Resp>(`/audit-cases/${currentCase!.id}/comptes-divers`),
    enabled: !!currentCase,
  });

  const label = (n: 'DEBIT' | 'CREDIT' | null) =>
    n === 'DEBIT'
      ? 'Solde débiteur — créances sur des tiers non identifiés'
      : 'Solde créditeur — dettes envers des tiers non identifiés';

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" />
        {t('nav.corporateTax')}
      </Link>
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Shuffle className="w-6 h-6 text-black" />
          Comptes divers — 4711 débiteurs / 4712 créditeurs
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Position mensuelle : un solde <b>débiteur</b> traduit des créances sur des tiers
          non identifiés, un solde <b>créditeur</b> des dettes envers des tiers non
          identifiés — les deux exposent à des amendes et pénalités.
        </p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center italic">
          Sélectionnez un dossier dans la liste « Dossiers en cours ».
        </div></CardContent></Card>
      )}
      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">Analyse…</div></CardContent></Card>
      )}
      {currentCase && data && !data.data_loaded && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center italic">
          Chargez la balance générale et le grand-livre dans « Données ».
        </div></CardContent></Card>
      )}

      {currentCase && data?.data_loaded && data.summary && (
        <>
          <ControlHeader
            expected={0}
            actual={data.summary.max_debit_xaf + data.summary.max_credit_xaf}
            variance={data.summary.max_debit_xaf + data.summary.max_credit_xaf}
            exposure={data.summary.max_debit_xaf + data.summary.max_credit_xaf}
            sublabels={{
              expected: 'Position attendue (soldes apurés)',
              actual: 'Positions constatées (débit + crédit)',
              variance: 'Soldes sur tiers non identifiés',
              exposure: 'Assiette des amendes et pénalités',
            }}
            stats={[
              { label: 'Comptes 4711', value: data.summary.debtor_account_count },
              { label: 'Comptes 4712', value: data.summary.creditor_account_count },
              { label: 'Mois signalés — 4711', value: data.summary.debtor_flagged_months,
                tone: data.summary.debtor_flagged_months > 0 ? 'err' : 'ok' },
              { label: 'Mois signalés — 4712', value: data.summary.creditor_flagged_months,
                tone: data.summary.creditor_flagged_months > 0 ? 'err' : 'ok' },
            ]}
          />

          <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900 flex items-start gap-2">
            <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>
              Les soldes en <b className="text-rose-700">rose</b> sont débiteurs (créances
              sur tiers non identifiés) ; ceux en <b className="text-amber-800">ambre</b>
              {' '}sont créditeurs (dettes envers tiers non identifiés). Cliquez un compte pour
              révéler les transactions à l&apos;origine de la position.
            </span>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">4711 — Débiteurs divers</CardTitle>
            </CardHeader>
            <CardContent>
              <AccountPositionTable accounts={data.debtors} caseId={currentCase.id}
                                    module="SUNDRY" flagLabel={label} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">4712 — Créditeurs divers</CardTitle>
            </CardHeader>
            <CardContent>
              <AccountPositionTable accounts={data.creditors} caseId={currentCase.id}
                                    module="SUNDRY" flagLabel={label} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
