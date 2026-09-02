'use client';

import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '@/lib/api';
import type { ListQuery } from '@/lib/people';
import type { Paginated } from '@/types/api';

export interface ListState<T> {
  data: Paginated<T> | null;
  error: ApiError | null;
  isLoading: boolean;
  query: ListQuery;
  setQuery: (changes: ListQuery) => void;
  setPage: (page: number) => void;
  toggleSort: (field: string) => void;
  reload: () => void;
}

/**
 * Drive a server-paginated, server-filtered list.
 *
 * Every knob — page, search, ordering, filters — becomes a query parameter, so
 * the database does the work and the browser only ever holds one page. Changing
 * a filter resets to page 1, which is what a user expects and what stops them
 * landing on an empty page 7 of a 2-page result.
 */
export function useList<T>(
  fetcher: (query: ListQuery) => Promise<Paginated<T>>,
  initialQuery: ListQuery = {},
): ListState<T> {
  const [query, setQueryState] = useState<ListQuery>({ page: 1, page_size: 20, ...initialQuery });
  const [attempt, setAttempt] = useState(0);

  const key = `${JSON.stringify(query)}#${attempt}`;

  const [state, setState] = useState<{
    data: Paginated<T> | null;
    error: ApiError | null;
    isLoading: boolean;
    key: string;
  }>({ data: null, error: null, isLoading: true, key });

  // Adjusting state during render when the request identity changes is React's
  // documented alternative to a synchronous setState inside an effect, which
  // would cause a cascading render.
  if (state.key !== key) {
    setState({ data: null, error: null, isLoading: true, key });
  }

  useEffect(() => {
    let cancelled = false;
    const requestQuery = JSON.parse(key.split('#')[0] ?? '{}') as ListQuery;

    fetcher(requestQuery)
      .then((result) => {
        if (!cancelled) setState({ data: result, error: null, isLoading: false, key });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            data: null,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            key,
          });
        }
      });

    // Stops a slow earlier request from overwriting a newer result.
    return () => {
      cancelled = true;
    };
    // `fetcher` is a stable module-level function at every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const setQuery = useCallback((changes: ListQuery) => {
    setQueryState((current) => ({ ...current, ...changes, page: 1 }));
  }, []);

  const setPage = useCallback((page: number) => {
    setQueryState((current) => ({ ...current, page }));
  }, []);

  const toggleSort = useCallback((field: string) => {
    setQueryState((current) => {
      const next = current.ordering === field ? `-${field}` : field;
      return { ...current, ordering: next, page: 1 };
    });
  }, []);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  return {
    data: state.data,
    error: state.error,
    isLoading: state.isLoading,
    query,
    setQuery,
    setPage,
    toggleSort,
    reload,
  };
}
