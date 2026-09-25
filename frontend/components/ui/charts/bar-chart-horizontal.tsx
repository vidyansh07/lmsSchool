'use client';

/**
 * A comparison between named things, read down the page instead of across it.
 *
 * A separate component rather than a `layout` prop on `BarChart`, because
 * Recharts' `layout="vertical"` swaps the role of every axis: the category
 * axis becomes the Y, the value axis becomes the X, the corner radius moves
 * to the trailing edge, the gridline flips from `vertical={false}` to
 * `horizontal={false}`, and the category axis needs an explicit pixel width
 * to leave room for its labels. Two mutually exclusive halves inside one
 * component would be harder to read and harder to test than two components.
 *
 * Prefer it over a vertical bar whenever the category labels are words
 * rather than dates: "Networking Basics" fits on one line here and is
 * rotated 30 degrees and clipped there.
 */

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Cell,
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

export interface HorizontalBarChartProps extends ChartBaseProps {
  data: CategoryDatum[];
  /** One entry per bar series. Defaults to a single series read from `value`. */
  series?: ChartSeriesDef[];
  /** Stack series within each category instead of grouping them. */
  stacked?: boolean;
  /** Give each bar its own palette step. Single-series only, as in
   *  `BarChart` -- with more than one series the colour already means
   *  "which series". */
  colorPerBar?: boolean;
  /** Pixels reserved for the left-hand category labels. Raise it for long
   *  names; the labels are clipped rather than wrapped if it is too small. */
  categoryWidth?: number;
}

const DEFAULT_SERIES: ChartSeriesDef[] = [{ key: 'value', label: 'Value' }];
const BAR_MAX_SIZE = 20;
/** Rounded on the trailing edge only -- a bar grows to the right. */
const BAR_RADIUS: [number, number, number, number] = [0, 4, 4, 0];

function cellText(value: CategoryDatum[string], format: (value: number) => string): string {
  if (typeof value === 'number') return Number.isFinite(value) ? format(value) : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function HorizontalBarChart({
  data,
  series = DEFAULT_SERIES,
  stacked = false,
  colorPerBar = false,
  categoryWidth = 120,
  height = 240,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: HorizontalBarChartProps) {
  const animation = useChartAnimation();

  if (loading) return <ChartSkeleton height={height} />;

  const hasData = data.some((row) => series.some((bar) => Number.isFinite(row[bar.key] as number)));
  if (!hasData) return <ChartEmpty message={emptyMessage} height={height} />;

  if (process.env.NODE_ENV !== 'production' && colorPerBar && series.length > 1) {
    console.warn(
      `HorizontalBarChart: colorPerBar is ignored for ${series.length} series. With more than one series a bar's colour already means "which series".`,
    );
  }

  const perBar = colorPerBar && series.length === 1;
  const format = valueFormatter ?? ((value: number) => String(value));
  const caption = ariaLabel ?? `${series.map((bar) => bar.label).join(', ')} by category`;

  return (
    <div className={cn('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart
          data={data}
          layout="vertical"
          margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
        >
          {/* Flipped: the value axis runs across, so the helpful gridlines
              are the vertical ones. */}
          <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: CHART_GRID_COLOR }}
            tickFormatter={(value: number) => format(value)}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={categoryWidth}
          />
          <Tooltip
            content={(tooltipProps) => <ChartTooltipContent {...tooltipProps} valueFormatter={format} />}
            cursor={{ fill: CHART_GRID_COLOR, fillOpacity: 0.4 }}
          />
          {series.length > 1 ? (
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
                      <Cell key={`${row.label}-${cellIndex}`} fill={paletteColor(cellIndex, CHART_PALETTE)} />
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
