'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import type { AuditCase } from '@/lib/types';

export default function BalancePage() {
  const { data: cases = [] } = useQuery({
    queryKey: ['audit-cases'],
    queryFn: () => api<AuditCase[]>('/audit-cases'),
  });
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold">Balance & Rollforward</h1>
        <p className="text-sm text-slate-500 mt-1">
          Sélectionnez un dossier pour importer la balance et le grand livre, puis lancer les contrôles SYSCOHADA.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Choisir un dossier d&apos;audit</CardTitle>
        </CardHeader>
        <CardContent>
          {cases.length === 0 ? (
            <div className="text-sm text-slate-500">Aucun dossier disponible.</div>
          ) : (
            <div className="grid md:grid-cols-2 gap-3">
              {cases.map((c) => (
                <Link key={c.id} href={`/dossiers/${c.id}`}>
                  <div className="border border-slate-200 rounded-lg p-4 hover:border-navy hover:bg-slate-50 cursor-pointer transition">
                    <div className="font-mono text-xs text-slate-500">{c.reference}</div>
                    <div className="font-semibold text-slate-900 mt-1">{c.taxpayer.raison_sociale}</div>
                    <div className="text-xs text-slate-500 mt-0.5">NIU {c.taxpayer.niu} · Exercice {c.fiscal_year}</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
