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
    const controller = new AbortController();

    apiFetch<T>(path, { signal: controller.signal })
      .then((result) => {
        if (!cancelled) {
          setState({ data: result, error: null, isLoading: false, requestKey });
        }
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        // A deliberate cancellation (this effect's own cleanup, below) is not
        // a failure — it never reaches here anyway, since `cancelled` is set
        // synchronously before `abort()`, but a belt-and-suspenders check
        // keeps this correct even if that ordering ever changes.
        if (cause instanceof ApiError && cause.code === 'cancelled') return;
        const error =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, 'unknown_error', 'The request failed.', '');
        setState({ data: null, error, isLoading: false, requestKey });
      });

    // Prevents a state update from a stale request overwriting a newer one,
    // and now also cancels the in-flight network request itself rather than
    // letting it run to completion for a result nobody will use.
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [path, requestKey]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  return { data: state.data, error: state.error, isLoading: state.isLoading, reload };
}
