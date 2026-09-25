'use client';

/**
 * One independently-loading region of a page.
 *
 * A dashboard makes several unrelated calls, and a single `Promise.all` makes
 * the weakest one able to blank the whole screen -- so each section carries
 * its own data, its own error and its own retry, and a failing endpoint
 * costs one card rather than the page.
 *
 * `app/dashboard/page.tsx` and `app/admissions/dashboard/page.tsx` each grew
 * their own private copy of this (`useDashboardSection`). This is that hook,
 * in one place, with one addition they did not need: a dependency list, so a
 * section can refetch when a control above it changes -- the analytics page's
 * period selector, for instance. Their copies should fold into this as each
 * of those pages is next touched.
 *
 * The `attempt` comparison happens during render rather than in an effect.
 * An unconditional `setState` the instant an effect fires is a synchronous
 * write inside that effect, which is the cascading-render anti-pattern both
 * `hooks/use-list.ts` and `hooks/use-api.ts` deliberately avoid, and which
 * this repo's lint config refuses.
 */

import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '@/lib/api';

export interface SectionState<T> {
  data: T;
  error: ApiError | null;
  isLoading: boolean;
  reload: () => void;
}

export function useSection<T>(
  loader: () => Promise<T>,
  empty: T,
  /** Values that should cause a refetch, like a period or a batch filter. */
  deps: readonly unknown[] = [],
): SectionState<T> {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    data: T;
    error: ApiError | null;
    isLoading: boolean;
    key: string;
  }>({ data: empty, error: null, isLoading: true, key: `0|${JSON.stringify(deps)}` });

  // One key covering both reasons to refetch -- a manual retry and a changed
  // dependency -- so the reset is a single comparison rather than two.
  const key = `${attempt}|${JSON.stringify(deps)}`;
  if (state.key !== key) {
    setState({ data: empty, error: null, isLoading: true, key });
  }

  useEffect(() => {
    let cancelled = false;
    // `loader` is rebuilt every render by every caller (it closes over the
    // current period), so it cannot be an effect dependency without
    // looping -- `key` is what decides when to run, and it already carries
    // every value the loader closes over. The same exemption
    // `useDashboardSection` takes, for the same reason.
    loader()
      .then((result) => {
        if (!cancelled) setState({ data: result, error: null, isLoading: false, key });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            data: empty,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            key,
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  return { data: state.data, error: state.error, isLoading: state.isLoading, reload };
}
