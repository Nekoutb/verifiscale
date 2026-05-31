import * as React from 'react';
import { cn } from '@/lib/utils';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-9 w-full rounded-lg border border-[#A3A3A3] bg-white px-3 py-2 text-sm shadow-sm placeholder:text-[#737373] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 focus-visible:border-black disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = 'Input';
