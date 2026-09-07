import * as React from 'react';

import { cn } from '@/lib/utils';

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-10 w-full rounded-md border border-border bg-surface px-3 text-sm',
        'placeholder:text-muted-foreground disabled:opacity-50',
        'aria-[invalid=true]:border-destructive',
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
        'w-full rounded-md border border-border bg-surface px-3 py-2 text-sm',
        'placeholder:text-muted-foreground disabled:opacity-50',
        'aria-[invalid=true]:border-destructive',
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
