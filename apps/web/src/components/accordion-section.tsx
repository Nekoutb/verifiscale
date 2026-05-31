'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

/**
 * Collapsible audit-subcategory section. Used by the tax control pages
 * (Impôts sur les sociétés, TVA, IRCM) where each component of the audit is
 * a self-contained drill-down.
 */
export function AccordionSection({
  title,
  subtitle,
  defaultOpen = false,
  badge,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'w-full flex items-center gap-3 px-5 py-3 text-left transition',
          open ? 'bg-slate-50' : 'hover:bg-slate-50',
        )}
      >
        {open ? <ChevronDown className="w-4 h-4 text-black" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-slate-900 text-sm">{title}</div>
          {subtitle && <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>}
        </div>
        {badge}
      </button>
      {open && (
        <CardContent className="border-t border-slate-100 bg-white">
          {children}
        </CardContent>
      )}
    </Card>
  );
}
