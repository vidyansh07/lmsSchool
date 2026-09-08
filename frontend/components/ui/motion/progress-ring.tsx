'use client';

/**
 * A percentage as a ring.
 *
 * Used where a bar would be wrong: inside a stat tile, where the number is the
 * headline and the ring is the context around it. A bar competes with the
 * figure for horizontal space; a ring wraps it.
 *
 * The colour carries meaning — a course 20% through its schedule is not the
 * same news as one 95% through — so the thresholds are a prop rather than
 * hard-coded, and the ring is never the *only* signal: the number sits inside
 * it, which is the WCAG requirement that colour alone must not convey
 * information.
 */

import { cn } from '@/lib/utils';

import { useReducedMotion } from './use-reduced-motion';

const SIZE = 44;
const STROKE = 4;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function ProgressRing({
  value,
  className,
  intent = 'brand',
  children,
}: {
  /** 0–100. Anything outside is clamped; anything unusable renders nothing. */
  value: number | null | undefined;
  className?: string;
  intent?: 'brand' | 'success' | 'warning' | 'destructive';
  children?: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  if (!Number.isFinite(value as number)) return null;

  const percent = Math.min(100, Math.max(0, value as number));
  const offset = CIRCUMFERENCE - (percent / 100) * CIRCUMFERENCE;
  const stroke = {
    brand: 'var(--color-primary)',
    success: 'var(--color-success)',
    warning: 'var(--color-warning)',
    destructive: 'var(--color-destructive)',
  }[intent];

  return (
    <div className={cn('relative inline-flex items-center justify-center', className)}>
      <svg width={SIZE} height={SIZE} className="-rotate-90" aria-hidden="true">
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="var(--color-muted)"
          strokeWidth={STROKE}
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={stroke}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          style={
            reduced
              ? undefined
              : {
                  transition: 'stroke-dashoffset var(--duration-slow) var(--ease-out-quick)',
                }
          }
        />
      </svg>
      {children ? (
        <span className="absolute text-2xs font-semibold tabular-nums">{children}</span>
      ) : null}
    </div>
  );
}
