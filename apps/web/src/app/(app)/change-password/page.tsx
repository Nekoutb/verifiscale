'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';

export default function ChangePasswordPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { user, setUser } = useApp();
  const [current, setCurrent] = useState('');
  const [pw1, setPw1] = useState('');
  const [pw2, setPw2] = useState('');

  const change = useMutation({
    mutationFn: () => api('/auth/change-password', {
      method: 'POST', body: { current_password: current, new_password: pw1 },
    }),
    onSuccess: () => {
      if (user) setUser({ ...user, must_change_password: false });
      qc.invalidateQueries({ queryKey: ['me'] });
      router.push('/dashboard');
    },
  });

  const valid = current.length > 0 && pw1.length >= 8 && pw1 === pw2 && pw1 !== current;

  return (
    <div className="max-w-md mx-auto mt-8">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="w-4 h-4" />
            {user?.must_change_password
              ? 'Changez votre mot de passe provisoire'
              : 'Changer mon mot de passe'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {user?.must_change_password && (
            <p className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              🔐 Votre mot de passe est provisoire — choisissez-en un nouveau pour
              accéder à votre espace.
            </p>
          )}
          <input type="password" className="w-full border border-neutral-300 rounded px-3 py-2 text-sm"
                 placeholder="Mot de passe actuel" value={current}
                 onChange={(e) => setCurrent(e.target.value)} />
          <input type="password" className="w-full border border-neutral-300 rounded px-3 py-2 text-sm"
                 placeholder="Nouveau mot de passe (≥8 caractères)" value={pw1}
                 onChange={(e) => setPw1(e.target.value)} />
          <input type="password" className="w-full border border-neutral-300 rounded px-3 py-2 text-sm"
                 placeholder="Confirmez le nouveau mot de passe" value={pw2}
                 onChange={(e) => setPw2(e.target.value)} />
          {pw2.length > 0 && pw1 !== pw2 && (
            <p className="text-xs text-rose-700">Les deux mots de passe ne correspondent pas.</p>
          )}
          <Button className="w-full" disabled={!valid || change.isPending} onClick={() => change.mutate()}>
            Enregistrer le nouveau mot de passe
          </Button>
          {change.isError && (
            <p className="text-xs text-rose-700">{(change.error as Error).message}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
