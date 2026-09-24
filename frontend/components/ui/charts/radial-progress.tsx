'use client';

/**
 * A single KPI against a target — a gauge, not a chart.
 *
 * Deliberately hand-rolled SVG/CSS, the same house convention as
 * `Sparkline`: this has one data point (the current value) and one reference
 * point (the target), not a series, so there is nothing here a real charting
 * library earns its bundle cost drawing. A half-circle scale from 0 to
 * `max`, the current value filled in, and a tick marking where the target
 * sits on that scale, so "on track" is a shape (fill past the tick) as well
 * as a color.
 */

import { cn } from '@/lib/utils';

import { useReducedMotion } from '@/hooks/use-reduced-motion';

const STROKE = 10;

function arcPath(cx: number, cy: number, r: number): string {
  return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
}

function pointOnArc(cx: number, cy: number, r: number, angleDeg: number): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
}

export interface RadialProgressProps {
  /** The KPI's current value. */
  value: number;
  /** The reference point the gauge marks on its scale. */
  target: number;
  /** The scale's upper bound. Defaults to whichever of `value`/`target` is
   *  larger, so the gauge never clips either one off the arc. */
  max?: number;
  /** Shown under the number, e.g. "of 85% target". */
  label?: string;
  valueFormatter?: (value: number) => string;
  size?: number;
  /** `'auto'` (default) colors by proximity to target: reached (success),
   *  within 75% (warning), further behind (destructive). */
  intent?: 'auto' | 'brand' | 'success' | 'warning' | 'destructive';
  className?: string;
}

export function RadialProgress({
  value,
  target,
  max,
  label,
  valueFormatter,
  size = 120,
  intent = 'auto',
  className,
}: RadialProgressProps) {
  const reduced = useReducedMotion();

  if (!Number.isFinite(value) || !Number.isFinite(target)) return null;

  const scaleMax = Number.isFinite(max as number) && (max as number) > 0 ? (max as number) : Math.max(value, target, 1);
  const radius = (size - STROKE) / 2;
  const cx = size / 2;
  const cy = size / 2 + radius * 0.12;
  const halfCircumference = Math.PI * radius;

  const valueFraction = Math.min(1, Math.max(0, value / scaleMax));
  const targetFraction = Math.min(1, Math.max(0, target / scaleMax));
  const offset = halfCircumference * (1 - valueFraction);

  const resolvedIntent =
    intent === 'auto'
      ? value >= target
        ? 'success'
        : value >= target * 0.75
          ? 'warning'
          : 'destructive'
      : intent;

  const stroke = {
    brand: 'var(--color-action)',
    success: 'var(--color-success)',
    warning: 'var(--color-warning)',
    destructive: 'var(--color-danger)',
  }[resolvedIntent];

  const format = valueFormatter ?? ((n: number) => String(Math.round(n)));
  const tickAngle = 180 - targetFraction * 180;
  const tickInner = pointOnArc(cx, cy, radius - STROKE / 2 - 2, tickAngle);
  const tickOuter = pointOnArc(cx, cy, radius + STROKE / 2 + 2, tickAngle);

  return (
    <div className={cn('inline-flex flex-col items-center', className)}>
      <svg width={size} height={size / 2 + radius * 0.12 + STROKE} viewBox={`0 0 ${size} ${size / 2 + radius * 0.12 + STROKE}`}>
        <path
          d={arcPath(cx, cy, radius)}
          fill="none"
          stroke="var(--color-sunken)"
          strokeWidth={STROKE}
          strokeLinecap="round"
        />
        <path
          d={arcPath(cx, cy, radius)}
          fill="none"
          stroke={stroke}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={halfCircumference}
          strokeDashoffset={offset}
          style={reduced ? undefined : { transition: 'stroke-dashoffset 320ms var(--ease-out)' }}
        />
        {/* The target tick — a fixed reference mark on the scale itself,
            independent of the fill, so "where is the goal" reads even when
            the fill is nowhere near it yet. */}
        <line
          x1={tickInner.x}
          y1={tickInner.y}
          x2={tickOuter.x}
          y2={tickOuter.y}
          stroke="var(--color-ink)"
          strokeWidth={2}
          strokeLinecap="round"
        />
      </svg>
      <div className="-mt-6 flex flex-col items-center">
        <span className="text-xl font-semibold tabular-nums text-ink">{format(value)}</span>
        <span className="text-2xs text-ink-muted">{label ?? `of ${format(target)} target`}</span>
      </div>
    </div>
  );
}
