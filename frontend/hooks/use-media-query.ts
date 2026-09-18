'use client';

/**
 * Whether a CSS media query currently matches — the general form of
 * `components/ui/motion/use-reduced-motion.ts`'s `(prefers-reduced-motion:
 * reduce)` check, for any other query a component needs to react to (a
 * breakpoint, most often).
 *
 * `useSyncExternalStore` rather than an effect that calls `setState`, for the
 * same reason that hook uses it: `matchMedia` is a value that lives outside
 * React and changes on its own (a window resize crossing the query's
 * threshold), and an effect only runs after paint, which would mean one
 * frame at the wrong value before the correction on every mount.
 *
 * The server snapshot is `false` — no assumption about the eventual
 * viewport, unlike the reduced-motion hook's deliberate `true` guess (that
 * one has a specific asymmetric cost on either side; a generic breakpoint
 * query does not). A caller that needs the opposite default should say so at
 * the call site, not here.
 */

import { useSyncExternalStore } from 'react';

function subscribe(query: string, onChange: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {};
  }
  const media = window.matchMedia(query);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

function getSnapshot(query: string): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(query).matches;
}

function getServerSnapshot(): boolean {
  return false;
}

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => subscribe(query, onChange),
    () => getSnapshot(query),
    getServerSnapshot,
  );
}
