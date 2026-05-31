import { Card, CardContent } from '@/components/ui/card';
import { Construction } from 'lucide-react';

interface Props {
  title: string;
  description: string;
  upcomingControls: { code: string; label: string; ref: string }[];
}

export function PlaceholderModule({ title, description, upcomingControls }: Props) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold">{title}</h1>
        <p className="text-sm text-slate-500 mt-1">{description}</p>
      </div>

      <Card>
        <CardContent>
          <div className="flex items-start gap-4 mb-5">
            <div className="w-10 h-10 rounded-lg bg-neutral-100 text-black border border-neutral-300 flex items-center justify-center flex-shrink-0">
              <Construction className="w-5 h-5" />
            </div>
            <div>
              <div className="font-semibold text-slate-900">Module en cours d&apos;implémentation</div>
              <div className="text-sm text-slate-600 mt-1">
                Les contrôles de ce module sont définis dans le référentiel et seront branchés sur le moteur
                au fil des sprints. Vous pouvez consulter ci-dessous la liste prévue.
              </div>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-5">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Contrôles prévus
            </h3>
            <div className="space-y-2">
              {upcomingControls.map((c) => (
                <div key={c.code} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-50">
                  <code className="font-mono text-[11px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                    {c.code}
                  </code>
                  <div className="flex-1 text-sm text-slate-800">{c.label}</div>
                  <div className="text-[11px] text-slate-500 font-mono">{c.ref}</div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
