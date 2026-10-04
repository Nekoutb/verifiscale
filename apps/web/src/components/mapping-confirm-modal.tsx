'use client';

/**
 * Ingest-v2 — mapping confirmation gate for GL / TB.
 *
 * Nothing is ingested until the auditor confirms here. The screen shows, in the
 * order the auditor reasons about it:
 *   1. column TOTALS pinned at the top + the balance verdict
 *   2. the mandatory-field checklist (what still blocks)
 *   3. the mapping table (remap any field; sample values inline)
 *   4. rows that will be EXCLUDED, with their balance impact
 *   5. header + 3-4 rows rendered exactly as they will be ingested
 *
 * An unbalanced import is allowed, but only after an explicit acknowledgement.
 */

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle, CheckCircle2, XCircle, Table2, Wand2, Loader2, ScanLine,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { cn, formatXAF } from '@/lib/utils';

type Column = {
  index: number;
  header: string;
  raw_header: string | null;
  banner: string | null;
  samples: string[];
  assigned_to: string[];
};
type FieldDef = {
  key: string; label_fr: string; mandatory: boolean;
  shape: 'SINGLE' | 'SIGNED' | 'PAIR'; members: string[];
  /** Distinct human label per member (e.g. « Valeur brute à l'ouverture »,
   *  « Dotation de la période ») — no more three identical entries. */
  member_labels?: Record<string, string>;
  allow_pattern_extraction: boolean;
};
type Check = {
  key: string; label_fr: string; mandatory: boolean;
  satisfied: boolean; shape_used: string | null; detail: string | null;
};
type BalanceGroup = { key: string; label: string; debit: number; credit: number; delta: number };
type Preview = {
  kind: 'GL' | 'TB' | 'FAR';
  detected: boolean;
  sheets?: { name: string }[];
  selected_sheet?: string | null;
  error?: string;
  raw_preview?: (string | null)[][];
  header_row: number;
  banner_row: number | null;
  columns: Column[];
  mapping: Record<string, number>;
  entry_id_extraction: { from_column: number; hit_rate: number; sample_source: string; sample_extracted: string } | null;
  fields: FieldDef[];
  checklist: Check[];
  blocking_errors: string[];
  can_confirm: boolean;
  rows_to_ingest: number;
  control_totals?: {
    file_rows: number; file_cols: number;
    read_rows: number; read_cols: number;
    excluded_rows: number; structural_rows: number;
    complete: boolean;
  } | null;
  sample_rows: Record<string, string | null>[];
  excluded_count: number;
  excluded: { row: number; reason: string; label: string; impact: Record<string, string> | null }[];
  excluded_summary: { reason: string; count: number }[];
  totals: { key: string; label: string; value: number }[];
  stated_totals: { values: Record<string, number>; note: string } | null;
  balance: { balanced: boolean; groups: BalanceGroup[]; message: string };
  warnings: string[];
};

/** Canonical keys the mapping table lets you assign, per kind. */
function assignableKeys(fields: FieldDef[]): { key: string; label: string; mandatory: boolean }[] {
  const out: { key: string; label: string; mandatory: boolean }[] = [];
  for (const f of fields) {
    if (f.shape === 'PAIR') {
      for (const m of f.members) {
        const isSigned = m.endsWith('_signed');
        const fallback = `${f.label_fr} — ${isSigned ? 'colonne unique signée' : m.endsWith('_debit') ? 'Débit' : 'Crédit'}`;
        out.push({
          key: m,
          label: f.member_labels?.[m] ?? fallback,
          mandatory: f.mandatory,
        });
      }
    } else {
      out.push({ key: f.key, label: f.label_fr, mandatory: f.mandatory });
    }
  }
  return out;
}

export function MappingConfirmModal({
  datasetId, filename, open, onClose,
}: {
  datasetId: string; filename: string; open: boolean; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, number> | null>(null);
  const [ack, setAck] = useState(false);
  // Which workbook tab to read. null = let the server auto-pick the first tab
  // whose header is recognisable; once the auditor picks one it is explicit.
  const [sheet, setSheet] = useState<string | null>(null);

  // Initial proposal (server-side heuristics + pattern detection). Keyed on the
  // chosen sheet so switching tabs refetches a fresh proposal for that tab.
  const proposal = useQuery({
    queryKey: ['mapping-preview', datasetId, sheet],
    queryFn: () => api<Preview>(`/datasets/${datasetId}/mapping-preview`, {
      method: 'POST', body: sheet ? { sheet } : {},
    }),
    enabled: open,
    refetchOnWindowFocus: false,
  });

  // Live re-preview whenever the auditor remaps something — on the current tab.
  const repreview = useMutation({
    mutationFn: (mapping: Record<string, number>) =>
      api<Preview>(`/datasets/${datasetId}/mapping-preview`, {
        method: 'POST', body: { mapping, ...(sheet ? { sheet } : {}) },
      }),
  });

  const view: Preview | undefined = repreview.data ?? proposal.data;
  // The tab actually read: the auditor's explicit pick, else the server's choice.
  const activeSheet = sheet ?? view?.selected_sheet ?? null;
  const tabs = (view?.sheets ?? []).map((s) => s.name).filter((n) => n !== '(fichier CSV)');

  useEffect(() => {
    if (proposal.data?.mapping && draft === null) setDraft(proposal.data.mapping);
  }, [proposal.data, draft]);

  useEffect(() => { if (!open) { setDraft(null); setAck(false); setSheet(null); repreview.reset(); } }, [open]); // eslint-disable-line

  // Switching tabs: adopt the new tab's proposed mapping (draft back to null so
  // the effect above picks it up) and drop the previous tab's live preview.
  const changeSheet = (name: string) => {
    if (name === activeSheet) return;
    setSheet(name);
    setDraft(null);
    setAck(false);
    repreview.reset();
  };

  const confirm = useMutation({
    mutationFn: () =>
      api(`/datasets/${datasetId}/confirm-mapping`, {
        method: 'POST',
        body: {
          mapping: { ...(draft ?? {}), ...extractionKeys(view) },
          acknowledge_unbalanced: ack,
          sheet: view?.selected_sheet ?? sheet ?? undefined,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['datasets'] });
      qc.invalidateQueries({ queryKey: ['reconciliations'] });
      onClose();
    },
  });

  const remap = (fieldKey: string, colIndex: number | null) => {
    const next = { ...(draft ?? {}) };
    if (colIndex === null) delete next[fieldKey];
    else next[fieldKey] = colIndex;
    setDraft(next);
    repreview.mutate(next);
  };

  const blocked = !view?.can_confirm;
  // A « detected: false » payload has NO balance/totals/columns — guard every
  // access (an unguarded read here white-paged the whole app on KPDC-style
  // files whose header the reader could not find).
  const needsAck = !!view?.detected && !!view.balance && !view.balance.balanced;
  const canSubmit = !blocked && (!needsAck || ack) && !confirm.isPending;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-start justify-center overflow-y-auto p-4">
      <div className="bg-white w-full max-w-6xl rounded-xl border border-neutral-200 shadow-xl my-4">
        {/* ── header ─────────────────────────────────────────────── */}
        <div className="flex items-start justify-between border-b border-neutral-200 px-6 py-4">
          <div>
            <div className="flex items-center gap-2">
              <ScanLine className="w-5 h-5 text-indigo-600" />
              <h2 className="font-display text-lg font-extrabold text-black">
                Confirmer le mapping avant import
              </h2>
              {view && (
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {view.kind === 'GL' ? 'Grand livre' : view.kind === 'TB' ? 'Balance' : 'Registre immobilisations'}
                </span>
              )}
            </div>
            <p className="text-xs text-neutral-600 mt-1">
              <span className="font-mono">{filename}</span>
              {view?.detected && (
                <> · en-tête ligne {view.header_row}
                  {view.banner_row && <> (bandeau ligne {view.banner_row})</>}
                  {' · '}<strong className="text-black">{view.rows_to_ingest.toLocaleString('fr-FR')}</strong> ligne(s) à importer
                </>
              )}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>Fermer</Button>
        </div>

        {/* ── sheet / tab selector — only for multi-tab workbooks ───── */}
        {tabs.length > 1 && (
          <div className="border-b border-neutral-200 bg-neutral-50 px-6 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-semibold text-neutral-600 mr-1">
                Onglet du fichier :
              </span>
              {tabs.map((name) => {
                const active = name === activeSheet;
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => changeSheet(name)}
                    disabled={proposal.isFetching || repreview.isPending}
                    className={cn(
                      'px-3 py-1 rounded-md text-xs font-medium border transition',
                      active
                        ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white text-neutral-700 border-neutral-300 hover:border-indigo-400',
                      (proposal.isFetching || repreview.isPending) && !active && 'opacity-50',
                    )}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
            <p className="text-[10px] text-neutral-500 mt-1.5">
              Ce fichier contient plusieurs onglets. Sélectionnez celui à importer —
              les colonnes et le mapping sont recalculés pour l&apos;onglet choisi.
            </p>
          </div>
        )}

        {(proposal.isLoading || (repreview.isPending && !view)) && (
          <div className="px-6 py-16 text-center text-sm text-neutral-500">
            <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
            Analyse du fichier…
          </div>
        )}

        {view && !view.detected && (
          <div className="px-6 py-8">
            <div className="text-center mb-4">
              <XCircle className="w-8 h-8 text-rose-600 mx-auto mb-2" />
              <div className="text-sm font-semibold text-black">{view.error}</div>
              <div className="text-xs text-neutral-600 mt-1">
                Voici les premières lignes telles que lues — vérifiez que le fichier
                contient bien une ligne d'en-tête avec les intitulés de colonnes.
              </div>
            </div>
            {view.raw_preview && view.raw_preview.length > 0 && (
              <div className="overflow-x-auto border border-neutral-200 rounded-lg">
                <table className="w-full text-[11px]">
                  <tbody className="divide-y divide-neutral-100">
                    {view.raw_preview.map((r, i) => (
                      <tr key={i} className={i === 0 ? 'bg-neutral-50 font-semibold' : ''}>
                        <td className="px-2 py-1 text-neutral-400 font-mono">{i + 1}</td>
                        {r.map((cell, j) => (
                          <td key={j} className="px-2 py-1 font-mono whitespace-nowrap text-neutral-800">
                            {cell ?? ''}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {view?.detected && (
          <div className="px-6 py-5 space-y-6">

            {/* ── 0. CONTROL TOTALS — file dims vs what will be read ── */}
            {view.control_totals && (
              <div className={cn(
                'rounded-lg border px-4 py-2.5 text-xs flex flex-wrap items-center gap-x-4 gap-y-1',
                view.control_totals.complete
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  : 'bg-rose-50 border-rose-300 text-rose-900',
              )}>
                <span className="font-bold uppercase tracking-wider text-[10px]">Totaux de contrôle</span>
                <span>Fichier : <b className="font-mono">{view.control_totals.file_rows.toLocaleString('fr-FR')}</b> lignes × <b className="font-mono">{view.control_totals.file_cols}</b> colonnes</span>
                <span>Lues : <b className="font-mono">{view.control_totals.read_rows.toLocaleString('fr-FR')}</b> lignes × <b className="font-mono">{view.control_totals.read_cols}</b> colonnes mappées</span>
                {view.control_totals.excluded_rows > 0 && (
                  <span>{view.control_totals.excluded_rows} exclue(s) avec motif</span>
                )}
                {view.control_totals.structural_rows > 0 && (
                  <span>{view.control_totals.structural_rows} ligne(s) de structure</span>
                )}
                <span className="font-bold">
                  {view.control_totals.complete
                    ? '✓ toutes les lignes du fichier sont prises en compte'
                    : '✗ des lignes du fichier ne sont pas prises en compte'}
                </span>
              </div>
            )}

            {/* ── 1. TOTALS + BALANCE (pinned at top, per spec) ───── */}
            <section>
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-neutral-500 mb-2">
                Totaux par colonne (calculés sur ce qui sera importé)
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {view.totals.map((t) => (
                  <div key={t.key} className="border border-neutral-200 rounded-lg px-3 py-2 bg-neutral-50">
                    <div className="text-[10px] uppercase tracking-wider text-neutral-500">{t.label}</div>
                    <div className="font-mono tabular-nums text-sm font-bold text-black mt-0.5">
                      {formatXAF(t.value)}
                    </div>
                  </div>
                ))}
              </div>

              <div className={cn(
                'mt-3 rounded-lg border px-4 py-3 flex items-start gap-3',
                view.balance.balanced
                  ? 'bg-emerald-50 border-emerald-200'
                  : 'bg-rose-50 border-rose-200',
              )}>
                {view.balance.balanced
                  ? <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                  : <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" strokeWidth={2.5} />}
                <div className="flex-1 min-w-0">
                  <div className={cn('text-sm font-semibold',
                    view.balance.balanced ? 'text-emerald-800' : 'text-rose-800')}>
                    {view.balance.message}
                  </div>
                  <div className="mt-2 grid gap-1">
                    {view.balance.groups.map((g) => (
                      <div key={g.key} className="flex items-center gap-3 text-xs font-mono tabular-nums">
                        <span className="w-24 text-neutral-600 font-sans">{g.label}</span>
                        <span className="text-neutral-700">D {formatXAF(g.debit)}</span>
                        <span className="text-neutral-700">C {formatXAF(g.credit)}</span>
                        <span className={cn('font-bold', g.delta === 0 ? 'text-emerald-700' : 'text-rose-700')}>
                          Δ {formatXAF(g.delta)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {view.stated_totals && (
                <p className="text-[11px] text-neutral-500 mt-2 leading-relaxed">
                  <strong>Total indiqué dans le fichier :</strong>{' '}
                  {Object.entries(view.stated_totals.values)
                    .filter(([, v]) => v !== 0)
                    .map(([k, v]) => `${k} ${formatXAF(v)}`).join(' · ') || '—'}
                  <br />{view.stated_totals.note}
                </p>
              )}
            </section>

            {/* ── 2. MANDATORY CHECKLIST ─────────────────────────── */}
            <section>
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-neutral-500 mb-2">
                Champs obligatoires
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {view.checklist.filter((c) => c.mandatory).map((c) => (
                  <div key={c.key} className={cn(
                    'flex items-start gap-2 border rounded-lg px-3 py-2',
                    c.satisfied ? 'border-emerald-200 bg-emerald-50/60' : 'border-rose-300 bg-rose-50',
                  )}>
                    {c.satisfied
                      ? <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                      : <XCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />}
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-black">{c.label_fr}</div>
                      {c.shape_used && (
                        <div className="text-[10px] text-neutral-600">
                          {c.shape_used === 'EXTRACTED' ? 'extrait par motif' :
                           c.shape_used === 'SIGNED' ? 'colonne unique signée' :
                           c.shape_used === 'PAIR' ? 'débit / crédit' : 'colonne'}
                          {c.detail ? ` — ${c.detail}` : ''}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {view.entry_id_extraction && (
                <div className="mt-2 flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2">
                  <Wand2 className="w-4 h-4 text-indigo-600 flex-shrink-0 mt-0.5" />
                  <div className="text-[11px] text-indigo-900">
                    <strong>N° d'écriture extrait par motif</strong> depuis la colonne{' '}
                    « {view.columns[view.entry_id_extraction.from_column]?.header} » —{' '}
                    {Math.round(view.entry_id_extraction.hit_rate * 100)} % des lignes.
                    <br />
                    <span className="font-mono">{view.entry_id_extraction.sample_source}</span>
                    {' → '}
                    <span className="font-mono font-bold">{view.entry_id_extraction.sample_extracted}</span>
                  </div>
                </div>
              )}
            </section>

            {/* ── 3. MAPPING TABLE ───────────────────────────────── */}
            <section>
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-neutral-500 mb-2">
                Mapping des colonnes — corrigez si nécessaire
              </div>
              {view.kind === 'GL' && (
                <p className="text-[11px] text-neutral-500 mb-2 -mt-1">
                  Identifiant unique d&apos;écriture : si une seule colonne ne suffit pas à
                  distinguer une écriture, renseignez aussi la 2ᵉ (et la 3ᵉ) colonne de la
                  clé — elles sont combinées pour former la référence unique.
                </p>
              )}
              <div className="overflow-x-auto border border-neutral-200 rounded-lg">
                <table className="w-full text-xs">
                  <thead className="bg-neutral-50 text-neutral-600">
                    <tr>
                      <th className="text-left px-3 py-2 font-semibold">Champ</th>
                      <th className="text-left px-3 py-2 font-semibold">Colonne du fichier</th>
                      <th className="text-left px-3 py-2 font-semibold">Exemples de valeurs</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100">
                    {assignableKeys(view.fields).map((f) => {
                      const col = draft?.[f.key];
                      const c = col !== undefined ? view.columns[col] : undefined;
                      return (
                        <tr key={f.key} className="hover:bg-neutral-50">
                          <td className="px-3 py-2 align-top">
                            <span className="font-medium text-black">{f.label}</span>
                            {f.mandatory && <span className="ml-1 text-rose-600 font-bold">*</span>}
                          </td>
                          <td className="px-3 py-2 align-top">
                            <select
                              className="border border-neutral-300 rounded px-2 py-1 text-xs w-full max-w-[240px] bg-white"
                              value={col ?? ''}
                              onChange={(e) => remap(f.key, e.target.value === '' ? null : Number(e.target.value))}
                            >
                              <option value="">— non mappé —</option>
                              {view.columns.map((cc) => (
                                <option key={cc.index} value={cc.index}>
                                  col {cc.index} · {cc.header || '(sans titre)'}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-3 py-2 align-top text-neutral-600 font-mono text-[11px]">
                            {c ? (c.samples.slice(0, 3).join(' · ') || '—') : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {repreview.isPending && (
                <div className="text-[11px] text-neutral-500 mt-1 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Recalcul…
                </div>
              )}
            </section>

            {/* ── 4. EXCLUDED ROWS ───────────────────────────────── */}
            {view.excluded_count > 0 && (
              <section>
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-neutral-500 mb-2">
                  Lignes exclues de l'import ({view.excluded_count})
                </div>
                <div className="flex flex-wrap gap-2 mb-2">
                  {view.excluded_summary.map((s) => (
                    <span key={s.reason}
                      className="text-[11px] px-2 py-1 rounded-full border border-neutral-300 text-neutral-700 bg-neutral-50">
                      <strong className="tabular-nums">{s.count}</strong> · {s.reason}
                    </span>
                  ))}
                </div>
                {view.excluded.some((e) => e.impact) && (
                  <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2">
                    <div className="text-[11px] font-semibold text-amber-900 flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Ces lignes portent des montants — leur exclusion modifie l'équilibre :
                    </div>
                    <ul className="mt-1 space-y-0.5">
                      {view.excluded.filter((e) => e.impact).map((e) => (
                        <li key={e.row} className="text-[11px] text-amber-900 font-mono">
                          ligne {e.row} · {e.label} ·{' '}
                          {Object.entries(e.impact!).map(([k, v]) => `${k} ${v}`).join(' / ')}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}

            {/* ── 5. SAMPLE AS INGESTED ──────────────────────────── */}
            <section>
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-neutral-500 mb-2 flex items-center gap-1.5">
                <Table2 className="w-3.5 h-3.5" />
                Aperçu — tel que les données seront importées
              </div>
              <div className="overflow-x-auto border border-neutral-200 rounded-lg">
                <table className="w-full text-[11px]">
                  <thead className="bg-black text-white">
                    <tr>
                      {view.sample_rows[0] && Object.keys(view.sample_rows[0])
                        .filter((k) => k !== 'row')
                        .map((k) => <th key={k} className="text-left px-2 py-1.5 font-semibold whitespace-nowrap">{k}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100">
                    {view.sample_rows.map((r, i) => (
                      <tr key={i} className="hover:bg-neutral-50">
                        {Object.entries(r).filter(([k]) => k !== 'row').map(([k, v]) => (
                          <td key={k} className="px-2 py-1.5 font-mono tabular-nums text-neutral-800 whitespace-nowrap">
                            {v ?? '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {view.sample_rows.length === 0 && (
                <p className="text-xs text-rose-700 mt-1">
                  Aucune ligne exploitable avec ce mapping — corrigez les champs ci-dessus.
                </p>
              )}
            </section>

            {view.warnings.map((w) => (
              <p key={w} className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">{w}</p>
            ))}
          </div>
        )}

        {/* ── footer ─────────────────────────────────────────────── */}
        {view?.detected && (
          <div className="border-t border-neutral-200 px-6 py-4 space-y-3">
            {view.blocking_errors.length > 0 && (
              <div className="text-xs text-rose-700 font-semibold">
                {view.blocking_errors.join(' · ')}
              </div>
            )}

            {needsAck && (
              <label className="flex items-start gap-2 cursor-pointer rounded-lg border border-rose-300 bg-rose-50 px-3 py-2">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)}
                       className="mt-0.5 accent-rose-600" />
                <span className="text-xs text-rose-900">
                  <strong>Je comprends les risques d'un import déséquilibré.</strong> Les écarts
                  constatés ci-dessus se répercuteront sur les rapprochements et la liquidation.
                </span>
              </label>
            )}

            {confirm.isError && (
              <div className="text-xs text-rose-700">
                Échec : {(confirm.error as Error)?.message ?? 'erreur inconnue'}
              </div>
            )}

            <div className="flex items-center justify-end gap-2">
              <Button variant="outline" onClick={onClose}>Annuler</Button>
              <Button onClick={() => confirm.mutate()} disabled={!canSubmit}>
                {confirm.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Confirmer &amp; importer {view.rows_to_ingest > 0 && `(${view.rows_to_ingest.toLocaleString('fr-FR')})`}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Carry the confirmed pattern-extraction directive through to the ingest call. */
function extractionKeys(view: Preview | undefined): Record<string, number> {
  if (!view?.entry_id_extraction) return {};
  return { entry_id__extract_from: view.entry_id_extraction.from_column };
}
