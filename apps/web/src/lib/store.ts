import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AuditCase, User } from './types';

export type Locale = 'fr' | 'en';

interface AppState {
  user: User | null;
  currentCaseId: string | null;
  currentCase: AuditCase | null;
  locale: Locale;
  setUser: (u: User | null) => void;
  setCurrentCase: (c: AuditCase | null) => void;
  setLocale: (l: Locale) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set) => ({
      user: null,
      currentCaseId: null,
      currentCase: null,
      locale: 'fr',
      setUser: (user) => set({ user }),
      setCurrentCase: (c) => set({ currentCase: c, currentCaseId: c?.id ?? null }),
      setLocale: (locale) => set({ locale }),
    }),
    {
      name: 'fa-app-state',
      partialize: (state) => ({
        currentCaseId: state.currentCaseId,
        locale: state.locale,
      }),
    },
  ),
);

/** Helper — return the list of fiscal years in scope: starting_year ... starting_year + N − 1. */
export function caseYearRange(c: AuditCase | null | undefined): number[] {
  if (!c) return [];
  const start = c.starting_year ?? c.fiscal_year;
  const n = c.number_of_years ?? 1;
  return Array.from({ length: n }, (_, i) => start + i);
}
