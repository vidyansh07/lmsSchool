import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * The column counts the call sites actually use, as literal strings.
 * Tailwind v4 scans source text, so `sm:grid-cols-${columns}` emits no class
 * at all and the grid silently collapses to one column.
 *
 * A shape not in this map passes its own grid classes through `className`,
 * which `cn` puts last and therefore wins: `<DescriptionList className="lg:grid-cols-6">`
 * is a supported override, not a fight with the default.
 */
const COLUMN_CLASSES = {
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-3',
  4: 'grid-cols-2 sm:grid-cols-4',
  5: 'grid-cols-2 sm:grid-cols-5',
} as const;

/**
 * The label/value pair grid the detail screens hand-roll.
 *
 * Seven sites across `app/` write this shape by hand and disagree about the
 * column count, the gap and the size of the term — `app/verify/[code]`,
 * `app/admissions/new`, `app/admissions/[studentId]`, `app/admin/academics`,
 * `app/my-progress`, `app/my-attendance` and `app/admissions/import`. None was
 * migrated here: this file exists so the eighth is not hand-rolled as well,
 * and so a later pass has one place to move them to.
 *
 * A real `<dl>`/`<dt>`/`<dd>`, not three divs: assistive technology announces
 * the pairing, so "Batch" and "Evening — Feb 2026" arrive together rather than
 * as two unrelated strings.
 *
 * It renders exactly what the caller passes and never substitutes a dash for
 * an absent value. `lib/format.ts` owns that decision and its vocabulary is
 * fixed — `NOT_AVAILABLE | NOT_ASSIGNED | NOT_SUBMITTED | NO_DATA | UNKNOWN` —
 * so a caller passes `fallback(value)` or `formatDate(value)` and the screen
 * says "Not assigned" where it means it, instead of an em dash that could mean
 * anything.
 */
export function DescriptionList({
  children,
  className,
  columns = 2,
}: {
  children: ReactNode;
  className?: string;
  /** Columns from the `sm` breakpoint up. Two, unless the screen says otherwise. */
  columns?: keyof typeof COLUMN_CLASSES;
}) {
  return (
    <dl className={cn('grid gap-x-4 gap-y-2', COLUMN_CLASSES[columns], className)}>{children}</dl>
  );
}

export function DescriptionItem({
  term,
  children,
  className,
}: {
  term: string;
  /** Already through `lib/format.ts` — see the module docstring. */
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-xs text-muted-foreground">{term}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}
