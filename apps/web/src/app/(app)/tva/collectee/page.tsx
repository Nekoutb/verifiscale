'use client';
import { Receipt } from 'lucide-react';
import { ControlPageShell } from '@/components/control-page-shell';

export default function Page() {
  return (
    <ControlPageShell
      parentHref="/tva"
      parentLabelKey="nav.vat"
      titleKey="vat.collectee.title"
      subtitleKey="vat.collectee.subtitle"
      Icon={Receipt}
    />
  );
}
