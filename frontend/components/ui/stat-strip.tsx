/**
 * The headline figures, as one divided card rather than N tiles.
 *
 * The reference product's overview strip: a single panel split by vertical
 * hairlines, each column a coloured dot, a small label and one figure. It
 * reads as "here are the seven numbers" in a way seven separate cards do
 * not -- seven cards read as seven things, and the gaps between them carry
 * no meaning.
 *
 * A sibling of `stat.tsx` rather than a mode of it. `StatCard` is one metric
 * with a trend, a delta and somewhere to click; this is a row of bare
 * figures. It reuses `StatCard`'s rules about what a figure is -- one text
 * node, `data-numeric` for tabular digits, and a non-number renders the
 * fallback label rather than a plausible-looking zero -- because those are
 * contracts, not styling.
 *
 * The dot colours come from the chart palette, and seven of them in a row is
 * the one place that many hues is fine: each dot is paired with its own text
 * label, so colour is never the identifier. The same seven as lines on one
 * plot would not be readable, which is what
 * `SERIES_COUNT_WARNING_THRESHOLD` is about.
 */

import Link from 'next/link';

import { paletteColor } from '@/components/ui/charts/chart-colors';
import { type FallbackLabel, NOT_AVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface StatStripItem {
  label: string;
  value: number | string | null | undefined;
  /** Which palette step paints the dot. Defaults to the column's position. */
  colorIndex?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  emptyLabel?: FallbackLabel;
  href?: string;
}

/**
 * Tailwind compiles the classes it can see in the source, so
 * `md:grid-cols-${n}` is not a class -- it silently renders one column. A
 * closed map, same reasoning as `GridItem`'s `SPANS`.
 */
const COLUMNS: Record<number, string> = {
  3: 'lg:grid-cols-3',
  4: 'lg:grid-cols-4',
  5: 'lg:grid-cols-5',
  6: 'lg:grid-cols-6',
  7: 'lg:grid-cols-7',
  8: 'lg:grid-cols-8',
};

function toFinite(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function Figure({ item }: { item: StatStripItem }) {
  const numeric = toFinite(item.value);
  if (numeric === null) {
    return <span className="text-ink-muted">{item.emptyLabel ?? NOT_AVAILABLE}</span>;
  }
  const formatted = numeric.toLocaleString(undefined, {
    minimumFractionDigits: item.decimals ?? 0,
    maximumFractionDigits: item.decimals ?? 0,
  });
  return <span data-numeric>{`${item.prefix ?? ''}${formatted}${item.suffix ?? ''}`}</span>;
}

function Column({ item, index }: { item: StatStripItem; index: number }) {
  const body = (
    <>
      <span className="flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="size-2 shrink-0 rounded-full"
          style={{ backgroundColor: paletteColor(item.colorIndex ?? index) }}
        />
        {/* Wraps rather than truncates. Seven columns at 1440px leaves
            about 150px each, which cut "Active students" to "ACTIVE
            STUDEN..." -- and a headline figure whose label is unreadable is
            not a headline figure. Two lines of 11px costs nothing here. */}
        <span className="text-2xs font-semibold uppercase leading-tight tracking-wider text-ink-faint">
          {item.label}
        </span>
      </span>
      <p data-testid="headline-figure" className="mt-1.5 text-3xl font-semibold leading-none">
        <Figure item={item} />
      </p>
    </>
  );

  if (!item.href) return <div className="min-w-0 px-3.5 py-3">{body}</div>;
  return (
    <Link
      href={item.href}
      className="min-w-0 px-3.5 py-3 transition-colors duration-150 hover:bg-sunken"
    >
      {body}
    </Link>
  );
}

export function StatStrip({
  items,
  className,
}: {
  items: readonly StatStripItem[];
  className?: string;
}) {
  if (items.length === 0) return null;

  return (
    <div
      className={cn(
        'grid grid-cols-1 overflow-hidden rounded-panel bg-surface ring-1 ring-line',
        // Hairlines between columns, and between rows once they wrap.
        'divide-y divide-line sm:grid-cols-2 sm:divide-x md:grid-cols-4',
        'lg:divide-y-0',
        COLUMNS[items.length] ?? 'lg:grid-cols-4',
        className,
      )}
    >
      {items.map((item, index) => (
        <Column key={item.label} item={item} index={index} />
      ))}
    </div>
  );
}
