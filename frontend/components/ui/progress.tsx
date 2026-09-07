import * as React from 'react';

import { cn } from '@/lib/utils';

export interface ProgressProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'role'> {
  /** Omit (or pass `undefined`) for an indeterminate bar — work is happening, duration unknown. */
  value?: number;
  max?: number;
  /** Accessible name for the bar, e.g. "Import progress". */
  label?: string;
}

/**
 * A bounded-progress bar, built as a `role="progressbar"` `<div>` rather than
 * the native `<progress>` element: `<progress>` is real and accessible, but
 * its fill can only be restyled through vendor pseudo-elements
 * (`::-webkit-progress-value`, `::-moz-progress-bar`) that do not agree with
 * each other on box model, which makes a rounded, on-brand fill unreliable
 * across browsers. A plain `<div>` with the matching ARIA attributes gets the
 * same semantics with none of that.
 *
 * The fill is a `scaleX` transform on a full-width bar, not a `width`
 * change, so animating it on every value update never triggers layout —
 * exactly the "transform and opacity only" rule the rest of this app's
 * motion follows, applied to a property update rather than an enter/exit.
 */
export function Progress({ value, max = 100, label, className, ...props }: ProgressProps) {
  const isIndeterminate = value === undefined;
  const fraction = isIndeterminate ? 1 : Math.min(1, Math.max(0, value / max));

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={isIndeterminate ? undefined : value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      <div
        className={cn(
          'h-full origin-left rounded-full bg-primary transition-transform',
          // No dedicated "indeterminate sweep" keyframe exists in globals.css
          // and this file cannot add one, so an indeterminate bar pulses in
          // place instead — honest about "still working", not a fabricated
          // sweep that implies a smoothness the state doesn't have.
          isIndeterminate && 'animate-pulse',
        )}
        style={{
          transform: `scaleX(${fraction})`,
          transitionDuration: 'var(--duration-base)',
          transitionTimingFunction: 'var(--ease-out-quick)',
        }}
      />
    </div>
  );
}
