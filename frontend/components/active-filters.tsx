'use client';

/**
 * What a list is narrowed by, said in words under its toolbar — "Role:
 * Manager ×", "Status: Inactive ×" — with each one removable and a "Clear
 * all". Without it a person scrolls back up to find which of five controls
 * is hiding the row they expected, and an empty table reads as "there is
 * nothing" when it means "your filters exclude it".
 *
 * Search is included: it narrows the same way and is the one most often
 * forgotten.
 */

import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { ListQuery } from '@/lib/people';

export interface FilterDescriptor {
  key: string;
  label: string;
  /** Turns the stored value into words; the raw value is shown otherwise. */
  display?: (value: string) => string;
}

export function ActiveFilters({
  query,
  filters,
  onChange,
}: {
  query: ListQuery;
  filters: readonly FilterDescriptor[];
  /** Receives the keys to clear, each set to `undefined`. */
  onChange: (changes: ListQuery) => void;
}) {
  const active = filters.filter((filter) => {
    const value = query[filter.key];
    return value !== undefined && value !== null && String(value) !== '';
  });
  if (active.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Active filters">
      <span className="text-xs text-ink-muted">Filtered by</span>
      {active.map((filter) => {
        const raw = String(query[filter.key]);
        const shown = filter.display ? filter.display(raw) : raw;
        return (
          <span
            key={filter.key}
            className="inline-flex items-center gap-1 rounded-full border border-line bg-surface py-0.5 pl-2.5 pr-1 text-xs"
          >
            <span>
              <span className="text-ink-muted">{filter.label}:</span>{' '}
              <span className="font-medium">{shown}</span>
            </span>
            <button
              type="button"
              aria-label={`Remove filter ${filter.label}: ${shown}`}
              onClick={() => onChange({ [filter.key]: undefined })}
              className="rounded-full p-0.5 text-ink-muted hover:bg-line hover:text-ink"
            >
              <X className="size-3" aria-hidden="true" />
            </button>
          </span>
        );
      })}
      {active.length > 1 ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() =>
            onChange(Object.fromEntries(active.map((filter) => [filter.key, undefined])) as ListQuery)
          }
        >
          Clear all
        </Button>
      ) : null}
    </div>
  );
}
