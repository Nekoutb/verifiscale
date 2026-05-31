import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        // Primary — pure black bg + white text + 1px black border + hover ink-800
        default: 'bg-black text-white border border-black hover:bg-[#171717]',
        // Gold (legacy) — re-skinned to inverse black (kept for API compat)
        gold: 'bg-black text-white border border-black hover:bg-[#171717]',
        // Outline — transparent + black text + 1px ink-300 + hover border black
        outline: 'border border-[#A3A3A3] bg-transparent text-black hover:border-black',
        // Ghost — transparent + ink-700 text + hover ink-100 bg
        ghost: 'text-[#404040] hover:bg-[#E5E5E5]',
        // Destructive — typographic emphasis, no colour
        destructive: 'bg-black text-white border border-black font-bold hover:bg-[#171717]',
        link: 'text-black underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-11 px-6 text-base',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = 'Button';
