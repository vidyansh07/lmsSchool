'use client';

/**
 * Two quantities on one plot, each with its own scale.
 *
 * The chart to reach for when a volume and a rate move together -- classes
 * held against attendance percent, payments taken against amount collected.
 * Bars carry the count, a line carries the rate, and the two axes keep each
 * readable at its own magnitude.
 *
 * `leftLabel` and `rightLabel` are **required props**, and that is the whole
 * design of this component. Two unlabelled scales on one plot is the classic
 * false-correlation chart: whichever way the reader happens to pair the
 * lines with the axes, they will believe a relationship the numbers do not
 * claim. A required prop is the only reliable way to make a label
 * unforgettable, so there is no default and no way to opt out.
 *
 * Each axis is also tinted to the series drawn against it, and the legend
 * always renders regardless of series count -- with two scales in play,
 * "which of these is which" is never obvious from the marks alone.
 */

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
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

export interface ComboChartProps extends ChartBaseProps {
  data: TrendDatum[];
  /** Series drawn as bars. Usually the count. */
  bars?: ChartSeriesDef[];
  /** Series drawn as lines. Usually the rate. */
  lines?: ChartSeriesDef[];
  /** Which series keys are measured against the right-hand axis. Anything
   *  not listed here belongs to the left. */
  rightAxisKeys?: string[];
  /** What the left axis measures. Required -- see the note above. */
  leftLabel: string;
  /** What the right axis measures. Required -- see the note above. */
  rightLabel: string;
  xLabel?: string;
  /** Formatter for the right-hand axis, when its unit differs from the
   *  left's (a percent beside a count, most often). */
  rightValueFormatter?: (value: number) => string;
}

const BAR_MAX_SIZE = 20;
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

function cellText(value: TrendDatum[string], format: (value: number) => string): string {
  if (typeof value === 'number') return Number.isFinite(value) ? format(value) : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function ComboChart({
  data,
  bars = [],
  lines = [],
  rightAxisKeys = [],
  leftLabel,
  rightLabel,
  xLabel = 'Date',
  height = 280,
  loading = false,
  emptyMessage,
  valueFormatter,
  rightValueFormatter,
  ariaLabel,
  className,
}: ComboChartProps) {
  const animation = useChartAnimation();

  if (loading) return <ChartSkeleton height={height} />;

  const all = [...bars, ...lines];
  const hasData = data.some((point) => all.some((s) => Number.isFinite(point[s.key] as number)));
  if (!hasData) return <ChartEmpty message={emptyMessage} height={height} />;

  const formatLeft = valueFormatter ?? ((value: number) => String(value));
  const formatRight = rightValueFormatter ?? formatLeft;
  const onRight = (key: string) => rightAxisKeys.includes(key);
  const colorFor = (s: ChartSeriesDef, index: number) => s.color ?? paletteColor(index, CHART_PALETTE);
  const caption = ariaLabel ?? `${all.map((s) => s.label).join(', ')} by ${xLabel.toLowerCase()}`;

  // The axes take their colour from the first series measured against each,
  // so a reader can pair a mark with its scale without counting.
  const leftTint = colorFor(
    all.find((s) => !onRight(s.key)) ?? all[0]!,
    all.findIndex((s) => !onRight(s.key)),
  );
  const rightTint = colorFor(
    all.find((s) => onRight(s.key)) ?? all[0]!,
    all.findIndex((s) => onRight(s.key)),
  );

  return (
    <div className={cn('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: CHART_GRID_COLOR }}
          />
          <YAxis
            yAxisId="left"
            tick={{ fill: leftTint, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(value: number) => formatLeft(value)}
            label={{
              value: leftLabel,
              angle: -90,
              position: 'insideLeft',
              style: { fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 },
            }}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fill: rightTint, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(value: number) => formatRight(value)}
            label={{
              value: rightLabel,
              angle: 90,
              position: 'insideRight',
              style: { fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 },
            }}
          />
          <Tooltip
            content={(tooltipProps) => <ChartTooltipContent {...tooltipProps} valueFormatter={formatLeft} />}
            cursor={{ fill: CHART_GRID_COLOR, fillOpacity: 0.4 }}
          />
          {/* Always, not only past one series: with two scales in play the
              marks alone never say which is which. */}
          <Legend content={(legendProps) => <ChartLegendContent {...legendProps} markShape="rect" />} />
          {bars.map((bar, index) => (
            <Bar
              key={bar.key}
              yAxisId={onRight(bar.key) ? 'right' : 'left'}
              dataKey={bar.key}
              name={bar.label}
              fill={colorFor(bar, index)}
              maxBarSize={BAR_MAX_SIZE}
              radius={BAR_RADIUS}
              {...animation}
            />
          ))}
          {lines.map((line, index) => (
            <Line
              key={line.key}
              yAxisId={onRight(line.key) ? 'right' : 'left'}
              type="monotone"
              dataKey={line.key}
              name={line.label}
              stroke={colorFor(line, bars.length + index)}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--color-surface)' }}
              {...animation}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      {/* Both units named, so the table is readable without the axes. */}
      <ChartDataTable
        caption={caption}
        columns={[
          xLabel,
          ...all.map((s) => `${s.label} (${onRight(s.key) ? rightLabel : leftLabel})`),
        ]}
        rows={data.map((point, index) => ({
          key: `${point.date}-${index}`,
          cells: [
            String(point.date),
            ...all.map((s) => cellText(point[s.key], onRight(s.key) ? formatRight : formatLeft)),
          ],
        }))}
      />
    </div>
  );
}
