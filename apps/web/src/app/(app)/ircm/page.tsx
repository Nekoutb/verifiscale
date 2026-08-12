'use client';

import { useQuery } from '@tanstack/react-query';
import { Coins, Info } from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { formatXAF } from '@/lib/utils';

/** Slice of /charges-financieres the IRCM section needs. */
type ChgFinSlice = {
  summary: { ircm_base_xaf: number; ircm_rate_pct: number };
  cc_rollforward: {
    total_imputed_interest_xaf: number;
    accounts: {
      account_code: string;
      account_name: string;
      debtor_months: number;
      max_debtor_xaf: number;
      imputed_interest_xaf: number;
    }[];
  } | null;
  associes: { nom: string; is_resident: boolean; interet_servi_xaf: number }[];
};

export default function IRCMPage() {
  const t = useT();
  const { currentCase } = useApp();

  const { data } = useQuery({
    queryKey: ['charges-financieres', currentCase?.id],
    queryFn: () => api<ChgFinSlice>(`/audit-cases/${currentCase!.id}/charges-financieres`),
    enabled: !!currentCase,
  });

  const ircmDue = data ? (data.summary.ircm_base_xaf * data.summary.ircm_rate_pct) / 100 : 0;
  const debtorAccounts = data?.cc_rollforward?.accounts.filter((a) => a.debtor_months > 0) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Coins className="w-6 h-6 text-black" />
          {t('nav.ircm')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Impôt sur le revenu des capitaux mobiliers — intérêts servis aux associés et
          soldes débiteurs des comptes courants.
        </p>
      </div>

      {!currentCase && (
        <Card><CardContent>
          <div className="text-sm text-slate-500 py-6 text-center italic">
            Sélectionnez un dossier pour afficher l&apos;analyse IRCM.
          </div>
        </CardContent></Card>
      )}

      {currentCase && data && (
        <>
          {/* Intérêts servis aux associés — assiette IRCM */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Intérêts servis aux associés — assiette IRCM</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                <div className="border border-neutral-200 rounded-lg px-3 py-2 bg-neutral-50">
                  <div className="text-[10px] uppercase tracking-wider text-neutral-500">Base IRCM</div>
                  <div className="font-mono tabular-nums text-sm font-bold text-black mt-0.5">
                    {formatXAF(data.summary.ircm_base_xaf)}
                  </div>
                </div>
                <div className="border border-neutral-200 rounded-lg px-3 py-2 bg-neutral-50">
                  <div className="text-[10px] uppercase tracking-wider text-neutral-500">Taux</div>
                  <div className="font-mono tabular-nums text-sm font-bold text-black mt-0.5">
                    {data.summary.ircm_rate_pct} %
                  </div>
                </div>
                <div className="border border-neutral-200 rounded-lg px-3 py-2 bg-rose-50 border-rose-200">
                  <div className="text-[10px] uppercase tracking-wider text-rose-700">IRCM dû (retenue à la source)</div>
                  <div className="font-mono tabular-nums text-sm font-extrabold text-rose-800 mt-0.5">
                    {formatXAF(ircmDue)}
                  </div>
                </div>
              </div>
              {data.associes.filter((a) => a.interet_servi_xaf > 0).length > 0 && (
                <div className="text-xs text-slate-600">
                  Associés servis en intérêts :{' '}
                  {data.associes.filter((a) => a.interet_servi_xaf > 0)
                    .map((a) => `${a.nom} (${formatXAF(a.interet_servi_xaf)}${a.is_resident ? '' : ' · non-résident'})`)
                    .join(' · ')}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Soldes débiteurs — mention déplacée depuis Charges d'intérêt */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Comptes courants d&apos;associés — soldes débiteurs (compte 462)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-[11px] text-slate-600 leading-relaxed flex items-start gap-2">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <span>
                  Un mois <b>débiteur</b> signifie que la société a avancé des fonds à
                  l&apos;associé : l&apos;intérêt théorique (taux BEAC + 2, prorata temporis)
                  est réintégré au résultat, et ce revenu réputé distribué entre dans le
                  champ de l&apos;<b>IRCM</b>. On ne nette jamais entre associés.
                </span>
              </div>
              {debtorAccounts.length === 0 ? (
                <div className="text-xs text-slate-500 italic">
                  Aucun solde débiteur détecté sur les comptes 462 du grand-livre chargé.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
                      <tr className="border-b border-neutral-200">
                        <th className="text-left px-2 py-1.5">Compte</th>
                        <th className="text-right px-2 py-1.5">Mois débiteurs</th>
                        <th className="text-right px-2 py-1.5">Pointe débitrice</th>
                        <th className="text-right px-2 py-1.5">Intérêt théorique réintégré</th>
                      </tr>
                    </thead>
                    <tbody>
                      {debtorAccounts.map((a) => (
                        <tr key={a.account_code} className="border-b border-neutral-100">
                          <td className="px-2 py-1.5">
                            <span className="font-mono font-semibold">{a.account_code}</span>
                            <span className="text-neutral-500 ml-1">{a.account_name}</span>
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">{a.debtor_months}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{formatXAF(a.max_debtor_xaf)}</td>
                          <td className="px-2 py-1.5 text-right font-mono font-bold text-rose-700">
                            {formatXAF(a.imputed_interest_xaf)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="text-[11px] text-slate-500">
                Détail mensuel et paramètres :{' '}
                <Link href="/impots-societes/charges-financieres" className="underline font-semibold text-black">
                  Charges d&apos;intérêt (comptes courants d&apos;associés)
                </Link>.
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
