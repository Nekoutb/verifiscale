'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Briefcase, ChevronDown } from 'lucide-react';
import { api } from '@/lib/api';
import { useApp, caseYearRange } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { AUDIT_TYPE_LABELS, type AuditCase, type AuditType } from '@/lib/types';

const AUDIT_TYPES_ORDERED: AuditType[] = ['VGC', 'VP', 'CSP', 'CI', 'CT', 'EF'];

type Variant = 'dark' | 'light';

interface Theme {
  wrap: string;
  label: string;
  hint: string;
  select: string;
  input: string;
  badgeBase: string;
  badgeActive: string;
  badgeIdle: string;
  niu: string;
  niuValue: string;
  niuSub: string;
  updating: string;
}

const THEMES: Record<Variant, Theme> = {
  dark: {
    wrap:        'bg-black/40 border-y border-white/5 px-3 py-3 space-y-2.5',
    label:       'text-[10px] uppercase tracking-widest text-slate-400 font-semibold flex items-center gap-1.5 px-1',
    hint:        'text-[9px] uppercase tracking-wider text-slate-500 mb-1 px-1',
    select:      'w-full bg-white/5 border border-white/10 rounded-md text-white text-xs px-2 py-1.5 pr-7 appearance-none focus:outline-none focus:border-white/50 cursor-pointer disabled:opacity-50',
    input:       'w-full bg-white/5 border border-white/10 rounded-md text-white text-xs px-2 py-1.5 focus:outline-none focus:border-white/50 disabled:opacity-50',
    badgeBase:   'text-[9px] font-mono px-1.5 py-0.5 rounded',
    badgeActive: 'bg-white/20 text-white border border-white/30',
    badgeIdle:   'bg-white/5 text-slate-400 border border-white/10',
    niu:         'text-[10px] text-slate-400 px-1 leading-relaxed',
    niuValue:    'font-mono text-slate-300',
    niuSub:      'text-slate-500',
    updating:    'text-[9px] text-white/80 px-1',
  },
  light: {
    wrap:        'space-y-3',
    label:       'text-[11px] uppercase tracking-widest text-slate-500 font-semibold flex items-center gap-1.5',
    hint:        'text-[10px] uppercase tracking-wider text-slate-500 mb-1',
    select:      'w-full bg-white border border-slate-200 rounded-md text-slate-900 text-sm px-3 py-2 pr-8 appearance-none focus:outline-none focus:border-black focus:ring-2 focus:ring-black/15 cursor-pointer disabled:opacity-50',
    input:       'w-full bg-white border border-slate-200 rounded-md text-slate-900 text-sm px-3 py-2 focus:outline-none focus:border-black focus:ring-2 focus:ring-black/15 disabled:opacity-50',
    badgeBase:   'text-[10px] font-mono px-2 py-0.5 rounded',
    badgeActive: 'bg-neutral-100 text-black border border-black',
    badgeIdle:   'bg-slate-100 text-slate-500 border border-slate-200',
    niu:         'text-xs text-slate-500 leading-relaxed',
    niuValue:    'font-mono text-slate-700',
    niuSub:      'text-slate-400',
    updating:    'text-[10px] text-neutral-700',
  },
};

/**
 * Auditee picker — auditor picks:
 *  - the auditee (audit case)
 *  - the audit type (VGC, VP, CSP, CI, CT, EF) — from LPF Cameroun
 *  - the audit scope (starting year + number of years, 1-10)
 *
 * `variant="dark"` is the sidebar look; `variant="light"` is the dashboard card.
 */
export function AuditeePicker({ variant = 'dark' }: { variant?: Variant } = {}) {
  const qc = useQueryClient();
  const { currentCase, currentCaseId, setCurrentCase } = useApp();
  const t = useT();
  const th = THEMES[variant];

  const { data: cases = [] } = useQuery({
    queryKey: ['audit-cases'],
    queryFn: () => api<AuditCase[]>('/audit-cases'),
  });

  useEffect(() => {
    if (!currentCaseId) return;
    const found = cases.find((c) => c.id === currentCaseId);
    if (found && (!currentCase || currentCase.id !== found.id)) {
      setCurrentCase(found);
    }
  }, [cases, currentCaseId, currentCase, setCurrentCase]);

  const updateCase = useMutation({
    mutationFn: (patch: Partial<AuditCase>) =>
      api<AuditCase>(`/audit-cases/${currentCase!.id}`, { method: 'PATCH', body: patch }),
    onSuccess: (updated) => {
      setCurrentCase(updated);
      qc.invalidateQueries({ queryKey: ['audit-cases'] });
      qc.invalidateQueries({ queryKey: ['audit-case', updated.id] });
      qc.invalidateQueries({ queryKey: ['monthly-returns', updated.id] });
      qc.invalidateQueries({ queryKey: ['datasets', updated.id] });
    },
  });

  const startingYear = currentCase?.starting_year ?? currentCase?.fiscal_year;
  const numberOfYears = currentCase?.number_of_years ?? 1;
  const years = useMemo(() => caseYearRange(currentCase), [currentCase]);

  // Local string state so the input lets you type freely (e.g. "2", "20", "203").
  // We commit to the backend only on blur / Enter, once the value parses to a
  // sensible year. Re-syncs whenever the active case changes.
  const [yearDraft, setYearDraft] = useState<string>(startingYear ? String(startingYear) : '');
  const [yearsDraft, setYearsDraft] = useState<string>(String(numberOfYears));
  useEffect(() => {
    setYearDraft(startingYear ? String(startingYear) : '');
    setYearsDraft(String(numberOfYears));
  }, [currentCase?.id, startingYear, numberOfYears]);

  const commitYear = () => {
    const v = parseInt(yearDraft, 10);
    if (!isNaN(v) && v >= 2000 && v <= 2099 && v !== startingYear) {
      updateCase.mutate({ starting_year: v, fiscal_year: v });
    } else {
      // invalid → snap back to last good value
      setYearDraft(startingYear ? String(startingYear) : '');
    }
  };
  const commitYears = () => {
    const v = parseInt(yearsDraft, 10);
    if (!isNaN(v) && v >= 1 && v <= 10 && v !== numberOfYears) {
      updateCase.mutate({ number_of_years: v });
    } else {
      setYearsDraft(String(numberOfYears));
    }
  };

  const optionBg = variant === 'dark' ? 'bg-black' : '';

  return (
    <div className={th.wrap}>
      <div className={th.label}>
        <Briefcase className="w-3.5 h-3.5" />
        {t('auditee.label')}
      </div>

      {/* Auditee selector */}
      <div className="relative">
        <select
          value={currentCase?.id ?? ''}
          onChange={(e) => {
            const c = cases.find((x) => x.id === e.target.value) ?? null;
            setCurrentCase(c);
          }}
          className={th.select}
        >
          <option value="" className={optionBg}>{t('auditee.selectPlaceholder')}</option>
          {cases.map((c) => (
            <option key={c.id} value={c.id} className={optionBg}>
              {c.taxpayer.raison_sociale} ({c.reference})
            </option>
          ))}
        </select>
        <ChevronDown className={cn(
          'w-3.5 h-3.5 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none',
          variant === 'dark' ? 'text-slate-400' : 'text-slate-500',
        )} />
      </div>

      {currentCase && (
        <>
          {/* NIU + brigade summary */}
          <div className={th.niu}>
            {t('auditee.niuLabel')} <span className={th.niuValue}>{currentCase.taxpayer.niu}</span>
            <br />
            <span className={th.niuSub}>{currentCase.taxpayer.sector ?? '—'}</span>
          </div>

          {/* Audit type */}
          <div>
            <div className={th.hint}>{t('auditee.controlNature')}</div>
            <div className="relative">
              <select
                value={currentCase.audit_type}
                disabled={updateCase.isPending}
                onChange={(e) => updateCase.mutate({ audit_type: e.target.value as AuditType })}
                className={th.select}
              >
                {AUDIT_TYPES_ORDERED.map((ty) => (
                  <option key={ty} value={ty} className={optionBg}>
                    {AUDIT_TYPE_LABELS[ty].short} — {AUDIT_TYPE_LABELS[ty].full}
                  </option>
                ))}
              </select>
              <ChevronDown className={cn(
                'w-3.5 h-3.5 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none',
                variant === 'dark' ? 'text-slate-400' : 'text-slate-500',
              )} />
            </div>
            <div className={cn('mt-0.5', variant === 'dark' ? 'text-[9px] text-slate-500 px-1' : 'text-[10px] text-slate-400')}>
              {AUDIT_TYPE_LABELS[currentCase.audit_type].ref}
            </div>
          </div>

          {/* Scope: starting year + number of years (free-typing — commits on blur / Enter) */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className={th.hint}>{t('auditee.startYear')}</div>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={yearDraft}
                disabled={updateCase.isPending}
                maxLength={4}
                onChange={(e) => setYearDraft(e.target.value.replace(/[^0-9]/g, ''))}
                onBlur={commitYear}
                onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                className={th.input}
              />
            </div>
            <div>
              <div className={th.hint}>{t('auditee.numberOfYears')}</div>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={yearsDraft}
                disabled={updateCase.isPending}
                maxLength={2}
                onChange={(e) => setYearsDraft(e.target.value.replace(/[^0-9]/g, ''))}
                onBlur={commitYears}
                onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                className={th.input}
              />
            </div>
          </div>

          {/* Year range badges */}
          <div className={cn('flex flex-wrap gap-1', variant === 'dark' && 'px-1')}>
            {years.map((y) => (
              <span
                key={y}
                className={cn(th.badgeBase, y === currentCase.fiscal_year ? th.badgeActive : th.badgeIdle)}
              >
                {y}
              </span>
            ))}
          </div>

          {updateCase.isPending && (
            <div className={th.updating}>{t('auditee.updating')}</div>
          )}
        </>
      )}
    </div>
  );
}
