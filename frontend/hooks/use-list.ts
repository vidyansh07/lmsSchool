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
export interface ListOptions {
  /**
   * Keep the search, the sort, the page and these filters in the address bar,
   * so a refresh, the Back button and a pasted link all return to the same
   * rows. Opt-in, and only for a page's main list: two lists on one screen
   * would fight over the same parameters.
   */
  urlKeys?: readonly string[];
}

/** Always in the address bar when a page opts in, alongside its own filters. */
const URL_BASE_KEYS = ['search', 'ordering', 'page'] as const;

function readUrlQuery(keys: readonly string[]): ListQuery {
  // The lists that opt in render only after the session check, on the client
  // (`RequireAuth`), so reading the address here cannot differ from a server
  // render.
  if (typeof window === 'undefined') return {};
  const params = new URLSearchParams(window.location.search);
  const query: ListQuery = {};
  for (const key of keys) {
    const value = params.get(key);
    if (!value) continue;
    if (key === 'page') {
      const page = Number.parseInt(value, 10);
      if (Number.isFinite(page) && page > 1) query.page = page;
    } else {
      query[key] = value;
    }
  }
  return query;
}

export function useList<T>(
  fetcher: (query: ListQuery, signal?: AbortSignal) => Promise<Paginated<T>>,
  initialQuery: ListQuery = {},
  options: ListOptions = {},
): ListState<T> {
  const urlKeys = options.urlKeys ? [...URL_BASE_KEYS, ...options.urlKeys] : null;
  const [query, setQueryState] = useState<ListQuery>(() => ({
    page: 1,
    page_size: 20,
    ...initialQuery,
    ...(urlKeys ? readUrlQuery(urlKeys) : {}),
  }));
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
    const controller = new AbortController();
    const requestQuery = JSON.parse(key.split('#')[0] ?? '{}') as ListQuery;

    fetcher(requestQuery, controller.signal)
      .then((result) => {
        if (!cancelled) setState({ data: result, error: null, isLoading: false, key });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        // A deliberate cancellation (query changed, unmount) is not a
        // failure to show — see the matching check in `useApi`.
        if (cause instanceof ApiError && cause.code === 'cancelled') return;
        setState({
          data: null,
          error: cause instanceof ApiError ? cause : null,
          isLoading: false,
          key,
        });
      });

    // Stops a slow earlier request from overwriting a newer result, and now
    // also cancels that request's underlying network call.
    return () => {
      cancelled = true;
      controller.abort();
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

  // Mirror the query into the address bar. `replaceState`, not a push: a
  // keystroke in the search box is not a page the Back button should visit,
  // but the entry the person leaves from is what Back returns them to.
  const urlKeyList = urlKeys?.join(',') ?? '';
  useEffect(() => {
    if (!urlKeyList || typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    for (const key of urlKeyList.split(',')) {
      const value = query[key];
      const keep = value !== undefined && value !== null && value !== '' && !(key === 'page' && value === 1);
      if (keep) params.set(key, String(value));
      else params.delete(key);
    }
    const search = params.toString();
    const next = `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`;
    if (next !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
      window.history.replaceState(window.history.state, '', next);
    }
  }, [query, urlKeyList]);

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
