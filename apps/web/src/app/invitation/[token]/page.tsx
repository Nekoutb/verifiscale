'use client';

import { use, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

/** Public page — a teammate opens the invite link, sets a name + password. */
export default function InvitationPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');

  const info = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => api<{ email: string; organization: string; role: string }>(`/auth/invitations/${token}`),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: () => api('/auth/accept-invitation', {
      method: 'POST', body: { token, full_name: fullName, password },
    }),
    onSuccess: () => router.push('/login?invited=1'),
  });

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-50 p-4">
      <div className="bg-white border border-neutral-200 rounded-xl shadow-sm w-full max-w-md p-6 space-y-4">
        <div>
          <div className="font-display text-lg font-extrabold text-black">FiscAudit Pro — Invitation</div>
          {info.data && (
            <p className="text-sm text-neutral-600 mt-1">
              Vous rejoignez <b>{info.data.organization}</b> en tant que{' '}
              <b>{info.data.role}</b> avec l&apos;adresse <b className="font-mono">{info.data.email}</b>.
            </p>
          )}
          {info.isError && (
            <p className="text-sm text-rose-700 mt-1">
              {(info.error as Error).message || 'Invitation introuvable ou expirée.'}
            </p>
          )}
        </div>
        {info.data && (
          <>
            <input className="w-full border border-neutral-300 rounded px-3 py-2 text-sm"
                   placeholder="Votre nom complet" value={fullName}
                   onChange={(e) => setFullName(e.target.value)} />
            <input className="w-full border border-neutral-300 rounded px-3 py-2 text-sm" type="password"
                   placeholder="Choisissez un mot de passe (≥6)" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
            <button
              className="w-full bg-black text-white rounded py-2 text-sm font-semibold disabled:opacity-50"
              disabled={accept.isPending || !fullName || password.length < 6}
              onClick={() => accept.mutate()}
            >
              Créer mon compte et rejoindre l&apos;équipe
            </button>
            {accept.isError && (
              <p className="text-xs text-rose-700">{(accept.error as Error).message}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
