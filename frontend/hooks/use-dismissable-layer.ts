'use client';

import { useEffect, useRef, type RefObject } from 'react';

/**
 * Closes a non-modal floating layer (a dropdown menu, a popover) on an
 * outside click or Escape, and returns focus to the trigger that opened it.
 *
 * Deliberately not `useFocusTrap`: nothing here traps Tab inside the layer or
 * locks page scroll, because a menu or popover is meant to be dismissible by
 * tabbing straight past it — only a true modal (`Dialog`, `Sheet`) is allowed
 * to hold focus hostage.
 */
export function useDismissableLayer<T extends HTMLElement>({
  open,
  onClose,
  triggerRef,
}: {
  open: boolean;
  onClose: () => void;
  triggerRef?: RefObject<HTMLElement | null>;
}): RefObject<T | null> {
  const containerRef = useRef<T | null>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (containerRef.current?.contains(target)) return;
      if (triggerRef?.current?.contains(target)) return;
      onClose();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        triggerRef?.current?.focus();
      }
    }

    // `mousedown`, not `click`: this listener is only attached once `open` is
    // already true, so the click that *opened* the layer can't self-close it
    // either way — but `mousedown` still closes a step earlier than `click`
    // would, before focus lands on whatever was underneath.
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onClose, triggerRef]);

  return containerRef;
}
