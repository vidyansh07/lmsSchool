'use client';

/**
 * A card that lights up under the cursor.
 *
 * Aceternity's signature effect, kept at ERP strength: a soft radial wash of
 * the brand colour follows the pointer, and the border warms slightly. On a
 * screen of twenty cards it answers "which one am I about to click" without a
 * hard hover state that would make the whole grid flicker as the mouse crosses
 * it.
 *
 * Implementation notes that matter:
 *
 * - The position is written to CSS custom properties, not to React state. A
 *   `setState` on every `mousemove` re-renders the subtree sixty times a
 *   second; setting a variable on the node touches nothing React knows about,
 *   and the browser composites the gradient without a layout pass.
 * - The glow lives in a `::before`-style overlay with `pointer-events: none`,
 *   so it can never intercept a click meant for the card.
 * - Touch devices have no cursor. The effect simply never fires, and the card
 *   is a perfectly good card without it — nothing here is load-bearing.
 */

import { useRef, type ReactNode } from 'react';

import { cn } from '@/lib/utils';

import { useReducedMotion } from './use-reduced-motion';

export function SpotlightCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  function onMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    if (reduced) return;
    const node = ref.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    node.style.setProperty('--spotlight-x', `${event.clientX - rect.left}px`);
    node.style.setProperty('--spotlight-y', `${event.clientY - rect.top}px`);
    node.style.setProperty('--spotlight-opacity', '1');
  }

  function onMouseLeave() {
    ref.current?.style.setProperty('--spotlight-opacity', '0');
  }

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className={cn('spotlight group relative overflow-hidden', className)}
    >
      {children}
    </div>
  );
}
