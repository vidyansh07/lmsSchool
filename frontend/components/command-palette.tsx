'use client';

/**
 * The global command palette (`mod+k`, DESIGN_DECISIONS.md "Navigation":
 * "jump to a screen by name, search records … Results come from `/search/`;
 * navigation items are local. Keyboard only; no mouse-hover fetches.").
 *
 * Two independent sources feed one flat, arrow-key-navigable list — this
 * role's visible local navigation entries (filtered client-side as the
 * person types, no request) and `GET /search/` results (debounced, fired
 * only once the query reaches the backend's own 2-character minimum,
 * `API_CONTRACTS.md`) — kept in the same visual order they render in, so
 * ArrowUp/ArrowDown walk the list exactly as shown.
 *
 * Built on this codebase's own `Dialog` rather than a `cmdk` dependency:
 * `package.json` has no command-menu primitive yet, and `Dialog` already
 * supplies the one thing a palette needs from a modal shell — a focus trap
 * that closes on Escape, focuses the first control on open and restores
 * focus on exit (`hooks/use-focus-trap.ts`). The arrow-key roving index and
 * result list are specific enough to this feature that a generic combobox
 * primitive would not have saved code.
 *
 * No mouse-hover fetches, and no hover-driven highlight either: the
 * highlighted row only moves on ArrowUp/ArrowDown, matching
 * DESIGN_DECISIONS.md's "Keyboard only; no mouse-hover fetches" in full,
 * not just the fetch half of it. A click still selects the row it lands on.
 */
import { useRouter } from 'next/navigation';
import { type KeyboardEvent, useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { navFor, STAFF_ROLES, STUDENT_NAV, isVisible, type NavGroup } from '@/components/navigation';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { search as runSearch } from '@/lib/search';
import { cn } from '@/lib/utils';
import type { SearchResultGroup } from '@/types/api';

/** Mirrors `API_CONTRACTS.md`'s `GET /search/` minimum — firing a request
 *  below this would only ever come back refused. */
const SEARCH_MIN_LENGTH = 2;
const SEARCH_DEBOUNCE_MS = 250;
const MAX_LOCAL_RESULTS = 8;

interface PaletteItem {
  id: string;
  title: string;
  subtitle: string | null;
  href: string;
}

interface PaletteGroup {
  label: string;
  items: PaletteItem[];
}

function localGroupsFor(user: { role: string; capabilities: string[] } | null): NavGroup[] {
  if (!user) return [];
  return STAFF_ROLES.includes(user.role) ? navFor(user.role) : [{ items: STUDENT_NAV }];
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { user, can } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const debouncedQuery = useDebouncedValue(query, SEARCH_DEBOUNCE_MS);

  // "Adjusting state when a prop changes" (react.dev), not an effect: a
  // value is reset synchronously during render by comparing against what it
  // was on the previous render, so no fetch or subscription is involved and
  // nothing needs to run *after* the DOM commits. A fresh session every time
  // the palette opens — a query left over from the last visit is stale
  // intent, not a draft worth keeping — and the highlight always follows
  // back to the top of whatever list a keystroke just reshuffled.
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setQuery('');
  }
  const [prevQuery, setPrevQuery] = useState(query);
  if (query !== prevQuery) {
    setPrevQuery(query);
    setActiveIndex(0);
  }

  const localItems = useMemo<PaletteItem[]>(() => {
    const trimmed = query.trim().toLowerCase();
    const items: PaletteItem[] = [];
    for (const group of localGroupsFor(user)) {
      for (const item of group.items) {
        if (!isVisible(item, user)) continue;
        if (trimmed && !item.label.toLowerCase().includes(trimmed)) continue;
        items.push({ id: `nav:${item.href}`, title: item.label, subtitle: group.title ?? 'Navigate', href: item.href });
        if (items.length >= MAX_LOCAL_RESULTS) return items;
      }
    }
    return items;
  }, [user, query]);

  const canSearch = Boolean(user) && can(Capability.searchGlobal);
  const trimmedQuery = debouncedQuery.trim();
  const searchEnabled = canSearch && trimmedQuery.length >= SEARCH_MIN_LENGTH;

  // `key` folds every input the fetch depends on into one string, the same
  // shape `student-activities-tab.tsx` uses: the render body derives the
  // "about to fetch" state the instant the key changes (a synchronous
  // adjustment, not an effect), and the effect below only ever calls
  // `setSearchState` from inside a promise callback — never synchronously in
  // its own body — which is what a "subscribe to an external system" effect
  // is for. `open && searchEnabled` collapses to one sentinel key so closing
  // the palette or dropping below the 2-character minimum reads as "idle"
  // without a request in flight.
  const searchKey = open && searchEnabled ? `q:${trimmedQuery}` : 'idle';
  interface SearchState {
    key: string;
    groups: SearchResultGroup[];
    isLoading: boolean;
    error: ApiError | null;
  }
  const [searchState, setSearchState] = useState<SearchState>({
    key: searchKey,
    groups: [],
    isLoading: searchKey !== 'idle',
    error: null,
  });
  if (searchState.key !== searchKey) {
    setSearchState({ key: searchKey, groups: [], isLoading: searchKey !== 'idle', error: null });
  }

  useEffect(() => {
    if (searchKey === 'idle') return;
    let cancelled = false;
    runSearch({ q: trimmedQuery })
      .then((response) => {
        if (!cancelled) setSearchState({ key: searchKey, groups: response.groups, isLoading: false, error: null });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setSearchState({
          key: searchKey,
          groups: [],
          isLoading: false,
          error: cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The search failed.', ''),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [searchKey, trimmedQuery]);

  const searchGroups = useMemo<PaletteGroup[]>(() => {
    if (!searchEnabled) return [];
    return searchState.groups
      .filter((group) => group.results.length > 0)
      .map((group) => ({
        label: group.label,
        items: group.results.map((result) => ({
          id: `search:${group.type}:${result.id}`,
          title: result.title,
          subtitle: result.subtitle,
          href: result.href,
        })),
      }));
  }, [searchEnabled, searchState.groups]);

  const flatItems = useMemo(
    () => [...localItems, ...searchGroups.flatMap((group) => group.items)],
    [localItems, searchGroups],
  );
  // A safety net for the one case the effect above does not cover: a search
  // response lands after the person stopped typing and shrinks the list out
  // from under an index that pointed at a row that no longer exists.
  const boundedIndex = flatItems.length === 0 ? 0 : Math.min(activeIndex, flatItems.length - 1);
  // Each row's position in `flatItems`, looked up rather than counted with a
  // mutable variable while rendering — a `let` incremented from JSX is state
  // React's own render pass does not own, which the compiler rejects outright.
  const indexById = useMemo(() => {
    const map = new Map<string, number>();
    flatItems.forEach((item, index) => map.set(item.id, index));
    return map;
  }, [flatItems]);

  function select(item: PaletteItem) {
    onOpenChange(false);
    router.push(item.href);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (flatItems.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => (Math.min(index, flatItems.length - 1) + 1) % flatItems.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => (Math.min(index, flatItems.length - 1) - 1 + flatItems.length) % flatItems.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const item = flatItems[boundedIndex];
      if (item) select(item);
    }
  }

  if (!user) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="p-0" hideCloseButton>
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search or jump to…"
            aria-label="Command palette"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={flatItems[boundedIndex] ? `command-palette-item-${boundedIndex}` : undefined}
            className="h-12 border-0 px-0 shadow-none focus-visible:outline-none"
          />
        </div>

        <ul id="command-palette-list" role="listbox" aria-label="Results" className="max-h-96 overflow-y-auto p-2">
          {localItems.length > 0 ? (
            <li role="presentation">
              <p className="px-2 pb-1 pt-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                Go to
              </p>
              <ul>
                {localItems.map((item) => (
                  <PaletteRow
                    key={item.id}
                    item={item}
                    index={indexById.get(item.id) ?? 0}
                    activeIndex={boundedIndex}
                    onSelect={select}
                  />
                ))}
              </ul>
            </li>
          ) : null}

          {canSearch && trimmedQuery.length > 0 && trimmedQuery.length < SEARCH_MIN_LENGTH ? (
            <p className="px-3 py-2 text-xs text-muted-foreground">Keep typing to search records…</p>
          ) : null}

          {searchEnabled && searchState.isLoading ? (
            <p className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
              <Spinner size="sm" /> Searching…
            </p>
          ) : null}

          {searchEnabled && searchState.error ? (
            <p className="px-3 py-2 text-xs text-destructive">Could not search records right now.</p>
          ) : null}

          {searchGroups.map((group) => (
            <li key={group.label} role="presentation">
              <p className="px-2 pb-1 pt-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.label}
              </p>
              <ul>
                {group.items.map((item) => (
                  <PaletteRow
                    key={item.id}
                    item={item}
                    index={indexById.get(item.id) ?? 0}
                    activeIndex={boundedIndex}
                    onSelect={select}
                  />
                ))}
              </ul>
            </li>
          ))}

          {flatItems.length === 0 && !(searchEnabled && searchState.isLoading) ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">No matches.</p>
          ) : null}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

function PaletteRow({
  item,
  index,
  activeIndex,
  onSelect,
}: {
  item: PaletteItem;
  index: number;
  activeIndex: number;
  onSelect: (item: PaletteItem) => void;
}) {
  const active = index === activeIndex;
  return (
    <li>
      <button
        type="button"
        id={`command-palette-item-${index}`}
        role="option"
        aria-selected={active}
        onClick={() => onSelect(item)}
        className={cn(
          'flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm',
          active ? 'bg-accent text-primary' : 'text-foreground hover:bg-muted',
        )}
      >
        <span className="truncate font-medium">{item.title}</span>
        {item.subtitle ? <span className="ml-3 shrink-0 truncate text-xs text-muted-foreground">{item.subtitle}</span> : null}
      </button>
    </li>
  );
}
