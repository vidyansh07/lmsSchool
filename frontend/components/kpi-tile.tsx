/**
 * The building block five role dashboards are made of: one number, its name,
 * and (optionally) which way it is moving.
 *
 * `value` is `unknown`-ish on purpose (`number | string | null | undefined`):
 * a KPI is often a report result that has not run yet, and the tile's whole
 * job is to turn that into "Not available" rather than a blank card or a
 * literal `NaN`. The trend delta never relies on colour by itself — the arrow
 * icon and the signed number are both text-equivalent, and the full sentence
 * ("Up 4% vs last week") is what a screen reader announces, so a colour-blind
 * viewer or an assistive-technology user gets the same information a sighted
 * one gets from the green/red tint.
 */
import type { ReactNode } from 'react';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';

import { Sparkline } from '@/components/sparkline';
import { Card, CardContent } from '@/components/ui/card';
import { fallback, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface KpiTrend {
  /** Signed change since the comparison point, e.g. `4.2` or `-3`. */
  delta: number;
  /** What the delta is measured against, e.g. "vs last week". */
  comparedTo: string;
  /** Whether a positive delta is the good outcome. Off for things like
   *  dropout counts, where "up" is bad news. Defaults to true. */
  positiveIsGood?: boolean;
  /** How to render the magnitude, e.g. `(d) => formatPercent(d)`. Defaults to a plain signed number. */
  format?: (delta: number) => string;
}

function TrendIndicator({ trend }: { trend: KpiTrend }) {
  const direction = trend.delta > 0 ? 'up' : trend.delta < 0 ? 'down' : 'flat';
  const positiveIsGood = trend.positiveIsGood ?? true;
  const isGoodNews = direction === 'flat' ? null : (direction === 'up') === positiveIsGood;

  const magnitude = trend.format
    ? trend.format(Math.abs(trend.delta))
    : formatNumber(Math.abs(trend.delta));
  const sign = direction === 'up' ? '+' : direction === 'down' ? '−' : '';
  const directionWord = direction === 'up' ? 'Up' : direction === 'down' ? 'Down' : 'No change';

  const Icon = direction === 'up' ? ArrowUp : direction === 'down' ? ArrowDown : Minus;
  const tone =
    isGoodNews === null
      ? 'text-muted-foreground'
      : isGoodNews
        ? 'text-success'
        : 'text-destructive';

  return (
    <p className={cn('flex items-center gap-1 text-xs font-medium', tone)}>
      <Icon aria-hidden="true" className="size-3.5" />
      <span aria-hidden="true">
        {sign}
        {magnitude}
      </span>
      <span className="sr-only">
        {directionWord} {magnitude} {trend.comparedTo}
      </span>
      <span aria-hidden="true" className="text-muted-foreground">
        {trend.comparedTo}
      </span>
    </p>
  );
}

export function KpiTile({
  label,
  value,
  format = (raw) => (typeof raw === 'string' ? raw : formatNumber(raw)),
  trend,
  sparkline,
  icon,
  className,
}: {
  label: string;
  value: number | string | null | undefined;
  /** How to render a present value. Defaults to locale-formatting a number, or passing a string through. */
  format?: (value: number | string) => string;
  trend?: KpiTrend;
  /** A short recent-history series for the inline sparkline. Omit to show no chart. */
  sparkline?: number[];
  icon?: ReactNode;
  className?: string;
}) {
  const displayValue =
    value === null || value === undefined ? fallback(value) : format(value);

  return (
    <Card className={className}>
      <CardContent className="flex flex-col gap-2 p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          {icon ? (
            <span aria-hidden="true" className="text-muted-foreground">
              {icon}
            </span>
          ) : null}
        </div>
        <p className="text-2xl font-semibold tabular-nums">{displayValue}</p>
        <div className="flex items-center justify-between gap-3">
          {trend ? <TrendIndicator trend={trend} /> : <span />}
          {sparkline && sparkline.length > 0 ? (
            <Sparkline
              values={sparkline}
              className="text-primary"
              label={`Recent trend for ${label}`}
            />
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
