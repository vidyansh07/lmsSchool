'use client';

/**
 * Composition — a whole broken into parts. Capped sensibly: past
 * `DONUT_CATEGORY_WARNING_THRESHOLD` (5) categories a donut reads as noise
 * rather than composition, per this session's own dataviz guidance, so a
 * caller with that many is almost always asking a comparison question
 * (`BarChart`), not a composition one. Enforced as a soft, dev-only console
 * warning — never a hard runtime check that silently drops the caller's own
 * categories or refuses to render.
 */

import { useEffect, useRef } from 'react';
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { useReducedMotion } from '@/components/ui/motion/use-reduced-motion';
import { cn } from '@/lib/utils';

import { CHART_ANIMATION_MS, CHART_PALETTE, DONUT_CATEGORY_WARNING_THRESHOLD, paletteColor } from './chart-colors';
import { ChartDataTable } from './chart-data-table';
import { ChartEmpty } from './chart-empty';
import { ChartLegendContent } from './chart-legend';
import { ChartSkeleton } from './chart-skeleton';
import { ChartTooltipContent } from './chart-tooltip';
import type { ChartBaseProps } from './types';

export interface DonutDatum {
  label: string;
  value: number;
  /** Overrides the fixed palette order for this one slice — e.g. to match a
   *  status color the rest of the app already uses for this category. */
  color?: string;
}

export interface DonutChartProps extends ChartBaseProps {
  data: DonutDatum[];
  /** Total shown in the donut's centre. Defaults to the sum of `value`. */
  centerLabel?: string;
}

export function DonutChart({
  data,
  centerLabel = 'Total',
  height = 240,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: DonutChartProps) {
  const reduced = useReducedMotion();
  const warned = useRef(false);

  useEffect(() => {
    if (
      !warned.current &&
      process.env.NODE_ENV !== 'production' &&
      data.length > DONUT_CATEGORY_WARNING_THRESHOLD
    ) {
      warned.current = true;
      console.warn(
        `DonutChart: ${data.length} categories is past the ~${DONUT_CATEGORY_WARNING_THRESHOLD} a donut reads clearly at — a BarChart usually answers this comparison better.`,
      );
    }
  }, [data.length]);

  if (loading) return <ChartSkeleton height={height} />;

  const usable = data.filter((slice) => Number.isFinite(slice.value) && slice.value > 0);
  if (usable.length === 0) return <ChartEmpty message={emptyMessage} height={height} />;

  const format = valueFormatter ?? ((value: number) => String(value));
  const total = usable.reduce((sum, slice) => sum + slice.value, 0);
  const caption = ariaLabel ?? `${centerLabel} by category`;

  return (
    <div className={cn('relative w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <Tooltip content={(tooltipProps) => <ChartTooltipContent {...tooltipProps} valueFormatter={format} />} />
          <Legend content={(legendProps) => <ChartLegendContent {...legendProps} markShape="rect" />} />
          <Pie
            data={usable}
            dataKey="value"
            nameKey="label"
            innerRadius="60%"
            outerRadius="85%"
            paddingAngle={usable.length > 1 ? 2 : 0}
            stroke="none"
            isAnimationActive={!reduced}
            animationDuration={CHART_ANIMATION_MS}
            animationEasing="ease-out"
          >
            {usable.map((slice, index) => (
              <Cell key={slice.label} fill={slice.color ?? paletteColor(index, CHART_PALETTE)} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      {/* The centre readout — same idea as `ProgressRing`'s inner number: the
          figure a reader wants first sits inside the shape, not beside it. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
        style={{ paddingBottom: 28 }}
      >
        <span className="text-xl font-semibold tabular-nums text-foreground">{format(total)}</span>
        <span className="text-2xs text-muted-foreground">{centerLabel}</span>
      </div>
      <ChartDataTable
        caption={caption}
        columns={['Category', 'Value']}
        rows={usable.map((slice, index) => ({
          key: `${slice.label}-${index}`,
          cells: [slice.label, format(slice.value)],
        }))}
      />
    </div>
  );
}
