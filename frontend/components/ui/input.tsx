import * as React from 'react';
import { Eye, EyeOff } from 'lucide-react';

import { cn } from '@/lib/utils';

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        // Pressed, not raised. An input is a place the page has been pushed
        // into, and a button is a thing pushed out of it -- that one contrast
        // is what tells somebody where to type without any instruction.
        'h-9 w-full rounded-control border border-line bg-surface px-2.5 text-sm text-ink',
        'shadow-pressed',
        'transition-colors duration-150 hover:border-line-strong',
        'placeholder:text-ink-faint disabled:opacity-50',
        'aria-[invalid=true]:border-danger',
        className,
      )}
      {...props}
    />
  );
}

/**
 * A password field you can choose to look at.
 *
 * Every password input in the product was a bare `type="password"` with no way
 * to see what had been typed. On a phone keyboard, with a generated password
 * pasted from an email, that is the difference between signing in and guessing
 * why you cannot — and the usual response is to retype it three times and then
 * ask for another reset link.
 *
 * Details that matter more than they look:
 *
 * - The toggle is a real `<button type="button">`, so it is reachable by
 *   keyboard and cannot submit the form it sits inside.
 * - `aria-pressed` carries the state, and the label says what the button will
 *   do next, so a screen reader is not left guessing.
 * - Revealing never changes the value, the name or `autoComplete`, so password
 *   managers behave exactly as before.
 * - It starts hidden, every time. Nothing is remembered between renders: a
 *   field that stayed revealed because of an earlier visit is a shoulder-surfing
 *   hole nobody asked for.
 */
export function PasswordInput({
  className,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [visible, setVisible] = React.useState(false);

  return (
    <div className="relative">
      <Input
        {...props}
        type={visible ? 'text' : 'password'}
        // Room for the button, so a long value never runs underneath it.
        className={cn('pr-10', className)}
      />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-pressed={visible}
        aria-label={visible ? 'Hide the password' : 'Show the password'}
        title={visible ? 'Hide the password' : 'Show the password'}
        className={cn(
          'absolute inset-y-0 right-0 flex w-10 items-center justify-center',
          'text-ink-muted transition-colors hover:text-ink',
          // `action`, not `primary`: the design system renamed the accent token,
          // and the theme-token test is what caught the stale name.
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action',
        )}
      >
        {visible ? (
          <EyeOff className="size-4" aria-hidden="true" />
        ) : (
          <Eye className="size-4" aria-hidden="true" />
        )}
      </button>
    </div>
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'w-full rounded-control border border-line bg-surface px-2.5 py-2 text-sm text-ink',
        'shadow-pressed',
        'transition-colors duration-150 hover:border-line-strong',
        'placeholder:text-ink-faint disabled:opacity-50',
        'aria-[invalid=true]:border-danger',
        className,
      )}
      {...props}
    />
  );
}

// `Select` now lives in `./select` (native `<select>`, extended with size
// variants) — re-exported here so the ~90 existing call sites that import it
// from this file do not need to change. See `select.tsx` for why.
export { Select, type SelectProps } from './select';
