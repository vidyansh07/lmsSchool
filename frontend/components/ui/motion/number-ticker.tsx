'use client';

/**
 * A figure that counts up to its value when it first comes into view.
 *
 * The point is not decoration. On a dashboard of twelve numbers, the ones that
 * moved are the ones that changed, and the eye finds movement before it reads
 * text — so the animation is doing the work a person would otherwise do by
 * comparing against memory.
 *
 * Three things it must not do, all of which the naive version does:
 *
 * - Never show `NaN` or a half-formatted number. The value is checked once and
 *   an unusable one renders the fallback immediately, with no animation to
 *   sit through.
 * - Never shift the layout. Digits are tabular and the box reserves the width
 *   of the final value, so a figure counting 0 → 1,000 does not push the label
 *   beside it sideways on every frame.
 * - Never animate for someone who asked it not to. Then it is simply the
 *   number, rendered once.
 */

import { animate } from 'motion/react';
import { useEffect, useState } from 'react';

import { type FallbackLabel, NOT_AVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';

import { useReducedMotion } from './use-reduced-motion';

export interface NumberTickerProps {
  value: number | string | null | undefined;
  /** Appended without a space: `%`, `×`. A unit that needs one, include it. */
  suffix?: string;
  prefix?: string;
  decimals?: number;
  /** Shown when the value is not a finite number. */
  label?: FallbackLabel;
  className?: string;
  /** Milliseconds. Long enough to read as counting, short enough not to wait. */
  duration?: number;
}

function toFinite(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function NumberTicker({
  value,
  suffix = '',
  prefix = '',
  decimals = 0,
  label = NOT_AVAILABLE,
  className,
  duration = 900,
}: NumberTickerProps) {
  const target = toFinite(value);
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(0);

  // On mount rather than on intersection. Everything that uses this sits at
  // the top of a dashboard and is already on screen when the page loads, so
  // waiting for an IntersectionObserver callback only delays the number.
  useEffect(() => {
    if (target === null || reduced) return;

    const controls = animate(0, target, {
      duration: duration / 1000,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest: number) => setShown(latest),
    });
    return () => controls.stop();
  }, [target, reduced, duration]);

  if (target === null) {
    // The label, not `fallback(value)`. This component's contract is "this is
    // a figure", so a value that is not one is missing data however
    // presentable its string form happens to be — rendering `"not a number"`
    // in the position of a headline metric states something false in the most
    // prominent type on the page.
    return <span className={cn('text-muted-foreground', className)}>{label}</span>;
  }

  // Derived, not stored. A reduced-motion reader is *at* the value rather than
  // being animated to it instantly, which is the difference between "no
  // animation" and "an animation nobody can see" — the second still costs a
  // render and still starts at zero.
  const displayed = reduced ? target : shown;
  const formatted = displayed.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  // One text node, not three. `{prefix}{formatted}{suffix}` renders as three
  // siblings, and then no `getByText('88%')` — in a test or in a browser's own
  // find-on-page — matches the thing a person can plainly see.
  const text = `${prefix}${formatted}${suffix}`;
  const finalText = `${prefix}${target.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${suffix}`;

  return (
    <span
      className={cn('tabular-nums', className)}
      // The final value is what a screen reader should hear, not whichever
      // frame it happened to catch.
      aria-label={finalText}
    >
      <span aria-hidden="true">{text}</span>
    </span>
  );
}
