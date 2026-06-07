import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 px-2 py-0.5 text-xs rounded-full bg-transparent',
  {
    variants: {
      variant: {
        // Risk / severity — tricolour (Proposal A): FAIBLE=emerald, MOYEN=amber, ÉLEVÉ=rose
        ok: 'font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200',
        warn: 'font-semibold text-amber-700 bg-amber-50 border border-amber-200',
        err: 'font-bold text-rose-700 bg-rose-50 border border-rose-200',
        info: 'font-medium text-blue-700 bg-blue-50 border border-blue-200',
        neutral: 'font-normal text-neutral-600 border border-neutral-300',
        // Status variants — outlined neutral (stay monochrome)
        default: 'font-medium text-neutral-700 border border-neutral-300',
        secondary: 'font-normal text-neutral-500 border border-neutral-200',
        destructive: 'font-bold text-rose-700 bg-rose-50 border border-rose-200',
        outline: 'font-normal text-neutral-600 border border-neutral-300',
        // Risk-specific aliases
        faible: 'font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200',
        moyen: 'font-semibold text-amber-700 bg-amber-50 border border-amber-200',
        eleve: 'font-bold text-rose-700 bg-rose-50 border border-rose-200',
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
