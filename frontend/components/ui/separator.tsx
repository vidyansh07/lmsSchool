import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const separatorVariants = cva('shrink-0 bg-border', {
  variants: {
    orientation: {
      horizontal: 'h-px w-full',
      vertical: 'h-full w-px',
    },
  },
  defaultVariants: { orientation: 'horizontal' },
});

export interface SeparatorProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof separatorVariants> {
  /**
   * True (the default) for a purely visual rule between unrelated content —
   * it is hidden from assistive technology, the same way a sheet of paper
   * does not narrate its own margin. Set false only when the separator marks
   * a real semantic boundary, e.g. between groups of menu items, and give it
   * `role="separator"` so a screen reader announces the structure.
   */
  decorative?: boolean;
}

/** A thin rule dividing two regions. Renders as a `<div>`, not `<hr>` — an
 *  `<hr>` carries its own default margin and border-style that would have to
 *  be undone on every use, and this app already draws every rule as a solid
 *  `border-border` line rather than the browser's inset default. */
export function Separator({ className, orientation, decorative = true, ...props }: SeparatorProps) {
  return (
    <div
      role={decorative ? undefined : 'separator'}
      aria-orientation={decorative ? undefined : (orientation ?? 'horizontal')}
      aria-hidden={decorative ? true : undefined}
      className={cn(separatorVariants({ orientation }), className)}
      {...props}
    />
  );
}
