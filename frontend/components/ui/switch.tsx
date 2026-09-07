'use client';

/**
 * A binary on/off control, built as `<button role="switch">` rather than
 * `<input type="checkbox">`: a switch is not a checkbox with a rounder shape
 * — it takes effect immediately (no surrounding form submission), and
 * `role="switch"` tells assistive technology exactly that, announcing
 * "on"/"off" instead of "checked"/"unchecked". This is the same pattern
 * Radix's own `Switch` renders under the hood.
 *
 * The visible track is 24px tall (`h-6`), under the 44px touch-target floor
 * this app requires. Rather than inflating the track itself — which would
 * throw off every row it sits in next to a label — the hit area is grown
 * with a `::before` pseudo-element extending 10px above and below,
 * invisible and un-laid-out, so the click target hits 44px without the
 * visible control changing size.
 */
import * as React from 'react';

import { cn } from '@/lib/utils';

export interface SwitchProps {
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  className?: string;
  'aria-label'?: string;
  'aria-labelledby'?: string;
}

export function Switch({
  checked,
  defaultChecked = false,
  onCheckedChange,
  disabled = false,
  required,
  id,
  className,
  ...aria
}: SwitchProps) {
  const [uncontrolled, setUncontrolled] = React.useState(defaultChecked);
  const isControlled = checked !== undefined;
  const isChecked = isControlled ? checked : uncontrolled;

  function toggle() {
    if (disabled) return;
    const next = !isChecked;
    if (!isControlled) setUncontrolled(next);
    onCheckedChange?.(next);
  }

  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={isChecked}
      aria-required={required}
      disabled={disabled}
      onClick={toggle}
      className={cn(
        'press relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full',
        'before:absolute before:inset-x-0 before:-inset-y-2.5 before:content-[""]',
        'disabled:pointer-events-none disabled:opacity-50',
        isChecked ? 'bg-primary' : 'bg-muted',
        className,
      )}
      {...aria}
    >
      <span
        aria-hidden="true"
        className={cn(
          'inline-block size-5 translate-x-0.5 rounded-full bg-surface shadow transition-transform',
          isChecked && 'translate-x-[1.375rem]',
        )}
        style={{ transitionDuration: 'var(--duration-quick)', transitionTimingFunction: 'var(--ease-out-quick)' }}
      />
    </button>
  );
}
