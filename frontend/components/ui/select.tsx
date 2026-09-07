import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * A styled native `<select>`.
 *
 * Not a custom listbox: on a data-entry screen this is filled in by someone
 * who already knows what they want and reaches for the keyboard, and a native
 * control gives them the operating system's own type-ahead, arrow-key
 * behaviour and (on touch) picker UI for free — a hand-rolled listbox would
 * have to re-implement all of that to match, for a worse result.
 *
 * This used to be defined inline in `components/ui/input.tsx`, unstyled
 * beyond a fixed size, and by the time this file was written around ninety
 * call sites across `app/` already imported it from there. Rather than a
 * second, competing `Select` living here, `input.tsx` now re-exports this
 * one — every existing call site keeps working untouched, and the size
 * variant is new, additive capability nothing existing opts into. `md`
 * reproduces the original's exact classes, so this is a pure extension, not
 * a behaviour change.
 *
 * The variant is named `uiSize`, not `size`: `<select>` already has a native
 * `size` attribute (the number of visible rows when it renders as a listbox,
 * as `search-picker.tsx` uses it), and CVA's `size` would silently shadow
 * that rather than compose with it.
 */
const selectVariants = cva(
  'w-full rounded-md border border-border bg-surface disabled:opacity-50 aria-[invalid=true]:border-destructive',
  {
    variants: {
      uiSize: {
        sm: 'h-8 px-2.5 text-xs',
        md: 'h-10 px-3 text-sm',
        lg: 'h-11 px-3.5 text-base',
      },
    },
    defaultVariants: { uiSize: 'md' },
  },
);

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement>,
    VariantProps<typeof selectVariants> {}

export function Select({ className, uiSize, ...props }: SelectProps) {
  return <select className={cn(selectVariants({ uiSize }), className)} {...props} />;
}

/** A native `<optgroup>`, typed and named to match the rest of this file. */
export function SelectGroup({ className, ...props }: React.OptgroupHTMLAttributes<HTMLOptGroupElement>) {
  return <optgroup className={cn('font-sans', className)} {...props} />;
}

export { selectVariants };
