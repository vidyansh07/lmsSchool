'use client';

/**
 * The unit a dashboard is built from: one figure, what it means, where it is
 * heading.
 *
 * This replaces the plain label-and-number tile the overviews used. The
 * additions each answer a question the old one left to the reader:
 *
 * - the counter draws the eye to what moved;
 * - the delta says whether that movement is good, in words as well as colour,
 *   because "green" is not a value a colourblind reader can read;
 *   the arrow and the sign carry it too;
 * - the sparkline says whether this is a trend or a blip;
 * - the spotlight says which card the cursor is on.
 *
 * Every one of them is optional. A card with only `label` and `value` renders
 * as a clean tile, which is what most of them are — the point is that the
 * screens which *have* a trend can show it without inventing a new component.
 */

import type { LucideIcon } from 'lucide-react';
import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react';
import Link from 'next/link';

import { fallback, type FallbackLabel, NOT_AVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';

import { NumberTicker } from './number-ticker';
import { Sparkline } from './sparkline';
import { SpotlightCard } from './spotlight-card';

export interface StatCardProps {
  label: string;
  value: number | string | null | undefined;
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

export function StatCard({
  label,
  value,
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
    <SpotlightCard
      className={cn(
        'press flex h-full flex-col justify-between gap-3 rounded-[var(--radius-card)] border border-border bg-surface p-4',
        'transition-shadow duration-[var(--duration-quick)] hover:shadow-[0_1px_2px_rgba(16,24,40,0.06),0_8px_24px_-12px_rgba(16,24,40,0.18)]',
        href && 'cursor-pointer',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {Icon ? (
          <Icon
            className="size-4 shrink-0 text-muted-foreground transition-colors duration-[var(--duration-quick)] group-hover:text-primary"
            aria-hidden="true"
          />
        ) : null}
      </div>

      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-3xl font-semibold leading-none">
            {typeof value === 'number' || (typeof value === 'string' && value.trim() !== '') ? (
              <NumberTicker
                value={value}
                prefix={prefix}
                suffix={suffix}
                decimals={decimals}
                label={emptyLabel}
              />
            ) : (
              <span className="text-muted-foreground">{fallback(value, emptyLabel)}</span>
            )}
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
        <span className="flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity duration-[var(--duration-quick)] group-hover:opacity-100">
          Open
          <ArrowRight className="size-3" aria-hidden="true" />
        </span>
      ) : null}
    </SpotlightCard>
  );

  if (!href) return body;
  return (
    <Link href={href} className="block h-full rounded-[var(--radius-card)] focus-visible:outline-none">
      {body}
    </Link>
  );
}
