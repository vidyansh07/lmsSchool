'use client';

/**
 * A tri-state checkbox: checked, unchecked, or indeterminate ("some of the
 * rows under this one are selected").
 *
 * A real `<input type="checkbox">`, not a `role="checkbox"` div — `indeterminate`
 * is a DOM property with no HTML attribute equivalent, so it has to be set
 * imperatively via a ref regardless of how the box is styled; a native input
 * gets native keyboard handling, native label association and a native
 * accessibility tree entry for free on top of that. This is the same
 * ref-plus-effect shape as `HeaderCheckbox` in `data-table.tsx`, generalised
 * into a standalone primitive.
 *
 * The input is visually hidden (`sr-only`) rather than removed — an `<input>`
 * that exists only in the accessibility tree still receives focus, Space,
 * and the surrounding `<label>`'s click-forwarding, which is what makes the
 * painted box next to it purely decorative (`aria-hidden`) instead of a
 * second, competing target.
 */
import * as React from 'react';
import { Check, Minus } from 'lucide-react';

import { cn } from '@/lib/utils';

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'checked' | 'onChange' | 'size'> {
  checked?: boolean | 'indeterminate';
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

export function Checkbox({
  checked,
  defaultChecked = false,
  onCheckedChange,
  disabled,
  className,
  id,
  ...props
}: CheckboxProps) {
  const [uncontrolled, setUncontrolled] = React.useState(defaultChecked);
  const isControlled = checked !== undefined;
  const isIndeterminate = checked === 'indeterminate';
  const isChecked = isControlled ? checked === true : uncontrolled;

  const inputRef = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = isIndeterminate;
  }, [isIndeterminate]);

  return (
    <label
      className={cn(
        'relative inline-flex size-4 shrink-0 cursor-pointer items-center justify-center',
        'before:absolute before:-inset-3.5 before:content-[""]', // ≥44px tap target, invisible
        disabled && 'cursor-not-allowed opacity-50',
        className,
      )}
    >
      <input
        ref={inputRef}
        id={id}
        type="checkbox"
        checked={isChecked}
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.checked;
          if (!isControlled) setUncontrolled(next);
          onCheckedChange?.(next);
        }}
        className="peer sr-only"
        {...props}
      />
      <span
        aria-hidden="true"
        className={cn(
          'flex size-4 items-center justify-center rounded border transition-colors',
          'peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary',
          isChecked || isIndeterminate ? 'border-primary bg-primary' : 'border-border bg-surface',
        )}
      >
        {isIndeterminate ? (
          <Minus className="size-3 text-primary-foreground" />
        ) : isChecked ? (
          <Check className="size-3 text-primary-foreground" />
        ) : null}
      </span>
    </label>
  );
}
