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
    { href: '/dashboard', labelKey: 'nav.dashboard', Icon: LayoutDashboard },
  ]},
  { sectionKey: 'sidebar.dataIntegrity', items: [
    { href: '/audit-data',     labelKey: 'nav.auditData',         Icon: Database },
    { href: '/rapprochements', labelKey: 'nav.rapprochements',    Icon: GitCompare },
    { href: '/factures',       labelKey: 'nav.supplierInvoices',  Icon: FileText },
  ]},
  { sectionKey: 'sidebar.accountingControls', items: [
    {
      href: '/impots-societes', labelKey: 'nav.corporateTax', Icon: Building2,
      children: [
        { href: '/impots-societes/amortissements',           labelKey: 'is.amortissements.title' },
        { href: '/impots-societes/reglements-especes',       labelKey: 'is.cash.title' },
        { href: '/impots-societes/dons',                     labelKey: 'is.dons.title' },
        { href: '/impots-societes/acomptes',                 labelKey: 'is.acomptes.title' },
        { href: '/impots-societes/primes-assurance',         labelKey: 'is.assurance.title' },
        { href: '/impots-societes/charges-financieres',      labelKey: 'is.financieres.title' },
        { href: '/impots-societes/petit-materiel',           labelKey: 'is.petitMateriel.title' },
        { href: '/impots-societes/non-deductibles',          labelKey: 'is.nonDeductible.title' },
        { href: '/impots-societes/partiellement-deductibles',labelKey: 'is.partiellementDeductible.title' },
        { href: '/impots-societes/synthese',                 labelKey: 'is.synthese.title' },
      ],
    },
    {
      href: '/tva', labelKey: 'nav.vat', Icon: Receipt,
      children: [
        { href: '/tva/rapprochement', labelKey: 'vat.rapprochement.title' },
        { href: '/tva/deductible',    labelKey: 'vat.deductible.title' },
        { href: '/tva/collectee',     labelKey: 'vat.collectee.title' },
        { href: '/tva/exonerations',  labelKey: 'vat.exonerations.title' },
        { href: '/tva/synthese',      labelKey: 'vat.synthese.title' },
      ],
    },
    { href: '/ircm', labelKey: 'nav.ircm', Icon: Coins },
  ]},
  { sectionKey: 'sidebar.restitution', items: [
    { href: '/rapports', labelKey: 'nav.rapports', Icon: BarChart3 },
  ]},
  { sectionKey: 'sidebar.reference', items: [
    { href: '/referentiel', labelKey: 'nav.referentiel', Icon: BookMarked },
  ]},
  { sectionKey: 'sidebar.administration', adminOnly: true, items: [
    { href: '/utilisateurs', labelKey: 'nav.utilisateurs', Icon: Users, adminOnly: true },
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
      <aside className="bg-navy-deep text-slate-200 w-64 flex-shrink-0 flex flex-col">
        <div className="px-5 py-5 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gold flex items-center justify-center text-navy-deep font-bold text-sm shadow">FA</div>
            <div>
              <div className="font-display font-bold text-white text-sm">{t('app.title')}</div>
              <div className="text-[10px] text-slate-400 tracking-wider">{t('app.subtitle')}</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 overflow-y-auto">
          {NAV.filter((sec) => !sec.adminOnly || user?.role === 'ADMIN').map((sec) => (
            <div key={sec.sectionKey}>
              <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold px-4 mt-5 mb-2">
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

        <div className="px-3 py-4 border-t border-white/5">
          <div className="flex items-center gap-3 px-2 py-2 rounded-lg">
            <div className="w-9 h-9 rounded-full bg-gold/20 text-gold flex items-center justify-center font-semibold text-sm">
              {user?.full_name?.split(' ').map(p => p[0]).slice(0, 2).join('') || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-white font-medium truncate">{user?.full_name || '…'}</div>
              <div className="text-[11px] text-slate-400 truncate">{user?.role || ''}</div>
            </div>
            <button onClick={logout} className="text-slate-400 hover:text-white" title={t('app.logout')}>
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-6 lg:px-8 py-3.5 flex items-center justify-between gap-4">
          <div className="hidden lg:block">
            <div className="text-[11px] text-slate-500 uppercase tracking-widest">{t('app.platform')}</div>
            <div className="text-sm font-semibold text-slate-900 mt-0.5">
              {t('app.platformDesc')}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                className="pl-9 pr-3 py-2 w-full text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-navy/20 focus:border-navy bg-slate-50"
                placeholder={t('app.searchPlaceholder')}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ActiveAuditeeBadge />
            <LanguageToggle />
            <button className="relative p-2 rounded-lg hover:bg-slate-100 text-slate-600">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-gold" />
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
  const { href, labelKey, Icon, children } = item;
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
          'flex items-center gap-1 px-1 rounded-lg transition',
          selfActive
            ? 'text-white bg-gradient-to-r from-gold/20 to-transparent border-l-[3px] border-gold pl-[1px]'
            : 'text-slate-300 hover:text-white hover:bg-white/5',
        )}
      >
        <Link
          href={href}
          className="flex items-center gap-3 flex-1 px-3 py-2.5 text-sm font-medium cursor-pointer min-w-0"
        >
          <Icon className="w-5 h-5 flex-shrink-0" />
          <span className="truncate">{t(labelKey)}</span>
        </Link>
        {hasChildren && (
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }}
            className="p-1 mr-1 rounded hover:bg-white/10 text-slate-400"
            aria-label={open ? 'Collapse' : 'Expand'}
          >
            {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        )}
      </div>

      {hasChildren && open && (
        <div className="ml-8 mt-0.5 mb-1 space-y-0.5 border-l border-white/10 pl-3">
          {children!.map((c) => {
            const active = pathname === c.href;
            return (
              <Link
                key={c.href}
                href={c.href}
                className={cn(
                  'block py-1.5 px-2 rounded text-[12.5px] transition',
                  active
                    ? 'text-gold bg-gold/10 font-semibold'
                    : 'text-slate-400 hover:text-white hover:bg-white/5',
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
      className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gold/10 border border-gold/30 hover:bg-gold/20 transition group"
      title={t('header.activeAuditeeTooltip')}
    >
      <Building2 className="w-4 h-4 text-amber-700 flex-shrink-0" />
      <div className="min-w-0 max-w-[260px]">
        <div className="text-[10px] uppercase tracking-wider text-amber-700 font-semibold leading-none">
          {t('header.activeAuditee')}
        </div>
        <div className="text-xs font-semibold text-slate-900 truncate leading-tight mt-0.5">
          {currentCase.taxpayer.raison_sociale}
        </div>
        <div className="text-[10px] font-mono text-slate-500 truncate leading-none mt-0.5">
          {currentCase.reference} · {t('app.year')} {currentCase.fiscal_year}
        </div>
      </div>
    </Link>
  );
}
