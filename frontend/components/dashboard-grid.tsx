/**
 * The responsive shell every role dashboard drops its tiles into.
 *
 * A plain CSS grid rather than a masonry/auto-placement layout: a dashboard
 * that is read all day should lay out identically every time it renders, and
 * an algorithm that repacks tiles based on their content height would move
 * things under a viewer's cursor between one load and the next.
 */
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export function DashboardGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4', className)}>
      {children}
    </div>
  );
}

/** A tile that should span the full row — a wide chart or a long list among KPI tiles. */
export function DashboardGridFullRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn('sm:col-span-2 xl:col-span-4', className)}>{children}</div>;
}
