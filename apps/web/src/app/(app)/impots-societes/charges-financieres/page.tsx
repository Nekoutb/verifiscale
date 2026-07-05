'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Building2, Info, Plus, Trash2, Upload, Paperclip, Pencil,
  ShieldCheck, ShieldX, ShieldAlert, RefreshCw, Landmark, MapPin, Globe,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, apiUploadForm, getToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF } from '@/lib/utils';

interface AssocieView {
  id: string;
  nom: string;
  niu: string | null;
  pct_detention: number | null;
  is_resident: boolean;
  is_significant: boolean;
  avance_moyenne_xaf: number;
  interet_servi_xaf: number;
  compte_gl: string | null;
  convention_enregistree: boolean;
  has_convention_file: boolean;
  taux_implicite_pct: number | null;
  t1_excess_xaf: number;
  t2_failed: boolean;
  t3_excess_xaf: number;
  t4_excess_xaf: number;
  reintegration_xaf: number;
  verdict: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE';
  verdict_reason: string;
  verdict_source: string;
  findings: string[];
}

interface ChgFinResp {
  case_id: string;
  interest_accounts: string[];
  gl_by_account: Record<string, number>;
  associes: AssocieView[];
  summary: {
    beac_cap_pct: number;
    capitaux_propres_xaf: number | null;
    ebitda_fiscal_xaf: number | null;
    avance_max_t3_xaf: number | null;
    interet_max_t4_xaf: number | null;
    gl_interest_67_xaf: number;
    gl_interest_assoc_xaf: number;
    avances_sig_total_xaf: number;
    interets_sig_total_xaf: number;
    cc_associe_debiteur_xaf: number;
    associe_count: number;
    non_eligible_count: number;
    total_reintegration_xaf: number;
    ircm_base_xaf: number;
    ircm_rate_pct: number;
  };
  beac: {
    tiao_pct: number; marginal_lending_pct: number; deposit_pct: number;
    art7b_cap_pct: number; fetched_at: string; source: string;
  };
  params: { capitaux_propres_xaf: number | null; ebitda_fiscal_xaf: number | null; rate_basis: string };
  equity_source: string;
  ebitda_source: string;
  derivation: {
    available: boolean;
    source_filename?: string;
    capitaux_propres_xaf?: number;
    resultat_avant_is_xaf?: number;
    interets_67_xaf?: number;
    amortissements_68_xaf?: number;
    ebitda_fiscal_xaf?: number;
  };
  cc_rollforward: {
    accounts: {
      account_code: string;
      account_name: string | null;
      opening_xaf: number;
      months: { month: number; label: string; closing_xaf: number; debtor: boolean }[];
      debtor_months: number;
      max_debtor_xaf: number;
      imputed_interest_xaf: number;
    }[];
    total_imputed_interest_xaf: number;
    any_debtor: boolean;
    opening_source: string;
  };
  legal_reference: string;
}

export default function ChargesFinancieresPage() {
  const t = useT();
  const { currentCase } = useApp();
  const qc = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['charges-fin', currentCase?.id],
    queryFn: () => api<ChgFinResp>(`/audit-cases/${currentCase!.id}/charges-financieres`),
    enabled: !!currentCase,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['charges-fin', currentCase?.id] });

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" /> Impôts sur les sociétés
      </Link>

      <div>
        <h1 className="font-display text-2xl font-extrabold flex items-center gap-2 text-black tracking-tight">
          <Building2 className="w-6 h-6 text-black" /> Charges financières
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          CGI Cameroun, Art. 7 B — intérêts servis aux associés : plafond de taux (BEAC + 2 pts),
          convention enregistrée, sous-capitalisation (1,5× capitaux propres), earnings-stripping (25% EBITDA).
        </p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-center py-10 text-slate-500">{t('data.noCaseTitle')}</div></CardContent></Card>
      )}
      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">Chargement…</div></CardContent></Card>
      )}

      {data && currentCase && (
        <>
          <BeacBanner caseId={currentCase.id} beac={data.beac} onChange={() => { void refetch(); }} />

          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <KPI label="Plafond taux (BEAC+2)" value={`${data.summary.beac_cap_pct}%`} />
            <KPI label="Σ intérêts cl.67 (GL)" value={formatXAF(data.summary.gl_interest_67_xaf)} />
            <KPI label="Intérêts associés" value={formatXAF(data.summary.gl_interest_assoc_xaf)} />
            <KPI label="Associés prêteurs" value={data.summary.associe_count} />
            <KPI label="Non déductibles" value={data.summary.non_eligible_count}
                 tone={data.summary.non_eligible_count > 0 ? 'err' : 'ok'} />
            <KPI label="Réintégration estimée" value={formatXAF(data.summary.total_reintegration_xaf)}
                 tone={data.summary.total_reintegration_xaf > 0 ? 'err' : 'ok'} />
          </div>

          <ParamsCard caseId={currentCase.id} data={data} onSaved={() => { void refetch(); }} />

          <CcRollforwardCard data={data} />

          <AssociesCard caseId={currentCase.id} data={data} onChange={() => { void refetch(); invalidate(); }} />

          <div className="text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              <b>Base légale :</b> CGI Cameroun, Art. 7 B. <b>Comptes SYSCOHADA :</b> 6713 (dettes liées
              aux participations), 6741/6742 (avances et comptes courants bloqués). Taux des avances BEAC
              récupéré en direct sur beac.int.
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function CcRollforwardCard({ data }: { data: ChgFinResp }) {
  const cc = data.cc_rollforward;
  if (!cc || cc.accounts.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle>Comptes courants d&apos;associés — suivi mensuel (compte 462)</CardTitle></CardHeader>
        <CardContent>
          <div className="text-xs text-slate-500 italic py-2">
            Aucun mouvement sur les comptes 462 dans le grand-livre chargé, ou grand-livre absent.
            Le suivi mensuel (ouverture + mouvements → clôture) s&apos;activera dès qu&apos;un GL contenant
            des comptes courants d&apos;associés sera importé.
          </div>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Comptes courants d&apos;associés — rollforward mensuel (acte anormal de gestion)</CardTitle>
          <span className="text-xs text-slate-500">
            Intérêt théorique total : <b className="font-mono tabular-nums text-black font-extrabold border-b-2 border-black">{formatXAF(cc.total_imputed_interest_xaf)}</b>
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-[11px] text-slate-500 mb-3">
          Solde de clôture mois par mois (ouverture {cc.opening_source === 'trial_balance' ? 'depuis la balance' : 'supposée 0 — balance absente'} + mouvements).
          ■ mois <b>débiteur</b> = la société a avancé des fonds à l&apos;associé → intérêt théorique réintégré
          (taux BEAC+2 prorata temporis). On ne nette jamais entre associés.
        </div>
        <div className="space-y-4">
          {cc.accounts.map((acc) => (
            <div key={acc.account_code} className="border border-slate-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2 text-xs">
                <div>
                  <span className="font-mono font-semibold">{acc.account_code}</span>
                  {acc.account_name && <span className="text-slate-500 ml-2">{acc.account_name}</span>}
                  <span className="text-slate-400 ml-2">· ouverture {formatXAF(acc.opening_xaf)}</span>
                </div>
                <div className="flex items-center gap-3">
                  {acc.debtor_months > 0 ? (
                    <span className="text-black font-extrabold">{acc.debtor_months} mois débiteur(s) · max {formatXAF(acc.max_debtor_xaf)}</span>
                  ) : (
                    <span className="text-neutral-700">toujours créditeur ✓</span>
                  )}
                  {acc.imputed_interest_xaf > 0 && (
                    <span className="font-mono tabular-nums text-black font-bold">intérêt {formatXAF(acc.imputed_interest_xaf)}</span>
                  )}
                </div>
              </div>
              {/* 12-month strip */}
              <div className="grid grid-cols-12 gap-1">
                {acc.months.map((m) => (
                  <div key={m.month}
                    className={cn('rounded text-center py-1 px-0.5',
                      m.debtor ? 'bg-black text-white border border-black' : 'bg-white border border-neutral-200')}
                    title={`${m.label} : clôture ${m.closing_xaf.toLocaleString('fr-FR')} FCFA`}>
                    <div className={cn('text-[9px] uppercase', m.debtor ? 'text-neutral-300' : 'text-neutral-500')}>{m.label}</div>
                    <div className={cn('text-[9px] font-mono tabular-nums font-semibold',
                      m.debtor ? 'text-white' : 'text-neutral-700')}>
                      {Math.abs(m.closing_xaf) >= 1_000_000
                        ? `${(m.closing_xaf / 1_000_000).toFixed(1)}M`
                        : Math.round(m.closing_xaf / 1000) + 'k'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function BeacBanner({ caseId, beac, onChange }: {
  caseId: string; beac: ChgFinResp['beac']; onChange: () => void;
}) {
  const qc = useQueryClient();
  const refreshMut = useMutation({
    mutationFn: async () => api(`/reference/beac-rates?refresh=true`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['charges-fin', caseId] }); onChange(); },
  });
  return (
    <Card>
      <CardContent>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <Landmark className="w-5 h-5 text-black" />
            <div className="text-xs">
              <div className="font-semibold text-slate-700">Taux de référence BEAC — TIAO (live · beac.int)</div>
              <div className="text-slate-600 mt-0.5">
                TIAO <b className="font-mono">{beac.tiao_pct}%</b>
                <span className="ml-2 px-1.5 py-0.5 rounded bg-slate-100 text-[10px]">
                  source : {beac.source}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <div className="px-2 py-1 rounded border border-black text-black font-mono tabular-nums font-bold">
              Plafond Art. 7 B = TIAO + 2 = {beac.art7b_cap_pct}%
            </div>
            <button onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}
              className="inline-flex items-center gap-1 px-2 py-1 rounded border border-neutral-300 hover:border-black">
              <RefreshCw className={cn('w-3 h-3', refreshMut.isPending && 'animate-spin')} /> Actualiser
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ParamsCard({ caseId, data, onSaved }: { caseId: string; data: ChgFinResp; onSaved: () => void }) {
  const [override, setOverride] = useState(false);
  const [cp, setCp] = useState(data.params.capitaux_propres_xaf?.toString() || '');
  const [eb, setEb] = useState(data.params.ebitda_fiscal_xaf?.toString() || '');
  useEffect(() => {
    setCp(data.params.capitaux_propres_xaf?.toString() || '');
    setEb(data.params.ebitda_fiscal_xaf?.toString() || '');
  }, [data.params.capitaux_propres_xaf, data.params.ebitda_fiscal_xaf]);

  const d = data.derivation;
  const eqAuto = data.equity_source === 'trial_balance';
  const ebAuto = data.ebitda_source === 'trial_balance';

  const saveMut = useMutation({
    mutationFn: async () => api(
      `/audit-cases/${caseId}/charges-financieres/params`,
      { method: 'PATCH', body: {
        capitaux_propres_xaf: cp ? Number(cp) : null,
        ebitda_fiscal_xaf: eb ? Number(eb) : null,
      } },
    ),
    onSuccess: () => { setOverride(false); onSaved(); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Paramètres dérivés de la comptabilité (T3 sous-cap. · T4 earnings-stripping)</CardTitle>
          <button onClick={() => setOverride(!override)} className="text-[11px] text-black hover:underline inline-flex items-center gap-1">
            <Pencil className="w-3 h-3" /> {override ? 'annuler la saisie manuelle' : 'forcer une valeur manuelle'}
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {!d.available && (
          <div className="text-xs text-black bg-neutral-50 border border-neutral-300 rounded p-2 mb-3">
            Aucune balance générale (TB) parsée — chargez la balance dans Données pour le calcul
            automatique des capitaux propres et de l'EBITDA fiscal.
          </div>
        )}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 text-xs">
          {/* Capitaux propres */}
          <div className="border border-slate-200 rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
              Capitaux propres (comptes 10–15)
            </div>
            <div className="font-mono tabular-nums text-lg font-extrabold text-black">
              {data.summary.capitaux_propres_xaf != null ? formatXAF(data.summary.capitaux_propres_xaf) : '—'}
              <span className="ml-2 text-[10px] font-normal text-slate-400">
                {eqAuto ? 'auto · balance' : data.equity_source === 'manual' ? 'saisie manuelle' : 'indisponible'}
              </span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              → Plafond avances T3 (1,5×) : <b>{data.summary.avance_max_t3_xaf ? formatXAF(data.summary.avance_max_t3_xaf) : '—'}</b>
            </div>
          </div>

          {/* EBITDA fiscal with derivation */}
          <div className="border border-slate-200 rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
              EBITDA fiscal (résultat av. IS + intérêts 67X + amortissements 68X)
            </div>
            <div className="font-mono tabular-nums text-lg font-extrabold text-black">
              {data.summary.ebitda_fiscal_xaf != null ? formatXAF(data.summary.ebitda_fiscal_xaf) : '—'}
              <span className="ml-2 text-[10px] font-normal text-slate-400">
                {ebAuto ? 'auto · balance' : data.ebitda_source === 'manual' ? 'saisie manuelle' : 'indisponible'}
              </span>
            </div>
            {d.available && (
              <div className="text-[10px] text-slate-500 mt-1 space-y-0.5">
                <div>Résultat avant IS (Σ 6/7/8 sauf 89) : <b className="font-mono">{formatXAF(d.resultat_avant_is_xaf || 0)}</b></div>
                <div>+ Intérêts (67X) : <b className="font-mono">{formatXAF(d.interets_67_xaf || 0)}</b></div>
                <div>+ Amortissements (68X) : <b className="font-mono">{formatXAF(d.amortissements_68_xaf || 0)}</b></div>
                <div className="pt-0.5 border-t border-slate-100">→ Plafond intérêts T4 (25%) : <b>{data.summary.interet_max_t4_xaf ? formatXAF(data.summary.interet_max_t4_xaf) : '—'}</b></div>
              </div>
            )}
          </div>
        </div>

        <div className="mt-3 flex items-center gap-6 text-[11px] text-slate-600">
          <div>Avances associés ≥25% : <b className="font-mono">{formatXAF(data.summary.avances_sig_total_xaf)}</b></div>
          <div>Intérêts associés ≥25% : <b className="font-mono">{formatXAF(data.summary.interets_sig_total_xaf)}</b></div>
        </div>

        {override && (
          <div className="mt-4 pt-3 border-t border-slate-200 grid grid-cols-1 lg:grid-cols-3 gap-3 items-end">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1">Capitaux propres (override FCFA)</label>
              <input value={cp} onChange={(e) => setCp(e.target.value)} type="number"
                className="w-full px-2 py-1.5 border border-slate-300 rounded font-mono"
                placeholder={d.capitaux_propres_xaf?.toString() || 'auto'} />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1">EBITDA fiscal (override FCFA)</label>
              <input value={eb} onChange={(e) => setEb(e.target.value)} type="number"
                className="w-full px-2 py-1.5 border border-slate-300 rounded font-mono"
                placeholder={d.ebitda_fiscal_xaf?.toString() || 'auto'} />
            </div>
            <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}
              className="px-3 py-2 text-xs rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-50">
              {saveMut.isPending ? 'Enregistrement…' : 'Enregistrer (laisser vide = auto)'}
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AssociesCard({ caseId, data, onChange }: { caseId: string; data: ChgFinResp; onChange: () => void }) {
  const [showAdd, setShowAdd] = useState(false);

  const delMut = useMutation({
    mutationFn: async (id: string) => api(`/audit-cases/${caseId}/charges-financieres/associes/${id}`, { method: 'DELETE' }),
    onSuccess: onChange,
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Associés prêteurs — tests T1 à T4</CardTitle>
          <button onClick={() => setShowAdd(!showAdd)}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded bg-black text-white hover:bg-neutral-800">
            <Plus className="w-3 h-3" /> Ajouter un associé
          </button>
        </div>
      </CardHeader>
      {showAdd && <AddAssocieForm caseId={caseId} onDone={() => { setShowAdd(false); onChange(); }} />}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
              <th className="px-3 py-2.5">Associé</th>
              <th className="px-3 py-2.5 text-right">% détention</th>
              <th className="px-3 py-2.5 text-right">Avance</th>
              <th className="px-3 py-2.5 text-right">Intérêt servi</th>
              <th className="px-3 py-2.5 text-right">Taux impl.</th>
              <th className="px-3 py-2.5">Convention</th>
              <th className="px-3 py-2.5">Tests</th>
              <th className="px-3 py-2.5">Verdict</th>
              <th className="px-3 py-2.5 text-right">Réint.</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {data.associes.map((a) => (
              <tr key={a.id} className={cn('border-b border-neutral-100',
                a.verdict === 'NON_ELIGIBLE' && 'bg-neutral-100/60',
                a.verdict === 'A_REINSTRUIRE' && 'bg-neutral-50/70')}>
                <td className="px-3 py-2">
                  <div className="font-medium">{a.nom}</div>
                  <div className="text-[10px] text-slate-500 flex items-center gap-1">
                    {a.is_resident ? <><MapPin className="w-2.5 h-2.5 text-neutral-700" /> Résident</>
                                   : <><Globe className="w-2.5 h-2.5 text-black" /> Non-résident</>}
                    {a.niu && <span className="font-mono">· {a.niu}</span>}
                  </div>
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  {a.pct_detention != null ? `${a.pct_detention}%` : '—'}
                  {a.is_significant && <span className="ml-1 text-[9px] px-1 rounded border border-black text-black font-bold">≥25%</span>}
                </td>
                <td className="px-3 py-2 text-right font-mono">{formatXAF(a.avance_moyenne_xaf)}</td>
                <td className="px-3 py-2 text-right font-mono">{formatXAF(a.interet_servi_xaf)}</td>
                <td className="px-3 py-2 text-right font-mono">{a.taux_implicite_pct != null ? `${a.taux_implicite_pct.toFixed(2)}%` : '—'}</td>
                <td className="px-3 py-2">
                  {a.convention_enregistree
                    ? <span className="text-neutral-700 text-[11px]">✓ enregistrée</span>
                    : <span className="text-black font-bold text-[11px]">✗ absente</span>}
                  <ConventionUpload caseId={caseId} associeId={a.id} hasFile={a.has_convention_file} onDone={onChange} />
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-0.5">
                    {a.findings.filter(f => f.startsWith('T')).map((f) => (
                      <span key={f} className="text-[8px] px-1 py-0.5 rounded border border-black text-black font-mono font-bold">{f.split('-')[0]}</span>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2"><VerdictBadge v={a.verdict} /></td>
                <td className="px-3 py-2 text-right font-mono tabular-nums font-extrabold text-black">
                  {a.reintegration_xaf > 0 ? formatXAF(a.reintegration_xaf) : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  <button onClick={() => { if (confirm(`Supprimer ${a.nom} ?`)) delMut.mutate(a.id); }}
                    className="text-neutral-600 hover:text-black hover:bg-neutral-100 rounded p-1" title="Supprimer">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </td>
              </tr>
            ))}
            {data.associes.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-8 text-center text-slate-500 italic">
                Aucun associé prêteur saisi. Cliquez « Ajouter un associé » et renseignez l'avance + l'intérêt servi.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      {/* Reasons detail */}
      {data.associes.some(a => a.verdict !== 'ELIGIBLE') && (
        <div className="px-3 py-3 border-t border-slate-100 space-y-1">
          {data.associes.filter(a => a.verdict !== 'ELIGIBLE').map((a) => (
            <div key={a.id} className="text-[11px] text-slate-600">
              <b>{a.nom} :</b> {a.verdict_reason}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function AddAssocieForm({ caseId, onDone }: { caseId: string; onDone: () => void }) {
  const [f, setF] = useState({ nom: '', niu: '', pct_detention: '', is_resident: true, avance_moyenne_xaf: '', interet_servi_xaf: '', compte_gl: '6713', convention_enregistree: false });
  const addMut = useMutation({
    mutationFn: async () => api(`/audit-cases/${caseId}/charges-financieres/associes`, {
      method: 'POST',
      body: {
        nom: f.nom, niu: f.niu || null,
        pct_detention: f.pct_detention ? Number(f.pct_detention) : null,
        is_resident: f.is_resident,
        avance_moyenne_xaf: f.avance_moyenne_xaf ? Number(f.avance_moyenne_xaf) : null,
        interet_servi_xaf: f.interet_servi_xaf ? Number(f.interet_servi_xaf) : null,
        compte_gl: f.compte_gl,
        convention_enregistree: f.convention_enregistree,
      },
    }),
    onSuccess: onDone,
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });
  return (
    <div className="px-3 py-3 bg-slate-50 border-b border-slate-200">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
        <input placeholder="Nom de l'associé*" value={f.nom} onChange={e => setF({ ...f, nom: e.target.value })} className="px-2 py-1.5 border border-slate-300 rounded" />
        <input placeholder="NIU" value={f.niu} onChange={e => setF({ ...f, niu: e.target.value })} className="px-2 py-1.5 border border-slate-300 rounded" />
        <input placeholder="% détention" type="number" value={f.pct_detention} onChange={e => setF({ ...f, pct_detention: e.target.value })} className="px-2 py-1.5 border border-slate-300 rounded" />
        <select value={f.compte_gl} onChange={e => setF({ ...f, compte_gl: e.target.value })} className="px-2 py-1.5 border border-slate-300 rounded">
          <option value="6713">6713 — dettes liées participations</option>
          <option value="6741">6741 — avances reçues</option>
          <option value="6742">6742 — comptes courants bloqués</option>
        </select>
        <input placeholder="Avance moyenne (FCFA)" type="number" value={f.avance_moyenne_xaf} onChange={e => setF({ ...f, avance_moyenne_xaf: e.target.value })} className="px-2 py-1.5 border border-slate-300 rounded font-mono" />
        <input placeholder="Intérêt servi (FCFA)" type="number" value={f.interet_servi_xaf} onChange={e => setF({ ...f, interet_servi_xaf: e.target.value })} className="px-2 py-1.5 border border-slate-300 rounded font-mono" />
        <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={f.is_resident} onChange={e => setF({ ...f, is_resident: e.target.checked })} /> Résident</label>
        <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={f.convention_enregistree} onChange={e => setF({ ...f, convention_enregistree: e.target.checked })} /> Convention enregistrée</label>
      </div>
      <div className="flex justify-end mt-2">
        <button onClick={() => addMut.mutate()} disabled={!f.nom.trim() || addMut.isPending}
          className="px-3 py-1.5 text-xs rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-50">
          {addMut.isPending ? 'Ajout…' : 'Ajouter'}
        </button>
      </div>
    </div>
  );
}

function ConventionUpload({ caseId, associeId, hasFile, onDone }: { caseId: string; associeId: string; hasFile: boolean; onDone: () => void }) {
  const upMut = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiUploadForm(`/audit-cases/${caseId}/charges-financieres/associes/${associeId}/convention`, fd);
    },
    onSuccess: onDone,
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });
  const openFile = async () => {
    const token = getToken();
    const res = await fetch(`/audit-cases/${caseId}/charges-financieres/associes/${associeId}/convention`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) { alert(`HTTP ${res.status}`); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };
  return (
    <div className="mt-1 flex items-center gap-1">
      <label className="inline-flex items-center gap-0.5 text-[10px] text-black hover:underline cursor-pointer">
        <Upload className="w-2.5 h-2.5" /> {hasFile ? 'remplacer' : 'charger PDF'}
        <input type="file" hidden accept=".pdf" onChange={(e) => { const f = e.target.files?.[0]; if (f) upMut.mutate(f); e.target.value=''; }} />
      </label>
      {hasFile && (
        <button onClick={openFile} className="text-[10px] text-black hover:underline inline-flex items-center gap-0.5">
          <Paperclip className="w-2.5 h-2.5" /> voir
        </button>
      )}
    </div>
  );
}

function VerdictBadge({ v }: { v: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE' }) {
  if (v === 'ELIGIBLE') return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 bg-transparent text-neutral-700 font-normal">
      <ShieldCheck className="w-3 h-3" /> Déductible <span className="tracking-widest">●○○</span>
    </span>
  );
  if (v === 'NON_ELIGIBLE') return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-black bg-transparent text-black font-extrabold">
      <ShieldX className="w-3 h-3" /> Non déductible <span className="tracking-widest">●●●</span>
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 bg-transparent text-neutral-700 font-medium">
      <ShieldAlert className="w-3 h-3" /> À réinstruire <span className="tracking-widest">●●○</span>
    </span>
  );
}

function KPI({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls =
    tone === 'err'  ? 'text-black font-extrabold border-b-[3px] border-black inline-block pb-0.5'
    : tone === 'warn' ? 'text-black font-semibold'
    : tone === 'ok'   ? 'text-neutral-700 font-medium'
    : 'text-black font-bold';
  return (
    <Card><CardContent>
      <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">{label}</div>
      <div className={`text-base mt-1 font-display tabular-nums ${cls}`}>{value}</div>
    </CardContent></Card>
  );
}
