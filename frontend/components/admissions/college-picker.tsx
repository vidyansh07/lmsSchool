'use client';

/**
 * Pick a college, or add the one that is missing.
 *
 * The institution has always been free text, and free text drifts: "Arya
 * College of Engineering", "Arya college" and "ARYA COLLEGE OF ENGG" are one
 * place and three rows, and no report can add them up.
 *
 * A picker alone does not fix that — it moves the problem, because a
 * counsellor who cannot find the college still has to put it somewhere and
 * will put it in the free-text box. So adding one is part of the same control,
 * two keystrokes from the search that failed to find it. The server matches on
 * the flattened name, so somebody adding a college that already exists in a
 * different case gets the existing row back rather than making a twin.
 *
 * The free-text field stays beside this on purpose. Some students name an
 * employer rather than a college, and some name something nobody wants in a
 * shared list. The link is what a report groups by; the text is what the
 * person actually said.
 */

import { Check, Plus, Search } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { addCollege, listColleges, type College } from '@/lib/people';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { cn } from '@/lib/utils';

export interface CollegePickerProps {
  value: College | null;
  onChange: (college: College | null) => void;
  /** Prefills the add box, so a typed name is not retyped. */
  defaultCity?: string;
  id?: string;
}

export function CollegePicker({ value, onChange, defaultCity = '', id }: CollegePickerProps) {
  const [query, setQuery] = React.useState('');
  const [options, setOptions] = React.useState<College[]>([]);
  const [isAdding, setIsAdding] = React.useState(false);
  const [addError, setAddError] = React.useState('');
  const search = useDebouncedValue(query, 250);
  // Which search the options on screen belong to. Derived state rather than an
  // `isSearching` flag set at the top of the effect: setting state
  // synchronously in an effect body triggers a second render before the first
  // has painted, and the answer here — "are these results current" — is
  // already a comparison.
  const [loadedFor, setLoadedFor] = React.useState<string | null>(null);
  const isSearching = !value && loadedFor !== search;

  React.useEffect(() => {
    if (value) return;
    const controller = new AbortController();
    listColleges({ search, page_size: 8 }, controller.signal)
      .then((page) => {
        setOptions(page.results);
        setLoadedFor(search);
      })
      // A picker that cannot reach the server offers nothing and says nothing;
      // the free-text field beside it still works, which is why this is not an
      // error state that blocks the form.
      .catch(() => {
        setOptions([]);
        setLoadedFor(search);
      });
    return () => controller.abort();
  }, [search, value]);

  async function onAdd() {
    const name = query.trim();
    if (!name) return;
    setIsAdding(true);
    setAddError('');
    try {
      onChange(await addCollege(name, defaultCity));
      setQuery('');
    } catch {
      setAddError('Could not add that college. Try again, or leave it blank.');
    } finally {
      setIsAdding(false);
    }
  }

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-control border border-line bg-sunken/40 px-2.5 py-2">
        <span className="min-w-0 truncate text-sm">
          <Check className="mr-1 inline size-3.5 text-success" aria-hidden="true" />
          {value.name}
          {value.city ? <span className="text-ink-muted"> · {value.city}</span> : null}
        </span>
        <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
          Change
        </Button>
      </div>
    );
  }

  // An exact match already on the list is not offered as "add": that is how a
  // second row gets made.
  const exact = options.some(
    (option) => option.name.trim().toLowerCase() === query.trim().toLowerCase(),
  );

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
          placeholder="Search for a college…"
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
                onClick={() => onChange(option)}
                className={cn(
                  'w-full px-2.5 py-1.5 text-left text-sm transition-colors',
                  'hover:bg-sunken focus-visible:bg-sunken focus-visible:outline-none',
                )}
              >
                {option.name}
                {option.city ? <span className="text-ink-muted"> · {option.city}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {query.trim() !== '' && !exact && !isSearching ? (
        <Button variant="outline" size="sm" onClick={onAdd} disabled={isAdding} className="gap-1.5">
          <Plus className="size-3.5" aria-hidden="true" />
          {isAdding ? 'Adding…' : `Add "${query.trim()}"`}
        </Button>
      ) : null}

      {addError ? <p className="text-xs text-danger">{addError}</p> : null}
    </div>
  );
}
