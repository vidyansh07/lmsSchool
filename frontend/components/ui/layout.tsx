/**
 * The page skeleton: a header, sections, and one grid.
 *
 * These replace a bento grid, a second dashboard grid, and the page headers
 * that every screen was hand-rolling out of a flex row and two spans. Having
 * three of those meant three answers to "how wide is a tile" and no answer to
 * "why", so a dashboard's layout depended on which component its author had
 * seen most recently.
 *
 * The grid is twelve columns on `md` and one column below it — the same
 * contract the bento grid had, deliberately, so a tile that claimed four
 * columns still claims four. What it no longer does is animate each tile in
 * on a staggered delay: a dashboard that assembles itself over a third of a
 * second is a third of a second in which the numbers cannot be read.
 */

import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export function PageHeader({
  title,
  meta,
  children,
  className,
}: {
  title: ReactNode;
  /** The line under the title. Carries live context where there is any —
   *  "sorted by last active", "12 of 340 shown" — not a restatement of the
   *  title in longer words. */
  meta?: ReactNode;
  /** Actions, right-aligned on the title's own row. At most one of them
   *  should be a filled primary button. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap items-start justify-between gap-4', className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {meta ? <p className="mt-1 text-sm text-ink-muted">{meta}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

export function Section({
  title,
  meta,
  children,
  className,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('flex flex-col gap-3', className)}>
      {title ? (
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-base font-semibold">{title}</h2>
          {meta ? <span className="text-xs text-ink-muted">{meta}</span> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Grid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('grid grid-cols-1 gap-4 md:grid-cols-12', className)}>{children}</div>;
}

/**
 * How many of the twelve columns this item claims, at `md` and up.
 *
 * A closed set rather than an arbitrary number: the widths that divide twelve
 * cleanly are the ones that tile without leaving a gap, and allowing `5` is
 * how a row ends up one column short with nothing to explain it.
 */
const SPANS = {
  3: 'md:col-span-3',
  4: 'md:col-span-4',
  6: 'md:col-span-6',
  8: 'md:col-span-8',
  9: 'md:col-span-9',
  12: 'md:col-span-12',
} as const;

export function GridItem({
  children,
  span = 3,
  className,
}: {
  children: ReactNode;
  span?: keyof typeof SPANS;
  className?: string;
}) {
  return <div className={cn(SPANS[span], className)}>{children}</div>;
}
