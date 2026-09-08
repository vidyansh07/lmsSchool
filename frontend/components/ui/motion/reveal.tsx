'use client';

/**
 * Content that arrives.
 *
 * On mount by default, because most of what uses this is the top of a
 * dashboard — already on screen when the page loads, so waiting for an
 * intersection callback only delays it.
 *
 * `whenVisible` switches to revealing on scroll, for the long sections
 * further down a page: animating those on mount means they finish their
 * entrance while nobody is looking and then sit there having already
 * happened, so the bottom of the page feels different from the top.
 *
 * Either way it fires once. A section that re-animates every time it scrolls
 * past is a section a person cannot scroll past, and on a screen somebody
 * keeps open all day that goes from charming to hostile in about a minute.
 */

import { m, useInView } from 'motion/react';
import { useRef, type ReactNode } from 'react';

import { useReducedMotion } from './use-reduced-motion';

export function Reveal({
  children,
  delay = 0,
  className,
  as = 'div',
  whenVisible = false,
}: {
  children: ReactNode;
  /** Seconds. Use `index * 0.04` for a list; past ~0.3s it reads as slow. */
  delay?: number;
  className?: string;
  as?: 'div' | 'section' | 'li';
  /** Wait for the element to scroll into view instead of animating on mount. */
  whenVisible?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: '-60px' });
  const reduced = useReducedMotion();
  const Component = m[as];

  if (reduced) {
    const Static = as;
    return (
      <Static ref={ref as never} className={className}>
        {children}
      </Static>
    );
  }

  const shown = whenVisible ? inView : true;

  return (
    <Component
      ref={ref as never}
      className={className}
      initial={{ opacity: 0, y: 12 }}
      animate={shown ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
      transition={{ duration: 0.42, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </Component>
  );
}
