'use client';

/** Onboarding — shown on the dashboard while the organisation has no dossier.
 *  3 steps: créer le premier dossier → charger les données → inviter l'équipe. */

import { useState } from 'react';
import Link from 'next/link';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Circle, Copy, Rocket, UserPlus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useApp } from '@/lib/store';

export function OnboardingWizard({ caseCount, onNewCase }: {
  caseCount: number; onNewCase: () => void;
}) {
  const user = useApp((s) => s.user);
  const currentCase = useApp((s) => s.currentCase);
  const [inviteEmail, setInviteEmail] = useState('');
  const [lastLink, setLastLink] = useState<string | null>(null);

  const { data: datasets = [] } = useQuery({
    queryKey: ['datasets', currentCase?.id],
    queryFn: () => api<unknown[]>(`/datasets/audit-case/${currentCase!.id}`),
    enabled: !!currentCase,
  });

  const invite = useMutation({
    mutationFn: () => api<{ invite_path: string }>('/orgs/invitations', {
      method: 'POST', body: { email: inviteEmail },
    }),
    onSuccess: (r) => {
      setLastLink(`${window.location.origin}${r.invite_path}`);
      setInviteEmail('');
    },
  });

  const steps = [
    { done: caseCount > 0, label: '1. Créez votre premier dossier de vérification',
      hint: 'Contribuable (NIU, raison sociale), nature du contrôle, exercices.' },
    { done: datasets.length > 0, label: '2. Chargez les données comptables',
      hint: 'Balance, grand-livre, registre des immobilisations… puis confirmez le mapping.' },
    { done: false, label: '3. Invitez votre équipe',
      hint: 'Chaque membre reçoit un lien sécurisé pour créer son compte dans votre espace.' },
  ];
  const allCore = steps[0].done && steps[1].done;
  if (allCore) return null;

  return (
    <Card className="border-black/40 shadow-md">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Rocket className="w-4 h-4" />
          Bienvenue{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''} — démarrez votre espace
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {steps.map((s, i) => (
          <div key={i} className="flex items-start gap-2">
            {s.done ? <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                    : <Circle className="w-4 h-4 text-neutral-400 mt-0.5" />}
            <div className="flex-1">
              <div className="text-sm font-semibold text-black">{s.label}</div>
              <div className="text-[11px] text-neutral-500">{s.hint}</div>
              {i === 0 && !s.done && (
                <Button size="sm" className="mt-1.5" onClick={onNewCase}>Créer le dossier</Button>
              )}
              {i === 1 && !s.done && caseCount > 0 && (
                <Link href="/audit-data" className="inline-block mt-1.5 text-xs font-semibold underline text-black">
                  Aller à « Données » →
                </Link>
              )}
              {i === 2 && user?.role === 'ADMIN' && (
                <div className="mt-1.5 flex items-center gap-2">
                  <UserPlus className="w-3.5 h-3.5 text-neutral-500" />
                  <input className="border border-neutral-300 rounded px-2 py-1 text-xs w-56"
                         placeholder="email du membre" value={inviteEmail}
                         onChange={(e) => setInviteEmail(e.target.value)} />
                  <Button size="sm" variant="outline" disabled={invite.isPending || !inviteEmail.includes('@')}
                          onClick={() => invite.mutate()}>
                    Générer le lien
                  </Button>
                </div>
              )}
              {i === 2 && lastLink && (
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(lastLink)}
                  className="mt-1.5 flex items-center gap-1.5 text-[11px] font-mono bg-neutral-100 border border-neutral-300 rounded px-2 py-1 hover:border-black"
                  title="Copier le lien d'invitation"
                >
                  <Copy className="w-3 h-3" /> {lastLink}
                </button>
              )}
              {i === 2 && invite.isError && (
                <div className="text-[11px] text-rose-700 mt-1">{(invite.error as Error).message}</div>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
