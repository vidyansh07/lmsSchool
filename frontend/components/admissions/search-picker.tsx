'use client';

import { useId, useRef } from 'react';

import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface PickerOption {
  value: string;
  label: string;
  /** Rendered after the label, e.g. a seat count or a code. */
  hint?: string;
}

/**
 * A search box wired to a always-visible results list, for choosing one of a
 * few dozen courses, batches, trainers or students without leaving the
 * keyboard.
 *
 * A dropdown-on-click combobox is the usual shape, but it costs a click just
 * to see what is available and a second round of arrow keys once it opens.
 * This shows the list the moment there is anything to show, so `Tab` into the
 * field, type, and `Enter` is the entire interaction — which is the point on a
 * screen built for somebody doing this dozens of times a day. Typing a query
 * that narrows the list to one match commits it on `Enter` directly, and
 * `ArrowDown` moves focus into the list for browsing.
 */
export function SearchPicker({
  label,
  query,
  onQueryChange,
  options,
  selected,
  onSelect,
  placeholder,
  isLoading = false,
  error,
  hint,
  emptyMessage = 'No matches.',
  required,
  autoFocus,
}: {
  label: string;
  query: string;
  onQueryChange: (value: string) => void;
  options: PickerOption[];
  selected: string;
  onSelect: (option: PickerOption) => void;
  placeholder?: string;
  isLoading?: boolean;
  error?: string;
  hint?: string;
  emptyMessage?: string;
  required?: boolean;
  autoFocus?: boolean;
}) {
  const inputId = useId();
  const listId = `${inputId}-results`;
  const listRef = useRef<HTMLSelectElement>(null);

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && options.length > 0) {
      event.preventDefault();
      listRef.current?.focus();
      return;
    }
    if (event.key === 'Enter' && options.length === 1) {
      // A query narrow enough to leave one match is a query worth committing
      // to immediately — the whole reason this exists is to save the second
      // step of reaching for the list.
      event.preventDefault();
      onSelect(options[0]!);
    }
  }

  function onListChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const option = options.find((candidate) => candidate.value === event.target.value);
    if (option) onSelect(option);
  }

  return (
    <div className="space-y-1.5">
      <Field label={label} htmlFor={inputId} error={error} hint={hint} required={required}>
        <Input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={options.length > 0}
          aria-controls={listId}
          autoComplete="off"
          autoFocus={autoFocus}
          value={query}
          placeholder={placeholder}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={onInputKeyDown}
        />
      </Field>
      <p aria-live="polite" className="sr-only">
        {isLoading ? 'Searching…' : `${options.length} result${options.length === 1 ? '' : 's'}.`}
      </p>
      {isLoading ? <p className="text-xs text-muted-foreground">Searching…</p> : null}
      {!isLoading && options.length === 0 ? (
        <p className="text-xs text-muted-foreground">{emptyMessage}</p>
      ) : null}
      {options.length > 0 ? (
        <select
          id={listId}
          ref={listRef}
          aria-label={`${label} results`}
          size={Math.min(6, options.length)}
          value={selected}
          onChange={onListChange}
          className={cn(
            'w-full rounded-md border border-border bg-surface text-sm',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
          )}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
              {option.hint ? ` — ${option.hint}` : ''}
            </option>
          ))}
        </select>
      ) : null}
    </div>
  );
}
