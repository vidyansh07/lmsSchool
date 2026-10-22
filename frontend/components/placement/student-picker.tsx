'use client';

/**
 * Pick the student an offer is for.
 *
 * Search, not a select: a centre has thousands of students and a dropdown of
 * thousands is unusable, so this reads `/students/?search=` — the same
 * already-scoped list every other student screen reads, which is why a
 * placement officer at one centre cannot find another centre's student to
 * file an offer against.
 *
 * Modelled on `admissions/college-picker.tsx`, including its derived
 * `loadedFor` rather than an `isSearching` flag set in the effect body: the
 * answer to "are these results current" is a comparison, and setting state
 * synchronously inside an effect is the cascading-render pattern this
 * codebase's lint config refuses.
 */
import { Check, Search } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { listStudents } from '@/lib/people';
import { cn } from '@/lib/utils';
import type { StudentListRow } from '@/types/api';

export function StudentPicker({
  value,
  label,
  onChange,
  id,
}: {
  /** The chosen student's id, or `''`. */
  value: string;
  /** Their name, for showing the choice without a second fetch. */
  label: string;
  onChange: (id: string, name: string) => void;
  id?: string;
}) {
  const [query, setQuery] = React.useState('');
  const [options, setOptions] = React.useState<StudentListRow[]>([]);
  const search = useDebouncedValue(query, 250);
  const [loadedFor, setLoadedFor] = React.useState<string | null>(null);
  const isSearching = !value && loadedFor !== search;

  React.useEffect(() => {
    if (value) return;
    const controller = new AbortController();
    listStudents({ search, page_size: 8 }, controller.signal)
      .then((page) => {
        setOptions(page.results);
        setLoadedFor(search);
      })
      .catch(() => {
        setOptions([]);
        setLoadedFor(search);
      });
    return () => controller.abort();
  }, [search, value]);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-control border border-line bg-sunken/40 px-2.5 py-2">
        <span className="min-w-0 truncate text-sm">
          <Check className="mr-1 inline size-3.5 text-success" aria-hidden="true" />
          {label || 'Chosen'}
        </span>
        <Button variant="ghost" size="sm" onClick={() => onChange('', '')}>
          Change
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-faint"
          aria-hidden="true"
        />
        <Input
          id={id}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name, email or student ID…"
          className="pl-8"
          autoComplete="off"
        />
        {isSearching ? (
          <Spinner className="absolute right-2.5 top-1/2 size-4 -translate-y-1/2" />
        ) : null}
      </div>

      {options.length > 0 ? (
        <ul className="max-h-44 overflow-y-auto rounded-control border border-line">
          {options.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                onClick={() => onChange(option.id, option.full_name)}
                className={cn(
                  'w-full px-2.5 py-1.5 text-left text-sm transition-colors',
                  'hover:bg-sunken focus-visible:bg-sunken focus-visible:outline-none',
                )}
              >
                {option.full_name}
                <span className="text-ink-muted"> · {option.student_id}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
