'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Warn before an uncommitted edit is lost (DESIGN_DECISIONS.md,
 * "Unsaved-changes guard"): a `beforeunload` prompt for leaving the tab
 * (refresh, close, an outside link), and a `guard()` function a screen wraps
 * its own in-app navigation with — a Stay/Discard confirmation first, the
 * action only after Discard.
 *
 * There is no global in-app router guard in this codebase yet (Next's App
 * Router gives no "confirm before this navigation" hook to intercept, and no
 * existing screen has grown one to extend), so this covers in-app navigation
 * the way every current call site already triggers it: through its own
 * button/link handler, not a raw `<Link>` the router drives on its own.
 * Wrap that handler in `guard(...)` and the prompt appears before it runs.
 *
 * `isDirty` is read through a ref, not depended on directly, so a consumer
 * passing a fresh boolean on every render does not re-attach the
 * `beforeunload` listener or invalidate an in-flight prompt's closure.
 */
export interface UseUnsavedChangesResult {
  /** True while the Stay/Discard prompt from `guard()` is open. A caller
   *  renders its own dialog (`components/confirm.tsx`'s `<Confirm>` fits)
   *  driven by this, `confirmDiscard` and `cancelDiscard`. */
  isPrompting: boolean;
  /** Run `action` immediately when there is nothing to lose; otherwise open
   *  the prompt and hold `action` until it is resolved. */
  guard: (action: () => void) => void;
  /** Discard button: runs the held action, then closes the prompt. */
  confirmDiscard: () => void;
  /** Stay button: closes the prompt without running anything. */
  cancelDiscard: () => void;
}

export function useUnsavedChanges(isDirty: boolean): UseUnsavedChangesResult {
  const isDirtyRef = useRef(isDirty);
  useEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  useEffect(() => {
    function onBeforeUnload(event: BeforeUnloadEvent) {
      if (!isDirtyRef.current) return;
      // The browser shows its own generic message for this on every modern
      // engine and ignores any string set here; both are still required for
      // the prompt to appear at all on some of them.
      event.preventDefault();
      event.returnValue = '';
    }
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  const pendingAction = useRef<(() => void) | null>(null);
  const [isPrompting, setIsPrompting] = useState(false);

  const guard = useCallback((action: () => void) => {
    if (!isDirtyRef.current) {
      action();
      return;
    }
    pendingAction.current = action;
    setIsPrompting(true);
  }, []);

  const confirmDiscard = useCallback(() => {
    const action = pendingAction.current;
    pendingAction.current = null;
    setIsPrompting(false);
    action?.();
  }, []);

  const cancelDiscard = useCallback(() => {
    pendingAction.current = null;
    setIsPrompting(false);
  }, []);

  return { isPrompting, guard, confirmDiscard, cancelDiscard };
}
