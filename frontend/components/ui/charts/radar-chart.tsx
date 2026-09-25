'use client';

/**
 * One subject across several dimensions at once.
 *
 * Built for the case this product actually has: a student measured on
 * attendance, assessments, assignments, projects and progress, where the
 * question is "where is the weak spoke" rather than "what is the trend".
 * A grouped bar answers the same question and is easier to read precisely;
 * a radar answers it faster, because an uneven shape is visible before any
 * label is read. Use it for a shape, and pair it with the figures.
 *
 * `max` is fixed at 100 and never inferred from the data, deliberately. A
 * radar whose radius scales to its own maximum cannot be compared to the
 * radar beside it -- two students with wildly different marks would draw the
 * same shape, which is worse than no chart.
 *
 * Past two series the overlapping fills stop being readable; the component
 * warns rather than silently drawing mud.
 */

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart as RechartsRadarChart,
  ResponsiveContainer,
  Tooltip,
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

/** Two overlapping fills read; three do not. */
const RADAR_SERIES_LIMIT = 2;

export interface RadarChartProps extends ChartBaseProps {
  /** One datum per spoke: a `label` plus one numeric field per series. */
  data: CategoryDatum[];
  series?: ChartSeriesDef[];
  /** The radius axis maximum. Fixed, never auto -- see the note above. */
  max?: number;
}

const DEFAULT_SERIES: ChartSeriesDef[] = [{ key: 'value', label: 'Value' }];

function cellText(value: CategoryDatum[string], format: (value: number) => string): string {
  if (typeof value === 'number') return Number.isFinite(value) ? format(value) : '—';
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function RadarChart({
  data,
  series = DEFAULT_SERIES,
  max = 100,
  height = 280,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: RadarChartProps) {
  const animation = useChartAnimation();

  if (loading) return <ChartSkeleton height={height} />;

  const hasData = data.some((row) => series.some((s) => Number.isFinite(row[s.key] as number)));
  // Three spokes is a triangle; fewer is not a shape at all, and the honest
  // rendering of two dimensions is two numbers.
  if (!hasData || data.length < 3) return <ChartEmpty message={emptyMessage} height={height} />;

  if (process.env.NODE_ENV !== 'production' && series.length > RADAR_SERIES_LIMIT) {
    console.warn(
      `RadarChart: ${series.length} series overlap into an unreadable fill. Two is the limit; past that use small multiples.`,
    );
  }

  const format = valueFormatter ?? ((value: number) => String(value));
  const caption = ariaLabel ?? `${series.map((s) => s.label).join(', ')} by dimension`;

  return (
    <div className={cn('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsRadarChart data={data} outerRadius="72%">
          <PolarGrid stroke={CHART_GRID_COLOR} />
          <PolarAngleAxis dataKey="label" tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 11 }} />
          <PolarRadiusAxis
            domain={[0, max]}
            tick={{ fill: CHART_AXIS_TEXT_COLOR, fontSize: 10 }}
            tickFormatter={(value: number) => format(value)}
            axisLine={false}
          />
          <Tooltip
            content={(tooltipProps) => <ChartTooltipContent {...tooltipProps} valueFormatter={format} />}
          />
          {series.map((s, index) => {
            const color = s.color ?? paletteColor(index, CHART_PALETTE);
            return (
              <Radar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stroke={color}
                strokeWidth={2}
                fill={color}
                fillOpacity={0.16}
                {...animation}
              />
            );
          })}
        </RechartsRadarChart>
      </ResponsiveContainer>
      {/* The legend sits outside the plot: Recharts' own would overlap the
          spoke labels at this radius. */}
      {series.length > 1 ? (
        <ChartLegendContent
          payload={series.map((s, index) => ({
            value: s.label,
            dataKey: s.key,
            color: s.color ?? paletteColor(index, CHART_PALETTE),
          }))}
          markShape="rect"
        />
      ) : null}
      <ChartDataTable
        caption={caption}
        columns={['Dimension', ...series.map((s) => s.label)]}
        rows={data.map((row, index) => ({
          key: `${row.label}-${index}`,
          cells: [String(row.label), ...series.map((s) => cellText(row[s.key], format))],
        }))}
      />
    </div>
  );
}
