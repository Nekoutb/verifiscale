'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  FileText, Upload, AlertTriangle, CheckCircle2, ExternalLink,
  ChevronDown, ChevronRight, Building2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api, apiUploadForm, getToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn, formatXAF, formatDate } from '@/lib/utils';


interface ControlResult { passed: boolean; label: string; }

interface Invoice {
  id: string;
  audit_case_id: string;
  dataset_id: string;
  status: 'PENDING' | 'PROCESSING' | 'PARSED' | 'OCR_ERROR';
  ocr_error: string | null;
  supplier_niu: string | null;
  supplier_name: string | null;
  supplier_rccm: string | null;
  supplier_address: string | null;
  supplier_tax_center: string | null;
  customer_niu: string | null;
  customer_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  base_ht_xaf: number | null;
  tva_xaf: number | null;
  ttc_xaf: number | null;
  tva_rate_pct: number | null;
  currency: string;
  description: string | null;
  control_results: { fond: Record<string, ControlResult>; forme: Record<string, ControlResult> } | null;
  failed_fond_count: number;
  failed_forme_count: number;
  is_compliant: boolean;
  original_filename: string | null;
}

interface InvoiceList { total: number; items: Invoice[]; }

interface VendorRow {
  supplier_niu: string | null;
  supplier_name: string;
  total_invoices: number;
  compliant_invoices: number;
  failed_invoices: number;
  total_ttc_xaf: number;
  sum_failed_fond: number;
  sum_failed_forme: number;
}
interface VendorList { vendors: VendorRow[]; }


export default function SupplierInvoicesPage() {
  const t = useT();
  const qc = useQueryClient();
  const { currentCase } = useApp();
  const inputRef = useRef<HTMLInputElement>(null);
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [activeVendorNiu, setActiveVendorNiu] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null);

  const caseId = currentCase?.id;

  const { data: invoiceList } = useQuery({
    queryKey: ['invoices', caseId, onlyFailed, activeVendorNiu],
    queryFn: () => api<InvoiceList>(
      `/invoices/audit-case/${caseId}?limit=500${onlyFailed ? '&only_failed=true' : ''}${activeVendorNiu ? `&vendor_niu=${activeVendorNiu}` : ''}`
    ),
    enabled: !!caseId,
    refetchInterval: 5000,
  });

  const { data: vendorList } = useQuery({
    queryKey: ['invoices-vendors', caseId],
    queryFn: () => api<VendorList>(`/invoices/audit-case/${caseId}/by-vendor`),
    enabled: !!caseId,
    refetchInterval: 5000,
  });

  // Chunk into batches of 50 client-side so 10K+ uploads work
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const BATCH = 50;
      const total = files.length;
      setBatchProgress({ done: 0, total });
      let done = 0;
      for (let i = 0; i < files.length; i += BATCH) {
        const slice = files.slice(i, i + BATCH);
        const fd = new FormData();
        fd.append('audit_case_id', caseId!);
        for (const f of slice) fd.append('files', f);
        await apiUploadForm('/invoices/bulk', fd);
        done += slice.length;
        setBatchProgress({ done, total });
      }
      return { processed: total };
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['invoices', caseId] });
      qc.invalidateQueries({ queryKey: ['invoices-vendors', caseId] });
      setTimeout(() => setBatchProgress(null), 2500);
    },
  });

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []).filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
    if (files.length) upload.mutate(files);
    e.target.value = '';
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files || []).filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
    if (files.length) upload.mutate(files);
  }, [upload]);

  const kpis = useMemo(() => {
    const items = invoiceList?.items || [];
    return {
      total: invoiceList?.total ?? 0,
      compliant: items.filter((i) => i.is_compliant).length,
      failed: items.filter((i) => !i.is_compliant && i.status === 'PARSED').length,
      totalTtc: items.reduce((s, i) => s + (i.ttc_xaf || 0), 0),
    };
  }, [invoiceList]);

  if (!currentCase) {
    return (
      <Card>
        <CardContent>
          <div className="text-center py-12 text-slate-500">
            <Building2 className="w-12 h-12 mx-auto text-slate-300 mb-3" />
            <div className="text-lg font-semibold text-slate-700 mb-2">{t('data.noCaseTitle')}</div>
            <div className="text-sm">{t('data.noCaseBody')}</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <FileText className="w-6 h-6 text-black" />
          {t('inv.title')}
        </h1>
        <p className="text-sm text-slate-500 mt-1">{t('inv.subtitle')}</p>
        <p className="text-xs text-slate-400 mt-0.5">
          {currentCase.taxpayer.raison_sociale} · {t('app.year')} {currentCase.fiscal_year}
        </p>
      </div>

      <Card>
        <CardContent>
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className="border-2 border-dashed border-slate-300 rounded-xl p-10 text-center cursor-pointer hover:border-black hover:bg-slate-50 transition"
          >
            <Upload className="w-10 h-10 mx-auto text-slate-400 mb-3" />
            <div className="font-semibold text-slate-800">{t('inv.dropTitle')}</div>
            <div className="text-xs text-slate-500 mt-1">{t('inv.dropHint')}</div>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              multiple
              className="hidden"
              onChange={onPick}
            />
          </div>
          {batchProgress && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-xs text-slate-600 mb-1">
                <span>{t('inv.uploading')}</span>
                <span>{batchProgress.done} / {batchProgress.total}</span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-black transition-all"
                  style={{ width: `${(batchProgress.done / batchProgress.total) * 100}%` }}
                />
              </div>
              {batchProgress.done === batchProgress.total && (
                <div className="text-xs text-neutral-700 mt-1 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> {batchProgress.done} {t('inv.uploaded')}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPI label={t('inv.totalInvoices')} value={kpis.total} />
        <KPI label={t('inv.compliant')}     value={kpis.compliant} tone="ok" />
        <KPI label={t('inv.failed')}        value={kpis.failed}    tone={kpis.failed ? 'err' : 'ok'} />
        <KPI label={t('inv.totalTtc')}      value={`${formatXAF(kpis.totalTtc)} FCFA`} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-black" />
            {t('inv.vendorsTabTitle')}
          </CardTitle>
        </CardHeader>
        {(vendorList?.vendors.length || 0) === 0 ? (
          <CardContent>
            <div className="text-sm text-slate-500 italic py-6 text-center">{t('inv.empty')}</div>
          </CardContent>
        ) : (
          <div className="divide-y divide-slate-100">
            {vendorList!.vendors.map((v) => (
              <VendorCard
                key={(v.supplier_niu ?? '_') + v.supplier_name}
                v={v}
                isActive={activeVendorNiu === v.supplier_niu}
                onToggle={() => setActiveVendorNiu(activeVendorNiu === v.supplier_niu ? null : v.supplier_niu)}
              />
            ))}
          </div>
        )}
      </Card>

      {(invoiceList?.items.length || 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('inv.invoicesTabTitle')}</CardTitle>
            <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyFailed}
                onChange={(e) => setOnlyFailed(e.target.checked)}
                className="rounded border-slate-300"
              />
              {t('inv.onlyFailedFilter')}
            </label>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                  <th className="text-left px-4 py-2">{t('inv.vendor')}</th>
                  <th className="text-left px-4 py-2">{t('inv.invoiceNumber')}</th>
                  <th className="text-left px-4 py-2">{t('inv.invoiceDate')}</th>
                  <th className="text-right px-4 py-2">{t('inv.amount')}</th>
                  <th className="text-center px-4 py-2">{t('inv.status')}</th>
                  <th className="text-left px-4 py-2">{t('inv.controlsFailed')}</th>
                  <th className="text-center px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {invoiceList!.items.map((i) => <InvoiceRow key={i.id} inv={i} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}


function VendorCard({ v, isActive, onToggle }: { v: VendorRow; isActive: boolean; onToggle: () => void; }) {
  const t = useT();
  const failureRate = v.total_invoices ? Math.round((v.failed_invoices / v.total_invoices) * 100) : 0;
  return (
    <div className={cn('px-5 py-3 transition', v.failed_invoices ? 'hover:bg-neutral-100/40' : 'hover:bg-neutral-50/30')}>
      <button onClick={onToggle} className="w-full text-left flex items-center gap-3">
        {isActive ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-900 truncate">{v.supplier_name}</span>
            {v.supplier_niu && <span className="text-[10px] font-mono text-slate-500">NIU {v.supplier_niu}</span>}
          </div>
          <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-3 flex-wrap">
            <span>{v.total_invoices} {t('inv.totalInvoices').toLowerCase()}</span>
            <span className="text-neutral-700">{v.compliant_invoices} {t('inv.compliant').toLowerCase()}</span>
            {v.failed_invoices > 0 && (
              <span className="text-rose-700 font-bold">
                {v.failed_invoices} {t('inv.failed').toLowerCase()} ({failureRate}%)
              </span>
            )}
            <span>· {formatXAF(v.total_ttc_xaf)} FCFA</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {v.sum_failed_fond > 0 && (
            <Badge variant="err" className="text-[10px]">
              {v.sum_failed_fond} {t('inv.failedFond')}
            </Badge>
          )}
          {v.sum_failed_forme > 0 && (
            <Badge variant="warn" className="text-[10px]">
              {v.sum_failed_forme} {t('inv.failedForme')}
            </Badge>
          )}
        </div>
      </button>
    </div>
  );
}


function InvoiceRow({ inv }: { inv: Invoice }) {
  const failedControls: string[] = [];
  if (inv.control_results) {
    for (const c of Object.values(inv.control_results.fond)) if (!c.passed) failedControls.push(c.label);
    for (const c of Object.values(inv.control_results.forme)) if (!c.passed) failedControls.push(c.label);
  }
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50 align-top">
      <td className="px-4 py-2">
        <div className="font-medium text-slate-800">{inv.supplier_name || '(inconnu)'}</div>
        {inv.supplier_niu && <div className="text-[10px] font-mono text-slate-500">{inv.supplier_niu}</div>}
      </td>
      <td className="px-4 py-2 font-mono text-xs">{inv.invoice_number || '—'}</td>
      <td className="px-4 py-2 text-xs">{formatDate(inv.invoice_date)}</td>
      <td className="px-4 py-2 text-right font-mono">{inv.ttc_xaf != null ? formatXAF(inv.ttc_xaf) : '—'}</td>
      <td className="px-4 py-2 text-center">
        {inv.status === 'OCR_ERROR' ? (
          <Badge variant="err">OCR err.</Badge>
        ) : inv.is_compliant ? (
          <Badge variant="ok"><CheckCircle2 className="w-3 h-3 inline mr-1" />OK</Badge>
        ) : (
          <Badge variant="err"><AlertTriangle className="w-3 h-3 inline mr-1" />{(inv.failed_fond_count + inv.failed_forme_count)}</Badge>
        )}
      </td>
      <td className="px-4 py-2 text-[11px] text-slate-700 max-w-md">
        {failedControls.length > 0 ? (
          <ul className="list-disc list-inside leading-snug">
            {failedControls.map((l, i) => <li key={i}>{l}</li>)}
          </ul>
        ) : inv.status === 'OCR_ERROR' ? (
          <span className="text-black font-bold">{inv.ocr_error}</span>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-center">
        <PdfButton invoiceId={inv.id} />
      </td>
    </tr>
  );
}


function PdfButton({ invoiceId }: { invoiceId: string }) {
  const t = useT();
  const onClick = async () => {
    const token = getToken();
    const res = await fetch(`/invoices/${invoiceId}/pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };
  return (
    <Button variant="outline" size="sm" onClick={onClick}>
      <ExternalLink className="w-3 h-3" />
      {t('inv.viewPdf')}
    </Button>
  );
}


function KPI({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'ok' | 'warn' | 'err' | 'neutral' }) {
  const cls = tone === 'err' ? 'text-black font-bold' : tone === 'warn' ? 'text-neutral-700' : tone === 'ok' ? 'text-neutral-700' : 'text-slate-900';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
        <div className={`text-2xl font-bold mt-1 font-display ${cls}`}>{value}</div>
      </CardContent>
    </Card>
  );
}
