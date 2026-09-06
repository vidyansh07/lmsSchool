/**
 * A label/value pair for a dense cluster of figures inside one card — "5 of 8
 * submitted", "82%", "Not available".
 *
 * Deliberately lighter than `KpiTile`: that component is a dashboard's own
 * building block (a card in its own right, with a trend arrow and a
 * sparkline) and reads as too heavy repeated eight times inside a single
 * section of a detail page. `Stat` is the same "always pre-formatted, never
 * a raw number" discipline in a shape meant to sit five-to-a-row inside a
 * card that already has its own heading.
 *
 * The caller always passes a formatted string — `formatNumber`, `formatPercent`
 * or `fallback` already applied — so the null-handling rule is enforced at the
 * one place every value on this screen passes through, not re-implemented
 * per section.
 */
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  /** Only ever a second signal alongside the text itself — see `StatGrid`'s caller for the icon/text that goes with it when tone matters. */
  tone?: 'default' | 'warning' | 'error';
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          'text-lg font-semibold tabular-nums',
          tone === 'warning' && 'text-warning',
          tone === 'error' && 'text-destructive',
        )}
      >
        {value}
      </p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function StatGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5', className)}>
      {children}
    </div>
  );
}
