import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full',
  {
    variants: {
      variant: {
        ok: 'bg-emerald-100 text-emerald-800',
        warn: 'bg-amber-100 text-amber-800',
        err: 'bg-rose-100 text-rose-800',
        info: 'bg-sky-100 text-sky-800',
        neutral: 'bg-slate-100 text-slate-700',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge: React.FC<BadgeProps> = ({ className, variant, ...props }) => (
  <span className={cn(badgeVariants({ variant }), className)} {...props} />
);

export const severityToVariant = (sev: string): 'ok' | 'warn' | 'err' | 'info' | 'neutral' => {
  switch (sev) {
    case 'BLOCKING':
    case 'HIGH':
      return 'err';
    case 'MEDIUM':
      return 'warn';
    case 'LOW':
      return 'info';
    case 'INFO':
      return 'neutral';
    default:
      return 'neutral';
  }
};

export const severityLabel = (sev: string): string => {
  switch (sev) {
    case 'BLOCKING': return 'Bloquant';
    case 'HIGH': return 'Élevée';
    case 'MEDIUM': return 'Moyenne';
    case 'LOW': return 'Faible';
    case 'INFO': return 'Info';
    default: return sev;
  }
};
