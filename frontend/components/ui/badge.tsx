import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * Two families of badge, and the difference is what the colour means.
 *
 * `success`/`warning`/`error`/`neutral` are *states*: the colour is the
 * message, so they keep their semantic tokens and a leading dot the eye can
 * find in a column before it reads a word.
 *
 * The accent set — `violet`, `indigo`, `pink`, `amber`, `cyan`, `teal`,
 * `blue`, `green`, `rose` — are *categories*: a department, a course family,
 * a batch kind. The colour tells two categories apart; it does not say either
 * is good or bad. They are the reference table's coloured pills, each one a
 * legible text colour on its own soft tint (the pairs are measured in
 * `tests/unit/theme-contrast.test.ts`).
 *
 * Borderless, unlike the old version: a pill with a border and a fill draws
 * the edge twice, and in a table of forty rows that is forty extra lines.
 */
const badgeVariants = cva(
  'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold',
  {
    variants: {
      variant: {
        neutral: 'bg-muted text-muted-foreground',
        success: 'bg-green-soft text-green',
        warning: 'bg-amber-soft text-amber',
        error: 'bg-rose-soft text-rose',
        violet: 'bg-violet-soft text-violet',
        indigo: 'bg-indigo-soft text-indigo',
        pink: 'bg-pink-soft text-pink',
        amber: 'bg-amber-soft text-amber',
        cyan: 'bg-cyan-soft text-cyan',
        teal: 'bg-teal-soft text-teal',
        blue: 'bg-blue-soft text-blue',
        green: 'bg-green-soft text-green',
        rose: 'bg-rose-soft text-rose',
      },
      /** A leading dot in the text colour — the reference's status pills. On
       *  by default for the state variants, off for categories. */
      dot: {
        true: "before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:content-['']",
        false: '',
      },
    },
    defaultVariants: { variant: 'neutral', dot: false },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

const STATE_VARIANTS = new Set(['success', 'warning', 'error', 'neutral']);

export function Badge({ className, variant, dot, ...props }: BadgeProps) {
  // A state pill gets its dot unless the caller says otherwise; a category
  // pill does not, because a dot beside "Engineering" implies a status that
  // is not there.
  const withDot = dot ?? STATE_VARIANTS.has(variant ?? 'neutral');
  return <span className={cn(badgeVariants({ variant, dot: withDot }), className)} {...props} />;
}

/** The category variants, for callers that assign a colour to each value of
 *  an enum — a department, a course family — and want the assignment stable. */
export const CATEGORY_VARIANTS = [
  'violet',
  'indigo',
  'pink',
  'amber',
  'cyan',
  'teal',
  'blue',
  'green',
  'rose',
] as const;

export type CategoryVariant = (typeof CATEGORY_VARIANTS)[number];

/** A stable colour for an arbitrary string, so "Python" is always the same
 *  pill on every screen without a table of every course ever created. */
export function categoryVariant(value: string): CategoryVariant {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  return CATEGORY_VARIANTS[hash % CATEGORY_VARIANTS.length] ?? 'blue';
}
