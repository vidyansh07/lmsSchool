import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * A badge says what state something is in.
 *
 * Five variants, each a semantic state, and a leading dot the eye can find in
 * a column before it reads a word -- the reference's status pills, where
 * `dot + word` is what makes the state readable without relying on colour.
 *
 * What was here before: nine further variants (`violet`, `indigo`, `pink`,
 * `cyan`, `teal`, `blue`, `green`, `rose`, `amber`) for *categories* -- a
 * department, a course family -- assigned by hashing the string. A hash means
 * "Python" is teal for no reason, and a colour that means something different
 * on every screen is decoration wearing a semantic costume. The category name
 * was always the information; it now renders in a neutral pill.
 *
 * Borderless: a pill with a border and a fill draws the edge twice, and in a
 * table of forty rows that is forty extra lines.
 */
const badgeVariants = cva(
  'inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2 py-0.5 text-2xs font-semibold',
  {
    variants: {
      variant: {
        neutral: 'bg-sunken text-ink-muted',
        info: 'bg-info-wash text-info',
        success: 'bg-success-wash text-success',
        warning: 'bg-warning-wash text-warning',
        error: 'bg-danger-wash text-danger',
      },
      /** A leading dot in the text colour. On by default, because the whole
       *  point of a status pill is being findable down a column. */
      dot: {
        true: "before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:content-['']",
        false: '',
      },
    },
    defaultVariants: { variant: 'neutral', dot: true },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, dot, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, dot }), className)} {...props} />;
}
