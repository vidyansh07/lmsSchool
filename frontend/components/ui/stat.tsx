/**
 * One figure, what it means, and where it is heading.
 *
 * The unit every dashboard is built from, and deliberately the *only* one —
 * this replaces four separate implementations that had grown up side by side
 * (`ui/motion/stat-card.tsx`, `kpi-tile.tsx`, `dashboard-grid.tsx`'s tile and
 * `manage/stat.tsx`'s compact variant), each with its own idea of how a label
 * and a number should sit together.
 *
 * What it is not, any more:
 *
 * - **No per-metric accent.** The old version tinted the whole card from a
 *   palette of six hues, so a dashboard read as six colours competing before
 *   a single number had been read. Colour here means *state* — a delta is
 *   better or worse, a status is good or bad — and nothing else. A tile is a
 *   white card with a hairline.
 * - **No counting animation.** A number that animates on every mount costs a
 *   render, starts at a value that is false, and makes a screen reader hear
 *   whichever frame it caught. The figure is simply the figure.
 * - **No cursor spotlight.** A gradient chasing the pointer told the reader
 *   which card the mouse was over, which the mouse already told them.
 *
 * What stays is the part that carried information: the delta says whether the
 * movement is good in words *and* colour *and* an arrow, because "green" is
 * not a value a colourblind reader can read; and the sparkline says whether
 * this is a trend or a blip.
 *
 * Every field but `label` and `value` is optional, and a tile with only those
 * two is the common case.
 */

import type { LucideIcon } from 'lucide-react';
import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react';
import Link from 'next/link';

import { type FallbackLabel, NOT_AVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';

import { Sparkline } from './charts/sparkline';

export interface StatCardProps {
  label: string;
  value: number | string | null | undefined;
  /** What window this figure covers — "This week", "All-time", "As of today".
   *  Rendered right beside the label, muted, so a reader never has to guess
   *  whether a number is a snapshot or a running total. Omitted entirely
   *  when the label already says so on its own. */
  period?: string;
  /** Rendered under the number. One short line, not a paragraph. */
  hint?: string;
  suffix?: string;
  prefix?: string;
  decimals?: number;
  icon?: LucideIcon;
  /** Percentage change against the previous period. */
  delta?: number | null;
  /** For a dropout rate, a rise is bad. Defaults to rise-is-good. */
  deltaIntent?: 'up-is-good' | 'down-is-good';
  trend?: readonly (number | null | undefined)[];
  href?: string;
  emptyLabel?: FallbackLabel;
  className?: string;
}

function toFinite(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * The figure itself, as a single text node.
 *
 * One node rather than `{prefix}{formatted}{suffix}` as three siblings: three
 * siblings mean no `getByText('88%')` — in a test, or in a browser's own
 * find-on-page — matches the thing a person can plainly see.
 */
function Figure({
  value,
  prefix = '',
  suffix = '',
  decimals = 0,
  emptyLabel,
}: Pick<StatCardProps, 'value' | 'prefix' | 'suffix' | 'decimals'> & {
  emptyLabel: FallbackLabel;
}) {
  const numeric = toFinite(value);

  if (numeric === null) {
    // The label, not the value. This component's contract is "this is a
    // figure", so a value that is not one is missing data however presentable
    // its string form happens to be — rendering `"pending"` in the position
    // of a headline metric states something false in the largest type on the
    // page.
    return <span className="text-muted-foreground">{emptyLabel}</span>;
  }

  const formatted = numeric.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  // `data-numeric` rather than a `tabular-nums` class: `globals.css`'s base
  // layer already gives that attribute tabular figures, which is what keeps a
  // column of these from shifting sideways as the values change.
  return <span data-numeric>{`${prefix}${formatted}${suffix}`}</span>;
}

export function StatCard({
  label,
  value,
  period,
  hint,
  suffix,
  prefix,
  decimals = 0,
  icon: Icon,
  delta,
  deltaIntent = 'up-is-good',
  trend,
  href,
  emptyLabel = NOT_AVAILABLE,
  className,
}: StatCardProps) {
  const hasDelta = Number.isFinite(delta as number) && delta !== 0;
  const rising = (delta ?? 0) > 0;
  const good = deltaIntent === 'up-is-good' ? rising : !rising;
  const DeltaIcon = rising ? ArrowUpRight : ArrowDownRight;

  const body = (
    <div
      className={cn(
        'flex h-full flex-col justify-between gap-3 rounded-card border border-border bg-surface p-4',
        href && 'cursor-pointer',
        className,
      )}
    >
      {/* `label` stays the row's first direct child at the depth it always
          was, so anything that locates a tile by walking up from the label
          text does not have to know a `period` was ever added. The icon's own
          `ml-auto` — not `justify-between` on the row — is what keeps it
          pinned to the far end with `period` free to sit beside the label. */}
      <div className="flex items-start gap-2">
        <span className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {period ? (
          <span className="text-2xs font-normal text-muted-foreground opacity-75">
            · {period}
          </span>
        ) : null}
        {Icon ? (
          <Icon className="ml-auto size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : null}
      </div>

      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-3xl font-semibold leading-none">
            <Figure
              value={value}
              prefix={prefix}
              suffix={suffix}
              decimals={decimals}
              emptyLabel={emptyLabel}
            />
          </p>

          {hasDelta ? (
            <p
              className={cn(
                'mt-1.5 flex items-center gap-1 text-xs font-medium',
                good ? 'text-success' : 'text-destructive',
              )}
            >
              <DeltaIcon className="size-3.5" aria-hidden="true" />
              {/* The sign is in the text, so the meaning survives without the
                  colour — and the word says which way is good. */}
              {rising ? '+' : ''}
              {(delta as number).toFixed(1)}%
              <span className="text-muted-foreground">
                {good ? 'better' : 'worse'} than last period
              </span>
            </p>
          ) : hint ? (
            <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>
          ) : null}
        </div>

        {trend && trend.length > 1 ? (
          <div className="w-24 shrink-0">
            <Sparkline
              values={trend}
              height={30}
              intent={deltaIntent === 'up-is-good' ? 'positive-up' : 'positive-down'}
              label={`${label} trend`}
            />
          </div>
        ) : null}
      </div>

      {href ? (
        <span className="flex items-center gap-1 text-xs font-medium text-primary">
          Open
          <ArrowRight className="size-3" aria-hidden="true" />
        </span>
      ) : null}
    </div>
  );

  if (!href) return body;
  return (
    <Link href={href} className="block h-full rounded-card focus-visible:outline-none">
      {body}
    </Link>
  );
}
