'use client';

import { useEffect, useState } from 'react';

/**
 * Keeps a conditionally-rendered element mounted for `exitDurationMs` after
 * `open` goes false, so an exit animation has time to play instead of the
 * element vanishing on the frame state changes.
 *
 * A timer, not `onAnimationEnd`: every exit animation in this component set
 * is an inline `animation` shorthand reusing an entrance keyframe in reverse
 * (see `dialog.tsx`), and jsdom — this project's test environment — never
 * fires animation events because it does not run the CSS animation timeline
 * at all. A timer driven by the same duration tokens the CSS uses is the one
 * mechanism that behaves the same under a real browser and under Vitest.
 *
 * Becoming mounted is handled during render rather than in the effect below,
 * the same way `use-list.ts` resets its request state when its query key
 * changes: a synchronous `setState` inside an effect body causes a needless
 * extra render, and React's own documented alternative is to compare against
 * the last-seen prop during render and adjust state right there.
 */
export function usePresence(open: boolean, exitDurationMs: number): boolean {
  const [state, setState] = useState({ mounted: open, lastOpen: open });

  if (open !== state.lastOpen) {
    setState({ mounted: open || state.mounted, lastOpen: open });
  }

  useEffect(() => {
    if (open || !state.mounted) return;

    const timer = setTimeout(() => setState((current) => ({ ...current, mounted: false })), exitDurationMs);
    return () => clearTimeout(timer);
  }, [open, exitDurationMs, state.mounted]);

  return state.mounted;
}
