import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * A bare "nothing here" layout: icon, title, description, actions.
 *
 * `components/states.tsx` already has an `EmptyState` — this is not a second
 * copy of it. `EmptyState` is a fixed, opinionated shape wired for one job:
 * the end of a `useList`-driven screen, always with an `Inbox` icon. `Empty`
 * is the loose primitive underneath that kind of component, for the places
 * that job doesn't fit — an empty search inside a popover, an empty panel
 * inside a card, anywhere the icon, the copy or the layout needs to be the
 * caller's choice rather than a list view's default. `EmptyState` was left
 * exactly as it is; nothing here reaches into it.
 */
export function Empty({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-6 py-12 text-center',
        className,
      )}
      {...props}
    />
  );
}

export function EmptyIcon({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn('mb-1 text-muted-foreground [&>svg]:size-6', className)}
      {...props}
    />
  );
}

export function EmptyTitle({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('font-medium', className)} {...props} />;
}

export function EmptyDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('max-w-sm text-sm text-muted-foreground', className)} {...props} />;
}

export function EmptyActions({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mt-2 flex items-center gap-2', className)} {...props} />;
}
