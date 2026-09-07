'use client';

/**
 * A set of mutually-exclusive options, built on native `<input type="radio">`
 * rather than a `role="radiogroup"` div of buttons — the native input keeps
 * label association, form participation and screen-reader state announcement
 * for free, the same trade this file's sibling `checkbox.tsx` makes.
 *
 * Arrow-key navigation is hand-rolled here rather than left to the browser's
 * own same-name-radio-group behaviour: that native behaviour exists, but it
 * is implemented deep in each browser's focus-management internals and jsdom
 * — this project's test environment — does not reproduce it, which would
 * leave arrow-key support real but untested. A small `onKeyDown` on the
 * group, calling `preventDefault()`, produces identical behaviour and works
 * the same way under Vitest as it does in a browser.
 */
import * as React from 'react';

import { cn } from '@/lib/utils';

const RadioGroupContext = React.createContext<{
  name: string;
  value: string | undefined;
  setValue: (value: string) => void;
  disabled: boolean;
} | null>(null);

function useRadioGroupContext() {
  const context = React.useContext(RadioGroupContext);
  if (!context) throw new Error('<RadioGroupItem> must be rendered inside <RadioGroup>');
  return context;
}

export interface RadioGroupProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  /** Grouping name for the underlying radio inputs. Generated if omitted. */
  name?: string;
  'aria-label'?: string;
  'aria-labelledby'?: string;
}

export function RadioGroup({
  value,
  defaultValue,
  onValueChange,
  disabled = false,
  name,
  className,
  children,
  ...aria
}: RadioGroupProps) {
  const generatedName = React.useId();
  const groupName = name ?? generatedName;
  const [uncontrolled, setUncontrolled] = React.useState(defaultValue);
  const isControlled = value !== undefined;
  const currentValue = isControlled ? value : uncontrolled;
  const containerRef = React.useRef<HTMLDivElement>(null);

  function commit(next: string) {
    if (!isControlled) setUncontrolled(next);
    onValueChange?.(next);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft'].includes(event.key)) return;
    if (!containerRef.current) return;
    event.preventDefault();

    const items = Array.from(
      containerRef.current.querySelectorAll<HTMLInputElement>('input[type="radio"]:not(:disabled)'),
    );
    if (items.length === 0) return;

    const currentIndex = items.findIndex((item) => item === document.activeElement);
    const forward = event.key === 'ArrowDown' || event.key === 'ArrowRight';
    const base = currentIndex === -1 ? 0 : currentIndex;
    const nextIndex = forward
      ? (base + 1) % items.length
      : (base - 1 + items.length) % items.length;

    const next = items[nextIndex];
    if (!next) return;
    next.focus();
    commit(next.value);
  }

  return (
    <RadioGroupContext.Provider value={{ name: groupName, value: currentValue, setValue: commit, disabled }}>
      <div
        ref={containerRef}
        role="radiogroup"
        onKeyDown={onKeyDown}
        className={cn('flex flex-col gap-2', className)}
        {...aria}
      >
        {children}
      </div>
    </RadioGroupContext.Provider>
  );
}

export interface RadioGroupItemProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'name' | 'checked' | 'onChange' | 'size'> {
  value: string;
}

export function RadioGroupItem({ value, disabled, className, id, ...props }: RadioGroupItemProps) {
  const group = useRadioGroupContext();
  const isChecked = group.value === value;
  const isDisabled = disabled ?? group.disabled;
  // Once something is selected, only that item sits in the Tab order — arrow
  // keys move within the group, same as `data-table.tsx`'s roving-tabIndex
  // rows, so Tab moves *past* the whole group in one step. Before anything is
  // selected there is no single item to prefer, so `tabIndex` is left alone
  // and every option is its own Tab stop, same as a plain native radio group.
  const tabIndex = group.value === undefined ? undefined : isChecked ? 0 : -1;

  return (
    <label
      className={cn(
        'relative inline-flex size-4 shrink-0 items-center justify-center',
        'before:absolute before:-inset-3.5 before:content-[""]', // ≥44px tap target, invisible
        isDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
        className,
      )}
    >
      <input
        id={id}
        type="radio"
        name={group.name}
        value={value}
        checked={isChecked}
        disabled={isDisabled}
        tabIndex={tabIndex}
        onChange={() => group.setValue(value)}
        className="peer sr-only"
        {...props}
      />
      <span
        aria-hidden="true"
        className={cn(
          'flex size-4 items-center justify-center rounded-full border transition-colors',
          'peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary',
          isChecked ? 'border-primary' : 'border-border bg-surface',
        )}
      >
        {isChecked ? <span className="size-2 rounded-full bg-primary" /> : null}
      </span>
    </label>
  );
}
