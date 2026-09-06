'use client';

/**
 * Edit a single value in place, without navigating to a form.
 *
 * The operating model an ERP wants for small fields — a fee note, a phone
 * number, a due date — is "click it, change it, move on", not "open a modal,
 * fill a form, save, wait, close". Saving happens on Enter or blur so a
 * person can tab through several cells in a row the way a spreadsheet works.
 *
 * On failure the value visibly rolls back to what it was rather than staying
 * on the rejected edit: leaving the invalid value on screen would look like
 * it saved, and a person who does not immediately re-read an error banner
 * would have no way to tell.
 */
import { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export function InlineEdit({
  value,
  onSave,
  label,
  placeholder,
  formatValue = (current) => current,
  className,
}: {
  value: string;
  onSave: (next: string) => Promise<void> | void;
  /** Accessible name for the edit control, e.g. "Fee note". */
  label: string;
  placeholder?: string;
  /** How the read-only value is displayed, e.g. adding a currency sign. */
  formatValue?: (value: string) => string;
  className?: string;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // No effect keeps `draft` synced to `value` while not editing: while
  // `!isEditing`, the read-only view renders `value` directly (never
  // `draft`), and `startEditing` below already resets `draft` to the current
  // `value` the moment editing begins. A value change arriving mid-edit (a
  // background refresh, another viewer's update) is exactly what must *not*
  // overwrite what this person is actively typing, so it is left alone.
  function startEditing() {
    setDraft(value);
    setError(null);
    setIsEditing(true);
  }

  function cancel() {
    setDraft(value);
    setError(null);
    setIsEditing(false);
  }

  async function commit() {
    if (draft === value) {
      setIsEditing(false);
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await onSave(draft);
      setIsEditing(false);
    } catch (cause) {
      // Roll back visibly: the field returns to the last-known-good value
      // rather than sitting on the rejected one.
      setDraft(value);
      setError(cause instanceof Error ? cause.message : 'Could not save. Please try again.');
    } finally {
      setIsSaving(false);
    }
  }

  if (!isEditing) {
    return (
      <button
        type="button"
        onClick={startEditing}
        onKeyDown={(event) => {
          if (event.key === 'Enter') startEditing();
        }}
        className={cn(
          'group inline-flex max-w-full items-center gap-1.5 rounded-md px-1.5 py-0.5 text-left hover:bg-muted',
          className,
        )}
      >
        <span className="truncate">{formatValue(value)}</span>
        <Pencil
          aria-hidden="true"
          className="size-3 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100"
        />
        <span className="sr-only">Edit {label}</span>
      </button>
    );
  }

  return (
    <div className={cn('inline-flex flex-col gap-1', className)}>
      <div className="inline-flex items-center gap-1">
        <Input
          autoFocus
          aria-label={label}
          aria-invalid={error ? true : undefined}
          value={draft}
          disabled={isSaving}
          placeholder={placeholder}
          className="h-8 w-auto min-w-[8rem]"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void commit();
            } else if (event.key === 'Escape') {
              event.preventDefault();
              cancel();
            }
          }}
          onBlur={() => void commit()}
        />
        {isSaving ? <Check aria-hidden="true" className="size-4 animate-pulse text-muted-foreground" /> : null}
        {!isSaving ? (
          <button
            type="button"
            // Prevent the blur handler above from committing before the
            // cancel click is processed.
            onMouseDown={(event) => event.preventDefault()}
            onClick={cancel}
            aria-label={`Cancel editing ${label}`}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
