import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * A banner, tinted by what it is telling you.
 *
 * Each variant is its semantic wash with a matching hairline, rather than the
 * state colour at 10% over the page -- a translucent fill picks up whatever
 * is behind it, so the same alert read differently on a card than on the
 * page. The washes are opaque and measured: `theme-contrast.test.ts` checks
 * ink on every one of them.
 */
const alertVariants = cva('rounded-control border px-3.5 py-3 text-sm text-ink', {
  variants: {
    variant: {
      info: 'border-line bg-info-wash',
      success: 'border-success/30 bg-success-wash',
      warning: 'border-warning/30 bg-warning-wash',
      error: 'border-danger/30 bg-danger-wash',
    },
  },
  defaultVariants: { variant: 'info' },
});

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

export function Alert({ className, variant, ...props }: AlertProps) {
  return (
    // `role="alert"` makes screen readers announce the message when it appears.
    <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
  );
}

export function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('font-medium', className)} {...props} />;
}
