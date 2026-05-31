import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 px-2 py-0.5 text-xs rounded-full bg-transparent',
  {
    variants: {
      variant: {
        // FAIBLE — weight 400 + pip ●○○ + 1px ink-300 outline
        ok: 'font-normal text-[#404040] border border-[#A3A3A3]',
        // MOYEN — weight 500 + pip ●●○ + 1px ink-300 outline
        warn: 'font-medium text-[#404040] border border-[#A3A3A3]',
        // ÉLEVÉ — weight 700 + pip ●●● + 1px pure-black outline + under-rule
        err: 'font-bold text-black border border-black underline decoration-2 underline-offset-4',
        info: 'font-normal text-[#404040] border border-[#A3A3A3]',
        neutral: 'font-normal text-[#404040] border border-[#A3A3A3]',
        // Status variants — outlined neutral
        default: 'font-medium text-[#404040] border border-[#A3A3A3]',
        secondary: 'font-normal text-[#737373] border border-[#D4D4D4]',
        destructive: 'font-bold text-black border border-black',
        outline: 'font-normal text-[#404040] border border-[#A3A3A3]',
        // Risk-specific typographic variants
        faible: 'font-normal text-[#404040] border border-[#A3A3A3]',
        moyen: 'font-medium text-[#404040] border border-[#A3A3A3]',
        eleve: 'font-bold text-black border border-black underline decoration-2 underline-offset-4',
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
