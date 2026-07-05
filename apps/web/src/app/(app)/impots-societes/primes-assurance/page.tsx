'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Building2, Info, Upload, Paperclip, Trash2, Pencil,
  ShieldCheck, ShieldAlert, ShieldX, Globe, MapPin,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, apiUploadForm, getToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';

interface ContractView {
  id: string;
  filename: string;
  numero_police: string | null;
  assureur_nom: string | null;
  assureur_pays: string;
  assureur_local: boolean;
  beneficiaire_nom: string | null;
  beneficiaire_type: string;
  type_assurance: string;
  date_debut: string | null;
  date_fin: string | null;
  prime_annuelle_ttc: number;
  prime_exercice: number;
  compte_syscohada: string | null;
  verdict: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE';
  verdict_reason: string;
  verdict_source: 'AUTO_CONTRACT' | 'MANUAL_OVERRIDE';
  findings: string[];
  estimated_reintegration_xaf: number;
}

interface PrimesResp {
  case_id: string;
  prime_account_prefixes: string[];
  gl_by_account: Record<string, number>;
  contracts: ContractView[];
  summary: {
    gl_total_xaf: number;
    contracts_total_annuel_xaf: number;
    contracts_total_exercice_xaf: number;
    variance_xaf: number;
    variance_pct: number;
    reconciliation_status: 'OK' | 'VARIANCE_MAJOR' | 'NO_GL';
    charges_sans_contrat_xaf: number;
    auto_insurance_xaf: number;
    contract_count: number;
    eligible_count: number;
    non_eligible_count: number;
    reinstruire_count: number;
    total_reintegration_xaf: number;
  };
  legal_reference: string;
}

const TYPE_LABELS: Record<string, string> = {
  MULTIRISQUE: 'Multirisque', MATERIEL_TRANSPORT: 'Matériel transport',
  RISQUES_EXPLOITATION: 'Risques exploit.', RESP_PRODUCTEUR: 'RC producteur',
  INSOLVABILITE_CLIENT: 'Insolvabilité clients', TRANSPORT_VENTES: 'Transport ventes',
  SANTE_PERSONNEL: 'Santé personnel', RETRAITE_FIN_CARRIERE: 'Fin de carrière',
  VIE_HOMME_CLE: 'Vie homme-clé', VIE_DIRIGEANT: 'Vie dirigeant', RC: 'RC', AUTRE: 'Autre',
};
const BENEF_LABELS: Record<string, string> = {
  ENTREPRISE: 'Entreprise', DIRIGEANT: 'Dirigeant', FAMILLE_DIRIGEANT: 'Famille dirigeant',
  PERSONNEL: 'Personnel', MIXTE: 'Mixte', INCONNU: 'Inconnu',
};

export default function PrimesAssurancePage() {
  const t = useT();
  const { currentCase } = useApp();
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number; current: string } | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['primes-assurance', currentCase?.id],
    queryFn: () => api<PrimesResp>(`/audit-cases/${currentCase!.id}/primes-assurance`),
    enabled: !!currentCase,
  });

  const uploadMut = useMutation({
    mutationFn: async (toUpload: File[]) => {
      // Sequential, one file per request → real progress feedback
      const allItems: any[] = [];
      setProgress({ done: 0, total: toUpload.length, current: toUpload[0]?.name || '' });
      for (let i = 0; i < toUpload.length; i++) {
        setProgress({ done: i, total: toUpload.length, current: toUpload[i].name });
        const fd = new FormData();
        fd.append('files', toUpload[i]);
        const res = await apiUploadForm<{ processed: number; items: any[] }>(
          `/audit-cases/${currentCase!.id}/primes-assurance/contracts`, fd,
        );
        allItems.push(...(res.items || []));
        setProgress({ done: i + 1, total: toUpload.length, current: toUpload[i].name });
        // Live-refresh the table after each file so the auditor sees results stream in
        void qc.invalidateQueries({ queryKey: ['primes-assurance', currentCase?.id] });
      }
      return { processed: allItems.length, items: allItems };
    },
    onSuccess: () => {
      setFiles([]);
      setProgress(null);
      void qc.invalidateQueries({ queryKey: ['primes-assurance', currentCase?.id] });
    },
    onError: (e: any) => { setProgress(null); alert(`Échec upload : ${e?.message || 'erreur'}`); },
  });

  const deleteMut = useMutation({
    mutationFn: async (contractId: string) =>
      api(`/audit-cases/${currentCase!.id}/primes-assurance/contracts/${contractId}`,
          { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['primes-assurance', currentCase?.id] }),
    onError: (e: any) => alert(`Échec suppression : ${e?.message || 'erreur'}`),
  });

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" /> Impôts sur les sociétés
      </Link>

      <div>
        <h1 className="font-display text-2xl font-extrabold flex items-center gap-2 text-black tracking-tight">
          <Building2 className="w-6 h-6 text-black" /> Primes d&apos;assurance
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          CGI Cameroun, Art. 7 A (4) — déductibles si compagnie locale, bénéficiaire entreprise,
          et risque entraînant une diminution d&apos;actif net. Auto-assurance explicitement exclue.
        </p>
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-center py-10 text-slate-500">{t('data.noCaseTitle')}</div></CardContent></Card>
      )}
      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">Chargement…</div></CardContent></Card>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <KPI label="Contrats chargés" value={data.summary.contract_count} />
            <KPI label="Σ contrats (exercice)" value={formatXAF(data.summary.contracts_total_exercice_xaf)} />
            <KPI label="Σ GL 625+6685+6686" value={formatXAF(data.summary.gl_total_xaf)} />
            <KPI label="Écart GL ↔ contrats"
                 value={`${formatXAF(data.summary.variance_xaf)} (${data.summary.variance_pct}%)`}
                 tone={data.summary.reconciliation_status === 'OK' ? 'ok' : 'warn'} />
            <KPI label="Non déductibles" value={data.summary.non_eligible_count}
                 tone={data.summary.non_eligible_count > 0 ? 'err' : 'ok'} />
            <KPI label="Réintégration estimée" value={formatXAF(data.summary.total_reintegration_xaf)}
                 tone={data.summary.total_reintegration_xaf > 0 ? 'err' : 'ok'} />
          </div>

          <Card>
            <CardHeader><CardTitle>Rapprochement Σ contrats ↔ comptes 625X + 6685 + 6686</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Comptes SYSCOHADA balayés</div>
                  <div className="font-mono text-base">{data.prime_account_prefixes.join(' · ')}</div>
                  <div className="text-[10px] text-slate-500 mt-2">Détail par compte :</div>
                  <ul className="text-[11px] mt-1 space-y-0.5">
                    {Object.entries(data.gl_by_account).map(([acc, amt]) => (
                      <li key={acc} className="flex justify-between border-b border-slate-100 py-0.5">
                        <span className="font-mono">{acc}</span>
                        <span className="font-mono">{formatXAF(amt)}</span>
                      </li>
                    ))}
                    {Object.keys(data.gl_by_account).length === 0 && (
                      <li className="text-slate-400 italic">aucun mouvement sur ces comptes</li>
                    )}
                  </ul>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Charges sans contrat</div>
                  <div className="font-mono tabular-nums text-base font-extrabold text-black border-b-2 border-black inline-block">
                    {formatXAF(data.summary.charges_sans_contrat_xaf)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-2 italic">
                    Demander au contribuable de justifier ces charges par les contrats correspondants
                    (art. L40 LPF).
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Auto-assurance (cpt 6911)</div>
                  <div className="font-mono tabular-nums text-base font-extrabold text-black border-b-2 border-black inline-block">
                    {formatXAF(data.summary.auto_insurance_xaf)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-2 italic">
                    Réintégration intégrale — Art. 7 A 4 : « ne sont pas admises… les sommes
                    constituées par l&apos;entreprise en vue de sa propre assurance ».
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Contrats d&apos;assurance — chargement en lot (DC L40 LPF)</CardTitle></CardHeader>
            <CardContent>
              <div
                className="border border-dashed border-neutral-300 rounded-lg p-4 bg-neutral-50/60"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const fs = Array.from(e.dataTransfer.files).filter((f) => f.name.toLowerCase().endsWith('.pdf'));
                  if (fs.length) setFiles((prev) => [...prev, ...fs]);
                }}
              >
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="text-sm text-slate-700">
                    <b>{files.length}</b> fichier(s) prêt(s). Demandez au contribuable la liste exhaustive
                    de ses polices en vigueur sur l&apos;exercice, puis chargez-les ici.
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-neutral-300 bg-white hover:border-black cursor-pointer">
                      <Upload className="w-3.5 h-3.5" /> Sélectionner PDF
                      <input type="file" multiple hidden accept=".pdf"
                        onChange={(e) => {
                          const fs = Array.from(e.target.files || []);
                          if (fs.length) setFiles((prev) => [...prev, ...fs]);
                          e.target.value = '';
                        }} />
                    </label>
                    <button type="button" onClick={() => uploadMut.mutate(files)}
                      disabled={!files.length || uploadMut.isPending}
                      className="px-3 py-1.5 text-xs rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-40">
                      {uploadMut.isPending ? 'Extraction en cours…' : 'Charger & extraire'}
                    </button>
                    {files.length > 0 && !uploadMut.isPending && (
                      <button onClick={() => setFiles([])} className="px-2 py-1.5 text-xs text-neutral-500 hover:text-black">vider</button>
                    )}
                  </div>
                </div>

                {/* Progress bar — shown during sequential extraction */}
                {progress && (
                  <UploadProgress progress={progress} />
                )}

                {files.length > 0 && !progress && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {files.map((f, i) => (
                      <span key={i} className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[11px]">{f.name}</span>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Analyse contrat par contrat (Art. 7 A 4)</CardTitle></CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2.5">Police</th>
                    <th className="px-3 py-2.5">Assureur</th>
                    <th className="px-3 py-2.5">Type</th>
                    <th className="px-3 py-2.5">Bénéf.</th>
                    <th className="px-3 py-2.5">Couverture</th>
                    <th className="px-3 py-2.5 text-right">Prime annuelle</th>
                    <th className="px-3 py-2.5 text-right">Prime exercice</th>
                    <th className="px-3 py-2.5">Cpt</th>
                    <th className="px-3 py-2.5">Verdict</th>
                    <th className="px-3 py-2.5 text-right">Réint.</th>
                    <th className="px-3 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {data.contracts.map((c) => (
                    <ContractRow key={c.id} caseId={currentCase!.id} contract={c}
                      onDelete={() => deleteMut.mutate(c.id)}
                      onVerdictSaved={() => { void refetch(); }} />
                  ))}
                  {data.contracts.length === 0 && (
                    <tr><td colSpan={11} className="px-3 py-8 text-center text-slate-500 italic">
                      Aucun contrat chargé. Demandez la liste au contribuable et déposez les PDF ci-dessus.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              <b>Base légale :</b> CGI Cameroun, Art. 7 A (4). <b>Comptes SYSCOHADA Révisé :</b>
              {' '}625X (services extérieurs — primes d&apos;assurance), 6685 (santé personnel),
              6686 (retraite / fin de carrière), 6911 (provisions auto-assurance — non déductibles).
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function ContractRow({
  caseId, contract, onDelete, onVerdictSaved,
}: {
  caseId: string;
  contract: ContractView;
  onDelete: () => void;
  onVerdictSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [overrideV, setOverrideV] = useState(contract.verdict);
  const [overrideR, setOverrideR] = useState('');

  const overrideMut = useMutation({
    mutationFn: async () => api(
      `/audit-cases/${caseId}/primes-assurance/contracts/${contract.id}/verdict`,
      { method: 'PATCH', body: { verdict: overrideV, reason: overrideR } },
    ),
    onSuccess: () => { setOverrideR(''); onVerdictSaved(); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  const openFile = async () => {
    const token = getToken();
    const res = await fetch(
      `/audit-cases/${caseId}/primes-assurance/contracts/${contract.id}/file`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    if (!res.ok) { alert(`Échec HTTP ${res.status}`); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };

  return (
    <>
      <tr className={cn('border-b border-neutral-100 hover:bg-neutral-50',
                       contract.verdict === 'NON_ELIGIBLE' && 'bg-neutral-100/60',
                       contract.verdict === 'A_REINSTRUIRE' && 'bg-neutral-50/70')}>
        <td className="px-3 py-2 font-mono text-[11px]">{contract.numero_police || '—'}</td>
        <td className="px-3 py-2">
          <div className="font-medium">{contract.assureur_nom || '—'}</div>
          <div className="text-[10px] text-slate-500 flex items-center gap-1">
            {contract.assureur_local
              ? <><MapPin className="w-2.5 h-2.5 text-neutral-700" /> Local ({contract.assureur_pays})</>
              : <><Globe className="w-2.5 h-2.5 text-black" /> Étranger ({contract.assureur_pays})</>}
          </div>
        </td>
        <td className="px-3 py-2">{TYPE_LABELS[contract.type_assurance] || contract.type_assurance}</td>
        <td className="px-3 py-2">
          <div>{BENEF_LABELS[contract.beneficiaire_type] || contract.beneficiaire_type}</div>
          <div className="text-[10px] text-slate-500 truncate max-w-[120px]" title={contract.beneficiaire_nom || ''}>
            {contract.beneficiaire_nom || ''}
          </div>
        </td>
        <td className="px-3 py-2 text-[10px]">
          <div>{formatDate(contract.date_debut) || '—'}</div>
          <div>→ {formatDate(contract.date_fin) || '—'}</div>
        </td>
        <td className="px-3 py-2 text-right font-mono">{formatXAF(contract.prime_annuelle_ttc)}</td>
        <td className="px-3 py-2 text-right font-mono font-semibold">{formatXAF(contract.prime_exercice)}</td>
        <td className="px-3 py-2 font-mono text-[11px]">{contract.compte_syscohada || '—'}</td>
        <td className="px-3 py-2">
          <VerdictBadge v={contract.verdict} />
          {contract.verdict_source === 'MANUAL_OVERRIDE' && (
            <div className="text-[9px] text-slate-500 mt-0.5">override</div>
          )}
        </td>
        <td className="px-3 py-2 text-right font-mono tabular-nums font-extrabold text-black">
          {contract.estimated_reintegration_xaf > 0 ? formatXAF(contract.estimated_reintegration_xaf) : '—'}
        </td>
        <td className="px-3 py-2 text-right">
          <button onClick={() => setOpen(!open)} className="text-black hover:underline text-[10px] mr-2">détail</button>
          <button onClick={onDelete} className="text-neutral-600 hover:text-black hover:bg-neutral-100 rounded p-1" title="Supprimer">
            <Trash2 className="w-3 h-3" />
          </button>
        </td>
      </tr>
      {open && (
        <tr className="bg-slate-50/80 border-b border-slate-200">
          <td colSpan={11} className="px-4 py-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
                  Diagnostic automatique (Art. 7 A 4)
                </div>
                <div className="bg-white border border-slate-200 rounded p-3 text-xs">
                  <p className="mb-2">{contract.verdict_reason}</p>
                  {contract.findings.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {contract.findings.map((f) => (
                        <span key={f} className="text-[9px] px-1.5 py-0.5 border border-neutral-300 text-neutral-800 rounded font-mono">{f}</span>
                      ))}
                    </div>
                  )}
                </div>
                <button onClick={openFile} className="mt-2 inline-flex items-center gap-1 text-xs text-black hover:underline">
                  <Paperclip className="w-3 h-3" /> Voir le PDF du contrat
                </button>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2 flex items-center gap-1">
                  <Pencil className="w-3 h-3" /> Override par le vérificateur
                </div>
                <div className="bg-white border border-slate-200 rounded p-3">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    {(['ELIGIBLE', 'A_REINSTRUIRE', 'NON_ELIGIBLE'] as const).map((v) => (
                      <label key={v} className="inline-flex items-center gap-1 text-xs cursor-pointer">
                        <input type="radio" checked={overrideV === v}
                          onChange={() => setOverrideV(v)} className="accent-black" />
                        <VerdictBadge v={v} />
                      </label>
                    ))}
                  </div>
                  <textarea value={overrideR} onChange={(e) => setOverrideR(e.target.value)}
                    placeholder="Motivation écrite obligatoire…"
                    className="w-full text-xs p-2 border border-slate-300 rounded h-16" />
                  <div className="flex justify-end mt-2">
                    <button onClick={() => overrideMut.mutate()}
                      disabled={!overrideR.trim() || overrideMut.isPending}
                      className="px-3 py-1.5 text-xs rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-50">
                      {overrideMut.isPending ? 'Enregistrement…' : 'Enregistrer le verdict'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
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
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">{label}</div>
        <div className={`text-base mt-1 font-display tabular-nums ${cls}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function UploadProgress({ progress }: { progress: { done: number; total: number; current: string } }) {
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  return (
    <div className="mt-3">
      <div className="flex items-center justify-between text-[11px] text-slate-600 mb-1">
        <span>
          Traitement IA : <b>{progress.done}/{progress.total}</b> fichier(s)
          {progress.done < progress.total && progress.current && (
            <span className="text-slate-400"> — en cours : {progress.current}</span>
          )}
        </span>
        <span className="font-mono font-semibold">{pct}%</span>
      </div>
      <div className="h-2 w-full bg-neutral-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-black transition-all duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
