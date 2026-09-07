'use client';

import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Focus containment for a modal surface (`Dialog`, `Sheet`): traps Tab inside
 * the container, moves focus in on open, restores it to whatever was focused
 * before, closes on Escape, and locks page scroll for as long as it is open.
 *
 * Scroll locking is bundled in rather than split into its own effect: both
 * behaviours live and die on exactly the same `open` transition, and a modal
 * that traps focus but leaves the page scrolling underneath it is a bug, not
 * a separate feature someone might reasonably want without the other.
 *
 * Lifted out of `components/confirm.tsx`, which hand-rolled this exact
 * Tab-cycling logic first — this is that logic made reusable for `Dialog` and
 * `Sheet` rather than a third copy drifting slowly out of sync with it.
 */
export function useFocusTrap<T extends HTMLElement>({
  open,
  onClose,
  initialFocusRef,
}: {
  open: boolean;
  onClose: () => void;
  /** Focus this on open instead of the first focusable descendant. */
  initialFocusRef?: RefObject<HTMLElement | null>;
}): RefObject<T | null> {
  const containerRef = useRef<T | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    (
      initialFocusRef?.current ?? containerRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
    )?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !containerRef.current) return;

      const focusable = Array.from(containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) return;
      const first = focusable[0] as HTMLElement;
      const last = focusable[focusable.length - 1] as HTMLElement;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused.current?.focus();
    };
    // `onClose` and `initialFocusRef` are expected to be stable-enough callers
    // (event handlers, refs); re-running this effect on every render of the
    // caller would re-capture "previously focused" mid-session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return containerRef;
}
