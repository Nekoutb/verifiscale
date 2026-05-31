'use client';
import { useApp } from '@/lib/store';
import { cn } from '@/lib/utils';

/**
 * FR | EN pill toggle. Sits in the header. The current locale is highlighted;
 * clicking the other side switches and persists via the Zustand store.
 */
export function LanguageToggle() {
  const locale = useApp((s) => s.locale);
  const setLocale = useApp((s) => s.setLocale);

  return (
    <div className="inline-flex items-center bg-slate-100 rounded-md p-0.5 text-xs font-semibold">
      <button
        type="button"
        onClick={() => setLocale('fr')}
        aria-pressed={locale === 'fr'}
        className={cn(
          'px-2.5 py-1 rounded transition',
          locale === 'fr' ? 'bg-white text-navy shadow-sm' : 'text-slate-500 hover:text-slate-700',
        )}
      >
        FR
      </button>
      <button
        type="button"
        onClick={() => setLocale('en')}
        aria-pressed={locale === 'en'}
        className={cn(
          'px-2.5 py-1 rounded transition',
          locale === 'en' ? 'bg-white text-navy shadow-sm' : 'text-slate-500 hover:text-slate-700',
        )}
      >
        EN
      </button>
    </div>
  );
}
