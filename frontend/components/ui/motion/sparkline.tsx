'use client';

/**
 * A trend line small enough to sit inside a stat card.
 *
 * Deliberately axis-free and label-free. This is not a chart a person reads
 * values off; it answers "which way, and how steadily" in the half-second
 * before they read the number beside it. Anything more — a scale, a tooltip,
 * a legend — belongs on the reports screen, at a size that can carry it.
 *
 * The line draws itself on entry using `stroke-dashoffset`, which the
 * compositor handles without touching layout. Under reduced motion it is
 * simply drawn.
 *
 * Fewer than two points is not a trend, and a series that is all one value is
 * a flat line rather than a divide-by-zero: both render as the empty state
 * instead of an SVG with `NaN` in its path, which is how this class of
 * component usually fails.
 */

import { useId } from 'react';

import { cn } from '@/lib/utils';

import { useReducedMotion } from './use-reduced-motion';

export interface SparklineProps {
  values: readonly (number | null | undefined)[];
  className?: string;
  /** Height in px. Width is fluid — the viewBox scales to the container. */
  height?: number;
  /** Rising is good for attendance, bad for dropouts. Colours accordingly. */
  intent?: 'brand' | 'positive-up' | 'positive-down';
  label?: string;
}

const VIEW_WIDTH = 100;
/** Vertical room for half a stroke at the top and bottom of the series. */
const INSET = 6;

export function Sparkline({
  values,
  className,
  height = 32,
  intent = 'brand',
  label = 'Recent trend',
}: SparklineProps) {
  const gradientId = useId();
  const reduced = useReducedMotion();

  const points = values.filter((value): value is number => Number.isFinite(value as number));
  if (points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min;

  // A flat series has no span to normalise against; drawing it down the middle
  // is honest, and dividing by zero is not.
  const y = (value: number) =>
    span === 0 ? 50 : INSET + (100 - 2 * INSET) * (1 - (value - min) / span);
  const x = (index: number) => (index / (points.length - 1)) * VIEW_WIDTH;

  const path = points.map((value, index) => `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(2)} ${y(value).toFixed(2)}`).join(' ');
  const area = `${path} L ${VIEW_WIDTH} 100 L 0 100 Z`;

  // Both indices exist: `points.length >= 2` was checked above, and the
  // compiler cannot see that through the length comparison.
  const direction = (points.at(-1) as number) - (points[0] as number);
  const stroke =
    intent === 'brand'
      ? 'var(--color-primary)'
      : (intent === 'positive-up' ? direction >= 0 : direction <= 0)
        ? 'var(--color-success)'
        : 'var(--color-destructive)';

  return (
    <svg
      viewBox={`0 0 ${VIEW_WIDTH} 100`}
      preserveAspectRatio="none"
      height={height}
      // Not `overflow-visible`: the stroke is centred on the path, so half of
      // it at the top and bottom of the series sits outside the viewBox. The
      // card that holds this clips its own overflow, and a line that runs to
      // the card's edge and stops mid-stroke looks like a rendering fault.
      className={cn('w-full', className)}
      role="img"
      aria-label={label}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.18" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        className={reduced ? undefined : 'sparkline-draw'}
      />
    </svg>
  );
}
