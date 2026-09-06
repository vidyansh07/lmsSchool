'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Row selection for a server-paginated table.
 *
 * The browser only ever holds one page of rows (see `use-list.ts`), so
 * "select all" has to mean two different things and this hook keeps them
 * distinct on purpose: `selectedIds` is the actual set of row ids a person
 * clicked, one page at a time, while `selectAllMatching` is a *flag* meaning
 * "every row this filter matches, including the ones never fetched" — the
 * bulk-action bar is the thing that turns that flag into an explicit count
 * before anything irreversible happens, because conflating "the 20 rows I
 * can see" with "all 4,000 rows in the filter" is exactly how somebody
 * deletes far more than they meant to.
 *
 * Selection is cleared whenever the caller's `filterKey` changes — a
 * selection made under one filter should not silently carry into another.
 */
export interface UseBulkSelectionResult<Id> {
  selectedIds: ReadonlySet<Id>;
  selectedCount: number;
  /** True once "select all matching the current filter" has been chosen. */
  selectAllMatching: boolean;
  isSelected: (id: Id) => boolean;
  /** `pageIds` is the current page in order — needed to resolve a shift-click range. */
  toggle: (id: Id, rowIndex: number, pageIds: Id[], shiftKey?: boolean) => void;
  /** Select the page's rows, or clear the page selection and the "all matching" flag. */
  toggleAll: (pageIds: Id[]) => void;
  /** Whether the page-level checkbox should render as fully, partially, or not checked. */
  pageSelectionState: (pageIds: Id[]) => 'all' | 'some' | 'none';
  selectAllMatchingFilter: () => void;
  clear: () => void;
}

export function useBulkSelection<Id extends string | number>(
  filterKey: string,
): UseBulkSelectionResult<Id> {
  const [selectedIds, setSelectedIds] = useState<Set<Id>>(new Set());
  const [selectAllMatching, setSelectAllMatching] = useState(false);
  const [trackedFilterKey, setTrackedFilterKey] = useState(filterKey);
  const lastToggledIndex = useRef<number | null>(null);

  // Reset during render (not an effect) when the filter identity changes —
  // the exact pattern `use-list.ts` uses for the same reason: a synchronous
  // setState inside an effect body causes an extra, cascading render. This
  // compares state, not a ref — a ref cannot be read or written during
  // render, only from an effect or an event handler.
  if (trackedFilterKey !== filterKey) {
    setTrackedFilterKey(filterKey);
    setSelectedIds(new Set());
    setSelectAllMatching(false);
  }

  // The shift-click anchor is a ref (it does not affect what renders), so
  // its own reset on a filter change belongs in an effect rather than the
  // render-time block above.
  useEffect(() => {
    lastToggledIndex.current = null;
  }, [filterKey]);

  const isSelected = useCallback((id: Id) => selectedIds.has(id), [selectedIds]);

  const toggle = useCallback(
    (id: Id, rowIndex: number, pageIds: Id[], shiftKey = false) => {
      // Captured *before* the state update, not read from the ref inside the
      // updater below: a `setState(updater)` callback runs during React's
      // commit, by which point a synchronous ref write made later in this
      // same function would already be visible — silently collapsing the
      // range to a single row. Capturing the previous index as a plain value
      // up front removes that race entirely.
      const previousIndex = lastToggledIndex.current;
      lastToggledIndex.current = rowIndex;

      setSelectAllMatching(false);
      setSelectedIds((current) => {
        const next = new Set(current);
        const willSelect = !next.has(id);

        // Shift-click extends the previous single click into a range, the
        // way a spreadsheet or file manager does — the fast way to select
        // "rows 12 through 40" without forty individual clicks. The caller
        // (the checkbox's own click handler) passes the modifier through
        // rather than this hook reading `window.event`, which is deprecated
        // and unavailable in a test environment.
        if (shiftKey && previousIndex !== null) {
          const start = Math.min(previousIndex, rowIndex);
          const end = Math.max(previousIndex, rowIndex);
          for (let index = start; index <= end; index += 1) {
            const rowId = pageIds[index];
            if (rowId === undefined) continue;
            if (willSelect) next.add(rowId);
            else next.delete(rowId);
          }
        } else if (willSelect) {
          next.add(id);
        } else {
          next.delete(id);
        }

        return next;
      });
    },
    [],
  );

  const toggleAll = useCallback((pageIds: Id[]) => {
    setSelectAllMatching(false);
    setSelectedIds((current) => {
      const allSelected = pageIds.length > 0 && pageIds.every((id) => current.has(id));
      if (allSelected) return new Set();
      return new Set(pageIds);
    });
  }, []);

  const pageSelectionState = useCallback(
    (pageIds: Id[]): 'all' | 'some' | 'none' => {
      if (pageIds.length === 0) return 'none';
      const selectedOnPage = pageIds.filter((id) => selectedIds.has(id)).length;
      if (selectedOnPage === 0) return 'none';
      if (selectedOnPage === pageIds.length) return 'all';
      return 'some';
    },
    [selectedIds],
  );

  const selectAllMatchingFilter = useCallback(() => setSelectAllMatching(true), []);

  const clear = useCallback(() => {
    setSelectedIds(new Set());
    setSelectAllMatching(false);
    lastToggledIndex.current = null;
  }, []);

  return useMemo(
    () => ({
      selectedIds,
      selectedCount: selectedIds.size,
      selectAllMatching,
      isSelected,
      toggle,
      toggleAll,
      pageSelectionState,
      selectAllMatchingFilter,
      clear,
    }),
    [selectedIds, selectAllMatching, isSelected, toggle, toggleAll, pageSelectionState, selectAllMatchingFilter, clear],
  );
}
