'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Building2, Info, FileWarning, Upload, Download,
  ShieldCheck, ShieldAlert, ShieldX, Paperclip, Trash2, Pencil,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api, apiUploadForm, getToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';

interface DonLine {
  piece_number: string;
  entry_date: string | null;
  line_number: number;
  account_code: string;
  account_name: string | null;
  libelle: string | null;
  amount_xaf: number;
  beneficiary_niu: string | null;
  beneficiary_name_guess: string | null;
  confidence: 'VERT' | 'ORANGE' | 'ROUGE';
  verdict: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE';
  verdict_reason: string;
  verdict_source: string;
  has_evidence: boolean;
  evidence_count: number;
  account_category: 'DON_DIRECT' | 'DON_HAO' | 'DON_CANDIDATE';
  // ── AI deepening ────────────────────────────────────────────────────
  ai_verdict: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE';
  ai_confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  ai_reason: string;
  ai_indicators: string[];
  group_id: string | null;
  group_name: string | null;
  group_verdict: string | null;
}

interface DonGroup {
  id: string;
  name: string;
  description: string | null;
  member_count: number;
  total_xaf: number;
  group_verdict: string | null;
  group_verdict_reason: string | null;
  group_verdict_source: string;
  ai_confidence: string | null;
  members: { piece_number: string; line_number: number }[];
}

interface BeneficiaryAgg {
  key: string;
  name: string;
  niu: string | null;
  line_count: number;
  total_xaf: number;
  eligible_xaf: number;
  non_eligible_xaf: number;
  to_reinstruct_xaf: number;
}

interface DonsResp {
  source_dataset_id: string | null;
  source_filename: string | null;
  account_prefixes: string[];
  candidate_prefixes: string[];
  ca_ht_xaf: number;
  ca_ht_source: string;
  plafond_per_mille: number;
  plafond_xaf: number;
  lines: DonLine[];
  by_beneficiary: BeneficiaryAgg[];
  groups?: DonGroup[];
  summary: {
    ca_ht_xaf: number;
    ca_ht_source: string;
    plafond_per_mille: number;
    plafond_xaf: number;
    line_count: number;
    beneficiary_count: number;
    total_engage_xaf: number;
    total_eligible_avant_plafond_xaf: number;
    total_non_eligible_xaf: number;
    total_a_reinstruire_xaf: number;
    excedent_plafond_xaf: number;
    reintegration_xaf: number;
    evidence_uploaded_count: number;
    confidence_breakdown: { VERT: number; ORANGE: number; ROUGE: number };
    verdict_breakdown: { ELIGIBLE: number; NON_ELIGIBLE: number; A_REINSTRUIRE: number };
  } | null;
  note?: string;
}

const DOC_KINDS = [
  { value: 'RECU', label: 'Reçu' },
  { value: 'CONVENTION', label: 'Convention' },
  { value: 'STATUTS', label: 'Statuts' },
  { value: 'AGREMENT', label: 'Agrément' },
  { value: 'VIREMENT', label: 'Preuve de virement' },
  { value: 'AUTRE', label: 'Autre' },
];

export default function DonsLiberalitesPage() {
  const t = useT();
  const { currentCase } = useApp();
  const qc = useQueryClient();
  const [openLine, setOpenLine] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['dons', currentCase?.id],
    queryFn: () => api<DonsResp>(`/audit-cases/${currentCase!.id}/dons-liberalites`),
    enabled: !!currentCase,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['dons', currentCase?.id] });

  const triggerAiMut = useMutation({
    mutationFn: async (lines: { piece_number: string; line_number: number }[]) =>
      api(`/audit-cases/${currentCase!.id}/dons-liberalites/ai-analyze`,
          { method: 'POST', body: { lines } }),
    onSuccess: () => { void refetch(); invalidate(); },
    onError: (e: any) => alert(`Échec analyse IA : ${e?.message || 'erreur'}`),
  });

  const createGroupMut = useMutation({
    mutationFn: async (body: { name: string; lines: { piece_number: string; line_number: number }[] }) =>
      api(`/audit-cases/${currentCase!.id}/dons-liberalites/groups`,
          { method: 'POST', body }),
    onSuccess: () => { setSelected(new Set()); void refetch(); invalidate(); },
    onError: (e: any) => alert(`Échec création groupe : ${e?.message || 'erreur'}`),
  });

  const groupAiMut = useMutation({
    mutationFn: async (groupId: string) =>
      api(`/audit-cases/${currentCase!.id}/dons-liberalites/groups/${groupId}/ai-analyze`,
          { method: 'POST' }),
    onSuccess: () => { void refetch(); invalidate(); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  const groupSetVerdictMut = useMutation({
    mutationFn: async ({ groupId, verdict, reason }: any) =>
      api(`/audit-cases/${currentCase!.id}/dons-liberalites/groups/${groupId}`,
          { method: 'PATCH', body: { group_verdict: verdict, group_verdict_reason: reason } }),
    onSuccess: () => { void refetch(); invalidate(); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  const groupDeleteMut = useMutation({
    mutationFn: async (groupId: string) =>
      api(`/audit-cases/${currentCase!.id}/dons-liberalites/groups/${groupId}`,
          { method: 'DELETE' }),
    onSuccess: () => { void refetch(); invalidate(); },
    onError: (e: any) => alert(`Échec : ${e?.message || 'erreur'}`),
  });

  const toggleSelected = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const handleGroupSelection = () => {
    const name = window.prompt('Nom du groupe (nature de don) :', '');
    if (!name || !name.trim()) return;
    const lines = Array.from(selected).map((k) => {
      const [piece_number, line_number] = k.split('::');
      return { piece_number, line_number: parseInt(line_number, 10) };
    });
    createGroupMut.mutate({ name: name.trim(), lines });
  };

  const handleAnalyzeSelection = () => {
    const lines = Array.from(selected).map((k) => {
      const [piece_number, line_number] = k.split('::');
      return { piece_number, line_number: parseInt(line_number, 10) };
    });
    triggerAiMut.mutate(lines);
  };

  const downloadDjp = async () => {
    if (!currentCase) return;
    const token = getToken();
    const res = await fetch(`/audit-cases/${currentCase.id}/dons-liberalites/djp.csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      alert(`Échec du téléchargement (HTTP ${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `djp_dons_${currentCase.id}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <Link href="/impots-societes" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-black">
        <ArrowLeft className="w-3.5 h-3.5" />
        {t('nav.corporateTax')}
      </Link>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-extrabold flex items-center gap-2 text-black tracking-tight">
            <Building2 className="w-6 h-6 text-black" />
            Dons et libéralités
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            CGI Cameroun, Art. 7 — non déductibles sauf œuvres d'intérêt général au Cameroun, plafond 5‰ × CA HT.
          </p>
        </div>
        {data?.summary && (
          <button onClick={downloadDjp}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs rounded-md border border-neutral-300 hover:border-black">
            <Download className="w-3.5 h-3.5" />
            Exporter DJP (CSV)
          </button>
        )}
      </div>

      {!currentCase && (
        <Card><CardContent><div className="text-center py-10 text-slate-500">{t('data.noCaseTitle')}</div></CardContent></Card>
      )}

      {currentCase && isLoading && (
        <Card><CardContent><div className="text-sm text-slate-500 py-6 text-center">{t('app.loading')}</div></CardContent></Card>
      )}

      {data?.note && (
        <Card><CardContent>
          <div className="flex items-start gap-3 py-2">
            <FileWarning className="w-5 h-5 text-black flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-700">{data.note}</div>
          </div>
        </CardContent></Card>
      )}

      {data?.summary && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <KPI label="Lignes 658X / 6713 / 838X" value={data.summary.line_count} />
            <KPI label="Engagé total"
                 value={formatXAF(data.summary.total_engage_xaf)} />
            <KPI label="Plafond légal (5‰ CA HT)"
                 value={formatXAF(data.summary.plafond_xaf)} tone="neutral" />
            <KPI label="Non éligible"
                 value={formatXAF(data.summary.total_non_eligible_xaf)}
                 tone={data.summary.total_non_eligible_xaf > 0 ? 'err' : 'ok'} />
            <KPI label="À réinstruire"
                 value={formatXAF(data.summary.total_a_reinstruire_xaf)}
                 tone={data.summary.total_a_reinstruire_xaf > 0 ? 'warn' : 'ok'} />
            <KPI label="Réintégration estimée"
                 value={formatXAF(data.summary.reintegration_xaf)}
                 tone={data.summary.reintegration_xaf > 0 ? 'err' : 'ok'} />
          </div>

          {/* Plafond detail strip */}
          <Card>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 text-xs">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">CA HT (exercice)</div>
                  <div className="font-mono text-base font-semibold">{formatXAF(data.summary.ca_ht_xaf)}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5 italic">source : {data.summary.ca_ht_source}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Éligible avant plafond</div>
                  <div className="font-mono tabular-nums text-base font-semibold text-neutral-700">{formatXAF(data.summary.total_eligible_avant_plafond_xaf)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Excédent plafond</div>
                  <div className="font-mono tabular-nums text-base font-extrabold text-black border-b-2 border-black inline-block">{formatXAF(data.summary.excedent_plafond_xaf)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Pièces justificatives uploadées</div>
                  <div className="font-mono text-base font-semibold">{data.summary.evidence_uploaded_count}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Per-beneficiary roll-up */}
          {data.by_beneficiary.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Top bénéficiaires</CardTitle></CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                      <th className="px-3 py-2.5">Bénéficiaire</th>
                      <th className="px-3 py-2.5">NIU</th>
                      <th className="px-3 py-2.5 text-right">Lignes</th>
                      <th className="px-3 py-2.5 text-right">Total</th>
                      <th className="px-3 py-2.5 text-right">Éligible</th>
                      <th className="px-3 py-2.5 text-right">Non éligible</th>
                      <th className="px-3 py-2.5 text-right">À réinstruire</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_beneficiary.slice(0, 25).map((b) => (
                      <tr key={b.key} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-3 py-2 font-medium">{b.name}</td>
                        <td className="px-3 py-2 font-mono text-[11px]">{b.niu || '—'}</td>
                        <td className="px-3 py-2 text-right font-mono">{b.line_count}</td>
                        <td className="px-3 py-2 text-right font-mono">{formatXAF(b.total_xaf)}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-neutral-700">{formatXAF(b.eligible_xaf)}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-black font-bold">{formatXAF(b.non_eligible_xaf)}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-neutral-800">{formatXAF(b.to_reinstruct_xaf)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Groupes existants */}
          {data.groups && data.groups.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Groupes par nature</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {data.groups.map((g) => (
                    <div key={g.id} className="border border-neutral-200 rounded p-2 text-xs">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div>
                          <span className="font-semibold">{g.name}</span>
                          <span className="text-slate-500 ml-2">{g.member_count} ligne(s) · {formatXAF(g.total_xaf)}</span>
                          {g.group_verdict && (
                            <span className="ml-2"><VerdictBadge v={g.group_verdict as any} /></span>
                          )}
                          {g.ai_confidence && (
                            <span className="ml-1 text-[10px] text-slate-500">{g.ai_confidence}</span>
                          )}
                        </div>
                        <div className="flex items-center gap-1">
                          <button onClick={() => groupAiMut.mutate(g.id)}
                            disabled={groupAiMut.isPending}
                            className="px-2 py-0.5 text-[11px] rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-50">
                            Analyser via Claude (pièces)
                          </button>
                          {(['ELIGIBLE', 'A_REINSTRUIRE', 'NON_ELIGIBLE'] as const).map((v) => (
                            <button key={v}
                              onClick={() => {
                                const reason = window.prompt('Motivation :', g.group_verdict_reason || '');
                                if (reason !== null) groupSetVerdictMut.mutate({ groupId: g.id, verdict: v, reason });
                              }}
                              className="px-1.5 py-0.5 text-[10px] rounded border border-neutral-300 hover:border-black">
                              {v === 'ELIGIBLE' ? '✓ Élig.' : v === 'A_REINSTRUIRE' ? '? Réinst.' : '✗ Non élig.'}
                            </button>
                          ))}
                          <button onClick={() => { if (confirm('Supprimer le groupe ?')) groupDeleteMut.mutate(g.id); }}
                            className="px-1.5 py-0.5 text-[10px] rounded border border-neutral-400 text-neutral-700 hover:border-black hover:text-black">
                            🗑
                          </button>
                        </div>
                      </div>
                      {g.group_verdict_reason && (
                        <div className="text-[10px] text-slate-500 mt-1">{g.group_verdict_reason}</div>
                      )}
                      <div className="text-[10px] text-slate-400 mt-0.5 italic">
                        Astuce : ouvrez le détail d&apos;une ligne membre pour charger ses pièces ;
                        ou utilisez l&apos;upload de groupe via /api/.../groups/{'{'+'id'+'}'}/evidence.
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Lines */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle>Lignes du grand-livre — comptes 658X / 6713 / 838X</CardTitle>
                <div className="flex items-center gap-2 text-xs">
                  {selected.size > 0 && (
                    <>
                      <span className="text-slate-500"><b>{selected.size}</b> ligne(s) sélectionnée(s)</span>
                      <button onClick={handleAnalyzeSelection}
                        disabled={triggerAiMut.isPending}
                        className="px-2 py-1 rounded border border-black text-black hover:bg-neutral-100 disabled:opacity-50">
                        {triggerAiMut.isPending ? 'Analyse IA…' : 'Analyser via Claude'}
                      </button>
                      <button onClick={handleGroupSelection}
                        disabled={createGroupMut.isPending}
                        className="px-2 py-1 rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-50">
                        Grouper par nature
                      </button>
                      <button onClick={() => setSelected(new Set())} className="text-neutral-500 hover:text-black">
                        annuler
                      </button>
                    </>
                  )}
                </div>
              </div>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                    <th className="px-2 py-2.5">
                      <input type="checkbox"
                        checked={data.lines.length > 0 && selected.size === data.lines.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelected(new Set(data.lines.map((l) => `${l.piece_number}::${l.line_number}`)));
                          } else {
                            setSelected(new Set());
                          }
                        }} />
                    </th>
                    <th className="px-3 py-2.5">Pièce</th>
                    <th className="px-3 py-2.5">Date</th>
                    <th className="px-3 py-2.5">Compte</th>
                    <th className="px-3 py-2.5">Libellé GL</th>
                    <th className="px-3 py-2.5">Bénéficiaire</th>
                    <th className="px-3 py-2.5 text-right">Montant</th>
                    <th className="px-3 py-2.5">Suggestion IA</th>
                    <th className="px-3 py-2.5">Confiance</th>
                    <th className="px-3 py-2.5">Verdict</th>
                    <th className="px-3 py-2.5 text-center">Pièces</th>
                  </tr>
                </thead>
                <tbody>
                  {data.lines.map((l) => {
                    const lineKey = `${l.piece_number}::${l.line_number}`;
                    const isOpen = openLine === lineKey;
                    return (
                      <>
                        <tr key={lineKey}
                            className={cn('border-b border-neutral-100 hover:bg-neutral-50',
                              isOpen && 'bg-neutral-50',
                              l.group_id && 'border-l-2 border-l-black')}>
                          <td className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" checked={selected.has(lineKey)}
                              onChange={() => toggleSelected(lineKey)} />
                          </td>
                          <td className="px-3 py-2 font-mono cursor-pointer"
                              onClick={() => setOpenLine(isOpen ? null : lineKey)}>{l.piece_number}</td>
                          <td className="px-3 py-2">{formatDate(l.entry_date) || '—'}</td>
                          <td className="px-3 py-2">
                            <div className="font-mono">{l.account_code}</div>
                            <div className="text-[10px] text-slate-500">{l.account_name || ''}</div>
                          </td>
                          <td className="px-3 py-2 text-slate-700 max-w-[260px] truncate" title={l.libelle || ''}>
                            {l.libelle || '—'}
                            {l.group_name && <div className="text-[9px] text-black font-semibold">↳ {l.group_name}</div>}
                          </td>
                          <td className="px-3 py-2">
                            <div className="text-slate-800">{l.beneficiary_name_guess || <span className="italic text-slate-400">non identifié</span>}</div>
                            {l.beneficiary_niu && <div className="text-[10px] font-mono text-slate-500">{l.beneficiary_niu}</div>}
                          </td>
                          <td className="px-3 py-2 text-right font-mono font-semibold">{formatXAF(l.amount_xaf)}</td>
                          <td className="px-3 py-2" title={l.ai_reason}>
                            <AiBadge v={l.ai_verdict} c={l.ai_confidence} />
                          </td>
                          <td className="px-3 py-2"><ConfidenceBadge c={l.confidence} /></td>
                          <td className="px-3 py-2"><VerdictBadge v={l.verdict} /></td>
                          <td className="px-3 py-2 text-center">
                            {l.has_evidence ? (
                              <span className="inline-flex items-center gap-1 text-black font-semibold">
                                <Paperclip className="w-3 h-3" /> {l.evidence_count}
                              </span>
                            ) : (
                              <span className="text-neutral-400">—</span>
                            )}
                          </td>
                        </tr>
                        {isOpen && currentCase && (
                          <tr key={`${lineKey}-detail`} className="bg-neutral-50 border-b border-neutral-200">
                            <td colSpan={11} className="px-4 py-4">
                              <LineDetail
                                caseId={currentCase.id}
                                line={l}
                                onChange={() => { void refetch(); void qc.invalidateQueries({ queryKey: ['dons'] }); }}
                              />
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                  {data.lines.length === 0 && (
                    <tr><td colSpan={11} className="px-3 py-8 text-center text-slate-500 italic">
                      Aucune ligne de don ou libéralité détectée dans ce grand-livre.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              Principe : les dons et libéralités ne sont pas déductibles. Exception : versements à des œuvres ou
              organismes d'intérêt général à caractère philanthropique, éducatif, sportif, scientifique, social,
              culturel ou familial, situés au Cameroun, dans la limite de 5‰ du CA HT — chaque ligne doit être
              appuyée par un reçu de l'organisme et son statut/agrément. CGI Cameroun, Art. 7.
            </span>
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-line detail panel — upload + verdict override
// ─────────────────────────────────────────────────────────────────────────────

function LineDetail({
  caseId, line, onChange,
}: {
  caseId: string;
  line: DonLine;
  onChange: () => void;
}) {
  const [docKind, setDocKind] = useState('RECU');
  const [overrideVerdict, setOverrideVerdict] = useState<'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE'>(line.verdict);
  const [overrideReason, setOverrideReason] = useState('');

  const evidenceQ = useQuery({
    queryKey: ['dons-evidence', caseId, line.piece_number, line.line_number],
    queryFn: () => api<{ items: any[] }>(
      `/audit-cases/${caseId}/dons-liberalites/line-evidence`
      + `?piece=${encodeURIComponent(line.piece_number)}&line=${line.line_number}`
    ),
  });

  const uploadMut = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_kind', docKind);
      fd.append('piece', line.piece_number);
      fd.append('line', String(line.line_number));
      return apiUploadForm(
        `/audit-cases/${caseId}/dons-liberalites/evidence`,
        fd,
      );
    },
    onSuccess: () => { void evidenceQ.refetch(); onChange(); },
    onError: (e: any) => { alert(`Échec de l'upload : ${e?.message || 'erreur'}`); },
  });

  const overrideMut = useMutation({
    mutationFn: async () => api(
      `/audit-cases/${caseId}/dons-liberalites/verdict`,
      {
        method: 'PATCH',
        body: {
          piece: line.piece_number,
          line: line.line_number,
          verdict: overrideVerdict,
          reason: overrideReason,
        },
      },
    ),
    onSuccess: () => { setOverrideReason(''); void evidenceQ.refetch(); onChange(); },
    onError: (e: any) => { alert(`Échec de l'enregistrement : ${e?.message || 'erreur'}`); },
  });

  const deleteMut = useMutation({
    mutationFn: async (evidenceId: string) => api(
      `/audit-cases/${caseId}/dons-liberalites/evidence/${evidenceId}`,
      { method: 'DELETE' },
    ),
    onSuccess: () => { void evidenceQ.refetch(); onChange(); },
    onError: (e: any) => { alert(`Échec de la suppression : ${e?.message || 'erreur'}`); },
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ── Upload + listing ─────────────────────────────────── */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
          Justificatifs
        </div>
        <div className="border border-dashed border-neutral-300 rounded-md p-3 bg-white">
          <div className="flex items-center gap-2 mb-2">
            <select value={docKind} onChange={(e) => setDocKind(e.target.value)}
              className="text-xs px-2 py-1 rounded border border-neutral-300">
              {DOC_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
            <label className="inline-flex items-center gap-1.5 px-2 py-1 text-xs rounded border border-neutral-300 bg-neutral-50 hover:border-black cursor-pointer">
              <Upload className="w-3.5 h-3.5" />
              Charger un fichier
              <input type="file" hidden
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadMut.mutate(f);
                  e.target.value = '';
                }}
              />
            </label>
            {uploadMut.isPending && <span className="text-[11px] text-slate-500">envoi…</span>}
          </div>
          <div className="space-y-1.5">
            {(evidenceQ.data?.items || []).map((e) => (
              <div key={e.id} className="flex items-center justify-between text-xs bg-neutral-50 rounded px-2 py-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  <Paperclip className="w-3 h-3 text-slate-500 flex-shrink-0" />
                  <button
                    type="button"
                    onClick={async () => {
                      const token = getToken();
                      const res = await fetch(
                        `/audit-cases/${caseId}/dons-liberalites/evidence/${e.id}/file`,
                        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
                      );
                      if (!res.ok) { alert(`Échec : HTTP ${res.status}`); return; }
                      const blob = await res.blob();
                      const url = URL.createObjectURL(blob);
                      window.open(url, '_blank');
                      setTimeout(() => URL.revokeObjectURL(url), 60_000);
                    }}
                    className="truncate text-black hover:underline text-left">{e.filename}</button>
                  <span className="text-[10px] text-neutral-500 flex-shrink-0">[{e.doc_kind}]</span>
                </div>
                <button onClick={() => deleteMut.mutate(e.id)}
                  className="text-neutral-600 hover:text-black hover:bg-neutral-100 rounded p-0.5">
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
            {(evidenceQ.data?.items || []).length === 0 && (
              <div className="text-[11px] text-slate-400 italic py-1">Aucun justificatif chargé pour cette ligne.</div>
            )}
          </div>
        </div>

        <div className="mt-3 text-[11px] text-neutral-700 bg-neutral-50 border border-neutral-300 rounded p-2">
          <div className="font-semibold flex items-center gap-1 mb-0.5">
            <Info className="w-3 h-3" /> Pièces attendues
          </div>
          Reçu de l'organisme bénéficiaire (avec NIU), statuts ou agrément d'utilité publique,
          preuve du versement bancaire.
        </div>
      </div>

      {/* ── Verdict override ─────────────────────────────────── */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
          Verdict actuel
        </div>
        <div className="bg-white border border-neutral-200 rounded-md p-3">
          <div className="flex items-center gap-2 mb-2">
            <VerdictBadge v={line.verdict} />
            <span className="text-[10px] text-neutral-500 uppercase tracking-wider">{line.verdict_source}</span>
          </div>
          <div className="text-xs text-neutral-700 mb-3">{line.verdict_reason}</div>
          <div className="border-t border-neutral-100 pt-3">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2 flex items-center gap-1">
              <Pencil className="w-3 h-3" /> Override par le vérificateur
            </div>
            <div className="flex items-center gap-2 mb-2">
              {(['ELIGIBLE', 'A_REINSTRUIRE', 'NON_ELIGIBLE'] as const).map((v) => (
                <label key={v} className="inline-flex items-center gap-1 text-xs cursor-pointer">
                  <input type="radio" checked={overrideVerdict === v}
                    onChange={() => setOverrideVerdict(v)}
                    className="accent-black" />
                  <VerdictBadge v={v} />
                </label>
              ))}
            </div>
            <textarea value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="Motivation écrite (obligatoire)…"
              className="w-full text-xs p-2 border border-neutral-300 rounded h-16" />
            <div className="flex justify-end mt-2">
              <button onClick={() => overrideMut.mutate()}
                disabled={!overrideReason.trim() || overrideMut.isPending}
                className="px-3 py-1.5 text-xs rounded bg-black text-white hover:bg-neutral-800 disabled:opacity-50">
                {overrideMut.isPending ? 'Enregistrement…' : 'Enregistrer le verdict'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tiny presentational helpers
// ─────────────────────────────────────────────────────────────────────────────

function AiBadge({ v, c }: { v: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE'; c: 'HIGH' | 'MEDIUM' | 'LOW' }) {
  const isUnset = !v || (v === 'A_REINSTRUIRE' && c === 'LOW');
  if (isUnset) return <span className="text-[10px] text-neutral-300 italic">non analysé</span>;
  const pip = c === 'HIGH' ? '●●●' : c === 'MEDIUM' ? '●●○' : '●○○';
  const cls =
    v === 'ELIGIBLE'     ? 'border-neutral-300 text-neutral-700 font-normal' :
    v === 'NON_ELIGIBLE' ? 'border-black text-black font-extrabold' :
                           'border-neutral-300 text-neutral-700 font-medium';
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border bg-transparent ${cls}`}>
      <span className="tracking-widest">{pip}</span>
      <span>{v === 'ELIGIBLE' ? 'Élig.' : v === 'NON_ELIGIBLE' ? 'Non élig.' : 'Réinst.'}</span>
      <span className="opacity-70">{c}</span>
    </span>
  );
}

function ConfidenceBadge({ c }: { c: 'VERT' | 'ORANGE' | 'ROUGE' }) {
  if (c === 'VERT') return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 text-neutral-700">
      <span className="tracking-widest">●○○</span> Vert
    </span>
  );
  if (c === 'ORANGE') return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 text-neutral-700 font-medium">
      <span className="tracking-widest">●●○</span> Orange
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-black text-black font-extrabold">
      <span className="tracking-widest">●●●</span> Rouge
    </span>
  );
}

function VerdictBadge({ v }: { v: 'ELIGIBLE' | 'NON_ELIGIBLE' | 'A_REINSTRUIRE' }) {
  if (v === 'ELIGIBLE') return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-neutral-300 bg-transparent text-neutral-700 font-normal">
      <ShieldCheck className="w-3 h-3" /> Éligible <span className="tracking-widest">●○○</span>
    </span>
  );
  if (v === 'NON_ELIGIBLE') return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border border-black bg-transparent text-black font-extrabold">
      <ShieldX className="w-3 h-3" /> Non éligible <span className="tracking-widest">●●●</span>
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
