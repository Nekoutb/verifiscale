'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Users, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ControlHeader } from '@/components/control-header';
import { AccountPositionTable, type PositionAccount } from '@/components/account-position';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { formatXAF } from '@/lib/utils';

type Resp = {
  data_loaded: boolean;
  summary: {
    account_count: number; accounts_in_debit: number; flagged_months_total: number;
    max_debit_xaf: number; unjustified_count: number; unjustified_xaf: number;
    tb_filename: string | null; gl_filename: string | null;
  } | null;
  accounts: PositionAccount[];
};

export default function ComptesAssociesPage() {
  const t = useT();
  const { currentCase } = useApp();

  const { data, isLoading } = useQuery({
    queryKey: ['comptes-associes', currentCase?.id],
    queryFn: () => api<Resp>(`/audit-cases/${currentCase!.id}/comptes-associes`),
    enabled: !!currentCase,
  });

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" />
        {t('nav.corporateTax')}
      </Link>
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Users className="w-6 h-6 text-black" />
          Comptes d&apos;associés — comptes 46XXX
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Position mensuelle du compte 46 : un solde <b>débiteur</b> est proscrit — il
          établit que des fonds ont été mis à la disposition de l&apos;associé.
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
            actual={data.summary.max_debit_xaf}
            variance={data.summary.max_debit_xaf}
            exposure={data.summary.unjustified_xaf}
            sublabels={{
              expected: 'Solde débiteur autorisé (aucun)',
              actual: 'Pointe débitrice constatée',
              variance: 'Dépassement',
              exposure: 'Avances non justifiées (revenus réputés distribués)',
            }}
            stats={[
              { label: 'Comptes 46 analysés', value: data.summary.account_count },
              { label: 'Comptes passés débiteurs', value: data.summary.accounts_in_debit,
                tone: data.summary.accounts_in_debit > 0 ? 'err' : 'ok' },
              { label: 'Mois en position débitrice', value: data.summary.flagged_months_total,
                tone: data.summary.flagged_months_total > 0 ? 'err' : 'ok' },
              { label: 'Transactions non justifiées', value: data.summary.unjustified_count,
                tone: data.summary.unjustified_count > 0 ? 'warn' : 'ok' },
            ]}
          />

          {data.summary.unjustified_count > 0 && (
            <div className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 text-xs text-rose-900 flex items-start gap-2">
              <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                <b>{data.summary.unjustified_count} transaction(s) débitrice(s) sans justification</b>{' '}
                ({formatXAF(data.summary.unjustified_xaf)}) — elles alimentent la table
                des constatations tant que la case « justification reçue » n&apos;est pas cochée.
              </span>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Position mensuelle par compte</CardTitle>
              <div className="text-xs text-slate-500 mt-1">
                Balance : <span className="font-mono">{data.summary.tb_filename ?? '—'}</span> ·
                Grand-livre : <span className="font-mono">{data.summary.gl_filename ?? '—'}</span>
              </div>
            </CardHeader>
            <CardContent>
              <AccountPositionTable
                accounts={data.accounts}
                caseId={currentCase.id}
                module="SHAREHOLDER"
                requireJustification
                flagLabel={() => 'Solde débiteur — fonds mis à disposition de l’associé'}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
