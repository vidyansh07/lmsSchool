import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * A labelled form control with an error slot.
 *
 * The error is wired to the input through `aria-describedby` and
 * `aria-invalid`, so a screen reader announces it instead of the message being
 * visual-only.
 */
export function Field({
  label,
  htmlFor,
  error,
  hint,
  required,
  optional,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  required?: boolean;
  /** Marks a field somebody may skip.
   *
   *  Required already carries a `*`, and that alone leaves every other field
   *  ambiguous: on a form of thirty questions an unmarked one reads as "not
   *  needed" or as "somebody forgot the asterisk", and the two cost very
   *  different amounts to get wrong. Marking both ends the guess, and makes a
   *  field carrying neither a mistake the eye can catch.
   *
   *  Visual only. The input's own `required` is what assistive technology
   *  announces, so this adds nothing a screen reader has to hear twice. */
  optional?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const errorId = `${htmlFor}-error`;
  const hintId = `${htmlFor}-hint`;

  return (
    <div className={cn('space-y-1.5', className)}>
      {/* `Optional` is a sibling of the label, never a child: inside, it
          becomes part of the field's own name for anything matching on label
          text, and every query for that field would have to know about the
          decoration. */}
      {/* Both markers are siblings of the label, never children.
          Inside, they join the label's own text, so a field called "Reason"
          answers to "Reason*" for anything matching on label text — which is
          why tests around this codebase carry a comment explaining to use
          `getByRole` instead. Beside it, the association and the accessible
          name are exactly the question asked, and the ordinary query works. */}
      <div className="flex items-baseline gap-1">
        <label htmlFor={htmlFor} className="block text-xs font-medium text-ink">
          {label}
        </label>
        {required ? (
          <span className="text-danger" aria-hidden="true">
            *
          </span>
        ) : null}
        {optional && !required ? (
          <span className="text-2xs font-normal text-ink-faint" aria-hidden="true">
            Optional
          </span>
        ) : null}
      </div>
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
            id: htmlFor,
            'aria-invalid': error ? true : undefined,
            'aria-describedby': error ? errorId : hint ? hintId : undefined,
            required,
          })
        : children}
      {hint && !error ? (
        <p id={hintId} className="text-2xs text-ink-faint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-2xs font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
