'use client';
import { Building2 } from 'lucide-react';
import { ControlPageShell } from '@/components/control-page-shell';

export default function Page() {
  return (
    <ControlPageShell
      parentHref="/impots-societes"
      parentLabelKey="nav.corporateTax"
      titleKey="is.synthese.title"
      subtitleKey="is.synthese.subtitle"
      Icon={Building2}
    />
  );
}
