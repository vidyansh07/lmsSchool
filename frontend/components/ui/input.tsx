import * as React from 'react';

import { cn } from '@/lib/utils';

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-9 w-full rounded-control border border-line bg-surface px-2.5 text-sm text-ink',
        'transition-colors duration-150 hover:border-line-strong',
        'placeholder:text-ink-faint disabled:opacity-50',
        'aria-[invalid=true]:border-danger',
        className,
      )}
      {...props}
    />
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
