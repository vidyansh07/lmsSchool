'use client';

/**
 * A bento grid, sized for an operations screen.
 *
 * Aceternity's version is a marketing layout: a few large tiles with room to
 * breathe. This one keeps the idea — tiles of different weights on one grid,
 * so importance is visible before anything is read — at a density that fits a
 * dashboard. Twelve columns, tiles claiming a span each, and a single
 * breakpoint where everything becomes one column.
 *
 * Stagger is per-tile and capped: eight tiles at 45ms is a third of a second
 * for the grid to arrive, which reads as deliberate. Twenty tiles at 45ms
 * would be nearly a second of waiting for the last one, so the delay stops
 * climbing after the eighth.
 */

import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

import { Reveal } from './reveal';

const STAGGER_STEP = 0.045;
const STAGGER_CAP = 8;

export function BentoGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('grid grid-cols-1 gap-4 md:grid-cols-12', className)}>{children}</div>
  );
}

const SPANS = {
  3: 'md:col-span-3',
  4: 'md:col-span-4',
  6: 'md:col-span-6',
  8: 'md:col-span-8',
  9: 'md:col-span-9',
  12: 'md:col-span-12',
} as const;

export function BentoTile({
  children,
  span = 3,
  index = 0,
  className,
}: {
  children: ReactNode;
  span?: keyof typeof SPANS;
  /** Position in the grid, for the entrance stagger. */
  index?: number;
  className?: string;
}) {
  return (
    <Reveal
      delay={Math.min(index, STAGGER_CAP) * STAGGER_STEP}
      className={cn(SPANS[span], className)}
    >
      {children}
    </Reveal>
  );
}
