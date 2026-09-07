import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';

import { cn } from '@/lib/utils';

const spinnerVariants = cva('animate-spin text-muted-foreground', {
  variants: {
    size: {
      sm: 'size-3.5',
      md: 'size-4',
      lg: 'size-6',
    },
  },
  defaultVariants: { size: 'md' },
});

export interface SpinnerProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof spinnerVariants> {
  /** Announced to assistive technology; not shown. Say what is loading, not just "Loading". */
  label?: string;
}

/**
 * An inline loading indicator for a control or a section too small to
 * justify `states.tsx`'s `LoadingState` skeleton rows — a button mid-submit,
 * a panel refreshing in place.
 *
 * Spins with Tailwind's built-in `animate-spin`, at its default one-second
 * rotation, rather than the bespoke `spin` keyframe `globals.css` also
 * defines: `Skeleton` already reaches for Tailwind's own `animate-pulse`
 * instead of the sibling `shimmer` keyframe for the same kind of indicator,
 * and matching that precedent means one rule — "continuous loading loops use
 * Tailwind's defaults; one-shot enter/exit motion uses this app's tokens" —
 * instead of a case-by-case choice.
 */
export function Spinner({ className, size, label = 'Loading…', ...props }: SpinnerProps) {
  return (
    <span role="status" className={cn('inline-flex', className)} {...props}>
      <Loader2 className={cn(spinnerVariants({ size }))} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}
