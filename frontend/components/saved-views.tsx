'use client';

/**
 * Saved views for a list: a person's own named filter-and-sort presets, kept
 * on the server per user and per screen (`/api/v1/saved-filters/`), so they
 * follow the person to another device. A view is exactly the list's query —
 * search, sort and the screen's own filters — the same keys the address bar
 * carries (`hooks/use-list.ts` `urlKeys`). Applying one replaces every one of
 * those keys, so nothing from the previous view lingers.
 *
 * Saving under an existing name replaces it; rename and delete are on each
 * chip. A failure to load or save is said, never shown as "no views".
 */

import { useEffect, useState, type FormEvent } from 'react';
import { Bookmark, Pencil, Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { errorMessage } from '@/lib/api';
import type { ListQuery } from '@/lib/people';
import { createSavedFilter, deleteSavedFilter, listSavedFilters } from '@/lib/saved-filters';
import type { SavedFilter } from '@/types/api';

/** The view's part of a list query: these keys only, empty ones dropped. */
export function viewOf(query: ListQuery, keys: readonly string[]): Record<string, string> {
  const view: Record<string, string> = {};
  for (const key of keys) {
    const value = query[key];
    if (value !== undefined && value !== null && String(value) !== '') view[key] = String(value);
  }
  return view;
}

export function SavedViews({
  screen,
  keys,
  query,
  onApply,
}: {
  /** A short, stable name for the screen, e.g. `admin-users`. */
  screen: string;
  /** Every key a view owns: search, ordering and the screen's filters. */
  keys: readonly string[];
  query: ListQuery;
  /** Receives every key — the saved value, or `undefined` to clear it. */
  onApply: (changes: ListQuery) => void;
}) {
  const [views, setViews] = useState<SavedFilter[]>([]);
  const [error, setError] = useState('');
  const [naming, setNaming] = useState<{ mode: 'new' } | { mode: 'rename'; view: SavedFilter } | null>(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const current = viewOf(query, keys);
  const hasFilters = Object.keys(current).length > 0;

  useEffect(() => {
    let cancelled = false;
    listSavedFilters(screen)
      .then((rows) => {
        if (!cancelled) setViews(rows);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(errorMessage(cause, 'Could not load your saved views.'));
      });
    return () => {
      cancelled = true;
    };
  }, [screen]);

  function apply(view: SavedFilter) {
    const changes: ListQuery = {};
    for (const key of keys) {
      const value = view.filters[key];
      changes[key] = typeof value === 'string' || typeof value === 'number' ? value : undefined;
    }
    onApply(changes);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || !naming) return;
    setBusy(true);
    setError('');
    try {
      const filters = naming.mode === 'rename' ? naming.view.filters : current;
      const created = await createSavedFilter({ screen, name: trimmed, filters });
      if (naming.mode === 'rename' && naming.view.name !== trimmed) {
        await deleteSavedFilter(naming.view.id);
      }
      setViews((rows) => [
        ...rows.filter(
          (row) => row.name !== trimmed && (naming.mode !== 'rename' || row.id !== naming.view.id),
        ),
        created,
      ]);
      setNaming(null);
      setName('');
    } catch (cause) {
      setError(errorMessage(cause, 'The view could not be saved.'));
    } finally {
      setBusy(false);
    }
  }

  async function remove(view: SavedFilter) {
    setError('');
    try {
      await deleteSavedFilter(view.id);
      setViews((rows) => rows.filter((row) => row.id !== view.id));
    } catch (cause) {
      setError(errorMessage(cause, 'The view could not be removed.'));
    }
  }

  const isActive = (view: SavedFilter) =>
    JSON.stringify(viewOf(view.filters as ListQuery, keys)) === JSON.stringify(current);

  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Saved views" role="group">
      {views.map((view) => (
        <span
          key={view.id}
          className={`inline-flex items-center gap-1 rounded-full border py-0.5 pl-2.5 pr-1 text-xs ${
            isActive(view) ? 'border-action bg-action/10' : 'border-line bg-sunken'
          }`}
        >
          <button
            type="button"
            onClick={() => apply(view)}
            aria-pressed={isActive(view)}
            className="inline-flex items-center gap-1 font-medium hover:text-action"
          >
            <Bookmark className="size-3" aria-hidden="true" />
            {view.name}
          </button>
          <button
            type="button"
            onClick={() => {
              setNaming({ mode: 'rename', view });
              setName(view.name);
            }}
            aria-label={`Rename saved view ${view.name}`}
            className="rounded-full p-0.5 text-ink-muted hover:bg-line hover:text-ink"
          >
            <Pencil className="size-3" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => void remove(view)}
            aria-label={`Remove saved view ${view.name}`}
            className="rounded-full p-0.5 text-ink-muted hover:bg-line hover:text-ink"
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}

      {naming ? (
        <form onSubmit={(event) => void submit(event)} className="inline-flex items-center gap-1.5">
          <Input
            autoFocus
            aria-label={naming.mode === 'rename' ? 'New name for this view' : 'Name this view'}
            placeholder="View name"
            value={name}
            maxLength={80}
            className="h-7 w-40 text-xs"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                setNaming(null);
                setName('');
              }
            }}
          />
          <Button type="submit" size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </form>
      ) : hasFilters ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() => {
            setNaming({ mode: 'new' });
            setName('');
          }}
        >
          <Plus className="size-3" aria-hidden="true" />
          Save this view
        </Button>
      ) : null}

      {error ? (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      ) : null}
    </div>
  );
}
