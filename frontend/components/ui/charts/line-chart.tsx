'use client';

/**
 * Trend-over-time, one or more series. The default wrapper for "how did this
 * number move" — an attendance rate by week, a KPI by month.
 *
 * `accessibilityLayer` (Recharts' own keyboard-nav + focus-triggered
 * tooltip) is on by default for a Cartesian chart, so tab-focusing the plot
 * reaches the same values a mouse hover would — the visually-hidden
 * `ChartDataTable` alongside it is the belt to that suspenders: every value
 * as plain text, reachable without touching the SVG at all.
 */

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart as RechartsLineChart,
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
import type { ChartBaseProps, ChartSeriesDef, TrendDatum } from './types';

export interface LineChartProps extends ChartBaseProps {
  data: TrendDatum[];
  /** One entry per line. Defaults to a single series read from `value`. */
  series?: ChartSeriesDef[];
  /** Column header for the x-axis series, used in the tooltip and the text
   *  alternative table (e.g. "Week"). */
  xLabel?: string;
}

const DEFAULT_SERIES: ChartSeriesDef[] = [{ key: 'value', label: 'Value' }];

function cellText(value: TrendDatum[string], format: (value: number) => string): string {
  if (typeof value === 'number') return Number.isFinite(value) ? format(value) : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function LineChart({
  data,
  series = DEFAULT_SERIES,
  xLabel = 'Date',
  height = 240,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: LineChartProps) {
  const animation = useChartAnimation();

  if (loading) return <ChartSkeleton height={height} />;

  const hasData = data.some((point) => series.some((line) => Number.isFinite(point[line.key] as number)));
  if (!hasData) return <ChartEmpty message={emptyMessage} height={height} />;

  const format = valueFormatter ?? ((value: number) => String(value));
  const caption = ariaLabel ?? `${series.map((line) => line.label).join(', ')} by ${xLabel.toLowerCase()}`;

  return (
    <div className={cn('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsLineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis
            dataKey="date"
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
            cursor={{ stroke: CHART_GRID_COLOR, strokeWidth: 1 }}
          />
          {series.length > 1 ? (
            <Legend content={(legendProps) => <ChartLegendContent {...legendProps} markShape="line" />} />
          ) : null}
          {series.map((line, index) => {
            const color = line.color ?? paletteColor(index, CHART_PALETTE);
            return (
              <Line
                key={line.key}
                type="monotone"
                dataKey={line.key}
                name={line.label}
                stroke={color}
                strokeWidth={2}
                dot={{ r: 3, strokeWidth: 0, fill: color }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                {...animation}
                connectNulls
              />
            );
          })}
        </RechartsLineChart>
      </ResponsiveContainer>
      <ChartDataTable
        caption={caption}
        columns={[xLabel, ...series.map((line) => line.label)]}
        rows={data.map((point, index) => ({
          key: `${point.date}-${index}`,
          cells: [String(point.date), ...series.map((line) => cellText(point[line.key], format))],
        }))}
      />
    </div>
  );
}
