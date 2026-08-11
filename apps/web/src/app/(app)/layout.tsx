'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  BarChart3, LogOut, Bell, Search, BookMarked, Users,
  Database, GitCompare, Building2, Receipt, Coins, FileText,
  ChevronDown, ChevronRight,
} from 'lucide-react';
import { api, getToken, setToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import { useT, type MessageKey } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { LanguageToggle } from '@/components/language-toggle';
import type { User } from '@/lib/types';

interface NavChild {
  href: string;
  labelKey: MessageKey;
}

interface NavItem {
  href: string;
  /** Translation key — looked up via useT() at render time. */
  labelKey: MessageKey;
  Icon: React.ComponentType<{ className?: string }>;
  /** Tailwind classes for the coloured icon tile (Proposal A — Wayfinding). */
  tint?: string;
  adminOnly?: boolean;
  /** Optional nested children — when present the item becomes expandable. */
  children?: NavChild[];
}

interface NavSection {
  /** Translation key for the section title. */
  sectionKey: MessageKey;
  adminOnly?: boolean;
  items: NavItem[];
}

const NAV: NavSection[] = [
  { sectionKey: 'sidebar.general', items: [
    { href: '/dashboard', labelKey: 'nav.dashboard', Icon: LayoutDashboard, tint: 'bg-indigo-50 text-indigo-600' },
  ]},
  { sectionKey: 'sidebar.dataIntegrity', items: [
    { href: '/audit-data',     labelKey: 'nav.auditData',         Icon: Database,   tint: 'bg-blue-50 text-blue-600' },
    {
      href: '/rapprochements', labelKey: 'nav.rapprochements',    Icon: GitCompare, tint: 'bg-cyan-50 text-cyan-600',
      children: [
        { href: '/rapprochements/acomptes', labelKey: 'is.acomptes.title' },
      ],
    },
    { href: '/factures',       labelKey: 'nav.supplierInvoices',  Icon: FileText,   tint: 'bg-teal-50 text-teal-600' },
  ]},
  { sectionKey: 'sidebar.accountingControls', items: [
    {
      href: '/impots-societes', labelKey: 'nav.corporateTax', Icon: Building2, tint: 'bg-violet-50 text-violet-600',
      children: [
        { href: '/impots-societes/amortissements',           labelKey: 'is.amortissements.title' },
        { href: '/impots-societes/reglements-especes',       labelKey: 'is.cash.title' },
        { href: '/impots-societes/dons',                     labelKey: 'is.dons.title' },
        { href: '/impots-societes/primes-assurance',         labelKey: 'is.assurance.title' },
        { href: '/impots-societes/charges-financieres',      labelKey: 'is.financieres.title' },
        { href: '/impots-societes/petit-materiel',           labelKey: 'is.petitMateriel.title' },
        { href: '/impots-societes/non-deductibles',          labelKey: 'is.nonDeductible.title' },
        { href: '/impots-societes/partiellement-deductibles',labelKey: 'is.partiellementDeductible.title' },
        { href: '/impots-societes/synthese',                 labelKey: 'is.synthese.title' },
      ],
    },
    {
      href: '/tva', labelKey: 'nav.vat', Icon: Receipt, tint: 'bg-fuchsia-50 text-fuchsia-600',
      children: [
        { href: '/tva/rapprochement', labelKey: 'vat.rapprochement.title' },
        { href: '/tva/deductible',    labelKey: 'vat.deductible.title' },
        { href: '/tva/collectee',     labelKey: 'vat.collectee.title' },
        { href: '/tva/exonerations',  labelKey: 'vat.exonerations.title' },
        { href: '/tva/synthese',      labelKey: 'vat.synthese.title' },
      ],
    },
    { href: '/ircm', labelKey: 'nav.ircm', Icon: Coins, tint: 'bg-rose-50 text-rose-600' },
  ]},
  { sectionKey: 'sidebar.restitution', items: [
    { href: '/rapports', labelKey: 'nav.rapports', Icon: BarChart3, tint: 'bg-amber-50 text-amber-700' },
  ]},
  { sectionKey: 'sidebar.reference', items: [
    { href: '/referentiel', labelKey: 'nav.referentiel', Icon: BookMarked, tint: 'bg-emerald-50 text-emerald-600' },
  ]},
  { sectionKey: 'sidebar.administration', adminOnly: true, items: [
    { href: '/utilisateurs', labelKey: 'nav.utilisateurs', Icon: Users, adminOnly: true, tint: 'bg-slate-100 text-slate-600' },
  ]},
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { setUser, user } = useApp();
  const t = useT();

  // Bootstrap session: if no token, kick to login. Otherwise fetch /auth/me.
  useEffect(() => {
    if (!getToken()) router.replace('/login');
  }, [router]);

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/auth/me'),
    enabled: !!getToken(),
  });

  useEffect(() => { if (me) setUser(me); }, [me, setUser]);

  const logout = () => {
    setToken(null);
    setUser(null);
    router.push('/login');
  };

  return (
    <div className="flex min-h-screen">
      <aside className="bg-white text-neutral-700 w-64 flex-shrink-0 flex flex-col border-r border-neutral-200">
        <div className="px-5 py-5 border-b border-neutral-200">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-600 to-sky-500 flex items-center justify-center text-white font-bold text-sm shadow-sm">FA</div>
            <div>
              <div className="font-display font-extrabold text-black text-sm">{t('app.title')}</div>
              <div className="text-[10px] text-neutral-500 tracking-wider uppercase">{t('app.subtitle')}</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 overflow-y-auto">
          {NAV.filter((sec) => !sec.adminOnly || user?.role === 'ADMIN').map((sec) => (
            <div key={sec.sectionKey}>
              <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-semibold px-4 mt-5 mb-2">
                {t(sec.sectionKey)}
              </div>
              {sec.items
                .filter((item) => !item.adminOnly || user?.role === 'ADMIN')
                .map((item) => (
                  <NavRow key={item.href} item={item} pathname={pathname} />
                ))}
            </div>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-neutral-200">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="w-9 h-9 rounded-full bg-black text-white flex items-center justify-center font-semibold text-sm">
              {user?.full_name?.split(' ').map(p => p[0]).slice(0, 2).join('') || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-black font-medium truncate">{user?.full_name || '…'}</div>
              <div className="text-[11px] text-neutral-500 truncate">{user?.role || ''}</div>
            </div>
            <button onClick={logout} className="text-neutral-500 hover:text-black" title={t('app.logout')}>
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-neutral-200 px-6 lg:px-8 py-3.5 flex items-center justify-between gap-4">
          <div className="hidden lg:block">
            <div className="text-[11px] text-neutral-500 uppercase tracking-widest">{t('app.platform')}</div>
            <div className="text-sm font-semibold text-black mt-0.5">
              {t('app.platformDesc')}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
              <input
                className="pl-9 pr-3 py-2 w-full text-sm border border-neutral-300 rounded-none focus:outline-none focus:border-black bg-transparent"
                placeholder={t('app.searchPlaceholder')}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ActiveAuditeeBadge />
            <LanguageToggle />
            <button className="relative p-2 rounded-none border border-neutral-300 hover:border-black text-neutral-700 hover:text-black transition">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500" />
            </button>
          </div>
        </header>

        <div className="flex-1 p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}


/**
 * Sidebar nav row. If the item has `children`, it renders as an expandable
 * group: clicking the chevron toggles the children, the row itself still
 * navigates to the parent route. The group auto-expands when any child
 * route is active.
 */
function NavRow({ item, pathname }: { item: NavItem; pathname: string }) {
  const t = useT();
  const { href, labelKey, Icon, children, tint } = item;
  const hasChildren = !!children && children.length > 0;
  const childActive = hasChildren && children!.some(
    (c) => pathname === c.href || pathname.startsWith(c.href + '/'),
  );
  // Active = the parent route exactly, NOT prefix-matching children (so the
  // parent only highlights when you're literally on that page).
  const selfActive = pathname === href;
  const [open, setOpen] = useState(childActive || selfActive);

  // Keep the group open when navigation lands on a child.
  useEffect(() => {
    if (childActive || selfActive) setOpen(true);
  }, [childActive, selfActive]);

  return (
    <>
      <div
        className={cn(
          'flex items-center gap-1 px-1 transition',
          selfActive
            ? 'text-black bg-neutral-100 border-l-[3px] border-black pl-[1px] font-semibold'
            : 'text-neutral-700 hover:text-black hover:bg-neutral-50',
        )}
      >
        <Link
          href={href}
          className="flex items-center gap-2.5 flex-1 px-2.5 py-2 text-sm font-medium cursor-pointer min-w-0"
        >
          <span className={cn(
            'w-7 h-7 rounded-lg grid place-items-center flex-shrink-0',
            tint ?? 'bg-neutral-100 text-neutral-600',
          )}>
            <Icon className="w-[17px] h-[17px]" />
          </span>
          <span className="truncate">{t(labelKey)}</span>
        </Link>
        {hasChildren && (
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }}
            className="p-1 mr-1 hover:bg-neutral-200 text-neutral-500"
            aria-label={open ? 'Collapse' : 'Expand'}
          >
            {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        )}
      </div>

      {hasChildren && open && (
        <div className="ml-8 mt-0.5 mb-1 space-y-0.5 border-l border-neutral-200 pl-3">
          {children!.map((c) => {
            const active = pathname === c.href;
            return (
              <Link
                key={c.href}
                href={c.href}
                className={cn(
                  'block py-1.5 px-2 text-[12.5px] transition',
                  active
                    ? 'text-black bg-neutral-100 font-semibold border-l-[3px] border-black -ml-3 pl-3'
                    : 'text-neutral-700 hover:text-black hover:bg-neutral-50',
                )}
              >
                {t(c.labelKey)}
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}


/**
 * Top-right chip showing the active auditee — taxpayer name + reference + FY.
 * Hidden when no auditee is selected. Clicking jumps to the dashboard where
 * the master filter lives.
 */
function ActiveAuditeeBadge() {
  const t = useT();
  const currentCase = useApp((s) => s.currentCase);
  if (!currentCase) return null;
  return (
    <Link
      href="/dashboard"
      className="hidden md:flex items-center gap-2 px-3 py-1.5 border border-neutral-300 hover:border-black transition group"
      title={t('header.activeAuditeeTooltip')}
    >
      <Building2 className="w-4 h-4 text-black flex-shrink-0" />
      <div className="min-w-0 max-w-[260px]">
        <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold leading-none">
          {t('header.activeAuditee')}
        </div>
        <div className="text-xs font-semibold text-black truncate leading-tight mt-0.5">
          {currentCase.taxpayer?.raison_sociale ?? '—'}
        </div>
        <div className="text-[10px] font-mono text-neutral-500 truncate leading-none mt-0.5">
          {currentCase.reference} · {t('app.year')} {currentCase.fiscal_year}
        </div>
      </div>
    </Link>
  );
}
