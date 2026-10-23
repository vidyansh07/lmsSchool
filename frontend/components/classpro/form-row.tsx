/**
 * The form layout the admissions screens use: a right-aligned label in a
 * fixed left column, the control to its right.
 *
 * This is deliberately not `components/ui/field.tsx`. That one stacks a label
 * above its control, which is right for a dialog and wrong here: these forms
 * are twelve rows deep and read as a column of labelled facts, which is how
 * the desk reads them off a printed form while typing.
 *
 * At phone width the two columns become one — a 140px label column leaves
 * nothing for the control — and the label goes back to sitting above, which
 * is the only layout that works in 360px.
 *
 * `required` draws the red asterisk the originals carry. `error` renders
 * under the control, where the eye already is.
 */
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export function FormRow({
  label,
  htmlFor,
  required = false,
  hint,
  error,
  children,
  className,
}: {
  label: ReactNode;
  /** Ties the label to its control. Omit for a row of several inputs, which
   *  label themselves. */
  htmlFor?: string;
  required?: boolean;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  const Label = htmlFor ? 'label' : 'span';
  return (
    <div className={cn('grid gap-1.5 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4 sm:py-2.5', className)}>
      <Label
        {...(htmlFor ? { htmlFor } : {})}
        className="pt-2 text-sm font-semibold text-ink sm:text-right"
      >
        {label}
        {required ? (
          <span className="text-danger" aria-hidden="true">
            {' '}
            *
          </span>
        ) : null}
      </Label>
      <div className="min-w-0 space-y-1.5">
        {children}
        {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
        {error ? (
          <p className="text-xs text-danger" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** The blue text link under a repeatable field — "Add another mobile number". */
export function AddAnother({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-sm text-action underline-offset-4 hover:underline"
    >
      {children}
    </button>
  );
}
