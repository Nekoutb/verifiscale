'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { ShieldCheck, ScaleIcon, FileCheck2, CalendarCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api, setToken } from '@/lib/api';
import type { User } from '@/lib/types';
import { useT } from '@/lib/i18n';

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

const SAMPLE_ACCOUNTS = [
  { email: 'b.etoundi@dgi.cm',    name: 'Etoundi Bertrand',   role: 'Auditeur principal — DGE' },
  { email: 's.ngono@dgi.cm',      name: 'Ngono Sylvie',       role: 'Superviseur — DGE' },
  { email: 'j.mbarga@dgi.cm',     name: 'Mbarga Joseph',      role: 'Auditeur — CIME Yaoundé' },
  { email: 'admin@dgi.cm',        name: 'Admin DGI',          role: 'Administrateur système' },
];

export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const [email, setEmail] = useState('b.etoundi@dgi.cm');
  const [password, setPassword] = useState('Password123!');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [organization, setOrganization] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api<LoginResponse>('/auth/login', {
        method: 'POST',
        body: {
          email,
          password,
          phone_number: phoneNumber.trim() || undefined,
          organization: organization.trim() || undefined,
        },
      });
      setToken(res.access_token);
      try {
        const me = await api<{ is_superadmin?: boolean; must_change_password?: boolean }>('/auth/me');
        if (me?.must_change_password) router.push('/change-password');
        else router.push(me?.is_superadmin ? '/admin' : '/dossiers');
      } catch {
        router.push('/dossiers');
      }
    } catch (err) {
      setError((err as Error).message || t('login.errorFallback'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="min-h-screen relative overflow-hidden"
      style={{
        background:
          'radial-gradient(1200px 600px at 80% -100px, rgba(255,255,255,0.04), transparent),' +
          'radial-gradient(800px 600px at 10% 110%, rgba(255,255,255,0.06), transparent),' +
          'linear-gradient(135deg, #000000 0%, #0A0A0A 60%, #171717 100%)',
      }}
    >
      <div className="relative max-w-7xl mx-auto px-6 py-10">
        <header className="flex items-center justify-between mb-16">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-black flex items-center justify-center text-white font-bold text-lg shadow-lg">
              FA
            </div>
            <div>
              <div className="text-white font-display font-bold text-lg leading-tight">FiscAudit Pro</div>
              <div className="text-slate-300 text-xs tracking-wider">
                DIRECTION GÉNÉRALE DES IMPÔTS
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-400 uppercase tracking-widest">{t('login.country')}</div>
            <div className="text-xs text-slate-500">{t('login.countryMotto')}</div>
          </div>
        </header>

        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="text-white">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/10 text-xs font-medium mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-white" />
              {t('login.heroBadge')}
            </div>
            <h1 className="font-display text-5xl lg:text-6xl font-extrabold leading-[1.05] mb-6">
              {t('login.heroTitle1')}<br />
              <span className="text-white">{t('login.heroTitle2')}</span> {t('login.heroTitleAnd')} <span className="text-white">{t('login.heroTitle3')}</span>
            </h1>
            <p className="text-slate-300 text-lg leading-relaxed mb-8 max-w-xl">
              {t('login.heroBlurb')}
            </p>
            <div className="grid grid-cols-2 gap-6 max-w-lg">
              {[
                { Icon: ScaleIcon,    label: t('login.feature1') },
                { Icon: ShieldCheck,  label: t('login.feature2') },
                { Icon: CalendarCheck,label: t('login.feature3') },
                { Icon: FileCheck2,   label: t('login.feature4') },
              ].map(({ Icon, label }, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-white/10 flex items-center justify-center text-white flex-shrink-0">
                    <Icon className="w-5 h-5" />
                  </div>
                  <div className="text-sm text-slate-200 leading-snug pt-1">{label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
            <div className="p-8">
              <h2 className="font-display text-2xl font-bold text-black mb-1">{t('login.cardTitle')}</h2>
              <p className="text-sm text-slate-500 mb-6">{t('login.cardSubtitle')}</p>

              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label htmlFor="email">{t('login.email')}</Label>
                  <Input
                    id="email" type="email" required
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="prenom.nom@dgi.cm"
                  />
                </div>
                <div>
                  <Label htmlFor="password">{t('login.password')}</Label>
                  <Input
                    id="password" type="password" required
                    value={password} onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="phone">{t('login.phone')}</Label>
                    <Input
                      id="phone" type="tel"
                      value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)}
                      placeholder="+237 6XX XX XX XX"
                    />
                  </div>
                  <div>
                    <Label htmlFor="organization">{t('login.organization')}</Label>
                    <Input
                      id="organization" type="text"
                      value={organization} onChange={(e) => setOrganization(e.target.value)}
                      placeholder="DGI / Cabinet / Société"
                    />
                  </div>
                </div>
                {error && (
                  <div className="text-sm text-black font-bold bg-white border-2 border-black rounded-lg px-3 py-2">
                    {error}
                  </div>
                )}
                <Button type="submit" disabled={busy} className="w-full" size="lg">
                  {busy ? t('login.submitting') : t('login.submit')}
                </Button>
              </form>

              <div className="mt-6 pt-5 border-t border-slate-200">
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  {t('login.demoAccounts')}
                </div>
                <div className="space-y-1.5">
                  {SAMPLE_ACCOUNTS.map((a) => (
                    <button
                      key={a.email}
                      type="button"
                      onClick={() => { setEmail(a.email); setPassword('Password123!'); }}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-50 text-xs flex items-center justify-between"
                    >
                      <div>
                        <div className="font-medium text-slate-800">{a.name}</div>
                        <div className="text-slate-500">{a.role}</div>
                      </div>
                      <code className="text-[10px] text-slate-400">{a.email}</code>
                    </button>
                  ))}
                </div>
                <div className="mt-3 text-[11px] text-slate-400">
                  Mot de passe commun : <code className="font-mono">Password123!</code>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
