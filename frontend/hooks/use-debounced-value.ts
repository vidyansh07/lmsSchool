'use client';

import { useEffect, useState } from 'react';

/**
 * Delay reacting to a fast-changing value (typically a search box) until it
 * has been still for `delayMs`.
 *
 * `list-toolbar.tsx` already does this inline for one input; this is the same
 * idea pulled out so `global-search.tsx` and anything else with a debounced
 * field does not re-implement its own timer and its own stale-closure bug.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
