'use client';

import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  label: string;
  accept?: Record<string, string[]>;
  onFile: (file: File) => Promise<void> | void;
  hint?: string;
  uploadedFilename?: string | null;
}

export function DropZone({ label, accept, onFile, hint, uploadedFilename }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(uploadedFilename ?? null);

  const onDrop = useCallback(async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      await onFile(files[0]);
      setDone(files[0].name);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [onFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: accept ?? {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
    },
    multiple: false,
    onDrop,
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        'border-2 border-dashed rounded-xl p-6 text-center transition cursor-pointer',
        isDragActive ? 'border-navy bg-navy/5'
                     : done   ? 'border-emerald-300 bg-emerald-50/40'
                     : error  ? 'border-rose-300 bg-rose-50/40'
                     :          'border-slate-300 bg-slate-50/60 hover:border-navy',
        busy && 'opacity-60 pointer-events-none',
      )}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-2">
        {done ? (
          <CheckCircle2 className="w-8 h-8 text-emerald-600" />
        ) : error ? (
          <AlertCircle className="w-8 h-8 text-rose-600" />
        ) : (
          <Upload className="w-8 h-8 text-slate-400" />
        )}
        <div className="text-sm font-medium text-slate-700">{label}</div>
        {done ? (
          <div className="flex items-center gap-2 text-xs text-emerald-700">
            <FileSpreadsheet className="w-4 h-4" /> {done}
          </div>
        ) : error ? (
          <div className="text-xs text-rose-700">{error}</div>
        ) : (
          <div className="text-xs text-slate-500">{hint ?? 'Glisser le fichier ou cliquer pour parcourir'}</div>
        )}
        {busy && <div className="text-xs text-slate-500 mt-1">Envoi en cours…</div>}
      </div>
    </div>
  );
}
