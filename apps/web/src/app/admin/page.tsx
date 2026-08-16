'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Building2, ChevronDown, ChevronRight, LogIn, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api, getToken, setToken } from '@/lib/api';
import { useApp } from '@/lib/store';
import { cn } from '@/lib/utils';

type Org = {
  id: string; name: string; contact_email: string | null; is_platform: boolean;
  is_active: boolean; created_at: string | null;
  user_count: number; case_count: number; dataset_count: number;
  last_upload_at: string | null; last_login_at: string | null;
};
type OrgDetail = Org & {
  members: { email: string; full_name: string; role: string; last_login_at: string | null }[];
  cases: { id: string; reference: string; taxpayer: string | null; fiscal_year: number; status: string; created_at: string | null }[];
};

const dt = (s: string | null) => (s ? s.slice(0, 10) : '—');

export default function AdminPage() {
  const user = useApp((s) => s.user);
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState({ name: '', contact_email: '', admin_full_name: '', admin_email: '', admin_password: '' });
  const [created, setCreated] = useState<{ email: string; password: string; emailSent?: boolean } | null>(null);

  const { data: orgs = [] } = useQuery({
    queryKey: ['admin-orgs'],
    queryFn: () => api<Org[]>('/admin/organizations'),
    enabled: !!user?.is_superadmin,
  });
  const { data: detail } = useQuery({
    queryKey: ['admin-org', open],
    queryFn: () => api<OrgDetail>(`/admin/organizations/${open}`),
    enabled: !!open,
  });

  const create = useMutation({
    mutationFn: () => api<{ email_sent?: boolean }>('/admin/organizations', { method: 'POST', body: form }),
    onSuccess: (r) => {
      setCreated({ email: form.admin_email, password: form.admin_password,
                   emailSent: !!(r as { email_sent?: boolean })?.email_sent });
      setForm({ name: '', contact_email: '', admin_full_name: '', admin_email: '', admin_password: '' });
      qc.invalidateQueries({ queryKey: ['admin-orgs'] });
    },
  });

  if (!user?.is_superadmin) {
    return (
      <Card><CardContent><div className="text-sm text-slate-500 py-8 text-center italic">
        Section réservée à l&apos;administrateur de la plateforme.
      </div></CardContent></Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <ShieldCheck className="w-6 h-6 text-black" />
          Administration plateforme — Clients
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Chaque client dispose de son espace isolé : ses dossiers, ses données, son équipe.
        </p>
      </div>

      {/* Nouveau client */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2">
          <Plus className="w-4 h-4" /> Nouveau client
        </CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-2 text-xs">
            <input className="border border-neutral-300 rounded px-2 py-1.5" placeholder="Raison sociale du cabinet / client *"
                   value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="border border-neutral-300 rounded px-2 py-1.5" placeholder="Email de contact"
                   value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
            <input className="border border-neutral-300 rounded px-2 py-1.5" placeholder="Nom de l'administrateur *"
                   value={form.admin_full_name} onChange={(e) => setForm({ ...form, admin_full_name: e.target.value })} />
            <input className="border border-neutral-300 rounded px-2 py-1.5" placeholder="Email administrateur *"
                   value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} />
            <input className="border border-neutral-300 rounded px-2 py-1.5" placeholder="Mot de passe provisoire * (≥6)"
                   value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} />
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" disabled={create.isPending} onClick={() => create.mutate()}>Créer le client</Button>
            {create.isError && <span className="text-xs text-rose-700">{(create.error as Error).message}</span>}
          </div>
          {created && (
            <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
              Client créé{created.emailSent ? ' — email de bienvenue envoyé ✓' : ''}.
              {!created.emailSent && ' Transmettez ces identifiants à son administrateur (email non configuré) :'}{' '}
              <b className="font-mono">{created.email}</b> / <b className="font-mono">{created.password}</b>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Clients + activité */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2">
          <Building2 className="w-4 h-4" /> Clients ({orgs.length})
        </CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
                <tr className="border-b border-neutral-200">
                  <th className="text-left px-2 py-1.5">Client</th>
                  <th className="text-right px-2 py-1.5">Membres</th>
                  <th className="text-right px-2 py-1.5">Dossiers</th>
                  <th className="text-right px-2 py-1.5">Fichiers</th>
                  <th className="text-left px-2 py-1.5">Dernier envoi</th>
                  <th className="text-left px-2 py-1.5">Dernière connexion</th>
                  <th className="text-left px-2 py-1.5">Créé le</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((o) => (
                  <>
                    <tr key={o.id} onClick={() => setOpen(open === o.id ? null : o.id)}
                        className="border-b border-neutral-100 cursor-pointer hover:bg-neutral-50">
                      <td className="px-2 py-2">
                        <span className="inline-flex items-center gap-1 font-semibold text-black">
                          {open === o.id ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          {o.name}
                          {o.is_platform && <span className="text-[9px] px-1 py-0.5 border border-black rounded uppercase">plateforme</span>}
                        </span>
                        <div className="text-[10px] text-neutral-500 ml-4">{o.contact_email}</div>
                      </td>
                      <td className="px-2 py-2 text-right font-mono">{o.user_count}</td>
                      <td className="px-2 py-2 text-right font-mono">{o.case_count}</td>
                      <td className="px-2 py-2 text-right font-mono">{o.dataset_count}</td>
                      <td className="px-2 py-2">{dt(o.last_upload_at)}</td>
                      <td className="px-2 py-2">{dt(o.last_login_at)}</td>
                      <td className="px-2 py-2">
                        <div className="flex items-center gap-2">
                          <span>{dt(o.created_at)}</span>
                          {!o.is_platform && (
                            <button
                              type="button"
                              title="Accéder à l'espace client (accès encadré, visible, réversible)"
                              onClick={async (e) => {
                                e.stopPropagation();
                                const r = await api<{ access_token: string; org_name: string }>(
                                  `/admin/organizations/${o.id}/impersonate`, { method: 'POST', body: {} });
                                window.localStorage.setItem('fa_token_admin', getToken() ?? '');
                                window.localStorage.setItem('fa_acting_org', r.org_name);
                                setToken(r.access_token);
                                window.location.href = '/dashboard';
                              }}
                              className="flex items-center gap-1 text-[10px] font-bold border border-black px-1.5 py-0.5 rounded hover:bg-black hover:text-white transition"
                            >
                              <LogIn className="w-3 h-3" /> Accéder à l'espace
                            </button>
                          )}
                          {!o.is_platform && (
                            <button
                              type="button"
                              title="Supprimer définitivement ce client (dossiers, données, membres)"
                              onClick={async (e) => {
                                e.stopPropagation();
                                const typed = window.prompt(
                                  `SUPPRESSION DÉFINITIVE de « ${o.name} »
` +
                                  `${o.case_count} dossier(s), ${o.dataset_count} fichier(s), ${o.user_count} membre(s) seront effacés.

` +
                                  `Tapez le nom exact du client pour confirmer :`);
                                if (typed !== o.name) return;
                                await api(`/admin/organizations/${o.id}`, { method: 'DELETE' });
                                qc.invalidateQueries({ queryKey: ['admin-orgs'] });
                              }}
                              className="flex items-center gap-1 text-[10px] font-bold border border-rose-400 text-rose-700 px-1.5 py-0.5 rounded hover:bg-rose-600 hover:text-white hover:border-rose-600 transition"
                            >
                              <Trash2 className="w-3 h-3" /> Supprimer
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {open === o.id && detail && (
                      <tr key={`${o.id}-d`}>
                        <td colSpan={7} className="px-4 py-3 bg-neutral-50">
                          <div className="grid lg:grid-cols-2 gap-4 text-[11px]">
                            <div>
                              <div className="font-bold uppercase text-[10px] tracking-wider text-neutral-500 mb-1">Membres</div>
                              {detail.members.map((m) => (
                                <div key={m.email} className="flex justify-between border-b border-neutral-100 py-1">
                                  <span>{m.full_name} <span className="text-neutral-500">· {m.email}</span></span>
                                  <span className={cn('font-mono', m.role === 'ADMIN' && 'font-bold')}>{m.role}</span>
                                </div>
                              ))}
                            </div>
                            <div>
                              <div className="font-bold uppercase text-[10px] tracking-wider text-neutral-500 mb-1">
                                Dossiers embarqués ({detail.cases.length})
                              </div>
                              {detail.cases.length === 0 && <div className="italic text-neutral-500">Aucun dossier pour l&apos;instant.</div>}
                              {detail.cases.slice(0, 8).map((c) => (
                                <div key={c.id} className="flex justify-between border-b border-neutral-100 py-1">
                                  <span>{c.taxpayer ?? '—'} <span className="text-neutral-500 font-mono">({c.reference})</span></span>
                                  <span className="text-neutral-600">{c.fiscal_year} · {c.status}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
