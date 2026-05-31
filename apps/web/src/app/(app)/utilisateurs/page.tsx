'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Users, Search, Phone, Mail, Download } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';
import { formatDate, cn } from '@/lib/utils';
import type { User } from '@/lib/types';

const ROLE_LABELS: Record<string, { label: string; tone: string }> = {
  ADMIN:        { label: 'Administrateur', tone: 'bg-rose-100 text-rose-800' },
  SUPERVISEUR:  { label: 'Superviseur',    tone: 'bg-indigo-100 text-indigo-800' },
  CHEF_BRIGADE: { label: 'Chef brigade',   tone: 'bg-amber-100 text-amber-800' },
  AUDITEUR:     { label: 'Auditeur',       tone: 'bg-emerald-100 text-emerald-800' },
};

function toCsv(users: User[]): string {
  const header = ['Nom complet', 'Email', 'Téléphone', 'Organisation', 'Rôle', 'Brigade', 'Dernière connexion', 'Créé le'];
  const rows = users.map((u) => [
    u.full_name,
    u.email,
    u.phone_number || '',
    u.organization || '',
    u.role,
    u.brigade_id || '',
    u.last_login_at || '',
    u.created_at || '',
  ]);
  const escape = (v: string) => `"${(v ?? '').replace(/"/g, '""')}"`;
  return [header, ...rows].map((r) => r.map(escape).join(',')).join('\n');
}

export default function UtilisateursPage() {
  const { user: me } = useApp();
  const [search, setSearch] = useState('');
  const [filterRole, setFilterRole] = useState<string>('all');
  const [filterContact, setFilterContact] = useState<'all' | 'with_phone' | 'without_phone'>('all');

  const isAdmin = me?.role === 'ADMIN';

  const { data: users = [], isLoading, error } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api<User[]>('/users'),
    enabled: isAdmin,
  });

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return users.filter((u) => {
      if (filterRole !== 'all' && u.role !== filterRole) return false;
      if (filterContact === 'with_phone' && !u.phone_number) return false;
      if (filterContact === 'without_phone' && u.phone_number) return false;
      if (q) {
        const hay = `${u.full_name} ${u.email} ${u.phone_number ?? ''} ${u.organization ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [users, search, filterRole, filterContact]);

  const stats = useMemo(() => {
    const withPhone = users.filter((u) => u.phone_number).length;
    return {
      total: users.length,
      withPhone,
      coverage: users.length ? Math.round((withPhone / users.length) * 100) : 0,
      activeLast30d: users.filter((u) => {
        if (!u.last_login_at) return false;
        return Date.now() - new Date(u.last_login_at).getTime() < 30 * 86_400_000;
      }).length,
    };
  }, [users]);

  const exportCsv = () => {
    const csv = toCsv(filtered);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `utilisateurs-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!isAdmin) {
    return (
      <Card>
        <CardContent>
          <div className="text-center py-12 text-slate-500">
            Cette section est réservée aux administrateurs.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Users className="w-6 h-6 text-rose-700" />
            Utilisateurs & contacts
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Annuaire complet des utilisateurs avec coordonnées capturées à la connexion — pour suivi et prospection.
          </p>
        </div>
        <Button variant="outline" onClick={exportCsv} disabled={filtered.length === 0}>
          <Download className="w-4 h-4" />
          Exporter CSV ({filtered.length})
        </Button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Total utilisateurs"   value={stats.total} />
        <Stat label="Avec téléphone"       value={stats.withPhone} sub={`${stats.coverage}% couverture`} tone="ok" />
        <Stat label="Sans téléphone"       value={stats.total - stats.withPhone} tone="warn" />
        <Stat label="Actifs (30 j)"        value={stats.activeLast30d} />
      </div>

      <Card>
        <CardHeader><CardTitle>Filtres</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Rechercher nom, email, téléphone, organisation…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <select
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
            className="h-9 px-3 text-sm border border-slate-300 rounded-lg bg-white"
          >
            <option value="all">Tous rôles</option>
            <option value="ADMIN">Administrateurs</option>
            <option value="SUPERVISEUR">Superviseurs</option>
            <option value="CHEF_BRIGADE">Chefs de brigade</option>
            <option value="AUDITEUR">Auditeurs</option>
          </select>
          <select
            value={filterContact}
            onChange={(e) => setFilterContact(e.target.value as typeof filterContact)}
            className="h-9 px-3 text-sm border border-slate-300 rounded-lg bg-white"
          >
            <option value="all">Tous contacts</option>
            <option value="with_phone">Avec téléphone</option>
            <option value="without_phone">Sans téléphone</option>
          </select>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{filtered.length} utilisateur(s)</CardTitle>
        </CardHeader>
        <div className="overflow-x-auto">
          {isLoading ? (
            <div className="text-center py-12 text-slate-500 text-sm">Chargement…</div>
          ) : error ? (
            <div className="text-center py-12 text-rose-600 text-sm">
              Erreur de chargement : {(error as Error).message}
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-sm">Aucun utilisateur ne correspond aux filtres.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
                  <th className="px-4 py-3 text-left">Utilisateur</th>
                  <th className="px-4 py-3 text-left">Contact</th>
                  <th className="px-4 py-3 text-left">Organisation</th>
                  <th className="px-4 py-3 text-left">Rôle</th>
                  <th className="px-4 py-3 text-left">Statut</th>
                  <th className="px-4 py-3 text-left">Dernière connexion</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => {
                  const role = ROLE_LABELS[u.role] ?? { label: u.role, tone: 'bg-slate-100 text-slate-700' };
                  const initials = u.full_name
                    .split(' ')
                    .map((p) => p[0])
                    .filter(Boolean)
                    .slice(0, 2)
                    .join('')
                    .toUpperCase();
                  return (
                    <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-navy/10 text-navy flex items-center justify-center text-xs font-semibold flex-shrink-0">
                            {initials}
                          </div>
                          <div>
                            <div className="font-medium text-slate-900">{u.full_name}</div>
                            <div className="text-[11px] text-slate-500">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 text-xs">
                            <Mail className="w-3 h-3 text-slate-400" />
                            <a href={`mailto:${u.email}`} className="text-slate-700 hover:text-navy">{u.email}</a>
                          </div>
                          {u.phone_number ? (
                            <div className="flex items-center gap-1.5 text-xs">
                              <Phone className="w-3 h-3 text-slate-400" />
                              <a href={`tel:${u.phone_number.replace(/\s/g, '')}`} className="font-mono text-slate-700 hover:text-navy">
                                {u.phone_number}
                              </a>
                            </div>
                          ) : (
                            <span className="text-[11px] text-slate-400 italic">Pas de téléphone</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-700">
                        {u.organization || <span className="text-slate-400 italic">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn('inline-flex px-2 py-0.5 text-xs font-medium rounded-full', role.tone)}>
                          {role.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {u.is_active ? (
                          <Badge variant="ok">Actif</Badge>
                        ) : (
                          <Badge variant="neutral">Désactivé</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600">
                        {u.last_login_at ? formatDate(u.last_login_at) : <span className="text-slate-400 italic">Jamais</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = 'neutral',
  sub,
}: {
  label: string;
  value: number | string;
  tone?: 'ok' | 'warn' | 'err' | 'neutral';
  sub?: string;
}) {
  const cls =
    tone === 'err' ? 'text-rose-600'
    : tone === 'warn' ? 'text-amber-600'
    : tone === 'ok' ? 'text-emerald-600'
    : 'text-slate-900';
  return (
    <Card>
      <CardContent>
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</div>
        <div className={`text-2xl font-bold mt-1 font-display ${cls}`}>{value}</div>
        {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  );
}
