'use client';

/**
 * A pipeline, stage by stage, with the drop-off named.
 *
 * Deliberately **not** a Recharts `Funnel`. A funnel encodes a count as a
 * trapezoid width, which is only honest when each stage is a strict subset
 * of the one above it, and is harder to read precisely even then -- the eye
 * compares the sloping sides rather than the lengths. What a counsellor
 * actually wants from a pipeline is the conversion between two stages, which
 * a trapezoid does not show at all.
 *
 * So: horizontal bars for the counts, and a column stating each stage's
 * conversion from the one above it. The bars come from
 * `HorizontalBarChart`, which brings the visually-hidden data table with
 * them.
 *
 * The caller is responsible for the stages genuinely nesting. If a later
 * stage exceeds an earlier one the conversion would read over 100%, so that
 * is surfaced rather than clamped -- it means the query is wrong, and hiding
 * it would leave a plausible-looking chart built on a broken aggregate.
 */

import { cn } from '@/lib/utils';

import { HorizontalBarChart } from './bar-chart-horizontal';
import type { ChartBaseProps } from './types';

export interface StageFunnelStage {
  key: string;
  label: string;
  count: number;
}

export interface StageFunnelProps extends ChartBaseProps {
  stages: readonly StageFunnelStage[];
}

export function StageFunnel({
  stages,
  height = 240,
  loading = false,
  emptyMessage,
  valueFormatter,
  ariaLabel,
  className,
}: StageFunnelProps) {
  const format = valueFormatter ?? ((value: number) => value.toLocaleString());

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <HorizontalBarChart
        data={stages.map((stage) => ({ label: stage.label, value: stage.count }))}
        series={[{ key: 'value', label: 'Reached this stage' }]}
        colorPerBar
        categoryWidth={150}
        height={height}
        loading={loading}
        emptyMessage={emptyMessage}
        valueFormatter={format}
        ariaLabel={ariaLabel ?? 'Pipeline stages, by how many reached each'}
      />
      {loading || stages.length === 0 ? null : (
        <ul className="flex flex-col gap-1 text-xs">
          {stages.map((stage, index) => {
            const previous = index > 0 ? stages[index - 1] : null;
            // No conversion for the first stage: there is nothing above it
            // to convert from. An empty previous stage has no rate either --
            // "0 of 0" is not 0%, it is undefined, and the codebase's own
            // `_percent` convention returns nothing rather than zero.
            const rate =
              previous && previous.count > 0
                ? Math.round((stage.count / previous.count) * 1000) / 10
                : null;
            return (
              <li key={stage.key} className="flex items-baseline justify-between gap-3">
                <span className="truncate text-ink-muted">{stage.label}</span>
                <span className="shrink-0 tabular-nums">
                  <span data-numeric className="font-medium text-ink">
                    {format(stage.count)}
                  </span>
                  {rate === null ? null : (
                    <span className="ml-2 text-ink-faint">
                      {rate}% of {previous?.label.toLowerCase()}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
