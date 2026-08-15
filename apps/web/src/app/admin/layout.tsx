'use client';

/** Console d'administration plateforme — chrome minimal, AUCUN élément
 *  d'audit : uniquement la gestion des tenants. */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, LogOut, ShieldCheck } from 'lucide-react';
import { api, getToken, setToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import type { User } from '@/lib/types';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, setUser } = useApp();

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
    window.localStorage.removeItem('fa_token_admin');
    window.localStorage.removeItem('fa_acting_org');
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="bg-black text-white px-6 py-3.5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-white/10 grid place-items-center">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <div className="font-display font-extrabold text-sm leading-none">VerifiScale — Administration plateforme</div>
            <div className="text-[10px] text-neutral-400 tracking-wider uppercase mt-0.5">Gestion des clients (tenants)</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="hidden sm:block text-neutral-300">{user?.email}</span>
          <Link href="/dashboard" className="flex items-center gap-1.5 border border-white/25 hover:border-white px-3 py-1.5 rounded transition">
            <ExternalLink className="w-3.5 h-3.5" /> Ouvrir l&apos;application
          </Link>
          <button onClick={logout} className="flex items-center gap-1.5 border border-white/25 hover:border-white px-3 py-1.5 rounded transition">
            <LogOut className="w-3.5 h-3.5" /> Déconnexion
          </button>
        </div>
      </header>
      <main className="max-w-6xl mx-auto p-6 lg:p-8">{children}</main>
    </div>
  );
}
