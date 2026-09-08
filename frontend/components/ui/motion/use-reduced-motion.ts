'use client';

/**
 * Whether this person has asked their system for less movement.
 *
 * `globals.css` already collapses every CSS animation under
 * `prefers-reduced-motion`, but JavaScript-driven motion — a number counting
 * up, an SVG path drawing itself, a spotlight tracking the cursor — never
 * reaches a stylesheet, so it has to ask.
 *
 * `useSyncExternalStore` rather than an effect that calls `setState`: this is
 * exactly the case it exists for, a value that lives outside React and changes
 * on its own. It also gets the first render right, which an effect cannot —
 * an effect runs *after* paint, so there would always be one frame of movement
 * before the correction, which is precisely the frame this hook exists to
 * prevent.
 *
 * The server snapshot is `true`, and the asymmetry is deliberate. Guessing "no
 * preference" costs someone who asked for stillness a frame of the thing they
 * turned off. Guessing "reduce" costs everyone else a static first frame that
 * nobody can perceive. Only one of those is a bug.
 */

import { useSyncExternalStore } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

function subscribe(onChange: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {};
  }
  const media = window.matchMedia(QUERY);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

function getSnapshot(): boolean {
  // Absent in some test environments and in any renderer that is not a
  // browser. Its absence is not a preference for stillness.
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(QUERY).matches;
}

function getServerSnapshot(): boolean {
  return true;
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
