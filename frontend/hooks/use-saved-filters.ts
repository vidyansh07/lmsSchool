'use client';

import { useCallback, useState } from 'react';

/**
 * Persist a viewer's named filter presets for one screen in `localStorage`.
 *
 * Storage-key convention: `grras.filters.<scope>`, where `scope` is a short,
 * stable name for the screen ("admin-users", "teaching-assignments"). One key
 * per screen rather than one key for the whole app keeps a corrupted or
 * oversized entry from ever affecting an unrelated screen.
 *
 * Every access is wrapped in try/catch. `localStorage` throws in a private
 * window with storage disabled, and in that case saved filters simply do not
 * persist — a graceful degradation, not a crash.
 */
export interface SavedFilter<Filters> {
  id: string;
  name: string;
  filters: Filters;
}

function storageKey(scope: string): string {
  return `grras.filters.${scope}`;
}

function readAll<Filters>(scope: string): SavedFilter<Filters>[] {
  try {
    const raw = window.localStorage.getItem(storageKey(scope));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SavedFilter<Filters>[]) : [];
  } catch {
    return [];
  }
}

function writeAll<Filters>(scope: string, filters: SavedFilter<Filters>[]): void {
  try {
    window.localStorage.setItem(storageKey(scope), JSON.stringify(filters));
  } catch {
    // Private window, storage disabled, or quota exceeded: the preset is
    // usable for the rest of this session but will not survive a reload.
  }
}

export interface UseSavedFiltersResult<Filters> {
  savedFilters: SavedFilter<Filters>[];
  save: (name: string, filters: Filters) => void;
  remove: (id: string) => void;
}

export function useSavedFilters<Filters>(scope: string): UseSavedFiltersResult<Filters> {
  const [savedFilters, setSavedFilters] = useState<SavedFilter<Filters>[]>(() => readAll<Filters>(scope));

  const save = useCallback(
    (name: string, filters: Filters) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setSavedFilters((current) => {
        // Saving under a name that already exists replaces it, so a person
        // can update "My open tickets" instead of accumulating duplicates.
        const next = [...current.filter((entry) => entry.name !== trimmed), { id: crypto.randomUUID(), name: trimmed, filters }];
        writeAll(scope, next);
        return next;
      });
    },
    [scope],
  );

  const remove = useCallback(
    (id: string) => {
      setSavedFilters((current) => {
        const next = current.filter((entry) => entry.id !== id);
        writeAll(scope, next);
        return next;
      });
    },
    [scope],
  );

  return { savedFilters, save, remove };
}
