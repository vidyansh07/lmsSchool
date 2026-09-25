'use client';

/**
 * Category comparison. One series is a plain comparison bar chart; more than
 * one is the grouped-bar variant (period-over-period, or one bar per
 * category per series) side by side — pass `stacked` for composition-within-
 * category instead.
 *
 * Mark spec per this session's own dataviz guidance: bars capped at 24px so
 * they never fill their slot, a 4px rounded cap with a square baseline, and
 * a 2px surface-color gap between touching bars (`barGap`/`barCategoryGap`
 * below) rather than a stroke drawn around each one.
 */

import {
  Bar,
  Cell,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { cn } from '@/lib/utils';

import { CHART_AXIS_TEXT_COLOR, CHART_GRID_COLOR, CHART_PALETTE, paletteColor } from './chart-colors';
import { ChartDataTable } from './chart-data-table';
import { ChartEmpty } from './chart-empty';
import { ChartLegendContent } from './chart-legend';
import { ChartSkeleton } from './chart-skeleton';
import { ChartTooltipContent } from './chart-tooltip';
import { useChartAnimation } from './use-chart-animation';
import type { CategoryDatum, ChartBaseProps, ChartSeriesDef } from './types';

export interface BarChartProps extends ChartBaseProps {
  data: CategoryDatum[];
  /** One entry per bar series. Defaults to a single series read from `value`. */
  series?: ChartSeriesDef[];
  /** With more than one series: side-by-side bars (`false`, the grouped-bar
   *  variant) or stacked within each category (`true`). Ignored for a single
   *  series. */
  stacked?: boolean;
  /** Suppress the chart's own legend, for when the card around it already
   *  carries one. Two legends for one plot is the same information twice. */
  hideLegend?: boolean;
  /** Give each bar its own palette step instead of one colour for the whole
   *  series. For a comparison *between* categories, where the bar's colour
   *  is its identity rather than decoration. Single-series only: with more
   *  than one series the colour already means "which series", and a second
   *  meaning for the same channel is how a chart stops being readable. */
  colorPerBar?: boolean;
  /** A field on each datum holding that bar's colour.
   *
   *  Different in kind from `colorPerBar`, which cycles the palette and so
   *  says only "these are different things". This says *what* each bar is --
   *  above or below a target, one severity or another -- which is the only
   *  reason a bar in a single-metric comparison should carry a colour at
   *  all. Takes precedence over `colorPerBar` when both are given. */
  colorKey?: string;
}

const DEFAULT_SERIES: ChartSeriesDef[] = [{ key: 'value', label: 'Value' }];
const BAR_MAX_SIZE = 24;
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

function cellText(value: CategoryDatum[string], format: (value: number) => string): string {
  if (typeof value === 'number') return Number.isFinite(value) ? format(value) : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function BarChart({
  data,
  series = DEFAULT_SERIES,
  stacked = false,
  hideLegend = false,
  colorPerBar = false,
  colorKey,
  height = 240,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: BarChartProps) {
  const animation = useChartAnimation();

  if (loading) return <ChartSkeleton height={height} />;

  // Finite *and* non-zero. A bar chart where every value is 0 draws an
  // axis with no bars on it, which reads as broken rather than as "nothing
  // happened" -- and "nothing happened" is exactly what the empty state is
  // for. A single non-zero bar is enough to be worth plotting.
  const hasData = data.some((row) =>
    series.some((bar) => {
      const value = row[bar.key];
      return typeof value === 'number' && Number.isFinite(value) && value !== 0;
    }),
  );
  if (!hasData) return <ChartEmpty message={emptyMessage} height={height} />;

  // Single series only, and say so rather than silently doing nothing.
  if (process.env.NODE_ENV !== 'production' && colorPerBar && series.length > 1) {
    console.warn(
      `BarChart: per-bar colour is ignored for ${series.length} series. With more than one series a bar's colour already means "which series".`,
    );
  }

  const perBar = (colorPerBar || Boolean(colorKey)) && series.length === 1;
  const colourFor = (row: (typeof data)[number], index: number): string => {
    const named = colorKey ? row[colorKey] : undefined;
    return typeof named === 'string' && named !== '' ? named : paletteColor(index, CHART_PALETTE);
  };
  const format = valueFormatter ?? ((value: number) => String(value));
  const caption = ariaLabel ?? `${series.map((bar) => bar.label).join(', ')} by category`;

  return (
    <div className={cn('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart
          data={data}
          margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
          barGap={2}
          barCategoryGap="24%"
        >
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: CHART_GRID_COLOR }}
          />
          <YAxis
            tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={40}
            tickFormatter={(value: number) => format(value)}
          />
          <Tooltip
            content={(tooltipProps) => <ChartTooltipContent {...tooltipProps} valueFormatter={format} />}
            cursor={{ fill: 'var(--color-sunken)' }}
          />
          {series.length > 1 && !hideLegend ? (
            <Legend content={(legendProps) => <ChartLegendContent {...legendProps} markShape="rect" />} />
          ) : null}
          {series.map((bar, index) => {
            const color = bar.color ?? paletteColor(index, CHART_PALETTE);
            return (
              <Bar
                key={bar.key}
                dataKey={bar.key}
                name={bar.label}
                stackId={stacked ? 'stack' : undefined}
                fill={color}
                maxBarSize={BAR_MAX_SIZE}
                radius={stacked && index < series.length - 1 ? [0, 0, 0, 0] : BAR_RADIUS}
                {...animation}
              >
                {perBar
                  ? data.map((row, cellIndex) => (
                      <Cell key={`${row.label}-${cellIndex}`} fill={colourFor(row, cellIndex)} />
                    ))
                  : null}
              </Bar>
            );
          })}
        </RechartsBarChart>
      </ResponsiveContainer>
      <ChartDataTable
        caption={caption}
        columns={['Category', ...series.map((bar) => bar.label)]}
        rows={data.map((row, index) => ({
          key: `${row.label}-${index}`,
          cells: [String(row.label), ...series.map((bar) => cellText(row[bar.key], format))],
        }))}
      />
    </div>
  );
}
