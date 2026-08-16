'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, setToken } from '@/lib/api';
import styles from './login.module.css';

type LoginResponse = { access_token: string; token_type: string };

/** Marque VF — recréation vectorielle du logo fourni (V blanc, F rouge). */
function VfMark({ size = 64 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" aria-hidden="true">
      <polygon points="6,18 26,18 46,74 36,92" fill="#FFFFFF" />
      <polygon points="36,92 46,74 66,18 82,18 50,92" fill="#FFFFFF" opacity="0.92" />
      <polygon points="52,18 96,18 90,30 48,30" fill="#D7222B" />
      <polygon points="46,40 84,40 78,52 42,52" fill="#D7222B" />
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api<LoginResponse>('/auth/login', {
        method: 'POST',
        body: { email: email.trim(), password },
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
      setError((err as Error).message || 'Connexion impossible — vérifiez vos identifiants.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.scene}>
      <div aria-hidden className={`${styles.glow} ${styles.glowRed}`} />
      <div aria-hidden className={`${styles.glow} ${styles.glowWhite}`} />

      <main className={`relative w-full max-w-sm ${styles.rise}`}>
        {/* Marque */}
        <div className="flex flex-col items-center mb-10 select-none">
          <VfMark size={72} />
          <div className="mt-5 text-[26px] tracking-[0.18em] font-medium lowercase">
            <span className="text-neutral-300">veri</span>
            <span className="text-[#D7222B] font-bold">fisc</span>
            <span className="text-neutral-300">ale</span>
          </div>
          <div className="mt-1.5 text-[11px] tracking-[0.32em] uppercase text-neutral-500">
            Plateforme d&apos;audit fiscal
          </div>
        </div>

        {/* Carte verre */}
        <form onSubmit={submit} className={`${styles.glass} rounded-2xl p-7 space-y-4`}>
          <label className="block">
            <span className="text-[11px] uppercase tracking-[0.14em] text-neutral-400">Adresse email</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="vous@cabinet.cm"
              className={`${styles.field} mt-1.5`}
            />
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-[0.14em] text-neutral-400">Mot de passe</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••"
              className={`${styles.field} mt-1.5`}
            />
          </label>

          {error && (
            <p role="alert" className="text-[13px] leading-snug text-[#ff8f95] bg-[#D7222B]/10 border border-[#D7222B]/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-[#D7222B] hover:bg-[#b91c24] active:bg-[#a01920] transition-colors
                       text-white font-semibold text-[15px] py-3 disabled:opacity-60 disabled:cursor-wait
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-[#D7222B] focus-visible:ring-offset-2 focus-visible:ring-offset-black"
          >
            {busy ? 'Connexion…' : 'Se connecter'}
          </button>
        </form>

        <p className="mt-8 text-center text-[11px] text-neutral-600">
          © {new Date().getFullYear()} CM-EA · VerifiScale
        </p>
      </main>
    </div>
  );
}
