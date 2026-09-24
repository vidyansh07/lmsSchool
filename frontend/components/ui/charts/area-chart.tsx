'use client';

/**
 * Volume-over-time — the filled sibling of `LineChart`. Same data shape and
 * the same accessibility story (Recharts' `accessibilityLayer` plus the
 * visually-hidden `ChartDataTable`); the only real difference is the mark:
 * a wash under the line rather than a bare stroke, per this session's own
 * dataviz guidance (~10% fill opacity — a wash, never a saturated block).
 */

import {
  Area,
  AreaChart as RechartsAreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useReducedMotion } from '@/hooks/use-reduced-motion';
import { cn } from '@/lib/utils';

import { CHART_ANIMATION_MS, CHART_AXIS_TEXT_COLOR, CHART_GRID_COLOR, CHART_PALETTE, paletteColor } from './chart-colors';
import { ChartDataTable } from './chart-data-table';
import { ChartEmpty } from './chart-empty';
import { ChartLegendContent } from './chart-legend';
import { ChartSkeleton } from './chart-skeleton';
import { ChartTooltipContent } from './chart-tooltip';
import type { ChartBaseProps, ChartSeriesDef, TrendDatum } from './types';

export interface AreaChartProps extends ChartBaseProps {
  data: TrendDatum[];
  /** One entry per area. Defaults to a single series read from `value`. */
  series?: ChartSeriesDef[];
  xLabel?: string;
  /** Stack series on top of each other (composition over time) instead of
   *  overlaying them. Only meaningful with more than one series. */
  stacked?: boolean;
}

const DEFAULT_SERIES: ChartSeriesDef[] = [{ key: 'value', label: 'Value' }];

function cellText(value: TrendDatum[string], format: (value: number) => string): string {
  if (typeof value === 'number') return Number.isFinite(value) ? format(value) : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function AreaChart({
  data,
  series = DEFAULT_SERIES,
  xLabel = 'Date',
  stacked = false,
  height = 240,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: AreaChartProps) {
  const reduced = useReducedMotion();

  if (loading) return <ChartSkeleton height={height} />;

  const hasData = data.some((point) => series.some((area) => Number.isFinite(point[area.key] as number)));
  if (!hasData) return <ChartEmpty message={emptyMessage} height={height} />;

  const format = valueFormatter ?? ((value: number) => String(value));
  const caption = ariaLabel ?? `${series.map((area) => area.label).join(', ')} by ${xLabel.toLowerCase()}`;

  return (
    <div className={cn('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsAreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
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
          {series.map((area, index) => {
            const color = area.color ?? paletteColor(index, CHART_PALETTE);
            return (
              <Area
                key={area.key}
                type="monotone"
                dataKey={area.key}
                name={area.label}
                stackId={stacked ? 'stack' : undefined}
                stroke={color}
                strokeWidth={2}
                fill={color}
                fillOpacity={0.12}
                dot={false}
                activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                isAnimationActive={!reduced}
                animationDuration={CHART_ANIMATION_MS}
                animationEasing="ease-out"
                connectNulls
              />
            );
          })}
        </RechartsAreaChart>
      </ResponsiveContainer>
      <ChartDataTable
        caption={caption}
        columns={[xLabel, ...series.map((area) => area.label)]}
        rows={data.map((point, index) => ({
          key: `${point.date}-${index}`,
          cells: [String(point.date), ...series.map((area) => cellText(point[area.key], format))],
        }))}
      />
    </div>
  );
}
