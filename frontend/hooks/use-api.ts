'use client';

import { useCallback, useEffect, useState } from 'react';

import { ApiError, apiFetch } from '@/lib/api';

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  isLoading: boolean;
  reload: () => void;
}

interface InternalState<T> {
  data: T | null;
  error: ApiError | null;
  isLoading: boolean;
  /** Identity of the request the state belongs to: `${path}#${attempt}`. */
  requestKey: string;
}

/**
 * Fetch a JSON resource from the API with loading/error state and manual reload.
 *
 * State is reset during render when the request identity changes rather than
 * from inside the effect: a synchronous `setState` in an effect body causes a
 * cascading render, and React flags it.
 *
 * Deliberately minimal. When the app needs caching, revalidation and mutations,
 * replace this with a data-fetching library rather than growing it — every call
 * site already goes through `apiFetch`.
 */
export function useApi<T>(path: string): AsyncState<T> {
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${path}#${attempt}`;

  const [state, setState] = useState<InternalState<T>>({
    data: null,
    error: null,
    isLoading: true,
    requestKey,
  });

  if (state.requestKey !== requestKey) {
    setState({ data: null, error: null, isLoading: true, requestKey });
  }

  useEffect(() => {
    let cancelled = false;

    apiFetch<T>(path)
      .then((result) => {
        if (!cancelled) {
          setState({ data: result, error: null, isLoading: false, requestKey });
        }
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, 'unknown_error', 'The request failed.', '');
        setState({ data: null, error, isLoading: false, requestKey });
      });

    // Prevents a state update from a stale request overwriting a newer one.
    return () => {
      cancelled = true;
    };
  }, [path, requestKey]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  return { data: state.data, error: state.error, isLoading: state.isLoading, reload };
}
